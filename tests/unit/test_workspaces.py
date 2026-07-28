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
    repo.ensure_schema(path)
    return path


# --- F-01 #1: workspace scoping ---------------------------------------------


def test_get_and_list_never_cross_workspace_boundaries(db_path):
    hr = ws.create_workspace(name="HR", folder_path="/data/hr", db_path=db_path)
    manuals = ws.create_workspace(name="Manuals", folder_path="/data/manuals", db_path=db_path)

    fetched_hr = ws.get_workspace(workspace_id=hr.id, db_path=db_path)
    assert fetched_hr.id == hr.id
    assert fetched_hr.name == "HR"
    assert fetched_hr.id != manuals.id

    # This is the discriminating half: fetching the SECOND-inserted
    # workspace must return its own row, not the first one back again.
    # Without `WHERE id = ?` on the read path, this returns HR instead.
    fetched_manuals = ws.get_workspace(workspace_id=manuals.id, db_path=db_path)
    assert fetched_manuals.id == manuals.id
    assert fetched_manuals.name == "Manuals"
    assert fetched_manuals.id != hr.id

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
            "SELECT COUNT(*) FROM sync_item WHERE sync_run_id = ?", (run_id,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM eval_run WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM eval_result WHERE eval_run_id = ?", (eval_run_id,)
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
            "SELECT COUNT(*) FROM sync_item WHERE sync_run_id = ?", (run_id,)
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM eval_run WHERE workspace_id = ?", (workspace.id,)
        ).fetchone()[0] == 0
        assert conn.execute(
            "SELECT COUNT(*) FROM eval_result WHERE eval_run_id = ?", (eval_run_id,)
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


def test_non_name_constraint_violation_does_not_surface_as_duplicate_name_error(db_path):
    """folder_path is NOT NULL (db/schema.sql). That violation must not be
    mistranslated into DuplicateWorkspaceNameError; it is not a name
    collision at all."""
    with pytest.raises(sqlite3.IntegrityError):
        ws.create_workspace(name="HR", folder_path=None, db_path=db_path)  # type: ignore[arg-type]


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


# --- name length validation (docs/phase2/openapi.yaml WorkspaceCreate/Update) --


def test_create_workspace_rejects_empty_name(db_path):
    with pytest.raises(ws.InvalidWorkspaceNameError):
        ws.create_workspace(name="", folder_path="/data/hr", db_path=db_path)


def test_create_workspace_rejects_name_over_100_chars(db_path):
    with pytest.raises(ws.InvalidWorkspaceNameError):
        ws.create_workspace(name="x" * 101, folder_path="/data/hr", db_path=db_path)


def test_create_workspace_accepts_name_at_the_100_char_boundary(db_path):
    workspace = ws.create_workspace(name="x" * 100, folder_path="/data/hr", db_path=db_path)
    assert workspace.name == "x" * 100


def test_rename_workspace_rejects_empty_name(db_path):
    hr = ws.create_workspace(name="HR", folder_path="/data/hr", db_path=db_path)
    with pytest.raises(ws.InvalidWorkspaceNameError):
        ws.rename_workspace(workspace_id=hr.id, new_name="", db_path=db_path)


def test_rename_workspace_rejects_name_over_100_chars(db_path):
    hr = ws.create_workspace(name="HR", folder_path="/data/hr", db_path=db_path)
    with pytest.raises(ws.InvalidWorkspaceNameError):
        ws.rename_workspace(workspace_id=hr.id, new_name="x" * 101, db_path=db_path)


# --- reads never fabricate a registry (second re-review, item 1) ------------


def test_list_workspaces_raises_for_nonexistent_path_and_creates_nothing(tmp_path):
    """The exact repro from review: a mistyped/unmounted db_path must not
    read back as an empty list. It must fail loudly, and it must not
    create the directory tree or the db file as a side effect of trying."""
    bad_path = tmp_path / "typo" / "deep" / "x.db"

    with pytest.raises(repo.RegistryNotFoundError):
        ws.list_workspaces(db_path=bad_path)

    assert not bad_path.exists()
    assert not bad_path.parent.exists()


def test_get_workspace_raises_registry_not_found_for_nonexistent_path(tmp_path):
    bad_path = tmp_path / "typo2" / "x.db"

    with pytest.raises(repo.RegistryNotFoundError):
        ws.get_workspace(workspace_id="anything", db_path=bad_path)

    assert not bad_path.exists()


def test_write_against_a_fresh_path_bootstraps_and_succeeds(tmp_path):
    """No fixture pre-bootstrap here: db_path is a path that has never
    been touched. A write (create_workspace) must still succeed end to
    end, unlike a read against the same kind of fresh path."""
    fresh_path = tmp_path / "fresh" / "sanad.db"
    assert not fresh_path.exists()

    created = ws.create_workspace(name="Fresh", folder_path="/data/fresh", db_path=fresh_path)

    assert fresh_path.exists()
    assert created.name == "Fresh"


def test_read_after_write_bootstrap_returns_the_row(tmp_path):
    fresh_path = tmp_path / "fresh2" / "sanad.db"
    created = ws.create_workspace(name="Fresh2", folder_path="/data/fresh2", db_path=fresh_path)

    fetched = ws.get_workspace(workspace_id=created.id, db_path=fresh_path)

    assert fetched == created
    assert ws.list_workspaces(db_path=fresh_path) == [created]


# --- folder_path validation (docs/phase2/openapi.yaml WorkspaceCreate) -------


def test_create_workspace_rejects_empty_folder_path(db_path):
    with pytest.raises(ws.InvalidFolderPathError):
        ws.create_workspace(name="HR", folder_path="", db_path=db_path)


def test_create_workspace_rejects_whitespace_only_folder_path(db_path):
    with pytest.raises(ws.InvalidFolderPathError):
        ws.create_workspace(name="HR", folder_path="   ", db_path=db_path)


def test_create_workspace_rejects_whitespace_only_name(db_path):
    with pytest.raises(ws.InvalidWorkspaceNameError):
        ws.create_workspace(name="   ", folder_path="/data/hr", db_path=db_path)


def test_rename_workspace_rejects_whitespace_only_name(db_path):
    hr = ws.create_workspace(name="HR", folder_path="/data/hr", db_path=db_path)
    with pytest.raises(ws.InvalidWorkspaceNameError):
        ws.rename_workspace(workspace_id=hr.id, new_name="   ", db_path=db_path)


# --- default DB path bootstrap (ST-10 follow-up 4) ----------------------------


def test_create_and_get_workspace_bootstraps_schema_on_default_path(tmp_path, monkeypatch):
    """No explicit db_path: repo's connection path must bootstrap
    schema.sql itself. Before this fix, every verb failed with
    `sqlite3.OperationalError: no such table: workspace` on a fresh
    default path because nothing ever called init_db outside tests."""
    from config import get_settings

    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "default-path" / "sanad.db"))
    get_settings.cache_clear()
    try:
        created = ws.create_workspace(name="Ops", folder_path="/data/ops")
        fetched = ws.get_workspace(workspace_id=created.id)
        assert fetched.name == "Ops"
        assert ws.list_workspaces() == [fetched]
    finally:
        get_settings.cache_clear()
