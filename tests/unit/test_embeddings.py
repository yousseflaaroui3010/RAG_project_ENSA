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