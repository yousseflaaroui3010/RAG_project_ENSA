"""ST-10 exit gate: PRAGMA foreign_keys cascade, all six sync_item.result
values, unique file-per-workspace.

Reference: docs/phase2/Sanad_Architecture_v1.0.md sections 7.3 (reference
DDL) and 7.4 (SQLite deviations). Every connection here is opened through
db.repo.get_connection()/session() (never sqlite3.connect() directly) so
`PRAGMA foreign_keys = ON` is always in effect.
"""

from __future__ import annotations

import sqlite3

import pytest

from db import repo


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "sanad.db"
    connection = repo.get_connection(db_path)
    repo.init_db(connection)
    yield connection
    connection.close()


def _count(conn: sqlite3.Connection, table: str, **where) -> int:
    clause = " AND ".join(f"{k} = ?" for k in where)
    sql = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {clause}" if clause else "")
    return conn.execute(sql, tuple(where.values())).fetchone()[0]


# --- PRAGMA + cascade delete ------------------------------------------------


def test_foreign_keys_pragma_is_on(conn):
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_delete_workspace_cascades_to_every_derived_row(conn):
    ws_id = repo.create_workspace(conn, name="ws-cascade", folder_path="/tmp/ws")
    doc_id = repo.insert_document(
        conn,
        workspace_id=ws_id,
        file_name="a.pdf",
        file_type="pdf",
        content_hash="hash1",
        status="active",
    )
    run_id = repo.insert_sync_run(conn, workspace_id=ws_id)
    repo.insert_sync_item(
        conn, sync_run_id=run_id, document_id=doc_id, file_name="a.pdf", result="added"
    )
    eval_run_id = repo.insert_eval_run(conn, workspace_id=ws_id)
    repo.insert_eval_result(
        conn, eval_run_id=eval_run_id, question_id="q1", kind="in_scope", passed=True
    )
    conn.commit()

    repo.delete_workspace(conn, ws_id)
    conn.commit()

    assert _count(conn, "workspace", id=ws_id) == 0
    assert _count(conn, "document", workspace_id=ws_id) == 0
    assert _count(conn, "sync_run", workspace_id=ws_id) == 0
    assert _count(conn, "sync_item", sync_run_id=run_id) == 0
    assert _count(conn, "eval_run", workspace_id=ws_id) == 0
    assert _count(conn, "eval_result", eval_run_id=eval_run_id) == 0


def test_delete_document_sets_sync_item_document_id_null(conn):
    """Reference DDL line 314: sync_item.document_id is ON DELETE SET NULL,
    not CASCADE -- the sync history row must survive a document delete."""
    ws_id = repo.create_workspace(conn, name="ws-setnull", folder_path="/tmp/ws2")
    doc_id = repo.insert_document(
        conn,
        workspace_id=ws_id,
        file_name="b.pdf",
        file_type="pdf",
        content_hash="hash2",
        status="active",
    )
    run_id = repo.insert_sync_run(conn, workspace_id=ws_id)
    item_id = repo.insert_sync_item(
        conn, sync_run_id=run_id, document_id=doc_id, file_name="b.pdf", result="added"
    )
    conn.commit()

    conn.execute("DELETE FROM document WHERE id = ?", (doc_id,))
    conn.commit()

    row = conn.execute(
        "SELECT document_id FROM sync_item WHERE id = ?", (item_id,)
    ).fetchone()
    assert row["document_id"] is None


# --- sync_item.result: all six enum values + rejection ----------------------


ALL_SIX_RESULTS = ["added", "changed", "unchanged", "failed", "removed", "skipped"]


@pytest.mark.parametrize("result", ALL_SIX_RESULTS)
def test_sync_item_accepts_each_of_the_six_result_values(conn, result):
    ws_id = repo.create_workspace(conn, name=f"ws-{result}", folder_path="/tmp/ws3")
    run_id = repo.insert_sync_run(conn, workspace_id=ws_id)

    item_id = repo.insert_sync_item(
        conn, sync_run_id=run_id, file_name="c.pdf", result=result
    )
    conn.commit()

    row = conn.execute(
        "SELECT result FROM sync_item WHERE id = ?", (item_id,)
    ).fetchone()
    assert row["result"] == result


def test_sync_item_rejects_a_seventh_invalid_result_value(conn):
    ws_id = repo.create_workspace(conn, name="ws-invalid", folder_path="/tmp/ws4")
    run_id = repo.insert_sync_run(conn, workspace_id=ws_id)

    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_sync_item(
            conn, sync_run_id=run_id, file_name="d.pdf", result="not_a_real_status"
        )


# --- document UNIQUE(workspace_id, file_name) -------------------------------


def test_duplicate_file_name_rejected_within_same_workspace(conn):
    ws_id = repo.create_workspace(conn, name="ws-unique", folder_path="/tmp/ws5")
    repo.insert_document(
        conn,
        workspace_id=ws_id,
        file_name="dup.pdf",
        file_type="pdf",
        content_hash="hash-a",
        status="active",
    )
    conn.commit()

    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_document(
            conn,
            workspace_id=ws_id,
            file_name="dup.pdf",
            file_type="pdf",
            content_hash="hash-b",
            status="active",
        )


def test_same_file_name_allowed_across_different_workspaces(conn):
    ws1 = repo.create_workspace(conn, name="ws-a", folder_path="/tmp/ws6a")
    ws2 = repo.create_workspace(conn, name="ws-b", folder_path="/tmp/ws6b")

    repo.insert_document(
        conn,
        workspace_id=ws1,
        file_name="shared.pdf",
        file_type="pdf",
        content_hash="hash-a",
        status="active",
    )
    repo.insert_document(
        conn,
        workspace_id=ws2,
        file_name="shared.pdf",
        file_type="pdf",
        content_hash="hash-b",
        status="active",
    )
    conn.commit()

    assert _count(conn, "document", workspace_id=ws1, file_name="shared.pdf") == 1
    assert _count(conn, "document", workspace_id=ws2, file_name="shared.pdf") == 1
