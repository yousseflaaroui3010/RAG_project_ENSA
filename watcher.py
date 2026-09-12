"""F-13 Live folder watching: a polling daemon that triggers Sync on its
own when a new, fully-written supported file lands in a workspace folder.

Architecture (Sanad_Architecture_v1.0.md p.97, p.387): "the watcher wraps
`ingestion.sync`" and excludes `watchdog` BY NAME, "F-13 is V2" -- the
module the architecture calls `ingestion.sync` is today's flat `sync.py`
(the codebase never grew the `ingestion` package the doc's line assumed;
same seam either way, `Runtime.start_sync`). No new dependency is added
here: this module polls with `os.stat`, exactly what the exclusion asks
for.

WHY POLLING WORKS AND WHAT IT COSTS. A folder has no push notification
without an OS-level watch library, so the only honest alternative is
looking again every `watch_interval_seconds` (config.py). Looking means
`os.stat`, not `change_detection.scan_folder`'s content hash: hashing
every file in every workspace on every poll would re-read a large PDF's
full bytes every five seconds forever, for a check whose only job is
"has anything changed at all". `is_supported` (change_detection.py) is
reused rather than re-listing PRD F-02's extensions a second time.

WHY TWO-POLL STABILITY. A file mid-copy has a size and mtime that keep
changing between polls; converting it now would hand ADR-07's conversion
ladder a half-written document. A file whose (size, mtime_ns) is
IDENTICAL across two consecutive polls has stopped changing, which is
the cheapest honest proxy for "fully written" available without opening
and locking the file.

WHAT COUNTS AS "ALREADY THERE", NOT "NEW". The first poll a workspace is
ever seen at records its current files as the baseline rather than
comparing them against nothing -- otherwise every file already sitting
in the folder when the server (re)starts would look "new" two polls
later and each workspace would pay for one redundant Sync every restart.
F-13's acceptance criterion is about a file DROPPED while watching is
on, not about the folder's contents at boot.

WHY A DISAPPEARANCE NEVER TRIGGERS HERE. A removed file has nothing to
stat, so it can never appear in `ready` (which only ever looks at names
present in the CURRENT poll). Sync's own `change_detection.py` already
reports and cleans up a removal the next time it runs for any reason;
this module choosing not to chase removals on its own trivially satisfies
the constraint "must not trigger repeatedly" for a bytes-never-changing
event.

TESTABILITY. `poll_once` (and the `_poll_workspace` it calls per
workspace) takes `list_workspaces`, `snapshot` and `trigger` as
parameters, so a unit test drives many polls with a fake clock and no
real files, no real sleeping and no real thread. Only `WatcherThread`
itself needs a real background thread and `threading.Event`, and only
tests aimed at that class exercise it.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import sync
import workspaces
from change_detection import is_supported
from config import Settings
from db.repo import RegistryNotFoundError

logger = logging.getLogger(__name__)

# file_name -> (size_bytes, mtime_ns). Cheap, and exactly the two numbers
# that stay put once a file has finished being written and untouched
# afterward.
Snapshot = dict[str, tuple[int, int]]


def snapshot_folder(folder: str | Path) -> Snapshot:
    """One cheap `os.stat` pass over a workspace folder's supported files.

    Deliberately NOT `change_detection.scan_folder`: that hashes every
    file's full contents, the right cost once per real Sync and the wrong
    cost every `watch_interval_seconds`. Not recursive, matching
    `scan_folder`'s own "one workspace is one folder" rule (PRD F-01).

    Returns {} for a missing, unreadable, or momentarily gone folder
    rather than raising -- a disconnected drive or a folder mid-delete
    must not stop the OTHER workspaces from being polled (see
    `poll_once`), and an empty snapshot naturally produces no `ready`
    files this poll, retried automatically next time the folder is back.

    A single file that cannot be stat'd (permission denied, or deleted in
    the gap between `iterdir` and `stat`) is skipped, not fatal, for the
    same reason: this module is a passive trigger, not the reporting
    layer -- `change_detection.scan_folder` is what tells the user about
    a specific bad file when a real Sync runs."""
    resolved = Path(folder)
    result: Snapshot = {}
    try:
        entries = list(resolved.iterdir())
    except OSError:
        return result
    for entry in entries:
        try:
            if not entry.is_file() or not is_supported(entry):
                continue
            stat = entry.stat()
        except OSError:
            continue
        result[entry.name] = (stat.st_size, stat.st_mtime_ns)
    return result


@dataclass
class _WorkspaceWatchState:
    """One workspace's memory between polls.

    `baseline` is "the last (size, mtime) this module already acted on or
    found already present at first sight" -- the value a file must move
    AWAY FROM to count as new-or-changed. `last_poll` is simply the
    previous poll's snapshot, compared against the current one to decide
    stability. `initialized` is False for exactly one poll per
    workspace: the first, which seeds both fields from whatever is on
    disk right then instead of comparing against nothing."""

    baseline: Snapshot = field(default_factory=dict)
    last_poll: Snapshot = field(default_factory=dict)
    initialized: bool = False


@dataclass
class WatcherState:
    """Every workspace's `_WorkspaceWatchState`, carried across calls to
    `poll_once`. A plain object rather than module globals so a test can
    build a fresh one per case and the real daemon thread owns exactly
    one for its whole life (mirrors `app.Runtime` being a value rather
    than globals, for the same reason)."""

    per_workspace: dict[str, _WorkspaceWatchState] = field(default_factory=dict)


def _poll_workspace(
    ws_state: _WorkspaceWatchState,
    workspace: workspaces.Workspace,
    *,
    snapshot: Callable[[str], Snapshot],
    trigger: Callable[[str], Any],
) -> None:
    """One workspace's share of one poll. Raises only for a `trigger`
    failure other than `sync.SyncInProgressError` (a deleted workspace,
    an unexpected error) -- `poll_once` catches that per workspace so one
    bad workspace never stops the rest from being watched this round."""
    current = snapshot(workspace.folder_path)

    if not ws_state.initialized:
        # First sighting: whatever is already in the folder is "already
        # there", not "new" -- see the module docstring.
        ws_state.baseline = dict(current)
        ws_state.last_poll = dict(current)
        ws_state.initialized = True
        return

    ready = {
        name
        for name, value in current.items()
        if value == ws_state.last_poll.get(name) and value != ws_state.baseline.get(name)
    }
    # WAIT FOR THE WHOLE BATCH. Sync reads the entire folder, not just the
    # ready files, so starting it while ANOTHER supported file is still
    # arriving (a batch copy, one file done and the next mid-copy) would
    # convert that second file half-written -- a Failed row the user sees,
    # then a second ingestion once it finishes. Any file that is new or
    # changed since the last poll holds the trigger back one more round.
    settling = any(value != ws_state.last_poll.get(name) for name, value in current.items())
    # Recorded BEFORE the trigger, and unconditionally: next poll's
    # stability check needs to know what THIS poll saw regardless of
    # whether a Sync was started from it.
    ws_state.last_poll = dict(current)
    if not ready or settling:
        return

    try:
        trigger(workspace.id)
    except sync.SyncInProgressError:
        # THE PENDING CHANGE IS NOT LOST: `baseline` is left untouched, so
        # `ready` computes true again next poll (the file is still stable,
        # still unequal to the old baseline) and the trigger is retried.
        logger.info(
            "watcher: sync already running for workspace %s; will retry next poll",
            workspace.id,
        )
        return

    # THE EXACTLY-ONCE LINE. Only the files that were actually ready --
    # not every file this poll saw -- move into the baseline, so a file
    # still being written elsewhere in the same folder is untouched and
    # stays eligible once IT stabilizes.
    ws_state.baseline.update({name: current[name] for name in ready})


def poll_once(
    state: WatcherState,
    *,
    list_workspaces: Callable[[], Iterable[workspaces.Workspace]],
    trigger: Callable[[str], Any],
    snapshot: Callable[[str], Snapshot] = snapshot_folder,
) -> None:
    """One full poll cycle: every workspace, one snapshot each, one
    trigger call at most each. Never raises -- a broken workspace or a
    listing failure is logged and the rest of the round still runs,
    mirroring `change_detection`/`sync`'s own "one bad file costs one
    row, everything else finishes" rule one level up, at the workspace
    grain."""
    try:
        active = list(list_workspaces())
    except Exception:  # noqa: BLE001 -- one listing failure must not kill the watcher
        logger.exception("watcher: could not list workspaces; skipping this poll")
        return

    seen_ids = set()
    for workspace in active:
        seen_ids.add(workspace.id)
        ws_state = state.per_workspace.setdefault(workspace.id, _WorkspaceWatchState())
        try:
            _poll_workspace(ws_state, workspace, snapshot=snapshot, trigger=trigger)
        except Exception:  # noqa: BLE001 -- one workspace's failure must not stop the rest
            logger.exception("watcher: poll failed for workspace %s", workspace.id)

    # Drop state for a workspace that no longer exists (deleted since the
    # last poll) so a long-running server's memory does not grow forever.
    for stale_id in set(state.per_workspace) - seen_ids:
        del state.per_workspace[stale_id]


def _registered_workspaces(db_path: str | Path | None) -> list[workspaces.Workspace]:
    """Every workspace in the registry, or none while the registry does not
    exist yet. `app.main()` starts this thread BEFORE uvicorn runs the
    lifespan that creates `sanad.db`, so on a fresh install the first poll
    can land a moment early. Found by a real first boot, which logged a full
    traceback for it; "no registry yet" is "nothing to watch yet", not an
    error."""
    try:
        return workspaces.list_workspaces(db_path=db_path)
    except RegistryNotFoundError:
        return []


class WatcherThread(threading.Thread):
    """The real background poller. Started only by `start_if_enabled`,
    which is in turn called only from `app.main()` -- never from a test
    importing this module, and never in evidence-only mode (see there)."""

    def __init__(
        self,
        *,
        interval_seconds: float,
        db_path: str | Path | None = None,
        trigger: Callable[[str], Any],
        list_workspaces: Callable[[], Iterable[workspaces.Workspace]] | None = None,
        snapshot: Callable[[str], Snapshot] = snapshot_folder,
    ) -> None:
        super().__init__(daemon=True, name="sanad-watcher")
        self._interval = interval_seconds
        self._trigger = trigger
        self._list_workspaces = list_workspaces or (lambda: _registered_workspaces(db_path))
        self._snapshot = snapshot
        self._stop_event = threading.Event()
        self._state = WatcherState()

    def run(self) -> None:  # pragma: no cover -- exercised via start()/stop() in tests
        logger.info("watcher: started, polling every %.1fs", self._interval)
        while not self._stop_event.is_set():
            poll_once(
                self._state,
                list_workspaces=self._list_workspaces,
                trigger=self._trigger,
                snapshot=self._snapshot,
            )
            self._stop_event.wait(self._interval)
        logger.info("watcher: stopped")

    def stop(self, *, timeout: float = 5.0) -> None:
        """Signal the loop to end and wait, but only up to `timeout`.

        A BOUNDED join, not an unbounded one: server shutdown must not
        hang forever behind one poll that is itself stuck (a workspace
        folder on a dead network share, say)."""
        self._stop_event.set()
        self.join(timeout=timeout)


def start_if_enabled(
    settings: Settings,
    *,
    db_path: str | Path | None,
    trigger: Callable[[str], Any],
) -> WatcherThread | None:
    """The one decision point for whether the real server starts the
    watcher at all. Returns None, starting nothing, unless both guards
    below pass -- `app.main()` calls this once and either gets a thread
    to keep for shutdown or nothing further to do.

    `settings` and `trigger` are taken as PARAMETERS rather than read
    globally (`config.get_settings()`, `app.Runtime.start_sync`) so a
    test can supply either without the module-import aliasing trap
    `tests/integration/test_evidence_only_mode.py` documents: two modules
    that each do `from config import get_settings` hold two different
    names, and patching one leaves the other reading the real settings.

    GUARD ORDER MATTERS. `evidence_only` is checked FIRST and returns
    before anything else runs, `watch_folders` included -- this must
    never spend a thread, a folder poll, or (once a question is ever
    asked) the embedding model on a container too small to hold it, even
    if an operator also left `watch_folders` on. `Runtime.start_sync`
    raising `sync.EvidenceOnlyError` is not a substitute for this: it
    would still leave a thread running that snapshots every workspace
    forever and fails every trigger it ever makes."""
    if settings.evidence_only:
        logger.info("watcher: not started (evidence_only mode)")
        return None
    if not settings.watch_folders:
        return None
    thread = WatcherThread(
        interval_seconds=settings.watch_interval_seconds,
        db_path=db_path,
        trigger=trigger,
    )
    thread.start()
    return thread
