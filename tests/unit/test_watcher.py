"""F-13 live folder watching (watcher.py).

Architecture p.97/387: the watcher wraps `Runtime.start_sync` (today's
name for what the doc calls `ingestion.sync`) and excludes `watchdog` by
name, so this is a polling design and these tests drive `poll_once`
directly with fake clocks/snapshots/triggers -- no real sleeping, no real
threads, except in the small section that tests `WatcherThread` and
`start_if_enabled` themselves, which is exactly where a real background
thread is the thing under test.
"""

from __future__ import annotations

import os
import threading
import time

import pytest

import sync
import watcher
from config import Settings
from db import repo
from workspaces import Workspace


def _ws(ws_id: str = "w1", folder: str = ".") -> Workspace:
    return Workspace(
        id=ws_id,
        name=ws_id,
        folder_path=folder,
        legal_flag=False,
        created_at="2026-01-01T00:00:00Z",
    )


class _ScriptedSnapshot:
    """Per-folder queue of canned `(size, mtime_ns)` snapshots.

    Repeats the LAST scripted value once its queue is exhausted, rather
    than raising, so a test can poll past its scripted setup (proving "a
    third/fourth poll changes nothing") without over-specifying every
    call -- a real stable file behaves exactly like this: the same stat
    forever."""

    def __init__(self, scripts: dict[str, list[dict]]):
        self._scripts = {path: list(seq) for path, seq in scripts.items()}

    def __call__(self, folder_path: str) -> dict:
        queue = self._scripts[folder_path]
        return queue.pop(0) if len(queue) > 1 else queue[0]


class _RecordingTrigger:
    """Fake `Runtime.start_sync`. `fail_times` raises SyncInProgressError
    that many times before succeeding, so a test can prove a failed
    attempt is retried rather than lost or counted as done."""

    def __init__(self, fail_times: int = 0):
        self.calls: list[str] = []
        self.successes: list[str] = []
        self._fail_times = fail_times

    def __call__(self, workspace_id: str) -> None:
        self.calls.append(workspace_id)
        if self._fail_times > 0:
            self._fail_times -= 1
            raise sync.SyncInProgressError(workspace_id, "run-1", "2026-01-01T00:00:00Z")
        self.successes.append(workspace_id)


def _poll(state, active, snapshot, trigger, *, times: int = 1) -> None:
    for _ in range(times):
        watcher.poll_once(
            state, list_workspaces=lambda: active, trigger=trigger, snapshot=snapshot
        )


# --- poll_once / _poll_workspace: the readiness rule -----------------------


def test_new_stable_file_triggers_exactly_once_and_stays_quiet():
    """Kill test for "forget to record the snapshot after a trigger": drop
    the `ws_state.baseline.update(...)` line in `_poll_workspace` and this
    goes red with more than one call, because the same stable file would
    look ready again on poll 4."""
    ws = _ws(folder="F")
    snap = _ScriptedSnapshot(
        {
            "F": [
                {},  # poll 1: nothing yet -- establishes the baseline
                {"a.pdf": (100, 1)},  # poll 2: file appears
                {"a.pdf": (100, 1)},  # poll 3: same as poll 2 -> stable -> ready
                {"a.pdf": (100, 1)},  # poll 4: already committed -> quiet
            ]
        }
    )
    trigger = _RecordingTrigger()
    state = watcher.WatcherState()

    _poll(state, [ws], snap, trigger, times=4)

    assert trigger.calls == ["w1"]


def test_growing_file_triggers_nothing_until_it_stabilizes():
    """Kill test for "remove the stability check": compare only against
    baseline (drop the `== last_poll` half of `ready`) and this goes red,
    triggering on poll 2 while the file is still being written."""
    ws = _ws(folder="F")
    snap = _ScriptedSnapshot(
        {
            "F": [
                {},
                {"a.pdf": (10, 1)},
                {"a.pdf": (20, 2)},  # still growing
                {"a.pdf": (30, 3)},  # still growing
                {"a.pdf": (30, 3)},  # now stable
            ]
        }
    )
    trigger = _RecordingTrigger()
    state = watcher.WatcherState()

    _poll(state, [ws], snap, trigger, times=4)
    assert trigger.calls == [], "must not trigger while the file is still changing"

    _poll(state, [ws], snap, trigger, times=1)
    assert trigger.calls == ["w1"]


def test_a_batch_copy_waits_until_every_file_has_finished_arriving():
    """Sync reads the whole folder, so a trigger while b.pdf is still being
    copied would ingest it half-written. Kill test for dropping the
    `settling` hold in `_poll_workspace`: a.pdf is stable on poll 3 and the
    mutant triggers there, while b.pdf is still growing."""
    ws = _ws(folder="F")
    snap = _ScriptedSnapshot(
        {
            "F": [
                {},
                {"a.pdf": (100, 1)},
                {"a.pdf": (100, 1), "b.pdf": (10, 2)},  # a stable, b arriving
                {"a.pdf": (100, 1), "b.pdf": (50, 3)},  # b still growing
                {"a.pdf": (100, 1), "b.pdf": (50, 3)},  # everything settled
                {"a.pdf": (100, 1), "b.pdf": (50, 3)},
            ]
        }
    )
    trigger = _RecordingTrigger()
    state = watcher.WatcherState()

    _poll(state, [ws], snap, trigger, times=4)
    assert trigger.calls == [], "must not sync while another file is still arriving"

    _poll(state, [ws], snap, trigger, times=2)
    assert trigger.calls == ["w1"], "one sync for the whole batch, exactly once"


def test_sync_in_progress_is_retried_next_poll_and_triggers_once_total():
    """Kill test for "swallow SyncInProgress by marking done": catch the
    exception but still record the baseline, and `successes` stays at 1
    while `calls` (the mutation this test also watches) would still be 2
    -- so the mutation to hunt for is recording success falsely; the
    assertion on `successes` is what would go red."""
    ws = _ws(folder="F")
    snap = _ScriptedSnapshot(
        {
            "F": [
                {},
                {"a.pdf": (5, 1)},
                {"a.pdf": (5, 1)},  # stable -> ready, first attempt fails
                {"a.pdf": (5, 1)},  # still stable -> retried, succeeds
                {"a.pdf": (5, 1)},  # already committed -> no more attempts
            ]
        }
    )
    trigger = _RecordingTrigger(fail_times=1)
    state = watcher.WatcherState()

    _poll(state, [ws], snap, trigger, times=5)

    assert trigger.calls == ["w1", "w1"], "must retry the failed attempt"
    assert trigger.successes == ["w1"], "exactly one successful trigger, not zero or two"


def test_two_workspaces_only_the_changed_one_triggers():
    ws1 = _ws("w1", "F1")
    ws2 = _ws("w2", "F2")
    snap = _ScriptedSnapshot(
        {
            "F1": [{}, {"a.pdf": (5, 1)}, {"a.pdf": (5, 1)}, {"a.pdf": (5, 1)}],
            "F2": [{}, {}, {}, {}],
        }
    )
    trigger = _RecordingTrigger()
    state = watcher.WatcherState()

    _poll(state, [ws1, ws2], snap, trigger, times=4)

    assert trigger.calls == ["w1"]


def test_pre_existing_stable_file_at_startup_is_not_treated_as_new():
    """The first poll a workspace is ever seen at seeds the baseline from
    whatever is already on disk -- F-13 is about a file DROPPED while
    watching runs, not the folder's contents at boot."""
    ws = _ws(folder="F")
    snap = _ScriptedSnapshot(
        {"F": [{"old.pdf": (100, 1)}, {"old.pdf": (100, 1)}, {"old.pdf": (100, 1)}]}
    )
    trigger = _RecordingTrigger()
    state = watcher.WatcherState()

    _poll(state, [ws], snap, trigger, times=3)

    assert trigger.calls == []


def test_disappeared_file_never_triggers_and_never_repeats():
    """Sync's own change detection already reports and cleans up a
    removal the next time it runs for any reason; the watcher choosing
    never to react to a pure disappearance trivially satisfies "must not
    trigger repeatedly" for that case."""
    ws = _ws(folder="F")
    snap = _ScriptedSnapshot(
        {
            "F": [
                {"a.pdf": (5, 1)},  # already there at startup
                {"a.pdf": (5, 1)},
                {},  # gone
                {},
                {},
            ]
        }
    )
    trigger = _RecordingTrigger()
    state = watcher.WatcherState()

    _poll(state, [ws], snap, trigger, times=5)

    assert trigger.calls == []


def test_a_workspace_that_no_longer_exists_is_forgotten():
    """Hygiene: a deleted workspace's watch state does not sit in memory
    forever on a long-running server."""
    ws = _ws(folder="F")
    snap = _ScriptedSnapshot({"F": [{}]})
    state = watcher.WatcherState()

    watcher.poll_once(state, list_workspaces=lambda: [ws], trigger=lambda _id: None, snapshot=snap)
    assert "w1" in state.per_workspace

    watcher.poll_once(state, list_workspaces=lambda: [], trigger=lambda _id: None, snapshot=snap)
    assert "w1" not in state.per_workspace


def test_a_broken_workspace_does_not_stop_the_others_this_poll():
    """One workspace's trigger raising something other than
    SyncInProgressError (e.g. the workspace was deleted mid-poll) must
    not stop the round for a workspace listed after it."""
    ws_bad = _ws("bad", "BAD")
    ws_good = _ws("good", "GOOD")
    snap = _ScriptedSnapshot(
        {
            "BAD": [{}, {"a.pdf": (5, 1)}, {"a.pdf": (5, 1)}],
            "GOOD": [{}, {"a.pdf": (5, 1)}, {"a.pdf": (5, 1)}],
        }
    )

    calls: list[str] = []

    def trigger(workspace_id: str) -> None:
        calls.append(workspace_id)
        if workspace_id == "bad":
            raise RuntimeError("workspace vanished mid-poll")

    state = watcher.WatcherState()
    _poll(state, [ws_bad, ws_good], snap, trigger, times=3)

    assert calls == ["bad", "good"]


# --- snapshot_folder: real files, real stat, reused extension list ---------


def test_snapshot_folder_excludes_unsupported_extensions_and_subfolders(tmp_path):
    (tmp_path / "a.pdf").write_text("x", encoding="utf-8")
    (tmp_path / "notes.pptx").write_text("x", encoding="utf-8")  # unsupported (F-11 is V1.1)
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.pdf").write_text("x", encoding="utf-8")  # not recursive

    result = watcher.snapshot_folder(tmp_path)

    assert set(result) == {"a.pdf"}


def test_snapshot_folder_of_a_missing_folder_is_empty_not_raising(tmp_path):
    assert watcher.snapshot_folder(tmp_path / "does-not-exist") == {}


def test_real_folder_real_files_driven_by_os_utime_no_sleeping(tmp_path):
    """One end-to-end pass with real files and real `os.stat`, still with
    a fake trigger and manually driven polls -- stability is forced with
    `os.utime` rather than a real sleep, so the test is fast and exact."""
    folder = tmp_path / "docs"
    folder.mkdir()
    ws = _ws(folder=str(folder))
    trigger = _RecordingTrigger()
    state = watcher.WatcherState()
    fixed_ns = 1_700_000_000 * 1_000_000_000

    def _poll_real() -> None:
        watcher.poll_once(state, list_workspaces=lambda: [ws], trigger=trigger)

    _poll_real()  # poll 1: empty folder -> baseline
    assert trigger.calls == []

    target = folder / "new.txt"
    target.write_text("hello", encoding="utf-8")
    os.utime(target, ns=(fixed_ns, fixed_ns))

    _poll_real()  # poll 2: seen once, one observation is not stability yet
    assert trigger.calls == []

    _poll_real()  # poll 3: identical stat as poll 2 -> stable -> triggers
    assert trigger.calls == ["w1"]

    _poll_real()  # poll 4: unchanged, already committed -> no repeat
    assert trigger.calls == ["w1"]

    ignored = folder / "notes.pptx"
    ignored.write_text("ignored", encoding="utf-8")
    os.utime(ignored, ns=(fixed_ns, fixed_ns))
    _poll_real()
    _poll_real()
    assert trigger.calls == ["w1"], "an unsupported extension must never become ready"


# --- config: watch_interval_seconds must fail loud on a bad value ----------


def test_watch_settings_default_off():
    settings = Settings(_env_file=None)
    assert settings.watch_folders is False
    assert settings.watch_interval_seconds == 5.0


@pytest.mark.parametrize("bad_value", [0, 0.0, -1.0])
def test_watch_interval_must_be_positive(bad_value):
    with pytest.raises(Exception) as excinfo:
        Settings(_env_file=None, watch_interval_seconds=bad_value)
    assert "watch_interval_seconds" in str(excinfo.value)


# --- WatcherThread: a real background thread, briefly ----------------------


def test_watcher_thread_polls_repeatedly_and_stops_promptly():
    third_poll = threading.Event()
    calls: list[int] = []

    def fake_list_workspaces():
        calls.append(1)
        if len(calls) >= 3:
            third_poll.set()
        return []

    thread = watcher.WatcherThread(
        interval_seconds=0.01,
        trigger=lambda _id: None,
        list_workspaces=fake_list_workspaces,
    )
    thread.start()
    try:
        assert third_poll.wait(timeout=5), "watcher did not poll repeatedly"
    finally:
        started = time.monotonic()
        thread.stop(timeout=2)
        elapsed = time.monotonic() - started

    # A BOUNDED join, not just a floor: the thread must actually have
    # stopped, and quickly -- not merely that `stop()` returned because its
    # own timeout expired while the thread kept running.
    assert not thread.is_alive()
    assert elapsed < 2.0


# --- start_if_enabled: the one decision point -------------------------------


def test_start_if_enabled_is_off_by_default(monkeypatch):
    def _exploding(**_kwargs):
        raise AssertionError("WatcherThread must not be constructed when watch_folders is off")

    monkeypatch.setattr(watcher, "WatcherThread", _exploding)
    settings = Settings(_env_file=None)

    result = watcher.start_if_enabled(settings, db_path=None, trigger=lambda _id: None)

    assert result is None


def test_start_if_enabled_evidence_only_wins_even_when_watch_folders_is_true(monkeypatch):
    """The exact guard order the task cares about: evidence_only must
    stop the watcher before anything else runs, `watch_folders=True`
    notwithstanding -- and, because `WatcherThread` is never even
    constructed, nothing here could load the embedding model either."""

    def _exploding(**_kwargs):
        raise AssertionError("must never construct the watcher thread in evidence-only mode")

    monkeypatch.setattr(watcher, "WatcherThread", _exploding)
    settings = Settings(_env_file=None, watch_folders=True, evidence_only=True)

    result = watcher.start_if_enabled(settings, db_path=None, trigger=lambda _id: None)

    assert result is None


def test_start_if_enabled_starts_a_real_thread_when_both_flags_allow_it(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    settings = Settings(
        _env_file=None, watch_folders=True, evidence_only=False, watch_interval_seconds=0.02
    )

    thread = watcher.start_if_enabled(settings, db_path=db_path, trigger=lambda _id: None)
    try:
        assert thread is not None
        assert thread.is_alive()
    finally:
        thread.stop(timeout=2)
    assert not thread.is_alive()


def test_a_registry_that_does_not_exist_yet_means_nothing_to_watch(tmp_path, caplog):
    """app.main() starts the watcher before the lifespan creates sanad.db,
    so a fresh install's first poll can find no registry. Found on a real
    first boot: that poll logged a full traceback. It must be a quiet
    "no workspaces", and a registry created later is picked up."""
    db_path = tmp_path / "sanad.db"
    assert watcher._registered_workspaces(db_path) == []
    state = watcher.WatcherState()
    with caplog.at_level("ERROR", logger="watcher"):
        watcher.poll_once(
            state,
            list_workspaces=lambda: watcher._registered_workspaces(db_path),
            trigger=_RecordingTrigger(),
        )
    assert caplog.records == []

    repo.ensure_schema(db_path)
    assert watcher._registered_workspaces(db_path) == []
