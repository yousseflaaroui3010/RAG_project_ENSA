"""ST-15/ST-16. Embeddings for the Sanad registry (ADR-05).

The whole point of this module is one rule that is easy to break and
impossible to notice breaking:

    every indexed chunk is embedded with "passage: "
    every search query is embedded with "query: "

`intfloat/multilingual-e5-base` requires those prefixes even for
non-English text (model card, reference [4] in the architecture). Leaving
them off raises NO error. Nothing crashes, nothing logs, and retrieval
quality quietly drops (qdrant issue 9024, reference [5]). That is the worst
shape a defect can have: silent, plausible, and only visible as "the answers
got a bit worse".

So the design does not ask callers to remember the rule. Exactly one
function talks to the model, `_encode`, and it is private. Every route to it
applies a prefix first. The prefix helpers and the model loader are private
too, because a public `load_model()` would hand a caller the raw encoder and
a public `prefix_passage()` is the only realistic way to double-prefix. The
public surface is three functions, and all three prefix.

The tests pin that by replacing `_encode` with a spy and asserting on the
strings that reach it, which is why the prefix test needs no model and runs
on every PR (architecture section 13.1, the fast tier of the test pyramid).

ST-16 added the SPARSE half (architecture section 7.5: every point carries a
dense E5 vector and a sparse BM25 vector). It lives here rather than in
`vector_store.py` because it has the same defect shape as the rule above,
and the same shape belongs behind the same seam: FastEmbed's BM25 is
ASYMMETRIC. `model.embed(...)` is the document side and returns IDF-weighted
values; `model.query_embed(...)` is the query side and returns flat 1.0
term indicators. Calling the wrong one raises nothing, returns a plausible
vector, and silently degrades retrieval -- proven by running both on the
same string, see `_load_sparse_model`. One module, one rule, one place to
get it wrong; `vector_store.py` never touches an encoder directly.

Sparse deliberately does NOT take the `passage: `/`query: ` prefixes. Those
are an E5 model-card requirement about how a neural encoder was trained;
BM25 is lexical, so prefixing would only push the literal tokens "passage"
and "query" into every document's term index and into every query.
"""

from __future__ import annotations

import functools
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from config import get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from chunking import Child


class EmbeddingError(Exception):
    """Base for every embedding failure."""


class EmptyTextError(EmbeddingError):
    """Raised when text with nothing in it reaches the encoder.

    Carries the position in the batch, because the realistic cause is one
    bad window out of hundreds. `chunking._windows` appends any truthy
    window (chunking.py, `if window:`), so a window of pure padding
    whitespace survives chunking and arrives here. Without the index, the
    report is "a document failed to index" and the search for which of 400
    chunks did it starts from nothing."""

    def __init__(self, where: str, index: int | None = None, text: str = ""):
        position = "" if index is None else f" at index {index}"
        preview = f" (got {text!r})" if text else ""
        super().__init__(
            f"cannot embed empty or whitespace-only text ({where}{position}){preview}"
        )
        self.index = index


class EmbeddingInputError(EmbeddingError):
    """Raised when the input is the wrong shape rather than the wrong content.

    Exists for one specific trap: `str` satisfies `Sequence[str]`, so
    `embed_passages("some text")` type-checks, iterates the string, and
    embeds one vector per CHARACTER. No error, no failing test, a corrupt
    index. Nothing else in the stack would catch it."""


class EmbeddingDimensionError(EmbeddingError):
    """Raised when the model returns vectors of an unexpected width.

    Guards against a mis-set `embedding_model`: a different model loads
    fine, embeds fine, and returns the wrong number of dimensions, which
    the vector store would then reject far away from the cause."""

    def __init__(self, expected: int, got: int):
        super().__init__(
            f"model returned {got}-dimensional vectors, expected {expected}. "
            "Check config.embedding_model against config.embedding_dense_dim."
        )


class EmbeddingCountError(EmbeddingError):
    """Raised when the encoder returns a different number of vectors than
    it was given.

    `embed_children` promises its output aligns with its input by index.
    ST-16 will zip the two together to build vector-store points, so a
    silent length mismatch would attach every vector to the wrong chunk
    from the mismatch onward. Citations would then point at the wrong
    passage while everything still looked healthy."""

    def __init__(self, expected: int, got: int):
        super().__init__(f"encoder returned {got} vectors for {expected} inputs")


@dataclass(frozen=True)
class SparseVector:
    """A BM25 term vector: which vocabulary slots fired, and how hard.

    Sanad's own shape rather than `qdrant_client.models.SparseVector` on
    purpose. This module is about turning text into numbers; it has no
    business importing the store those numbers are later written to, and
    the day the store changes, nothing here should have to. `vector_store`
    owns the two-line conversion, which is the correct place for it."""

    indices: list[int]
    values: list[float]


def _prefix_passage(text: str, index: int | None = None) -> str:
    """Return `text` with the passage prefix applied.

    Deliberately does NOT check whether the text already starts with the
    prefix. A document can legitimately contain the literal characters
    "passage: ", and skipping the prefix in that case would silently break
    the ADR-05 rule for exactly the documents that look suspicious. Applying
    it unconditionally is the correct reading of "prefix the raw text"."""
    if not text or not text.strip():
        raise EmptyTextError("passage", index, text)
    return f"{get_settings().embedding_passage_prefix}{text}"


def _prefix_query(text: str) -> str:
    """Return `text` with the query prefix applied. See `_prefix_passage`."""
    if not text or not text.strip():
        raise EmptyTextError("query", None, text)
    return f"{get_settings().embedding_query_prefix}{text}"


@functools.lru_cache(maxsize=2)
def _load_model(model_name: str) -> Any:
    """Load a sentence-transformers model once per process, keyed by name.

    Keyed on the name rather than cached on a no-argument function so that
    changing `embedding_model` and clearing the settings cache actually
    yields the new model. A `maxsize=1` cache on a no-arg function survives
    `get_settings.cache_clear()` and would keep serving the old weights.

    The import is lazy so importing this module costs nothing and the fast
    prefix tests never touch the model. The first real call downloads the
    weights and caches them on disk; later calls reuse them (ST-15
    acceptance: "model downloads once + caches")."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def _encode(prefixed_texts: Sequence[str]) -> list[list[float]]:
    """The ONLY place this codebase calls the embedding model.

    Everything above this has already applied a prefix. Nothing below it
    knows what a prefix is. Keeping that seam narrow is what makes the
    ADR-05 rule testable without loading a model, and what stops a future
    caller from quietly adding a second, unprefixed path to the encoder.

    `normalize_embeddings=True` is passed explicitly because the library
    default is False (verified against the installed signature, not from
    memory); E5 vectors are compared with cosine similarity, which assumes
    unit length."""
    if not prefixed_texts:
        return []
    model = _load_model(get_settings().embedding_model)
    vectors = model.encode(
        list(prefixed_texts),
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return [[float(x) for x in vector] for vector in vectors]


def _check_batch(inputs: Sequence[str], vectors: list[list[float]]) -> list[list[float]]:
    if len(vectors) != len(inputs):
        raise EmbeddingCountError(len(inputs), len(vectors))
    expected = get_settings().embedding_dense_dim
    for vector in vectors:
        if len(vector) != expected:
            raise EmbeddingDimensionError(expected, len(vector))
    return vectors


def embed_passages(texts: Sequence[str]) -> list[list[float]]:
    """Embed indexed text. Returns one vector per input, in the same order.

    Callers pass RAW text; the passage prefix is applied here. Passing a
    bare `str` is rejected rather than iterated, because iterating it would
    embed one vector per character without complaining."""
    if isinstance(texts, str):
        raise EmbeddingInputError(
            "embed_passages takes a sequence of texts, not a single string. "
            "A bare str would be iterated one character at a time. "
            "Use embed_passages([text])."
        )
    prefixed = [_prefix_passage(text, index) for index, text in enumerate(texts)]
    return _check_batch(prefixed, _encode(prefixed))


def embed_query(text: str) -> list[float]:
    """Embed one search query. Callers pass the raw question."""
    prefixed = [_prefix_query(text)]
    return _check_batch(prefixed, _encode(prefixed))[0]


def embed_children(children: Sequence[Child]) -> list[list[float]]:
    """Embed chunked children, aligned by index with `children`.

    The bridge from ST-14 to ST-16: children are the searched unit, so they
    are what gets a vector. Parents are read at answer time and are never
    embedded. The index alignment is enforced, not assumed: see
    `EmbeddingCountError`."""
    return embed_passages([child.text for child in children])


# --- sparse BM25, the lexical half of the hybrid (ST-16, section 7.5) ---


@functools.lru_cache(maxsize=2)
def _load_sparse_model(model_name: str) -> Any:
    """Load the FastEmbed sparse model once per process, keyed by name.

    Keyed on the name for the same reason `_load_model` is: a `maxsize=1`
    cache on a no-argument function survives `get_settings.cache_clear()`
    and would keep serving the previous model after the config changed.

    The import is lazy so the fast tests never construct it. The first real
    call DOWNLOADS the model, which is why nothing in the default test tier
    reaches this function -- `tests/unit/test_embeddings.py` fakes it, and
    the one test that uses the real thing is opt-in behind
    `SANAD_RUN_MODEL_TESTS=1`, matching ST-15's dense-model test."""
    from fastembed import SparseTextEmbedding

    return SparseTextEmbedding(model_name)


def _to_sparse(raw: Any) -> SparseVector:
    """Convert one FastEmbed embedding into Sanad's shape.

    `indices` and `values` come back as numpy arrays; they are converted to
    plain ints and floats here so nothing downstream has to care that
    FastEmbed uses numpy, and so a stored vector is JSON-shaped all the way
    down."""
    return SparseVector(
        indices=[int(i) for i in raw.indices],
        values=[float(v) for v in raw.values],
    )


def embed_sparse_passages(texts: Sequence[str]) -> list[SparseVector]:
    """BM25-encode indexed text, one vector per input, in the same order.

    Uses `embed`, the DOCUMENT side of FastEmbed's asymmetric BM25. Raw
    text, no `passage: ` prefix -- see the module docstring."""
    if isinstance(texts, str):
        raise EmbeddingInputError(
            "embed_sparse_passages takes a sequence of texts, not a single "
            "string. FastEmbed accepts a bare str and returns ONE vector, so "
            "the caller would silently get 1 vector where it expected len(). "
            "Use embed_sparse_passages([text])."
        )
    for index, text in enumerate(texts):
        if not text or not text.strip():
            raise EmptyTextError("sparse passage", index, text)
    if not texts:
        return []
    model = _load_sparse_model(get_settings().embedding_sparse_model)
    vectors = [_to_sparse(raw) for raw in model.embed(list(texts))]
    if len(vectors) != len(texts):
        raise EmbeddingCountError(len(texts), len(vectors))
    return vectors


def embed_sparse_query(text: str) -> SparseVector:
    """BM25-encode one search query.

    Uses `query_embed`, the QUERY side. This is the whole reason the sparse
    encoder lives behind this module: `embed` would also return a vector
    here, with IDF weights applied a second time, and nothing anywhere
    would complain -- the only symptom is worse answers."""
    if not text or not text.strip():
        raise EmptyTextError("sparse query", None, text)
    model = _load_sparse_model(get_settings().embedding_sparse_model)
    return _to_sparse(next(iter(model.query_embed(text))))


def embed_sparse_children(children: Sequence[Child]) -> list[SparseVector]:
    """BM25-encode chunked children, aligned by index with `children`.

    The sparse mirror of `embed_children`, so ST-16 builds both halves of a
    point from the same list in the same order."""
    return embed_sparse_passages([child.text for child in children])