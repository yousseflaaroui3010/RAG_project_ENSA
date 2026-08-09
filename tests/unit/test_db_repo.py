"""ST-10 exit gate: PRAGMA foreign_keys cascade, all six sync_item.result
values, unique file-per-workspace.

Reference: docs/phase2/Sanad_Architecture_v1.0.md sections 7.3 (reference
DDL) and 7.4 (SQLite deviations). Every connection here is opened through
db.repo.get_connection()/session() (never sqlite3.connect() directly) so
`PRAGMA foreign_keys = ON` is always in effect.
"""

from __future__ import annotations

import sqlite3
import time

import pytest

from config import get_settings
from db import repo


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    connection = repo.get_connection(db_path)
    yield connection
    connection.close()


# Table/column identifiers this test module is allowed to interpolate into
# SQL via `_count`. Whitelisted against db/schema.sql so no caller can ever
# splice an arbitrary identifier into a query string (.claude/rules/backend.md
# forbids f-string SQL, even test-only, call-site-literal instances).
_ALLOWED_TABLES = {"workspace", "document", "sync_run", "sync_item", "eval_run", "eval_result"}
_ALLOWED_COLUMNS = {"id", "workspace_id", "sync_run_id", "eval_run_id", "file_name"}


def _count(conn: sqlite3.Connection, table: str, **where) -> int:
    if table not in _ALLOWED_TABLES:
        raise ValueError(f"_count: table {table!r} is not whitelisted")
    for column in where:
        if column not in _ALLOWED_COLUMNS:
            raise ValueError(f"_count: column {column!r} is not whitelisted")
    clause = " AND ".join(f"{k} = ?" for k in where)
    sql = f"SELECT COUNT(*) FROM {table}" + (f" WHERE {clause}" if clause else "")
    return conn.execute(sql, tuple(where.values())).fetchone()[0]


# --- PRAGMA + cascade delete ------------------------------------------------


def test_foreign_keys_pragma_is_on(conn, tmp_path):
    """PRAGMA foreign_keys is a per-connection setting, not a database-level
    one -- it does not persist in the file. Assert it on the fixture
    connection AND on a second, independently opened connection to the same
    database file so the story's actual stated risk is locked in, not just
    the behavior of one shared connection object."""
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    second = repo.get_connection(tmp_path / "sanad.db")
    try:
        assert second.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        second.close()


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

    repo.delete_document(conn, doc_id)
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


# --- document.workspace_id FK enforcement ------------------------------------


def test_insert_document_rejects_a_bogus_workspace_id(conn):
    """Cascade delete (above) proves FK enforcement fires on the delete
    side. Nothing until now locked in the insert side: an orphan child
    row referencing a workspace that does not exist must be rejected."""
    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_document(
            conn,
            workspace_id="not-a-real-workspace-id",
            file_name="orphan.pdf",
            file_type="pdf",
            content_hash="hash-orphan",
            status="active",
        )


# --- get_connection / ensure_schema: reads never bootstrap -------------------


def test_get_connection_raises_and_creates_nothing_for_nonexistent_path(tmp_path):
    bad_path = tmp_path / "typo" / "deep" / "x.db"

    with pytest.raises(repo.RegistryNotFoundError):
        repo.get_connection(bad_path)

    assert not bad_path.exists()
    assert not bad_path.parent.exists()


def test_ensure_schema_bootstraps_a_fresh_path(tmp_path):
    fresh_path = tmp_path / "fresh" / "sanad.db"
    assert not fresh_path.exists()

    repo.ensure_schema(fresh_path)

    assert fresh_path.exists()
    conn = repo.get_connection(fresh_path)
    try:
        assert _count(conn, "workspace") == 0
    finally:
        conn.close()


# --- session() commit / rollback / close -------------------------------------


def test_session_commits_on_success_and_row_persists(tmp_path):
    """A successful `with repo.session(...)` block must commit, and that
    commit must be durable: reopening a fresh connection to the same file
    afterward must still see the row."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)

    with repo.session(db_path) as conn:
        repo.create_workspace(conn, name="ws-session-commit", folder_path="/tmp/ws-commit")

    reopened = repo.get_connection(db_path)
    try:
        row = reopened.execute(
            "SELECT COUNT(*) FROM workspace WHERE name = ?", ("ws-session-commit",)
        ).fetchone()
        assert row[0] == 1
    finally:
        reopened.close()


def test_session_rolls_back_everything_on_exception(tmp_path):
    """Regression proof for the init_db/session transaction bug (reviewer
    finding 1): a write made earlier in a `session()` block must NOT
    survive a later exception in the same block, even when `init_db` is
    called again partway through (a legal, idempotent call per its
    IF NOT EXISTS schema). Before the fix, `init_db`'s stray `commit()`
    silently finalized the earlier write, so it survived the rollback and
    this assertion failed. After the fix, `init_db` never commits, so the
    whole block rolls back together."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)

    with pytest.raises(RuntimeError):
        with repo.session(db_path) as conn:
            repo.create_workspace(conn, name="ws-session-rollback", folder_path="/tmp/ws-rb")
            repo.init_db(conn)  # reproduces the finding-1 bug if it regresses
            raise RuntimeError("simulated failure mid-session")

    reopened = repo.get_connection(db_path)
    try:
        row = reopened.execute(
            "SELECT COUNT(*) FROM workspace WHERE name = ?", ("ws-session-rollback",)
        ).fetchone()
        assert row[0] == 0
    finally:
        reopened.close()


# --- busy timeout (ST-12, BUILD-STATE data-layer follow-up 7) ----------------

# sqlite3.connect()'s own default when `timeout` is not passed. Named here so
# the two tests below can assert against the exact value they exist to keep
# the project OFF -- it is the fallback a dropped argument silently restores.
_SQLITE_DEFAULT_TIMEOUT_SECONDS = 5.0


def test_connection_timeout_is_taken_from_config_not_sqlite_default(tmp_path, monkeypatch):
    """`_connect_raw` must pass `timeout` through from config. sqlite3's own
    default is 5.0 seconds, which is too short once ST-17's sync writes while
    the UI reads; dropping the argument would silently restore that default,
    and nothing else in the suite would notice."""
    recorded: list[float | None] = []
    real_connect = sqlite3.connect

    def spy(*args, **kwargs):
        recorded.append(kwargs.get("timeout"))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(get_settings(), "sqlite_busy_timeout_seconds", 12.5)
    monkeypatch.setattr(sqlite3, "connect", spy)

    repo.ensure_schema(tmp_path / "sanad.db")

    assert recorded, "_connect_raw never called sqlite3.connect"
    assert all(t == 12.5 for t in recorded)


def test_writer_contention_waits_for_the_timeout_instead_of_failing_instantly(
    tmp_path, monkeypatch
):
    """The behaviour follow-up 7 actually asks for: a second writer must WAIT
    for the CONFIGURED timeout before giving up -- neither failing the moment
    it finds the database locked, nor falling back to sqlite3's own default.

    Both bounds are load-bearing, and the upper one is the subtle half. A
    lower bound alone is vacuous here: dropping the `timeout` argument gives
    sqlite3's 5.0 second default, which is LONGER than the value configured
    below, so "it waited at least 0.4s" would still pass while the config was
    being ignored entirely. Mutation-proven: with only the lower bound, the
    dropped-argument mutation stayed green. The ceiling sits ~5x under that
    5.0 second default, so it separates the two cases without being tight
    enough to flake on a loaded machine.

    Configured down to a fraction of a second so the test stays fast; the
    30 second production default would make this unrunnable."""
    timeout_seconds = 0.5
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    monkeypatch.setattr(get_settings(), "sqlite_busy_timeout_seconds", timeout_seconds)

    holder = repo.get_connection(db_path)
    holder.execute("BEGIN EXCLUSIVE")
    try:
        waiter = repo.get_connection(db_path)
        try:
            started = time.monotonic()
            with pytest.raises(sqlite3.OperationalError, match="locked"):
                waiter.execute("BEGIN IMMEDIATE")
            waited = time.monotonic() - started
        finally:
            waiter.close()
    finally:
        holder.rollback()
        holder.close()

    # Floor: it blocked rather than returning immediately.
    assert waited >= timeout_seconds * 0.8, (
        f"second writer gave up after {waited:.3f}s with a "
        f"{timeout_seconds}s timeout configured -- it did not wait at all"
    )
    # Ceiling: it used OUR timeout, not sqlite3's 5.0 second default.
    assert waited < _SQLITE_DEFAULT_TIMEOUT_SECONDS / 2, (
        f"second writer waited {waited:.3f}s with a {timeout_seconds}s timeout "
        f"configured -- that is sqlite3's own default, so `timeout` is not "
        f"reaching sqlite3.connect()"
    )
