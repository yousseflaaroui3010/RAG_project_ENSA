"""app.main()'s F-13 wiring: it must call `watcher.start_if_enabled` with
the real settings, the real `Runtime`'s `db_path`, and that same
`Runtime`'s bound `start_sync` as the trigger, then stop whatever thread
comes back once `uvicorn.run` returns.

`watcher.WatcherThread` is faked in every test here -- a real one would
poll the production `data/sanad.db` the instant `main()` builds a bare
`Runtime()`, which is exactly what "never in tests by default" forbids.
`watcher.start_if_enabled`'s own guard logic (the real evidence_only /
watch_folders decision) is never touched, so these tests exercise the
REAL decision reached from real settings, not a restated boolean --
matching how `tests/unit/test_app_warmup.py` reads `runtime.warm_up` off
the object `main()` actually built rather than trusting a flag name."""

from __future__ import annotations

import app as app_module
from app import Runtime
from config import get_settings


class _FakeThread:
    instances: list[_FakeThread] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.started = False
        self.stopped = False
        _FakeThread.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self, *, timeout: float = 5.0) -> None:
        self.stopped = True


class _ExplodingThread:
    def __init__(self, **_kwargs):
        raise AssertionError("WatcherThread must not be constructed here")


def _settings(**overrides):
    return get_settings().model_copy(update=overrides)


def test_main_wires_and_stops_the_watcher_when_enabled(monkeypatch):
    _FakeThread.instances.clear()
    monkeypatch.setattr(app_module.watcher, "WatcherThread", _FakeThread)
    settings = _settings(watch_folders=True, evidence_only=False)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module.uvicorn, "run", lambda _app, **_kwargs: None)

    app_module.main()

    assert len(_FakeThread.instances) == 1
    thread = _FakeThread.instances[0]
    assert thread.started is True, "main() must start the returned thread"
    assert thread.stopped is True, "main() must stop the watcher after serving ends"
    # The trigger is the REAL server's own Runtime.start_sync, not a copy
    # or a lambda -- a second implementation here would be a second answer
    # to "how does a workspace get synced" (ADR-13's whole point).
    assert isinstance(thread.kwargs["trigger"].__self__, Runtime)
    assert thread.kwargs["trigger"].__func__ is Runtime.start_sync
    assert thread.kwargs["db_path"] == thread.kwargs["trigger"].__self__.db_path


def test_main_never_constructs_the_watcher_when_watch_folders_is_false(monkeypatch):
    monkeypatch.setattr(app_module.watcher, "WatcherThread", _ExplodingThread)
    settings = _settings(watch_folders=False, evidence_only=False)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module.uvicorn, "run", lambda _app, **_kwargs: None)

    app_module.main()  # must not raise


def test_main_never_constructs_the_watcher_in_evidence_only_mode(monkeypatch):
    """The exact case the task calls out: evidence_only=True must win even
    with watch_folders=True, checked at the real `main()` seam rather than
    only inside `watcher.start_if_enabled`'s own unit tests."""
    monkeypatch.setattr(app_module.watcher, "WatcherThread", _ExplodingThread)
    settings = _settings(watch_folders=True, evidence_only=True)
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    monkeypatch.setattr(app_module.uvicorn, "run", lambda _app, **_kwargs: None)

    app_module.main()  # must not raise
