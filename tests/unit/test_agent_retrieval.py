"""ST-23: the retrieve port, and the two things it must NOT do.

Reference: architecture 5.2 box S, ADR-04 (embedded Qdrant, one client per
process) and ADR-05 (hybrid retrieval, and the encoding asymmetry that
lives behind `vector_store`).

This file is short because the port is wiring. What is worth testing is
not that search returns hits -- `test_vector_store.py` already proves that
against a real Qdrant -- but that this adapter adds nothing of its own: it
opens no client, invents no search depth, and swallows no error.
"""

from __future__ import annotations

import pytest

import vector_store
from agent.retrieval import build_retrieve
from vector_store import SearchHit

WORKSPACE = "11111111-1111-1111-1111-111111111111"
HIT = SearchHit(
    parent_id="p-1",
    source_file="code-du-travail.pdf",
    section_label="Article 13",
    chunk_text="Trois mois.",
    score=0.9,
)


class _SpySearch:
    def __init__(self, result=(HIT,)):
        self.result = result
        self.calls: list[tuple] = []

    def __call__(self, client, **kwargs):
        self.calls.append((client, kwargs))
        return list(self.result)


def test_the_port_passes_the_workspace_and_the_raw_query(monkeypatch):
    """The RAW question, never a vector. `vector_store.search` owns the
    encoding, which is what makes ADR-05's `passage:`/`query:` asymmetry
    impossible to get wrong from this side: a caller that cannot hand over
    a vector cannot hand over one encoded the wrong way."""
    spy = _SpySearch()
    monkeypatch.setattr(vector_store, "search", spy)
    client = object()

    hits = build_retrieve(client)(WORKSPACE, "duree periode essai")

    assert list(hits) == [HIT]
    called_client, kwargs = spy.calls[0]
    assert called_client is client
    assert kwargs["workspace_id"] == WORKSPACE
    assert kwargs["query_text"] == "duree periode essai"


def test_the_port_does_not_pass_a_search_depth_of_its_own(monkeypatch):
    """Deliberate, and the opposite of what it looks like.

    `vector_store.search` resolves `limit=None` to
    `config.retrieval_depth_k` itself, and its docstring says why: "F-04
    makes the depth operator-tunable; never hardcode it at a call site."
    Reading the setting here as well would be a SECOND place reading it --
    the shape that drifts, where one caller gets updated and another does
    not and two searches in the same product use different depths.

    So the assertion is an absence. The integration test proves the
    operator's setting is what actually governs the hit count."""
    spy = _SpySearch()
    monkeypatch.setattr(vector_store, "search", spy)

    build_retrieve(object())(WORKSPACE, "q")

    _client, kwargs = spy.calls[0]
    assert "limit" not in kwargs or kwargs["limit"] is None


def test_the_port_never_opens_a_client_of_its_own(monkeypatch):
    """ADR-04 is single-process, and `open_store` raises on a second
    client for the same storage path -- with a message about a lock folder
    that reads exactly like stale state somebody should delete. So the
    client's lifetime belongs to whoever composes the app, and this
    adapter must only ever borrow it."""
    monkeypatch.setattr(vector_store, "search", _SpySearch())

    def explode(*_args, **_kwargs):
        raise AssertionError("the retrieve port opened its own Qdrant client")

    monkeypatch.setattr(vector_store, "open_store", explode)

    build_retrieve(object())(WORKSPACE, "q")


def test_a_workspace_that_was_never_synced_reaches_the_caller(monkeypatch):
    """`CollectionNotFoundError` is deliberately not caught.

    "Never synced" and "the documents do not cover this" are different
    facts with different next steps -- press Sync, versus rephrase -- and
    turning the first into the second sends the user to fix a question
    that was never the problem. The error already carries the right
    sentence."""

    def never_synced(*_args, **_kwargs):
        raise vector_store.CollectionNotFoundError("run a Sync before searching it")

    monkeypatch.setattr(vector_store, "search", never_synced)

    with pytest.raises(vector_store.CollectionNotFoundError, match="run a Sync"):
        build_retrieve(object())(WORKSPACE, "q")
