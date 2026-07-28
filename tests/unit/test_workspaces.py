"""ST-11 exit gate: workspace create/rename/delete/list/get + legal_flag,
interpreted against the three signed F-01 acceptance criteria
(docs/phase2/Sanad_PRD_v1.0.md) at module level per the ST-11 task card:

  1. workspace-scoped queries never return another workspace's rows.
  2. listing with no workspaces returns cleanly (empty, no exception).
  3. deleting a workspace removes derived rows only; source files on disk
     are untouched.
"""

from __future__ import annotations

import sqlite3

import pytest

import workspaces as ws
from db import repo


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "sanad.db"
    conn = repo.get_connection(path)
    repo.init_db(conn)
    conn.commit()
    conn.close()
    return path


# --- F-01 #1: workspace scoping ---------------------------------------------


def test_get_and_list_never_cross_workspace_boundaries(db_path):
    hr = ws.create_workspace(name="HR", folder_path="/data/hr", db_path=db_path)
    manuals = ws.create_workspace(name="Manuals", folder_path="/data/manuals", db_path=db_path)

    fetched_hr = ws.get_workspace(workspace_id=hr.id, db_path=db_path)
    assert fetched_hr.id == hr.id
    assert fetched_hr.name == "HR"
    assert fetched_hr.id != manuals.id

    all_ws = ws.list_workspaces(db_path=db_path)
    assert {w.id for w in all_ws} == {hr.id, manuals.id}


def test_get_workspace_raises_not_found_for_unknown_id(db_path):
    with pytest.raises(ws.WorkspaceNotFoundError):
        ws.get_workspace(workspace_id="does-not-exist", db_path=db_path)


# --- F-01 #2: empty listing --------------------------------------------------


def test_list_workspaces_returns_empty_list_when_none_exist(db_path):
    assert ws.list_workspaces(db_path=db_path) == []


# --- F-01 #3: derived-data-only delete ---------------------------------------


def test_delete_workspace_removes_derived_rows_but_leaves_disk_files_untouched(
    db_path, tmp_path
):
    folder = tmp_path / "hr-files"
    folder.mkdir()
    doc_path = folder / "policy.pdf"
    original_bytes = b"%PDF-1.4 fake policy content"
    doc_path.write_bytes(original_bytes)

    workspace = ws.create_workspace(name="HR", folder_path=str(folder), db_path=db_path)

    conn = repo.get_connection(db_path)
    try:
        doc_id = repo.insert_document(
            conn,
            workspace_id=workspace.id,
            file_name="policy.pdf",
            file_type="pdf",
            content_hash="hash1",
            status="active",
        )
        run_id = repo.insert_sync_run(conn, workspace_id=workspace.id)
        repo.insert_sync_item(
            conn, sync_run_id=run_id, document_id=doc_id, file_name="policy.pdf", result="added"
        )
        eval_run_id = repo.insert_eval_run(conn, workspace_id=workspace.id)
        repo.insert_eval_result(
            conn, eval_run_id=eval_run_id, question_id="q1", kind="in_scope", passed=True
        )
        conn.commit()

        assert conn.execute(
            "SELECT COUNT(*) FROM document WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM sync_run WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM eval_run WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0] == 1
    finally:
        conn.close()

    ws.delete_workspace(workspace_id=workspace.id, db_path=db_path)

    conn = repo.get_connection(db_path)
    try:
        assert conn.execute(
            "SELECT COUNT(*) FROM workspace WHERE id = ?", (workspace.id,)
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM document WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM sync_run WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM eval_run WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0] == 0
    finally:
        conn.close()

    assert doc_path.exists()
    assert doc_path.read_bytes() == original_bytes


def test_delete_workspace_raises_not_found_for_unknown_id(db_path):
    with pytest.raises(ws.WorkspaceNotFoundError):
        ws.delete_workspace(workspace_id="does-not-exist", db_path=db_path)


# --- duplicate / rename rules -------------------------------------------------


def test_create_workspace_rejects_duplicate_name_with_domain_error(db_path):
    ws.create_workspace(name="HR", folder_path="/data/hr", db_path=db_path)

    with pytest.raises(ws.DuplicateWorkspaceNameError):
        ws.create_workspace(name="HR", folder_path="/data/hr2", db_path=db_path)


def test_create_workspace_duplicate_never_leaks_raw_integrity_error(db_path):
    ws.create_workspace(name="HR", folder_path="/data/hr", db_path=db_path)

    try:
        ws.create_workspace(name="HR", folder_path="/data/hr2", db_path=db_path)
    except sqlite3.IntegrityError:
        pytest.fail("raw sqlite3.IntegrityError leaked past the workspaces module")
    except ws.DuplicateWorkspaceNameError:
        pass


def test_rename_workspace_rejects_existing_name_with_domain_error(db_path):
    hr = ws.create_workspace(name="HR", folder_path="/data/hr", db_path=db_path)
    ws.create_workspace(name="Manuals", folder_path="/data/manuals", db_path=db_path)

    with pytest.raises(ws.DuplicateWorkspaceNameError):
        ws.rename_workspace(workspace_id=hr.id, new_name="Manuals", db_path=db_path)


def test_rename_workspace_to_its_own_current_name_is_a_no_op(db_path):
    hr = ws.create_workspace(name="HR", folder_path="/data/hr", db_path=db_path)

    result = ws.rename_workspace(workspace_id=hr.id, new_name="HR", db_path=db_path)

    assert result.id == hr.id
    assert result.name == "HR"
    assert ws.list_workspaces(db_path=db_path) == [result]


def test_rename_workspace_raises_not_found_for_unknown_id(db_path):
    with pytest.raises(ws.WorkspaceNotFoundError):
        ws.rename_workspace(workspace_id="does-not-exist", new_name="X", db_path=db_path)


# --- legal_flag round-trip ------------------------------------------------------


def test_legal_flag_round_trips_as_a_real_bool_not_an_integer(db_path):
    hr = ws.create_workspace(
        name="HR", folder_path="/data/hr", legal_flag=True, db_path=db_path
    )
    assert hr.legal_flag is True

    toggled = ws.set_legal_flag(workspace_id=hr.id, legal_flag=False, db_path=db_path)
    assert toggled.legal_flag is False
    assert type(toggled.legal_flag) is bool

    fetched = ws.get_workspace(workspace_id=hr.id, db_path=db_path)
    assert fetched.legal_flag is False


def test_set_legal_flag_raises_not_found_for_unknown_id(db_path):
    with pytest.raises(ws.WorkspaceNotFoundError):
        ws.set_legal_flag(workspace_id="does-not-exist", legal_flag=True, db_path=db_path)
