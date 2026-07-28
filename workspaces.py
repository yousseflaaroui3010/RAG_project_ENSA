"""Sanad workspace business rules (ST-11).

Sits above db/repo.py: this module owns the domain rules (duplicate-name
rejection, rename no-op, not-found handling, legal_flag typing) and calls
the thin SQL functions in db/repo.py to do the actual reads/writes. No
inline SQL here (.claude/rules/backend.md).

Single module, not a package: five verbs (create, rename, delete, list,
get) plus a legal-flag toggle over one table is not enough surface to
justify package-splitting yet (see docs/build/DECISIONS.md). Revisit if
ST-12+ adds enough workspace-adjacent logic to warrant sub-modules.

PRD F-01 (docs/phase2/Sanad_PRD_v1.0.md):
  - every workspace-scoped read must stay scoped to that workspace id.
  - listing with no workspaces returns cleanly (empty list, no exception).
  - deleting a workspace removes derived rows only; source files on disk
    are untouched (enforced by db.repo.delete_workspace's cascade).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from config import get_settings
from db import repo

# The exact sqlite3 error text for a UNIQUE violation on workspace.name,
# per db/schema.sql's `name TEXT NOT NULL UNIQUE`. Used to tell a genuine
# duplicate-name collision apart from any other IntegrityError (NOT NULL,
# a future FK, etc.) that also happens to be a sqlite3.IntegrityError.
_NAME_UNIQUE_VIOLATION = "UNIQUE constraint failed: workspace.name"


class WorkspaceError(Exception):
    """Base class for workspace domain errors. Callers should catch this
    (or a subclass) instead of sqlite3.IntegrityError, which is an
    implementation detail of the SQLite-backed repo layer."""


class WorkspaceNotFoundError(WorkspaceError):
    def __init__(self, workspace_id: str):
        self.workspace_id = workspace_id
        super().__init__(f"workspace not found: {workspace_id!r}")


class DuplicateWorkspaceNameError(WorkspaceError):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"workspace name already in use: {name!r}")


class InvalidWorkspaceNameError(WorkspaceError):
    """Raised when a workspace name violates the length bounds in
    docs/phase2/openapi.yaml (WorkspaceCreate/WorkspaceUpdate `name`:
    minLength 1, maxLength 100), sourced from config.py. A route maps
    this to HTTP 422."""

    def __init__(self, name: str):
        self.name = name
        settings = get_settings()
        super().__init__(
            "workspace name must be between "
            f"{settings.workspace_name_min_length} and "
            f"{settings.workspace_name_max_length} characters: {name!r}"
        )


def _validate_name(name: str) -> None:
    settings = get_settings()
    if not (settings.workspace_name_min_length <= len(name) <= settings.workspace_name_max_length):
        raise InvalidWorkspaceNameError(name)


@dataclass(frozen=True)
class Workspace:
    """Domain view of a workspace row. legal_flag is a real bool here;
    the 0/1 INTEGER storage detail (db/schema.sql) never leaks past
    db/repo.py."""

    id: str
    name: str
    folder_path: str
    legal_flag: bool
    created_at: str


def _from_row(row: sqlite3.Row) -> Workspace:
    return Workspace(
        id=row["id"],
        name=row["name"],
        folder_path=row["folder_path"],
        legal_flag=bool(row["legal_flag"]),
        created_at=row["created_at"],
    )


def create_workspace(
    *,
    name: str,
    folder_path: str,
    legal_flag: bool = False,
    db_path: str | Path | None = None,
) -> Workspace:
    """Create a workspace. Raises InvalidWorkspaceNameError if `name` is
    outside the contract's length bounds, or DuplicateWorkspaceNameError
    if `name` is already taken, instead of letting sqlite3.IntegrityError
    escape (only a UNIQUE violation on workspace.name is translated; any
    other constraint violation re-raises as-is)."""
    _validate_name(name)
    with repo.session(db_path) as conn:
        try:
            ws_id = repo.create_workspace(
                conn, name=name, folder_path=folder_path, legal_flag=legal_flag
            )
        except sqlite3.IntegrityError as exc:
            if _NAME_UNIQUE_VIOLATION not in str(exc):
                raise
            raise DuplicateWorkspaceNameError(name) from exc
        row = repo.get_workspace(conn, ws_id)
    return _from_row(row)


def rename_workspace(
    *, workspace_id: str, new_name: str, db_path: str | Path | None = None
) -> Workspace:
    """Rename a workspace. Renaming to the workspace's own current name
    is a no-op (returns the unchanged workspace, no write). Raises
    InvalidWorkspaceNameError if `new_name` is outside the contract's
    length bounds. Renaming to a name already used by another workspace
    raises DuplicateWorkspaceNameError rather than a raw IntegrityError
    (only a UNIQUE violation on workspace.name is translated; any other
    constraint violation re-raises as-is)."""
    _validate_name(new_name)
    with repo.session(db_path) as conn:
        row = repo.get_workspace(conn, workspace_id)
        if row is None:
            raise WorkspaceNotFoundError(workspace_id)
        if row["name"] == new_name:
            return _from_row(row)
        try:
            repo.update_workspace_name(conn, workspace_id, new_name)
        except sqlite3.IntegrityError as exc:
            if _NAME_UNIQUE_VIOLATION not in str(exc):
                raise
            raise DuplicateWorkspaceNameError(new_name) from exc
        row = repo.get_workspace(conn, workspace_id)
    return _from_row(row)


def delete_workspace(*, workspace_id: str, db_path: str | Path | None = None) -> None:
    """Delete a workspace and its derived rows (db.repo.delete_workspace
    cascade). Source files on disk are never touched (PRD F-01 #3).
    Raises WorkspaceNotFoundError if the id does not exist."""
    with repo.session(db_path) as conn:
        row = repo.get_workspace(conn, workspace_id)
        if row is None:
            raise WorkspaceNotFoundError(workspace_id)
        repo.delete_workspace(conn, workspace_id)


def list_workspaces(*, db_path: str | Path | None = None) -> list[Workspace]:
    """List every workspace, ordered by name. Empty list (no exception)
    when none exist, so a caller (ST-28 UI) can render an empty state
    (PRD F-01 #2)."""
    with repo.session(db_path) as conn:
        rows = repo.list_workspaces(conn)
    return [_from_row(row) for row in rows]


def get_workspace(*, workspace_id: str, db_path: str | Path | None = None) -> Workspace:
    """Fetch one workspace by id. Raises WorkspaceNotFoundError if it
    does not exist."""
    with repo.session(db_path) as conn:
        row = repo.get_workspace(conn, workspace_id)
    if row is None:
        raise WorkspaceNotFoundError(workspace_id)
    return _from_row(row)


def set_legal_flag(
    *, workspace_id: str, legal_flag: bool, db_path: str | Path | None = None
) -> Workspace:
    """Set the legal-content flag (F-09 disclaimer). Raises
    WorkspaceNotFoundError if the workspace does not exist. Idempotent:
    setting the same value twice is a harmless no-op write."""
    with repo.session(db_path) as conn:
        row = repo.get_workspace(conn, workspace_id)
        if row is None:
            raise WorkspaceNotFoundError(workspace_id)
        repo.update_workspace_legal_flag(conn, workspace_id, legal_flag)
        row = repo.get_workspace(conn, workspace_id)
    return _from_row(row)
