"""ST-39 warm-up: the server loads both search encoders on a background
thread once it starts, so the first real question does not pay for it.

BUILD-STATE's "THE LIVE RUN, 2026-08-30" measured 23s on a fresh process's
first search, with the server serving nothing else meanwhile. The fix is a
`Runtime.warm_up` flag: OFF by default (every test in this codebase builds
a `Runtime` directly and must never download a model), ON only where
`app.main()` builds the real server's `Runtime`.

Nothing here touches a real model. `embeddings.embed_query` and
`embeddings.embed_sparse_query` are monkeypatched at the module level app.py
calls them through (`import embeddings; embeddings.embed_query(...)`), so
patching `embeddings.embed_query` is visible to `app.py` without app.py
needing to be reloaded."""

from __future__ import annotations

import logging
import threading
import time

from fastapi.testclient import TestClient

import embeddings
from app import Runtime, create_app


def test_default_runtime_never_calls_the_encoders(tmp_path, monkeypatch):
    """Kill test 1: remove the `if runtime.warm_up:` guard (or flip the
    default to True) and this goes red.

    NOTE: the fake below records a call rather than raising, and the test
    waits on an `Event` rather than trusting "no exception happened" --
    `_warm_up_models` catches and swallows every exception on purpose (a
    warm-up must never crash the server), so a fake that raised would have
    its failure silently caught by the very code under test and this would
    pass whether or not the guard existed."""
    db_path = tmp_path / "sanad.db"
    called = threading.Event()

    def record_dense(*_args, **_kwargs):
        called.set()
        return [0.0]

    def record_sparse(*_args, **_kwargs):
        called.set()
        return embeddings.SparseVector(indices=[], values=[])

    monkeypatch.setattr(embeddings, "embed_query", record_dense)
    monkeypatch.setattr(embeddings, "embed_sparse_query", record_sparse)

    with TestClient(create_app(Runtime(db_path=db_path))) as client:
        response = client.get("/workspaces")
        assert response.status_code == 200
        # A generous window for a wrongly-spawned background thread to have
        # made its call; the correct behaviour makes no call, ever.
        assert not called.wait(timeout=0.5)


def test_warm_up_calls_both_encoders_once_on_the_named_background_thread(
    tmp_path, monkeypatch
):
    """Kill test 2: delete the thread (call `_warm_up_models()` directly
    inside the lifespan, on whatever thread runs it) and the thread-name
    assertion goes red -- it would then run on the ASGI server's own
    lifespan thread, never on one named "sanad-warmup".

    NOTE: comparing against `threading.get_ident()` captured in the test
    body would NOT catch that mutation -- `TestClient`'s lifespan already
    runs on its own internal thread, distinct from the test's, whether or
    not this code spawns a further thread of its own. The thread NAME this
    code sets is the only signal that discriminates "a thread we spawned"
    from "whatever thread the test harness happened to use"."""
    db_path = tmp_path / "sanad.db"
    calls: list[tuple[str, str, str]] = []
    done = threading.Event()

    def fake_dense(text: str):
        calls.append(("dense", text, threading.current_thread().name))
        return [0.0]

    def fake_sparse(text: str):
        calls.append(("sparse", text, threading.current_thread().name))
        done.set()
        return embeddings.SparseVector(indices=[], values=[])

    monkeypatch.setattr(embeddings, "embed_query", fake_dense)
    monkeypatch.setattr(embeddings, "embed_sparse_query", fake_sparse)

    with TestClient(create_app(Runtime(db_path=db_path, warm_up=True))):
        assert done.wait(timeout=5), "warm-up never ran"

    dense_calls = [c for c in calls if c[0] == "dense"]
    sparse_calls = [c for c in calls if c[0] == "sparse"]
    assert len(dense_calls) == 1
    assert len(sparse_calls) == 1
    # Same fixed text on both halves -- the whole point is walking the same
    # loading path a real question would use, and a real question asks one
    # question, not two different strings.
    assert dense_calls[0][1] == sparse_calls[0][1]
    assert dense_calls[0][1]
    assert dense_calls[0][2] == "sanad-warmup"
    assert sparse_calls[0][2] == "sanad-warmup"


def test_a_slow_warm_up_does_not_block_a_request(tmp_path, monkeypatch):
    """Kill test 3: make the warm-up call happen on the request-serving /
    lifespan thread (e.g. call `_warm_up_models()` synchronously instead of
    spawning a thread for it) and the FIRST assertion below goes red --
    entering the app's lifespan would then wait for the whole slow load
    before start-up could even finish, let alone serve a request.

    Timing the `with TestClient(...)` ENTRY itself, not just the request
    that follows, is the part that actually catches that mutation: a
    synchronous warm-up still finishes eventually (its own `proceed.wait`
    times out and `_warm_up_models` swallows the resulting exception), so by
    the time a request-timing-only assertion ran, the slow call would
    already be over and look identical to the correct, concurrent
    behaviour."""
    db_path = tmp_path / "sanad.db"
    started = threading.Event()
    proceed = threading.Event()

    def slow_dense(text: str):
        started.set()
        proceed.wait(timeout=10)
        return [0.0]

    def fake_sparse(text: str):
        return embeddings.SparseVector(indices=[], values=[])

    monkeypatch.setattr(embeddings, "embed_query", slow_dense)
    monkeypatch.setattr(embeddings, "embed_sparse_query", fake_sparse)

    before_enter = time.monotonic()
    with TestClient(create_app(Runtime(db_path=db_path, warm_up=True))) as client:
        enter_elapsed = time.monotonic() - before_enter
        assert enter_elapsed < 1.0, "starting the server waited for warm-up"
        assert started.wait(timeout=5), "warm-up never started"
        before_request = time.monotonic()
        response = client.get("/workspaces")
        request_elapsed = time.monotonic() - before_request
        assert response.status_code == 200
        # The warm-up is still parked on `proceed` right now. A request
        # answered this fast could not have waited behind it.
        assert request_elapsed < 1.0
        proceed.set()


def test_a_failing_warm_up_is_logged_and_does_not_crash_the_server(
    tmp_path, monkeypatch, caplog
):
    """Kill test 4: let the exception propagate out of the warm-up thread
    (remove the try/except) and the server either crashes the lifespan or
    this test's request never gets a chance to run, depending on how it
    escapes; either way the assertion below goes red or the run errors."""
    db_path = tmp_path / "sanad.db"
    done = threading.Event()

    def broken_dense(text: str):
        done.set()
        raise RuntimeError("no network for the first-ever model download")

    monkeypatch.setattr(embeddings, "embed_query", broken_dense)

    with caplog.at_level(logging.ERROR, logger="app"):
        with TestClient(create_app(Runtime(db_path=db_path, warm_up=True))) as client:
            assert done.wait(timeout=5), "warm-up never ran"
            response = client.get("/workspaces")
            assert response.status_code == 200

    assert any("warm-up" in record.message for record in caplog.records)
    # No secret or stack-trace-only detail is asserted on here; the log
    # message itself is a fixed, safe sentence (see `_warm_up_models`).


def test_starting_the_real_server_turns_warm_up_on():
    """`app.main` must be the one caller that flips the default. This reads
    the source rather than starting a real uvicorn server (which would
    actually bind a socket and load real models) -- see CLAUDE.md on not
    guessing a shape: the shape checked here is "the literal call inside
    `main`", not a re-implementation of what `main` does."""
    import inspect

    import app as app_module

    source = inspect.getsource(app_module.main)
    assert "warm_up=True" in source
