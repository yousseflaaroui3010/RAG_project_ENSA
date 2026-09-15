"""S6 saved chat history business rules (law 09-08).

Sits above db/repo.py exactly as workspaces.py and sync.py do: this module
owns the retention POLICY -- what a non-positive `chat_history_retention_days`
means, when a stored row counts as expired, and how a cutoff timestamp is
computed -- and calls the plain CRUD functions in db/repo.py to do the
actual reads and writes. db/repo.py's own module docstring says it carries
no business logic; a cold review found four chat-history functions there
had grown exactly that (retention_days branches, cutoff arithmetic, an
expiry decision, all inline in the SQL layer). This module is the fix.

Concurrency is NOT this module's job. The per-person lock and the
"is this still the live conversation?" check that stop a save from
resurrecting a concurrent delete (app.py Runtime) are in-process state;
this module has none and is safe to call from any thread as long as the
caller serializes its own writes the way Runtime does.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from db import repo


def _cutoff(retention_days: int) -> str:
    """Rows with `updated_at` at or before this are expired.

    `retention_days == 0` (config.py's "keep nothing between restarts"
    switch) is folded into "everything up to right now" rather than
    special-cased: a real row's `updated_at` can never be later than the
    instant this runs, so a cutoff of "now" deletes every row that
    exists -- exactly what 0 means -- through the SAME single
    time-based primitive (`db.repo.delete_chat_history_older_than`) a
    positive window uses, rather than a second "delete everything"
    primitive that could drift out of step with this one."""
    days = max(retention_days, 0)
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def save(
    *,
    user_id: str,
    workspace_id: str,
    payload: str,
    retention_days: int,
    db_path: str | Path | None = None,
) -> None:
    """Persist one person's whole transcript for one workspace.

    `retention_days == 0` means nothing survives a restart: a save then
    DELETES any existing row for this key instead of writing one, so the
    setting is provably "stores nothing" rather than "stores it, just
    briefly"."""
    with repo.session(db_path) as conn:
        if retention_days <= 0:
            repo.delete_chat_history(conn, user_id=user_id, workspace_id=workspace_id)
            return
        repo.upsert_chat_history(
            conn,
            user_id=user_id,
            workspace_id=workspace_id,
            payload=payload,
            updated_at=repo.utc_now(),
        )


def load(
    *,
    user_id: str,
    workspace_id: str,
    retention_days: int,
    db_path: str | Path | None = None,
) -> str | None:
    """This person's stored payload for this workspace, or None.

    `retention_days == 0` never even queries storage -- nothing is meant
    to survive a restart, so there is nothing to check an age against.
    A row found OLDER than the retention window is expired: deleted
    here, on read, rather than merely ignored, so an old transcript
    nobody has swept yet can never come back into memory just because it
    was asked for before the next start-up sweep runs."""
    if retention_days <= 0:
        return None
    with repo.session(db_path) as conn:
        row = repo.get_chat_history(conn, user_id=user_id, workspace_id=workspace_id)
        if row is None:
            return None
        if row["updated_at"] <= _cutoff(retention_days):
            repo.delete_chat_history(conn, user_id=user_id, workspace_id=workspace_id)
            return None
        return row["payload"]


def delete(*, user_id: str, workspace_id: str, db_path: str | Path | None = None) -> None:
    """Drop the stored row for just this one (person, workspace) pair.
    Used by "New conversation", and by an admin revoking a person's
    access to one workspace (that stored transcript quotes passages they
    should no longer hold)."""
    with repo.session(db_path) as conn:
        repo.delete_chat_history(conn, user_id=user_id, workspace_id=workspace_id)


def delete_for_user(*, user_id: str, db_path: str | Path | None = None) -> int:
    """Every stored conversation belonging to one person, across every
    workspace -- law 09-08's "Delete my saved history" and admin
    "sign out everywhere" both call this. Returns the row count deleted."""
    with repo.session(db_path) as conn:
        return repo.delete_chat_history_for_user(conn, user_id=user_id)


def sweep_expired(*, retention_days: int, db_path: str | Path | None = None) -> int:
    """Every row past the retention window, gone (app.py start-up sweep).
    `retention_days == 0` clears the table outright, through the same
    cutoff-based primitive a positive window uses (see `_cutoff`)."""
    with repo.session(db_path) as conn:
        return repo.delete_chat_history_older_than(conn, cutoff=_cutoff(retention_days))
