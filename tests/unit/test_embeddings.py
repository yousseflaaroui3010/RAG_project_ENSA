"""ST-15 exit gate: the ADR-05 prefix rule, enforced without loading a model.

Architecture section 14 puts this test in the fast, no-model, every-PR tier
on purpose. The failure it guards against is silent: embedding text without
its "passage: " / "query: " prefix raises nothing and only shows up as
slightly worse answers. A test is the only thing that turns that into a
loud red.

Every test here spies on `embeddings._encode`, the single seam that talks to
the model, and asserts on the strings that actually reach it. Asserting on
what a helper RETURNS would pass even if a public function bypassed the
helper; asserting on what the encoder RECEIVES cannot.
"""

from __future__ import annotations

import os

import pytest

import embeddings
from chunking import Child
from config import get_settings


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


# --- the exit gate: nothing reaches the model without its prefix -------------


def test_every_passage_reaching_the_model_carries_the_passage_prefix(spy):
    embeddings.embed_passages(["le congé annuel", "la période d'essai"])
    prefix = get_settings().embedding_passage_prefix
    assert len(spy) == 2
    assert all(text.startswith(prefix) for text in spy), spy


def test_every_query_reaching_the_model_carries_the_query_prefix(spy):
    embeddings.embed_query("combien de jours de congé ?")
    prefix = get_settings().embedding_query_prefix
    assert len(spy) == 1
    assert spy[0].startswith(prefix), spy


def test_children_are_embedded_as_passages_not_queries(spy):
    children = [
        Child(text="article 5", parent_id="p1", source_file="code.pdf"),
        Child(text="article 6", parent_id="p1", source_file="code.pdf"),
    ]
    embeddings.embed_children(children)
    passage = get_settings().embedding_passage_prefix
    query = get_settings().embedding_query_prefix
    assert len(spy) == 2
    assert all(text.startswith(passage) for text in spy), spy
    assert not any(text.startswith(query) for text in spy), spy


def test_the_prefix_is_the_only_thing_added(spy):
    embeddings.embed_passages(["exact body text"])
    prefix = get_settings().embedding_passage_prefix
    assert spy == [f"{prefix}exact body text"]


# --- deliberate behaviour, pinned so nobody "fixes" it later -----------------


def test_text_that_already_looks_prefixed_is_prefixed_again(spy):
    """A real document can contain the literal characters "passage: ".

    Skipping the prefix when the text happens to start with it would break
    the ADR-05 rule for exactly those documents, silently. Applying it
    unconditionally is the correct reading of "prefix the raw text"."""
    prefix = get_settings().embedding_passage_prefix
    embeddings.embed_passages([f"{prefix}already"])
    assert spy == [f"{prefix}{prefix}already"]


def test_order_is_preserved_so_vectors_align_with_their_children(spy):
    """Asserts the whole expected strings, not a split.

    Splitting on ": " to recover the body raises IndexError when the prefix
    is missing, which still fails but reports the wrong thing. Comparing the
    full list fails as a plain assertion and names both faults at once:
    order, and the prefix."""
    prefix = get_settings().embedding_passage_prefix
    embeddings.embed_passages(["first", "second", "third"])
    assert spy == [f"{prefix}first", f"{prefix}second", f"{prefix}third"]


def test_embedding_nothing_calls_the_model_zero_times(spy):
    assert embeddings.embed_passages([]) == []
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


def test_one_empty_item_rejects_the_whole_batch_before_any_encoding(spy):
    """Fail before the model call, not halfway through it, so a caller never
    gets a partially embedded batch it might treat as complete."""
    with pytest.raises(embeddings.EmptyTextError):
        embeddings.embed_passages(["fine", "", "also fine"])
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


# --- the real model, opt-in only ---------------------------------------------


@pytest.mark.skipif(
    os.environ.get("SANAD_RUN_MODEL_TESTS") != "1",
    reason="downloads multilingual-e5-base; set SANAD_RUN_MODEL_TESTS=1 to run",
)
def test_real_model_returns_normalised_vectors_of_the_configured_width():
    """Kept out of the PR gate on purpose: it downloads the model.

    Everything above proves the prefix RULE. This proves the model contract
    the rule sits on, which is a different claim and a slower one."""
    vectors = embeddings.embed_passages(["congé annuel", "période d'essai"])
    dim = get_settings().embedding_dense_dim
    assert len(vectors) == 2
    assert all(len(v) == dim for v in vectors)
    for v in vectors:
        length = sum(x * x for x in v) ** 0.5
        assert abs(length - 1.0) < 1e-3, f"expected unit length, got {length}"