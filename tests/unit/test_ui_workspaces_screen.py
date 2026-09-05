"""ui/workspaces_screen.py: the S2 view-model helpers (ST-28), unit-level
and off the real database -- `file_rows` only ever calls `item["..."]`, so
a plain dict stands in for a `sqlite3.Row` here the same way a fake stands
in for the chat model elsewhere on this project."""

from __future__ import annotations

from sync import SyncResult
from ui.workspaces_screen import (
    FileRow,
    WorkspaceScreenState,
    file_rows,
    screen_state,
    sort_rows,
)


def _item(file_name: str, result: str, reason: str | None = None) -> dict:
    return {"file_name": file_name, "result": result, "reason": reason}


def test_no_workspaces_is_the_empty_state():
    assert screen_state(workspace_count=0) is WorkspaceScreenState.NO_WORKSPACES


def test_any_workspace_at_all_is_the_list_state():
    assert screen_state(workspace_count=1) is WorkspaceScreenState.LIST
    assert screen_state(workspace_count=9) is WorkspaceScreenState.LIST


def test_every_one_of_the_six_sync_statuses_maps_to_a_distinct_role_and_shape():
    """UX spec 3.5's own table, name for name. Six statuses, six pairs, and
    no two may share both a role and a shape or the "shape plus label plus
    colour, any one removable" property (3.5) is broken for that pair."""
    items = [
        _item("added.txt", "added"),
        _item("changed.txt", "changed"),
        _item("unchanged.txt", "unchanged"),
        _item("failed.txt", "failed", "could not be indexed"),
        _item("removed.txt", "removed", "no longer in the workspace folder"),
        _item("skipped.txt", "skipped", "unsupported file type"),
    ]
    rows = file_rows(folder_path="/does/not/exist", items=items)
    assert [row.result for row in rows] == list(SyncResult)
    pairs = {(row.role, row.shape) for row in rows}
    assert len(pairs) == 6, f"two statuses share a role+shape pair: {pairs}"
    # Reason is "" (never None) for the three clean outcomes, and carries
    # text for the three UX spec 7.2 requires it for.
    by_name = {row.file_name: row for row in rows}
    assert by_name["added.txt"].reason == ""
    assert by_name["changed.txt"].reason == ""
    assert by_name["unchanged.txt"].reason == ""
    assert by_name["failed.txt"].reason == "could not be indexed"
    assert by_name["removed.txt"].reason == "no longer in the workspace folder"
    assert by_name["skipped.txt"].reason == "unsupported file type"


def test_file_type_comes_from_the_extension_alone():
    """A Removed file may already be gone from disk (that is WHY it is
    Removed) and a file that failed before conversion may never have had a
    document row -- the type column must still print for both, so it
    cannot depend on either."""
    rows = file_rows(
        folder_path="/does/not/exist",
        items=[_item("report.PDF", "removed", "gone")],
    )
    assert rows[0].file_type == "PDF"


def test_file_type_falls_back_when_there_is_no_extension():
    rows = file_rows(folder_path="/does/not/exist", items=[_item("README", "unchanged")])
    assert rows[0].file_type == "—"


def test_size_is_read_live_off_disk(tmp_path):
    (tmp_path / "doc.txt").write_bytes(b"x" * 2048)
    rows = file_rows(folder_path=str(tmp_path), items=[_item("doc.txt", "added")])
    assert rows[0].size_bytes == 2048
    assert rows[0].size_label == "2.0 KB"


def test_a_missing_file_reports_an_absence_not_a_fabricated_zero(tmp_path):
    """A Removed row's file is gone by definition. Rendering "0 B" would be
    a fabricated fact about a file that no longer exists; "—" says so."""
    rows = file_rows(
        folder_path=str(tmp_path),
        items=[_item("gone.txt", "removed", "no longer in the workspace folder")],
    )
    assert rows[0].size_bytes is None
    assert rows[0].size_label == "—"


def _row(name: str, size: int | None) -> FileRow:
    return FileRow(
        file_name=name,
        file_type="TXT",
        size_bytes=size,
        size_label="" if size is None else f"{size} B",
        result=SyncResult.ADDED,
        role="positive",
        shape="filled-circle",
        status_label="Added",
        reason="",
    )


def test_sort_rows_by_name_is_case_insensitive():
    rows = [_row("banana.txt", 1), _row("Apple.txt", 2), _row("cherry.txt", 3)]
    ordered = sort_rows(rows, sort="name", direction="asc")
    assert [row.file_name for row in ordered] == ["Apple.txt", "banana.txt", "cherry.txt"]


def test_sort_rows_by_size_uses_the_real_byte_count_not_the_label():
    """The whole reason `size_bytes` travels separately from `size_label`:
    sorting the text "1.0 MB" against "500 KB" alphabetically would put the
    smaller-looking string first regardless of which file is bigger."""
    rows = [_row("a.txt", 1_500_000), _row("b.txt", 500_000)]
    ordered = sort_rows(rows, sort="size", direction="asc")
    assert [row.file_name for row in ordered] == ["b.txt", "a.txt"]


def test_sort_rows_direction_reverses():
    rows = [_row("a.txt", 1), _row("b.txt", 2)]
    assert [r.file_name for r in sort_rows(rows, sort="name", direction="desc")] == [
        "b.txt",
        "a.txt",
    ]


def test_sort_rows_is_a_no_op_for_an_unrecognised_column():
    """A stale or hand-edited `?sort=` must not raise or silently return an
    empty table -- it leaves the file-name reading order that
    `repo.list_sync_items` already gives, which is always legitimate on
    its own (UX spec 7.2)."""
    rows = [_row("b.txt", 2), _row("a.txt", 1)]
    assert sort_rows(rows, sort="not-a-real-column", direction="asc") == rows
    assert sort_rows(rows, sort=None, direction="asc") == rows
