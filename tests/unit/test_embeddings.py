"""ST-15 exit gate: the ADR-05 prefix rule, enforced without loading a model.

Architecture section 13.1 puts this in the fast, no-model, every-PR tier of
the test pyramid. The failure it guards against is silent: embedding text
without its "passage: " / "query: " prefix raises nothing and only shows up
as slightly worse answers. A test is the only thing that turns that into a
loud red.

Two rules this file follows on purpose:

1. The expected prefixes are written out as LITERALS here, never read from
   config. Reading `get_settings().embedding_passage_prefix` to build the
   expectation makes the test agree with the code by construction: set that
   setting to "" and every `startswith` passes trivially, which is exactly
   the silent degradation ADR-05 exists to prevent. The literal is the
   independent statement of the requirement.

2. Assertions are on what the encoder RECEIVES, via a spy on the `_encode`
   seam. Asserting on what a helper returns would pass even if a public
   function bypassed that helper.
"""

from __future__ import annotations

import os

import pytest

import embeddings
from chunking import Child
from config import get_settings

# From ADR-05 and the multilingual-e5-base model card. Written here rather
# than imported so that a change to config fails this file loudly.
PASSAGE = "passage: "
QUERY = "query: "


@pytest.fixture
def spy(monkeypatch):
    """Replace the encoder with a recorder that returns correctly sized vectors.

    Returns the list that collects every string handed to the model."""
    seen: list[str] = []
    dim = get_settings().embedding_dense_dim

    def fake_encode(prefixed_texts):
        seen.extend(prefixed_texts)
        return [[0.0] * dim for _ in prefixed_texts]

    monkeypatch.setattr(embeddings, "_encode", fake_encode)
    return seen


# --- the config itself is part of the contract -------------------------------


def test_configured_prefixes_are_exactly_what_the_model_card_requires():
    """Pins the settings against ADR-05.

    Without this, emptying either prefix in config would leave every other
    test in this file passing while retrieval silently degraded."""
    settings = get_settings()
    assert settings.embedding_passage_prefix == PASSAGE
    assert settings.embedding_query_prefix == QUERY


# --- the exit gate: nothing reaches the model without its prefix -------------


def test_every_passage_reaching_the_model_carries_the_passage_prefix(spy):
    embeddings.embed_passages(["le congé annuel", "la période d'essai"])
    assert len(spy) == 2
    assert all(text.startswith(PASSAGE) for text in spy), spy


def test_every_query_reaching_the_model_carries_the_query_prefix(spy):
    embeddings.embed_query("combien de jours de congé ?")
    assert spy == [f"{QUERY}combien de jours de congé ?"]


def test_children_are_embedded_as_passages_not_queries(spy):
    children = [
        Child(text="article 5", parent_id="p1", source_file="code.pdf"),
        Child(text="article 6", parent_id="p1", source_file="code.pdf"),
    ]
    embeddings.embed_children(children)
    assert spy == [f"{PASSAGE}article 5", f"{PASSAGE}article 6"]


def test_the_prefix_is_the_only_thing_added(spy):
    embeddings.embed_passages(["exact body text"])
    assert spy == [f"{PASSAGE}exact body text"]


# --- deliberate behaviour, pinned so nobody "fixes" it later -----------------


def test_text_that_already_looks_prefixed_is_prefixed_again(spy):
    """A real document can contain the literal characters "passage: ".

    Skipping the prefix when the text happens to start with it would break
    the ADR-05 rule for exactly those documents, silently. Applying it
    unconditionally is the correct reading of "prefix the raw text"."""
    embeddings.embed_passages([f"{PASSAGE}already"])
    assert spy == [f"{PASSAGE}{PASSAGE}already"]


def test_order_is_preserved_so_vectors_align_with_their_children(spy):
    """Asserts the whole expected strings, not a split.

    Splitting on ": " to recover the body raises IndexError when the prefix
    is missing, which still fails but reports the wrong thing. Comparing the
    full list fails as a plain assertion and names both faults at once:
    order, and the prefix."""
    embeddings.embed_passages(["first", "second", "third"])
    assert spy == [f"{PASSAGE}first", f"{PASSAGE}second", f"{PASSAGE}third"]


def test_embedding_nothing_never_loads_the_model(monkeypatch):
    """Exercises the real `_encode` short-circuit, not the spy.

    Patching the model loader to explode proves the empty case returns
    before touching it. Asserting against the fake encoder would only prove
    the fake behaves."""

    def explode(_model_name):
        raise AssertionError("the model must not load for an empty batch")

    monkeypatch.setattr(embeddings, "_load_model", explode)
    assert embeddings.embed_passages([]) == []


# --- wrong shape, not just wrong content -------------------------------------


def test_a_bare_string_is_rejected_instead_of_embedded_per_character(spy):
    """`str` satisfies `Sequence[str]`, so this type-checks and would embed
    one vector per character without raising anything."""
    with pytest.raises(embeddings.EmbeddingInputError) as exc:
        embeddings.embed_passages("some text")
    assert "single string" in str(exc.value)
    assert spy == []


# --- loud failures instead of quiet bad vectors ------------------------------


@pytest.mark.parametrize("bad", ["", "   ", "\n\t "])
def test_empty_passage_raises_instead_of_embedding_nothing(spy, bad):
    with pytest.raises(embeddings.EmptyTextError):
        embeddings.embed_passages([bad])
    assert spy == [], "nothing should have reached the model"


@pytest.mark.parametrize("bad", ["", "   ", "\n\t "])
def test_empty_query_raises_instead_of_embedding_nothing(spy, bad):
    with pytest.raises(embeddings.EmptyTextError):
        embeddings.embed_query(bad)
    assert spy == []


def test_one_empty_item_rejects_the_whole_batch_and_names_which_one(spy):
    """Fail before the model call, not halfway through it, so a caller never
    gets a partially embedded batch it might treat as complete.

    The index matters: `chunking._windows` keeps any truthy window, so a
    window of pure padding whitespace reaches here. Without the position,
    the report is "a document failed" and finding which of hundreds of
    chunks did it starts from nothing."""
    with pytest.raises(embeddings.EmptyTextError) as exc:
        embeddings.embed_passages(["fine", "   ", "also fine"])
    assert exc.value.index == 1
    assert "index 1" in str(exc.value)
    assert spy == []


def test_wrong_vector_width_raises_rather_than_reaching_the_vector_store(monkeypatch):
    """Catches a mis-set embedding_model at the source.

    A different model loads and embeds happily; the mismatch would otherwise
    surface as an opaque rejection inside the vector store (ST-16), far from
    the setting that caused it."""
    monkeypatch.setattr(embeddings, "_encode", lambda texts: [[0.0] * 384 for _ in texts])
    with pytest.raises(embeddings.EmbeddingDimensionError) as exc:
        embeddings.embed_passages(["text"])
    assert "384" in str(exc.value)
    assert str(get_settings().embedding_dense_dim) in str(exc.value)


def test_a_short_batch_from_the_encoder_raises_instead_of_misaligning(monkeypatch):
    """ST-16 will zip children with vectors. If the encoder returns fewer
    vectors than inputs, every pairing after the gap attaches a vector to
    the wrong chunk, and citations point at the wrong passage while
    everything still looks healthy."""
    dim = get_settings().embedding_dense_dim
    monkeypatch.setattr(embeddings, "_encode", lambda texts: [[0.0] * dim])
    with pytest.raises(embeddings.EmbeddingCountError) as exc:
        embeddings.embed_passages(["one", "two", "three"])
    assert "1 vectors for 3 inputs" in str(exc.value)


# --- the real model, opt-in only ---------------------------------------------


@pytest.mark.skipif(
    os.environ.get("SANAD_RUN_MODEL_TESTS") != "1",
    reason="downloads multilingual-e5-base; set SANAD_RUN_MODEL_TESTS=1 to run",
)
def test_real_model_returns_normalised_vectors_of_the_configured_width():
    """Kept out of the PR gate on purpose: it downloads the model.

    Everything above proves the prefix RULE. This proves the model contract
    the rule sits on, which is a different claim and a slower one. It is the
    only test that exercises `_encode` and the `normalize_embeddings=True`
    argument for real."""
    vectors = embeddings.embed_passages(["congé annuel", "période d'essai"])
    dim = get_settings().embedding_dense_dim
    assert len(vectors) == 2
    assert all(len(v) == dim for v in vectors)
    for v in vectors:
        length = sum(x * x for x in v) ** 0.5
        assert abs(length - 1.0) < 1e-3, f"expected unit length, got {length}"


# --- ST-16: the sparse half, and the asymmetry that has no error message -----
#
# Same rule as the dense half above, one layer down. FastEmbed's BM25 exposes
# two methods and neither complains about being used on the wrong side:
#
#     model.embed(texts)      DOCUMENT side, IDF-weighted values
#     model.query_embed(text) QUERY side, flat term indicators
#
# Every test below asserts on which METHOD was reached, by spying on the model
# rather than on the vectors that come back. Asserting on the vectors would
# make the test agree with the code by construction, which is the ST-15 defect
# repeated: the prefix tests once built their expectation from the same config
# the code read, and passed with the prefix emptied out.


class _FakeSparseModel:
    """Records which side was called, and returns distinguishable vectors.

    The two sides return DIFFERENT values on purpose. A fake that returned
    the same thing either way would let a test claiming to prove the
    asymmetry pass while the code called whichever method it liked."""

    DOCUMENT_VALUE = 1.75
    QUERY_VALUE = 1.0

    def __init__(self):
        self.embed_calls: list[list[str]] = []
        self.query_embed_calls: list[str] = []

    def embed(self, documents, **_kwargs):
        texts = list(documents)
        self.embed_calls.append(texts)
        return [
            _RawSparse([index], [self.DOCUMENT_VALUE]) for index, _ in enumerate(texts)
        ]

    def query_embed(self, query, **_kwargs):
        self.query_embed_calls.append(query)
        return iter([_RawSparse([0], [self.QUERY_VALUE])])


class _RawSparse:
    """The shape FastEmbed hands back: `.indices` and `.values`."""

    def __init__(self, indices, values):
        self.indices = indices
        self.values = values


@pytest.fixture
def sparse_model(monkeypatch):
    model = _FakeSparseModel()
    monkeypatch.setattr(embeddings, "_load_sparse_model", lambda _name: model)
    return model


def test_configured_sparse_model_is_the_one_section_7_5_names():
    """Pins the setting itself, for the reason the dense prefix test exists:
    every other test here fakes the loader, so nothing else would notice
    `embedding_sparse_model` being changed to something that is not BM25."""
    assert get_settings().embedding_sparse_model == "Qdrant/bm25"


def test_indexed_text_goes_through_the_document_side(sparse_model):
    embeddings.embed_sparse_passages(["les congés payés", "la période d'essai"])
    assert sparse_model.embed_calls == [["les congés payés", "la période d'essai"]]
    assert sparse_model.query_embed_calls == [], "documents must not use query_embed"


def test_a_query_goes_through_the_query_side(sparse_model):
    """The one that matters. `embed` would also return a vector here, with
    IDF weights applied to a query that should carry none, and nothing
    anywhere would raise -- the only symptom is worse answers."""
    embeddings.embed_sparse_query("combien de jours de congé ?")
    assert sparse_model.query_embed_calls == ["combien de jours de congé ?"]
    assert sparse_model.embed_calls == [], "a query must not use embed"


def test_children_go_through_the_document_side(sparse_model):
    children = [
        Child(text="article 5", parent_id="p1", source_file="code.pdf"),
        Child(text="article 6", parent_id="p1", source_file="code.pdf"),
    ]
    embeddings.embed_sparse_children(children)
    assert sparse_model.embed_calls == [["article 5", "article 6"]]
    assert sparse_model.query_embed_calls == []


def test_sparse_gets_the_raw_text_with_no_e5_prefix(sparse_model):
    """`passage: ` and `query: ` are an E5 model-card requirement about a
    neural encoder. BM25 is lexical: prefixing would push the literal tokens
    "passage" and "query" into every document's term index and every query,
    where they match each other and mean nothing."""
    embeddings.embed_sparse_passages(["exact body text"])
    embeddings.embed_sparse_query("exact question")
    assert sparse_model.embed_calls == [["exact body text"]]
    assert sparse_model.query_embed_calls == ["exact question"]


def test_sparse_vectors_are_plain_python_not_numpy(sparse_model):
    """FastEmbed returns numpy arrays. They are converted at this seam so
    nothing downstream has to know that, and so a stored vector is
    JSON-shaped all the way to Qdrant."""
    [vector] = embeddings.embed_sparse_passages(["text"])
    assert isinstance(vector, embeddings.SparseVector)
    assert all(isinstance(i, int) for i in vector.indices)
    assert all(isinstance(v, float) for v in vector.values)


def test_sparse_order_is_preserved_so_vectors_align_with_their_children(sparse_model):
    vectors = embeddings.embed_sparse_passages(["first", "second", "third"])
    assert [v.indices for v in vectors] == [[0], [1], [2]]


def test_a_bare_string_is_rejected_by_the_sparse_side_too(sparse_model):
    """FastEmbed accepts a bare `str` and treats it as ONE document, so a
    caller expecting `len(texts)` vectors would get exactly one and zip it
    against the wrong children."""
    with pytest.raises(embeddings.EmbeddingInputError):
        embeddings.embed_sparse_passages("some text")
    assert sparse_model.embed_calls == []


@pytest.mark.parametrize("bad", ["", "   ", "\n\t "])
def test_empty_sparse_passage_raises_before_the_model(sparse_model, bad):
    with pytest.raises(embeddings.EmptyTextError):
        embeddings.embed_sparse_passages([bad])
    assert sparse_model.embed_calls == []


@pytest.mark.parametrize("bad", ["", "   ", "\n\t "])
def test_empty_sparse_query_raises_before_the_model(sparse_model, bad):
    with pytest.raises(embeddings.EmptyTextError):
        embeddings.embed_sparse_query(bad)
    assert sparse_model.query_embed_calls == []


def test_one_empty_item_rejects_the_whole_sparse_batch_and_names_which_one(
    sparse_model,
):
    with pytest.raises(embeddings.EmptyTextError) as exc:
        embeddings.embed_sparse_passages(["fine", "   ", "also fine"])
    assert exc.value.index == 1
    assert sparse_model.embed_calls == []


def test_sparse_embedding_nothing_never_loads_the_model(monkeypatch):
    def explode(_model_name):
        raise AssertionError("the sparse model must not load for an empty batch")

    monkeypatch.setattr(embeddings, "_load_sparse_model", explode)
    assert embeddings.embed_sparse_passages([]) == []


def test_a_short_sparse_batch_raises_instead_of_misaligning(monkeypatch):
    class _ShortModel:
        def embed(self, documents, **_kwargs):
            return [_RawSparse([0], [1.0])]

    monkeypatch.setattr(embeddings, "_load_sparse_model", lambda _n: _ShortModel())
    with pytest.raises(embeddings.EmbeddingCountError):
        embeddings.embed_sparse_passages(["one", "two", "three"])


@pytest.mark.skipif(
    os.environ.get("SANAD_RUN_MODEL_TESTS") != "1",
    reason="downloads Qdrant/bm25; set SANAD_RUN_MODEL_TESTS=1 to run",
)
def test_real_bm25_really_is_asymmetric():
    """The claim the fake above encodes, checked against the real library.

    Kept out of the PR gate because it downloads the model, but it is the
    only thing that proves the asymmetry is a fact about FastEmbed 0.8.0
    and not a fact about our fake. If a future release makes the two sides
    identical, this fails and the seam can be simplified on evidence."""
    text = "les congés payés sont de 18 jours ouvrables par an"
    document = embeddings.embed_sparse_passages([text])[0]
    as_query = embeddings.embed_sparse_query(text)
    assert (document.indices, document.values) != (as_query.indices, as_query.values)