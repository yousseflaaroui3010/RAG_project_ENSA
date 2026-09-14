"""Which state the S2 screen is in, and the small view-model pieces the
templates read (ST-28).

Mirrors `ui/screen.py`'s own reasoning for S1: decide state and shape data
here, in a module a test can call without an HTTP request, rather than in
`{% if %}` chains spread across a template.

UX spec 7.3 names three S2 states -- Empty, Loading, Error -- and this
module's job stops at handing the template the facts; app.py decides
which workspace is being looked at and this decides how to describe it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from config import get_settings
from sync import SyncResult


class WorkspaceScreenState(StrEnum):
    NO_WORKSPACES = "no_workspaces"
    LIST = "list"


def screen_state(*, workspace_count: int) -> WorkspaceScreenState:
    """The one value the template branches on for the top-level layout.

    UX spec 7.3: "No workspaces. Guided creation... the app's first-run
    screen and the only entry point when nothing exists." Everything else
    (which workspace is selected, whether its Sync is running) is a
    property of the LIST state, not a state of its own -- a workspace list
    with one busy row is still the list screen."""
    if workspace_count == 0:
        return WorkspaceScreenState.NO_WORKSPACES
    return WorkspaceScreenState.LIST


# UX spec 3.5's six-row table, name for name. `role` is a sanad.css status
# role and `shape` a status-dot shape class; neither is invented here, both
# are copied off the signed table rather than picked to look nice.
_STATUS_META: dict[SyncResult, tuple[str, str, str]] = {
    SyncResult.ADDED: ("positive", "filled-circle", "Added"),
    SyncResult.CHANGED: ("notice", "half-circle", "Changed"),
    SyncResult.UNCHANGED: ("neutral", "hollow-circle", "Unchanged"),
    SyncResult.FAILED: ("danger", "filled-square", "Failed"),
    SyncResult.REMOVED: ("neutral-strong", "dash", "Removed"),
    SyncResult.SKIPPED: ("warning", "hollow-square", "Skipped"),
}


@dataclass(frozen=True)
class FileRow:
    """One row of the FileTable component (UX spec 5, 7.2).

    Columns are name (mono), type, size, status, reason -- in that order,
    matching 7.2 exactly. `reason` is "" for Added/Changed/Unchanged,
    never None, so the template has one type to print rather than two."""

    file_name: str
    file_type: str
    size_bytes: int | None
    size_label: str
    result: SyncResult
    role: str
    shape: str
    status_label: str
    reason: str
    # S6: the file is on disk with a supported extension, so the table
    # offers Download and Remove for it. A Removed row, or a file that
    # vanished since the Sync, has nothing to download.
    downloadable: bool = False


def capacity_warning(*, folder_path: str, documents: list[Any]) -> str | None:
    """Return the signed soft-cap warning with measured counts, if needed."""
    try:
        file_count = sum(1 for path in Path(folder_path).iterdir() if path.is_file())
    except OSError:
        return None
    page_count = sum(
        row["page_count"] or 0 for row in documents if row["status"] != "removed"
    )
    settings = get_settings()
    if (
        file_count <= settings.workspace_soft_cap_files
        and page_count <= settings.workspace_soft_cap_pages
    ):
        return None
    return (
        f"This workspace has {file_count} files and {page_count} measured PDF pages, "
        f"above the recommended limit of {settings.workspace_soft_cap_files} files "
        f"or {settings.workspace_soft_cap_pages} pages. Split it into smaller "
        "workspace folders before the next large Sync."
    )


def _file_type(file_name: str) -> str:
    """The "type" column, from the name alone.

    No backend call is made and none is needed: `document.file_type` is
    only set for a file that made it as far as a document row, and this
    table also has to show a type for a file that failed before that
    point, or that was Removed and is already gone from disk. A file
    extension is available for every row this table can ever have."""
    suffix = Path(file_name).suffix.lstrip(".")
    return suffix.upper() if suffix else "—"


def _size(folder_path: str, file_name: str) -> tuple[int | None, str]:
    """The "size" column, read live off disk at render time: (bytes, label).

    Not stored anywhere -- db/schema.sql's `document` table has no
    byte-size column -- so this reads it rather than inventing one. A
    Removed file, or one that failed before conversion ever opened it, may
    already be gone; that is a real absence, `None`/"—", never a
    fabricated 0 B. The byte count travels alongside the label because
    sorting the LABEL as text would put "1.0 MB" before "500 KB"."""
    try:
        raw = (Path(folder_path) / file_name).stat().st_size
    except OSError:
        return None, "—"
    size = float(raw)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            label = f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            return raw, label
        size /= 1024
    return raw, f"{size:.1f} TB"


def file_rows(*, folder_path: str, items: list[sqlite3.Row]) -> list[FileRow]:
    """One FileRow per `sync_item` row, in the order `repo.list_sync_items`
    already gives them (by file_name -- UX spec 7.2's own reading order,
    "a human looking for a specific file"; `sort_rows` below re-orders on
    request, UX spec 7.4's "sortable headers")."""
    rows = []
    for item in items:
        result = SyncResult(item["result"])
        role, shape, label = _STATUS_META[result]
        size_bytes, size_label = _size(folder_path, item["file_name"])
        rows.append(
            FileRow(
                file_name=item["file_name"],
                file_type=_file_type(item["file_name"]),
                size_bytes=size_bytes,
                size_label=size_label,
                result=result,
                role=role,
                shape=shape,
                status_label=label,
                reason=item["reason"] or "",
                downloadable=(
                    size_bytes is not None
                    and Path(item["file_name"]).suffix.lstrip(".").lower()
                    in get_settings().supported_document_extensions
                ),
            )
        )
    return rows


# UX spec 7.4: "The file table is fully keyboard navigable by row and by
# cell, with sortable headers reachable and their sort state announced."
# Every key here is a real, stable column value -- `size_bytes` rather
# than the formatted label, for the reason `_size` already gives.
SORT_KEYS: dict[str, Any] = {
    "name": lambda row: row.file_name.lower(),
    "type": lambda row: row.file_type,
    "size": lambda row: row.size_bytes if row.size_bytes is not None else -1,
    "status": lambda row: row.status_label,
    "reason": lambda row: row.reason,
}


def sort_rows(rows: list[FileRow], *, sort: str | None, direction: str) -> list[FileRow]:
    """Re-order `rows` by one column, or return them unchanged.

    An unrecognised `sort` (a stale or hand-edited query string) is not an
    error -- it leaves the file-name order `list_sync_items` already gives,
    which is always a legitimate reading order on its own."""
    key = SORT_KEYS.get(sort or "")
    if key is None:
        return rows
    return sorted(rows, key=key, reverse=direction == "desc")
