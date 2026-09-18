"""ST-10 exit gate: PRAGMA foreign_keys cascade, all six sync_item.result
values, unique file-per-workspace.

Reference: docs/phase2/Sanad_Architecture_v1.0.md sections 7.3 (reference
DDL) and 7.4 (SQLite deviations). Application-facing connections here are
opened through db.repo.get_connection()/session() so `PRAGMA foreign_keys =
ON` is always in effect. The migration fixture deliberately uses sqlite3
directly to create the exact database shape that predates the repository
migration.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime, timedelta

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
# splice an arbitrary identifier into a query string (the team backend rules
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


def test_ensure_schema_claims_the_writer_lock_before_migration_checks(
    tmp_path, monkeypatch
):
    statements: list[str] = []
    real_connect = repo._connect_raw

    def traced_connect(path):
        connection = real_connect(path)
        connection.set_trace_callback(statements.append)
        return connection

    monkeypatch.setattr(repo, "_connect_raw", traced_connect)
    repo.ensure_schema(tmp_path / "locked-migration.db")

    begin = next(i for i, sql in enumerate(statements) if "BEGIN IMMEDIATE" in sql)
    first_schema_write = next(
        i for i, sql in enumerate(statements) if "CREATE TABLE" in sql
    )
    assert begin < first_schema_write


# --- incremental evaluation schema ------------------------------------------


def _create_old_eval_database(db_path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            CREATE TABLE workspace (
              id          TEXT PRIMARY KEY,
              name        TEXT NOT NULL UNIQUE,
              folder_path TEXT NOT NULL,
              legal_flag  INTEGER NOT NULL DEFAULT 0,
              created_at  TEXT NOT NULL
            );
            CREATE TABLE eval_run (
              id            TEXT PRIMARY KEY,
              workspace_id  TEXT NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
              run_at        TEXT NOT NULL,
              groundedness  REAL,
              relevancy     REAL,
              refusal_pass  INTEGER NOT NULL DEFAULT 0,
              refusal_total INTEGER NOT NULL DEFAULT 0,
              passed        INTEGER NOT NULL DEFAULT 0,
              report_path   TEXT
            );
            CREATE TABLE eval_result (
              id           TEXT PRIMARY KEY,
              eval_run_id  TEXT NOT NULL REFERENCES eval_run(id) ON DELETE CASCADE,
              question_id  TEXT NOT NULL,
              kind         TEXT NOT NULL CHECK (kind IN ('in_scope', 'out_of_scope')),
              groundedness REAL,
              relevancy    REAL,
              passed       INTEGER NOT NULL
            );
            """
        )
        connection.execute(
            "INSERT INTO workspace (id, name, folder_path, created_at) VALUES (?, ?, ?, ?)",
            ("old-workspace", "Old workspace", "/old", "2026-09-01T00:00:00+00:00"),
        )
        connection.executemany(
            "INSERT INTO eval_run "
            "(id, workspace_id, run_at, groundedness, relevancy, refusal_pass, "
            "refusal_total, passed, report_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "old-run-two-results",
                    "old-workspace",
                    "2026-09-01T01:00:00+00:00",
                    0.75,
                    0.8,
                    1,
                    2,
                    0,
                    "/reports/old-two.json",
                ),
                (
                    "old-run-no-results",
                    "old-workspace",
                    "2026-09-01T02:00:00+00:00",
                    1.0,
                    1.0,
                    2,
                    2,
                    1,
                    "/reports/old-zero.json",
                ),
            ],
        )
        connection.executemany(
            "INSERT INTO eval_result "
            "(id, eval_run_id, question_id, kind, groundedness, relevancy, passed) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("old-result-1", "old-run-two-results", "q1", "in_scope", 1.0, 0.9, 1),
                ("old-result-2", "old-run-two-results", "q2", "out_of_scope", None, None, 1),
            ],
        )
        connection.commit()
    finally:
        connection.close()


def test_old_eval_schema_migrates_rows_and_is_idempotent(tmp_path):
    db_path = tmp_path / "old-sanad.db"
    _create_old_eval_database(db_path)

    with repo.session(db_path):
        pass

    connection = repo.get_connection(db_path)
    try:
        runs_after_first_migration = connection.execute(
            "SELECT id, status, question_total, groundedness, report_path "
            "FROM eval_run ORDER BY id"
        ).fetchall()
        results_after_first_migration = connection.execute(
            "SELECT id, eval_run_id, question_id, answer_kind, answer_text, "
            "sources_present, error FROM eval_result ORDER BY id"
        ).fetchall()
    finally:
        connection.close()

    assert [tuple(row) for row in runs_after_first_migration] == [
        ("old-run-no-results", "completed", 0, 1.0, "/reports/old-zero.json"),
        ("old-run-two-results", "completed", 2, 0.75, "/reports/old-two.json"),
    ]
    assert [tuple(row) for row in results_after_first_migration] == [
        ("old-result-1", "old-run-two-results", "q1", None, None, None, None),
        ("old-result-2", "old-run-two-results", "q2", None, None, None, None),
    ]

    repo.ensure_schema(db_path)
    repo.ensure_schema(db_path)

    connection = repo.get_connection(db_path)
    try:
        runs_after_repeated_migration = connection.execute(
            "SELECT id, status, question_total, groundedness, report_path "
            "FROM eval_run ORDER BY id"
        ).fetchall()
        results_after_repeated_migration = connection.execute(
            "SELECT id, eval_run_id, question_id, answer_kind, answer_text, "
            "sources_present, error FROM eval_result ORDER BY id"
        ).fetchall()
    finally:
        connection.close()

    assert [tuple(row) for row in runs_after_repeated_migration] == [
        tuple(row) for row in runs_after_first_migration
    ]
    assert [tuple(row) for row in results_after_repeated_migration] == [
        tuple(row) for row in results_after_first_migration
    ]


def test_eval_run_rejects_invalid_status(conn):
    workspace_id = repo.create_workspace(
        conn, name="eval-invalid-status", folder_path="/tmp/eval-invalid"
    )

    with pytest.raises(sqlite3.IntegrityError):
        repo.insert_eval_run(conn, workspace_id=workspace_id, status="failed")


def test_incremental_eval_fields_persist(conn):
    workspace_id = repo.create_workspace(
        conn, name="eval-rich-fields", folder_path="/tmp/eval-rich"
    )
    run_id = repo.insert_eval_run(
        conn,
        workspace_id=workspace_id,
        status="running",
        question_total=60,
        failed_question_number=7,
        failed_question_id="g-in-007",
        error="provider stopped",
    )
    result_id = repo.insert_eval_result(
        conn,
        eval_run_id=run_id,
        question_id="g-in-007",
        kind="in_scope",
        passed=False,
        answer_kind="answer",
        answer_text="Saved answer text",
        sources_present=True,
        error="judge unavailable",
    )

    run = conn.execute("SELECT * FROM eval_run WHERE id = ?", (run_id,)).fetchone()
    result = conn.execute("SELECT * FROM eval_result WHERE id = ?", (result_id,)).fetchone()

    assert run["status"] == "running"
    assert run["question_total"] == 60
    assert run["failed_question_number"] == 7
    assert run["failed_question_id"] == "g-in-007"
    assert run["error"] == "provider stopped"
    assert result["answer_kind"] == "answer"
    assert result["answer_text"] == "Saved answer text"
    assert result["sources_present"] == 1
    assert result["error"] == "judge unavailable"


def test_update_eval_run_preserves_start_fields(conn):
    workspace_id = repo.create_workspace(
        conn, name="eval-update", folder_path="/tmp/eval-update"
    )
    run_id = repo.insert_eval_run(
        conn,
        workspace_id=workspace_id,
        status="running",
        question_total=60,
        report_path="/reports/incremental.json",
    )

    repo.update_eval_run(
        conn,
        run_id,
        status="partial",
        groundedness=0.8,
        relevancy=0.9,
        refusal_pass=18,
        refusal_total=20,
        passed=False,
        failed_question_number=23,
        failed_question_id="g-in-023",
        error="provider timeout",
    )

    row = conn.execute("SELECT * FROM eval_run WHERE id = ?", (run_id,)).fetchone()
    assert row["status"] == "partial"
    assert row["groundedness"] == 0.8
    assert row["relevancy"] == 0.9
    assert row["refusal_pass"] == 18
    assert row["refusal_total"] == 20
    assert row["passed"] == 0
    assert row["failed_question_number"] == 23
    assert row["failed_question_id"] == "g-in-023"
    assert row["error"] == "provider timeout"
    assert row["report_path"] == "/reports/incremental.json"
    assert row["question_total"] == 60


def test_eval_run_progress_counts_only_the_requested_run(conn):
    workspace_id = repo.create_workspace(
        conn, name="eval-progress", folder_path="/tmp/eval-progress"
    )
    first_run_id = repo.insert_eval_run(conn, workspace_id=workspace_id)
    second_run_id = repo.insert_eval_run(conn, workspace_id=workspace_id)
    for question_id in ("q1", "q2"):
        repo.insert_eval_result(
            conn,
            eval_run_id=first_run_id,
            question_id=question_id,
            kind="in_scope",
            passed=True,
        )
    repo.insert_eval_result(
        conn,
        eval_run_id=second_run_id,
        question_id="q3",
        kind="in_scope",
        passed=True,
    )

    assert repo.eval_run_progress(conn, first_run_id) == 2
    assert repo.eval_run_progress(conn, second_run_id) == 1
    assert repo.eval_run_progress(conn, "missing-run") == 0


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


# --- S6 saved chat history, ST-53 conversations: plain CRUD, no policy --------
#
# db/repo.py carries no retention rule (a cold review moved it to
# chat_history.py -- see tests/unit/test_chat_history.py for the policy:
# what 0 means, when a row is expired, how a cutoff is computed, what a
# title is). These tests exercise the plain operations, that each one
# matches the OWNER as well as the id, and the one-time migration from the
# pre-ST-53 `chat_history` table.


def _conversation(conn, conversation_id, ws_id, *, user="local", payload="p", title=None,
                  updated_at=None):
    repo.upsert_conversation(
        conn,
        conversation_id=conversation_id,
        user_id=user,
        workspace_id=ws_id,
        title=title,
        payload=payload,
        updated_at=updated_at or repo.utc_now(),
    )
    conn.commit()


def test_upsert_then_get_conversation_round_trips(conn):
    ws_id = repo.create_workspace(conn, name="ws-history", folder_path="/tmp/wsh")
    conn.commit()

    _conversation(conn, "c1", ws_id, payload='{"messages": []}', title="Q?")

    row = repo.get_conversation(conn, conversation_id="c1", user_id="local")
    assert (row["payload"], row["title"], row["workspace_id"]) == ('{"messages": []}', "Q?", ws_id)
    assert row["created_at"] == row["updated_at"]


def test_a_second_upsert_updates_payload_and_time_but_never_title_or_start(conn):
    """Every settled answer upserts. The second must update the one row --
    not collide on the key -- and must leave the title (a rename must
    survive) and `created_at` (when it began) alone."""
    ws_id = repo.create_workspace(conn, name="ws-upsert", folder_path="/tmp/wsu")
    conn.commit()
    _conversation(conn, "c1", ws_id, payload="first", title="original",
                  updated_at="2026-01-01T00:00:00+00:00")

    _conversation(conn, "c1", ws_id, payload="second", title="ignored",
                  updated_at="2026-01-02T00:00:00+00:00")

    row = repo.get_conversation(conn, conversation_id="c1", user_id="local")
    assert row["payload"] == "second"
    assert row["title"] == "original"
    assert row["created_at"] == "2026-01-01T00:00:00+00:00"
    assert row["updated_at"] == "2026-01-02T00:00:00+00:00"
    assert conn.execute("SELECT COUNT(*) FROM conversation").fetchone()[0] == 1


def test_get_conversation_matches_the_owner_not_just_the_id(conn):
    ws_id = repo.create_workspace(conn, name="ws-owner", folder_path="/tmp/wso")
    conn.commit()
    _conversation(conn, "c1", ws_id, user="alice")

    assert repo.get_conversation(conn, conversation_id="c1", user_id="bob") is None
    assert repo.get_conversation(conn, conversation_id="unknown", user_id="alice") is None
    assert repo.get_conversation(conn, conversation_id="c1", user_id="alice") is not None


def test_rename_and_delete_touch_only_the_owners_row(conn):
    ws_id = repo.create_workspace(conn, name="ws-own-ops", folder_path="/tmp/wsoo")
    conn.commit()
    _conversation(conn, "c1", ws_id, user="alice", title="alice's")

    assert repo.rename_conversation(conn, conversation_id="c1", user_id="bob", title="x") == 0
    assert repo.delete_conversation(conn, conversation_id="c1", user_id="bob") == 0
    conn.commit()
    assert repo.get_conversation(conn, conversation_id="c1", user_id="alice")["title"] == "alice's"

    assert repo.rename_conversation(conn, conversation_id="c1", user_id="alice", title="new") == 1
    assert repo.delete_conversation(conn, conversation_id="c1", user_id="alice") == 1


def test_delete_conversations_in_workspace_and_for_user(conn):
    ws1 = repo.create_workspace(conn, name="ws-del-a", folder_path="/tmp/wsda")
    ws2 = repo.create_workspace(conn, name="ws-del-b", folder_path="/tmp/wsdb")
    conn.commit()
    for conversation_id, ws_id, user in [
        ("a1", ws1, "alice"), ("a2", ws1, "alice"), ("a3", ws2, "alice"), ("b1", ws1, "bob"),
    ]:
        _conversation(conn, conversation_id, ws_id, user=user)

    assert repo.delete_conversations_in_workspace(conn, user_id="alice", workspace_id=ws1) == 2
    conn.commit()
    left = {row[0] for row in conn.execute("SELECT id FROM conversation")}
    assert left == {"a3", "b1"}

    assert repo.delete_conversations_for_user(conn, user_id="alice") == 1
    conn.commit()
    assert {row[0] for row in conn.execute("SELECT id FROM conversation")} == {"b1"}


def test_list_conversations_is_newest_first_and_carries_no_payload(conn):
    ws_id = repo.create_workspace(conn, name="ws-list", folder_path="/tmp/wsl")
    conn.commit()
    _conversation(conn, "old", ws_id, updated_at="2026-01-01T00:00:00+00:00")
    _conversation(conn, "new", ws_id, updated_at="2026-01-03T00:00:00+00:00")
    _conversation(conn, "mid", ws_id, updated_at="2026-01-02T00:00:00+00:00")

    rows = repo.list_conversations(
        conn, user_id="local", workspace_id=ws_id, newer_than="2026-01-01T12:00:00+00:00"
    )

    assert [row["id"] for row in rows] == ["new", "mid"]
    assert "payload" not in rows[0].keys()


def test_delete_conversations_older_than_removes_rows_at_or_before_the_cutoff(conn):
    """A plain timestamp comparison, no notion of 'retention days' here --
    that arithmetic belongs to chat_history.py, which computes the cutoff
    this function is handed."""
    ws_id = repo.create_workspace(conn, name="ws-cutoff", folder_path="/tmp/wsco")
    conn.commit()
    cutoff = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    older = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    _conversation(conn, "old", ws_id, updated_at=older)
    _conversation(conn, "edge", ws_id, updated_at=cutoff)
    _conversation(conn, "new", ws_id, updated_at=datetime.now(UTC).isoformat())

    removed = repo.delete_conversations_older_than(conn, cutoff=cutoff)
    conn.commit()

    assert removed == 2
    assert {row[0] for row in conn.execute("SELECT id FROM conversation")} == {"new"}


def test_deleting_a_workspace_cascades_to_its_stored_conversations(conn):
    ws_id = repo.create_workspace(conn, name="ws-cascade-history", folder_path="/tmp/wsch")
    conn.commit()
    _conversation(conn, "c1", ws_id, payload="gone soon")
    _conversation(conn, "c2", ws_id, payload="gone too")

    repo.delete_workspace(conn, ws_id)
    conn.commit()

    assert conn.execute(
        "SELECT COUNT(*) FROM conversation WHERE workspace_id = ?", (ws_id,)
    ).fetchone()[0] == 0


# --- the one-time move from `chat_history` (ST-53) ---------------------------

_OLD_TABLE = (
    "CREATE TABLE chat_history (user_id TEXT NOT NULL, workspace_id TEXT NOT NULL "
    "REFERENCES workspace(id) ON DELETE CASCADE, payload TEXT NOT NULL, "
    "updated_at TEXT NOT NULL, PRIMARY KEY (user_id, workspace_id))"
)


def _pre_st53_database(tmp_path, rows):
    """A database as a pre-ST-53 server left it: today's schema plus the
    old `chat_history` table holding `rows` (user, workspace name,
    payload, updated_at). Returns the path and {workspace name: id}."""
    db_path = tmp_path / "old.db"
    repo.ensure_schema(db_path)
    connection = repo.get_connection(db_path)
    try:
        names = {name for _, name, _, _ in rows}
        ids = {
            name: repo.create_workspace(connection, name=name, folder_path=f"/tmp/{name}")
            for name in sorted(names)
        }
        connection.execute(_OLD_TABLE)
        for user, name, payload, updated_at in rows:
            connection.execute(
                "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
                "VALUES (?, ?, ?, ?)",
                (user, ids[name], payload, updated_at),
            )
        connection.commit()
    finally:
        connection.close()
    return db_path, ids


def _payload(*questions):
    return (
        '{"v": 1, "messages": ['
        + ", ".join(f'{{"kind": "user", "text": "{q}"}}' for q in questions)
        + "]}"
    )


def _tables(db_path):
    connection = repo.get_connection(db_path)
    try:
        return {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )}
    finally:
        connection.close()


def test_the_migration_copies_every_old_row_then_drops_the_old_table(tmp_path):
    db_path, ids = _pre_st53_database(tmp_path, [
        (
            "alice", "hr", _payload("Durée du préavis ?", "Et pour un cadre ?"),
            "2026-09-01T10:00:00+00:00",
        ),
        ("bob", "hr", '{"v": 1, "messages": []}', "2026-09-02T10:00:00+00:00"),
        ("alice", "legal", "not json at all", "2026-09-03T10:00:00+00:00"),
    ])

    repo.ensure_schema(db_path)

    assert "chat_history" not in _tables(db_path)
    connection = repo.get_connection(db_path)
    try:
        rows = {
            (row["user_id"], row["workspace_id"]): row
            for row in connection.execute("SELECT * FROM conversation")
        }
    finally:
        connection.close()
    assert set(rows) == {("alice", ids["hr"]), ("bob", ids["hr"]), ("alice", ids["legal"])}
    moved = rows[("alice", ids["hr"])]
    assert all(row["title"] is None for row in rows.values()), (
        "titles are a chat_history.py rule; the migration copies them as NULL"
    )
    assert moved["payload"] == _payload("Durée du préavis ?", "Et pour un cadre ?")
    assert moved["created_at"] == moved["updated_at"] == "2026-09-01T10:00:00+00:00"
    assert rows[("alice", ids["legal"])]["payload"] == "not json at all"
    assert len({row["id"] for row in rows.values()}) == 3, "every row gets its own id"


def test_a_migrated_conversation_gets_its_title_at_its_next_save_and_keeps_it(conn):
    """Migrated rows start untitled; the next save fills the title once,
    and a later save (or one after a rename) never replaces it."""
    ws_id = repo.create_workspace(conn, name="ws-migrated", folder_path="/tmp/wsm")
    conn.commit()
    _conversation(conn, "c1", ws_id, title=None)

    _conversation(conn, "c1", ws_id, title="first question")
    _conversation(conn, "c1", ws_id, title="something else")

    assert repo.get_conversation(conn, conversation_id="c1", user_id="local")["title"] == (
        "first question"
    )


def test_an_old_row_for_a_deleted_workspace_is_skipped_not_fatal(tmp_path):
    """A row naming a workspace that no longer exists (possible only with
    foreign keys once off) must not stop start-up -- ensure_schema runs
    before every write, so raising here would stop every write."""
    db_path, ids = _pre_st53_database(tmp_path, [
        ("alice", "hr", _payload("kept"), "2026-09-01T10:00:00+00:00"),
    ])
    connection = repo.get_connection(db_path)
    try:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('alice', 'gone-workspace', 'orphan', '2026-09-01T10:00:00+00:00')"
        )
        connection.commit()
    finally:
        connection.close()

    repo.ensure_schema(db_path)

    assert "chat_history" not in _tables(db_path)
    connection = repo.get_connection(db_path)
    try:
        moved = [tuple(row) for row in connection.execute(
            "SELECT workspace_id, payload FROM conversation"
        )]
    finally:
        connection.close()
    assert moved == [(ids["hr"], _payload("kept"))]


def test_the_migration_runs_once_and_later_start_ups_change_nothing(tmp_path):
    db_path, _ = _pre_st53_database(tmp_path, [
        ("alice", "hr", _payload("Q?"), "2026-09-01T10:00:00+00:00"),
    ])
    repo.ensure_schema(db_path)
    connection = repo.get_connection(db_path)
    try:
        first = [tuple(row) for row in connection.execute("SELECT * FROM conversation")]
    finally:
        connection.close()

    repo.ensure_schema(db_path)

    connection = repo.get_connection(db_path)
    try:
        assert [tuple(row) for row in connection.execute("SELECT * FROM conversation")] == first
    finally:
        connection.close()


def test_a_migration_that_fails_part_way_keeps_the_old_table_whole(tmp_path, monkeypatch):
    """Copy, check and drop are ONE transaction: if anything fails, the
    old table is still there with every row, and nothing half-copied is
    left in the new one. Forced here by giving two rows the same id."""
    db_path, _ = _pre_st53_database(tmp_path, [
        ("alice", "hr", _payload("one"), "2026-09-01T10:00:00+00:00"),
        ("bob", "hr", _payload("two"), "2026-09-02T10:00:00+00:00"),
    ])
    monkeypatch.setattr(repo, "new_id", lambda: "same-id-twice")

    with pytest.raises(sqlite3.IntegrityError):
        repo.ensure_schema(db_path)

    assert "chat_history" in _tables(db_path)
    connection = repo.get_connection(db_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM conversation").fetchone()[0] == 0
    finally:
        connection.close()
