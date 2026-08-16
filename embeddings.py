"""ST-15. Dense embeddings for the Sanad registry (ADR-05).

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

So the design does not ask callers to remember the rule. There is exactly
one function that talks to the model, `_encode`, and it is only ever reached
through a function that has already applied a prefix. There is no public way
to embed raw text. The test suite pins that by replacing `_encode` with a
spy and asserting every string that reaches it carries a prefix, which is
why the prefix test needs no model and runs on every PR (architecture
section 14).
"""

from __future__ import annotations

import functools
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from config import get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from chunking import Child


class EmbeddingError(Exception):
    """Base for every embedding failure."""


class EmptyTextError(EmbeddingError):
    """Raised when text with nothing in it reaches the encoder.

    An empty chunk is an upstream bug, not a user mistake: chunking never
    emits one. Embedding it would produce a vector that matches everything
    weakly and nothing well, so it fails loudly here instead."""

    def __init__(self, where: str):
        super().__init__(f"cannot embed empty or whitespace-only text ({where})")


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


def prefix_passage(text: str) -> str:
    """Return `text` with the passage prefix applied.

    Deliberately does NOT check whether the text already starts with the
    prefix. A document can legitimately contain the literal characters
    "passage: ", and skipping the prefix in that case would silently break
    the ADR-05 rule for exactly the documents that look suspicious. Applying
    it unconditionally is correct: the rule is "prefix the raw text", and
    raw text is whatever the caller holds."""
    if not text or not text.strip():
        raise EmptyTextError("passage")
    return f"{get_settings().embedding_passage_prefix}{text}"


def prefix_query(text: str) -> str:
    """Return `text` with the query prefix applied. See `prefix_passage`."""
    if not text or not text.strip():
        raise EmptyTextError("query")
    return f"{get_settings().embedding_query_prefix}{text}"


@functools.lru_cache(maxsize=1)
def load_model() -> Any:
    """Load the sentence-transformers model once per process.

    Imported lazily and cached so that importing this module costs nothing
    and the prefix tests never touch the model. The first real call
    downloads the weights and caches them on disk; every later call reuses
    them (ST-15 acceptance: "model downloads once + caches")."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(get_settings().embedding_model)


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
    model = load_model()
    vectors = model.encode(
        list(prefixed_texts),
        normalize_embeddings=True,
        convert_to_numpy=True,
    )
    return [[float(x) for x in vector] for vector in vectors]


def _check_dimensions(vectors: list[list[float]]) -> list[list[float]]:
    expected = get_settings().embedding_dense_dim
    for vector in vectors:
        if len(vector) != expected:
            raise EmbeddingDimensionError(expected, len(vector))
    return vectors


def embed_passages(texts: Sequence[str]) -> list[list[float]]:
    """Embed indexed text. Returns one vector per input, in the same order.

    Callers pass RAW text. The passage prefix is applied here; applying it
    yourself first would double it."""
    prefixed = [prefix_passage(text) for text in texts]
    return _check_dimensions(_encode(prefixed))


def embed_query(text: str) -> list[float]:
    """Embed one search query. Callers pass the raw question."""
    vectors = _check_dimensions(_encode([prefix_query(text)]))
    return vectors[0]


def embed_children(children: Sequence[Child]) -> list[list[float]]:
    """Embed chunked children, aligned by index with `children`.

    The bridge from ST-14 to ST-16: children are the searched unit, so they
    are what gets a vector. Parents are read at answer time and are never
    embedded."""
    return embed_passages([child.text for child in children])