"""Where a half-written answer goes while the model is still writing (S6).

The `write_answer` port returns ONE string, and every node, fake and test
in the graph relies on that shape. Streaming is added without changing it:
`ui.runs.Run` opens a listener around the writing call, and the answer
writer publishes to whoever is listening. Every question driven by a `Run`
therefore streams -- the chat screen, the HTTP API (`api/service.py`) and
the evaluation capture (`evaluation/capture.py`) -- so a release run
measures the same path a reader gets. A direct `agent.graph.ask` call with
no `Run` (unit tests, the ST-18 spike) has nobody listening, and the writer
makes the single `complete` call it always made.

A `ContextVar`, not a module global: two questions in flight on two worker
threads must never see each other's text, and a context variable set in a
thread is invisible to every other thread.

A listener may RAISE. `Run` raises `RunCancelled` from inside it when the
operator presses Cancel, which stops the model stream mid-answer instead of
paying for the rest of it. The writer lets that exception through untouched.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

Listener = Callable[[str], None]

_listener: ContextVar[Listener | None] = ContextVar("sanad_answer_listener", default=None)


@contextmanager
def listening_with(listener: Listener) -> Iterator[None]:
    """Send every partial answer published inside this block to `listener`."""
    token = _listener.set(listener)
    try:
        yield
    finally:
        _listener.reset(token)


def listening() -> bool:
    return _listener.get() is not None


def publish(text_so_far: str) -> None:
    """The whole answer written so far (not a delta), or nothing if no one
    is listening. Whole text rather than pieces, so a listener that misses
    one call is never left holding a garbled answer."""
    listener = _listener.get()
    if listener is not None:
        listener(text_so_far)
