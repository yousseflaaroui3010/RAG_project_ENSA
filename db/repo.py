"""Sanad SQLite data access layer.

Hard technical rule (docs/phase2/ENGINEERING-RULES.md, architecture section 7.4):
every SQLite connection is opened with `PRAGMA foreign_keys = ON`, and
that happens in exactly one place -- `_connect_raw` below. No other
module may call `sqlite3.connect()` directly; go through
`get_connection()` / `session()` instead, so cascade / SET NULL rules
from db/schema.sql always apply.

Scope (ST-10): connection management, schema bootstrap, and the
minimal insert/delete functions needed to exercise the schema's
constraints (cascade delete, sync_item.result CHECK, document
unique-per-workspace). Business logic (hashing, diffing, sync
orchestration) belongs to later stories (ST-11, ST-12) built on top of
this module.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from config import get_settings

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_EVAL_RUN_COLUMN_MIGRATIONS = (
    (
        "status",
        "ALTER TABLE eval_run ADD COLUMN status TEXT NOT NULL DEFAULT 'completed' "
        "CHECK (status IN ('running', 'completed', 'partial'))",
    ),
    (
        "question_total",
        "ALTER TABLE eval_run ADD COLUMN question_total INTEGER NOT NULL DEFAULT 0",
    ),
    (
        "failed_question_number",
        "ALTER TABLE eval_run ADD COLUMN failed_question_number INTEGER",
    ),
    (
        "failed_question_id",
        "ALTER TABLE eval_run ADD COLUMN failed_question_id TEXT",
    ),
    ("error", "ALTER TABLE eval_run ADD COLUMN error TEXT"),
)

_EVAL_RESULT_COLUMN_MIGRATIONS = (
    ("answer_kind", "ALTER TABLE eval_result ADD COLUMN answer_kind TEXT"),
    ("answer_text", "ALTER TABLE eval_result ADD COLUMN answer_text TEXT"),
    (
        "sources_present",
        "ALTER TABLE eval_result ADD COLUMN sources_present INTEGER",
    ),
    ("error", "ALTER TABLE eval_result ADD COLUMN error TEXT"),
)


def new_id() -> str:
    """App-generated identifier for the `uuid` columns (arch section 7.4:
    SQLite has no gen_random_uuid(), the application generates it)."""
    return str(uuid.uuid4())


def utc_now() -> str:
    """App-set ISO-8601 UTC timestamp for the `timestamptz` columns
    (arch section 7.4: SQLite has no now(), the application sets it)."""
    return datetime.now(UTC).isoformat()


class RegistryNotFoundError(Exception):
    """Raised by `get_connection` when `db_path` does not exist on disk.

    Reads must never create the registry (a mistyped `SQLITE_DB_PATH` or
    an unmounted folder must not be indistinguishable from a genuinely
    fresh, empty registry -- PRD F-01 criterion 2 depends on
    `list_workspaces()` returning `[]` meaning "the registry exists and
    is empty", never "I could not find it"). Only `ensure_schema` /
    `session` (write paths) may create the file; this error is what a
    read gets instead."""

    def __init__(self, db_path: str | Path):
        self.db_path = db_path
        super().__init__(f"registry database does not exist: {db_path!r}")


def _connect_raw(db_path: str | Path) -> sqlite3.Connection:
    """The single call site for `sqlite3.connect()` in the codebase.
    Every connection gets `PRAGMA foreign_keys = ON` before use. Nothing
    else: no `mkdir`, no schema bootstrap. Bootstrapping is an explicit,
    write-path-only step -- see `ensure_schema` -- so that merely
    connecting (as every read does) can never fabricate a directory tree
    or an empty database file for a path that was never meant to exist.

    Also sets an explicit busy `timeout`. sqlite3's default is 5.0
    seconds, which is not enough once ST-17's sync writes concurrently
    with a UI read: writer contention would surface as a bare "database
    is locked" after a 5 second stall. The value lives in config.py
    (`sqlite_busy_timeout_seconds`), never as a literal here."""
    conn = sqlite3.connect(
        str(db_path), timeout=get_settings().sqlite_busy_timeout_seconds
    )
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection to the Sanad registry DB for READS. Defaults to
    `config.get_settings().sqlite_db_path` -- never hardcode the path a
    second time.

    Never bootstraps. Raises `RegistryNotFoundError` if `db_path` does
    not exist, instead of letting `sqlite3.connect()` silently create an
    empty file. Write paths do not call this directly; they go through
    `session()`, which calls `ensure_schema()` first."""
    path = db_path if db_path is not None else get_settings().sqlite_db_path
    resolved = Path(path)
    if not resolved.exists():
        raise RegistryNotFoundError(resolved)
    return _connect_raw(resolved)


def ensure_schema(db_path: str | Path | None = None) -> None:
    """Bootstrap the registry: create the parent directory if needed and
    apply db/schema.sql. Idempotent (every statement is `CREATE TABLE IF
    NOT EXISTS`) -- safe to call on every write. This is the only place
    in the codebase that may create the db file or its parent directory;
    reads (`get_connection`) deliberately never do either."""
    path = db_path if db_path is not None else get_settings().sqlite_db_path
    resolved = Path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    conn = _connect_raw(resolved)
    try:
        # Claim the writer lock before inspecting old columns. Otherwise two
        # processes can both observe a missing column and race to add it.
        conn.execute("BEGIN IMMEDIATE")
        init_db(conn)
        conn.commit()
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    """Apply db/schema.sql and additive migrations to `conn`. Safe to call
    repeatedly: every CREATE TABLE uses IF NOT EXISTS and migrations inspect
    the existing columns before adding anything.

    Does NOT commit, and deliberately does not use
    `sqlite3.Connection.executescript()`. `executescript()` is
    documented to issue an implicit COMMIT of any pending transaction
    before it runs its script -- verified directly against this
    schema.sql: even with the trailing `conn.commit()` removed,
    `executescript()` alone still force-committed a write made earlier
    in the same transaction. That is unacceptable for a function meant
    to run inside `session()`, where a later exception must be able to
    roll back everything, including writes made before `init_db` was
    called. So each DDL statement (comment lines stripped, split on
    `;`) is executed individually via `conn.execute()`, which carries no
    implicit commit. `init_db` therefore never commits or rolls back;
    ownership of the connection's transaction stays entirely with the
    caller (typically `session()`).
    """
    ddl = _SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [line for line in ddl.splitlines() if not line.strip().startswith("--")]
    for statement in "\n".join(statements).split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)
    _migrate_incremental_evaluation(conn)
    _migrate_chat_history_to_conversation(conn)


def _migrate_incremental_evaluation(conn: sqlite3.Connection) -> None:
    """Add incremental evaluation columns to databases created before S3."""
    eval_run_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(eval_run)").fetchall()
    }
    question_total_added = "question_total" not in eval_run_columns
    for column, statement in _EVAL_RUN_COLUMN_MIGRATIONS:
        if column not in eval_run_columns:
            conn.execute(statement)

    eval_result_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(eval_result)").fetchall()
    }
    for column, statement in _EVAL_RESULT_COLUMN_MIGRATIONS:
        if column not in eval_result_columns:
            conn.execute(statement)

    if question_total_added:
        conn.execute(
            "UPDATE eval_run SET question_total = "
            "(SELECT COUNT(*) FROM eval_result WHERE eval_result.eval_run_id = eval_run.id)"
        )


@contextmanager
def session(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a connection for a WRITE, commit on success, roll back and
    re-raise on error, always close. Use for any multi-statement write so
    partial failures never leave the registry half-written.

    Calls `ensure_schema(db_path)` first, so a genuinely fresh install
    still works end to end with no manual bootstrap step. This is the
    write-path/read-path seam: `session()` bootstraps, `get_connection()`
    (used by pure reads) does not."""
    ensure_schema(db_path)
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# --- workspace ---------------------------------------------------------


def create_workspace(
    conn: sqlite3.Connection,
    *,
    name: str,
    folder_path: str,
    legal_flag: bool = False,
    id: str | None = None,
    created_at: str | None = None,
) -> str:
    ws_id = id or new_id()
    conn.execute(
        "INSERT INTO workspace (id, name, folder_path, legal_flag, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (ws_id, name, folder_path, int(legal_flag), created_at or utc_now()),
    )
    return ws_id


def delete_workspace(conn: sqlite3.Connection, workspace_id: str) -> None:
    """Delete a workspace. Cascades (per db/schema.sql, requires
    PRAGMA foreign_keys = ON) remove its document, sync_run, sync_item,
    eval_run and eval_result rows; source files on disk are untouched
    (PRD F-01)."""
    conn.execute("DELETE FROM workspace WHERE id = ?", (workspace_id,))


def get_workspace(conn: sqlite3.Connection, workspace_id: str) -> sqlite3.Row | None:
    """Raw row lookup by id, or None. Business rules (not-found handling,
    domain errors) belong to workspaces.py, not here."""
    return conn.execute(
        "SELECT * FROM workspace WHERE id = ?", (workspace_id,)
    ).fetchone()


def list_workspaces(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Raw row listing, ordered by name. Returns an empty list when no
    workspace exists (PRD F-01 criterion 2: the UI's empty state)."""
    return conn.execute("SELECT * FROM workspace ORDER BY name").fetchall()


def update_workspace_name(conn: sqlite3.Connection, workspace_id: str, name: str) -> None:
    """Raw UPDATE. `name` is UNIQUE (db/schema.sql); a collision raises
    sqlite3.IntegrityError for the caller to translate into a domain error."""
    conn.execute("UPDATE workspace SET name = ? WHERE id = ?", (name, workspace_id))


def update_workspace_legal_flag(
    conn: sqlite3.Connection, workspace_id: str, legal_flag: bool
) -> None:
    conn.execute(
        "UPDATE workspace SET legal_flag = ? WHERE id = ?",
        (int(legal_flag), workspace_id),
    )


# --- document ------------------------------------------------------------


def insert_document(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    file_name: str,
    file_type: str,
    content_hash: str,
    status: str,
    page_count: int | None = None,
    last_synced_at: str | None = None,
    id: str | None = None,
) -> str:
    doc_id = id or new_id()
    conn.execute(
        "INSERT INTO document "
        "(id, workspace_id, file_name, file_type, content_hash, page_count, status, "
        "last_synced_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            doc_id,
            workspace_id,
            file_name,
            file_type,
            content_hash,
            page_count,
            status,
            last_synced_at,
        ),
    )
    return doc_id


def list_documents(conn: sqlite3.Connection, workspace_id: str) -> list[sqlite3.Row]:
    """Every document row registered for one workspace, ordered by
    file_name. Scoped by workspace_id (PRD F-01: a workspace-scoped read
    never crosses into another workspace's rows). Returns [] for an
    unknown or empty workspace -- the caller decides whether that means
    "not found"; this layer holds no business rules."""
    return conn.execute(
        "SELECT * FROM document WHERE workspace_id = ? ORDER BY file_name",
        (workspace_id,),
    ).fetchall()


def delete_document(conn: sqlite3.Connection, document_id: str) -> None:
    """Delete one document row. Its sync_item history survives with
    `document_id` set to NULL (db/schema.sql: ON DELETE SET NULL, not
    CASCADE) -- a past sync report must never lose rows because the file
    was later removed from the folder."""
    conn.execute("DELETE FROM document WHERE id = ?", (document_id,))


def update_document(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    file_type: str,
    content_hash: str,
    status: str,
    page_count: int | None = None,
    last_synced_at: str | None = None,
) -> None:
    """Overwrite one document row's mutable columns after a sync.

    Every column a re-ingest can change is written, none is optional-by-
    omission. That is deliberate: `page_count` is legitimately None for a
    format that has no pages (DOCX, TXT, MD), so a "None means leave it
    alone" convention would make it impossible to move a row FROM a page
    count TO none -- a PDF replaced by a DOCX under the same file name
    would keep the PDF's page count forever.

    Exists because a file returning after removal is classified NEW yet
    already owns a registry row (change_detection.FileChange): inserting
    would violate UNIQUE (workspace_id, file_name)."""
    conn.execute(
        "UPDATE document SET file_type = ?, content_hash = ?, page_count = ?, "
        "status = ?, last_synced_at = ? WHERE id = ?",
        (file_type, content_hash, page_count, status, last_synced_at, document_id),
    )


# --- sync_run --------------------------------------------------------------


def insert_sync_run(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    started_at: str | None = None,
    finished_at: str | None = None,
    added: int = 0,
    changed: int = 0,
    unchanged: int = 0,
    failed: int = 0,
    removed: int = 0,
    skipped: int = 0,
    id: str | None = None,
) -> str:
    run_id = id or new_id()
    conn.execute(
        "INSERT INTO sync_run "
        "(id, workspace_id, started_at, finished_at, added, changed, unchanged, failed, "
        "removed, skipped) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            workspace_id,
            started_at or utc_now(),
            finished_at,
            added,
            changed,
            unchanged,
            failed,
            removed,
            skipped,
        ),
    )
    return run_id


def get_sync_run(conn: sqlite3.Connection, sync_run_id: str) -> sqlite3.Row | None:
    """One sync run by id, or None. Backs openapi.yaml `getSyncRun`; the
    `state` field there is derived from `finished_at` being NULL, not
    stored, so there is exactly one fact about whether a run is over."""
    return conn.execute(
        "SELECT * FROM sync_run WHERE id = ?", (sync_run_id,)
    ).fetchone()


def get_running_sync_run(
    conn: sqlite3.Connection, workspace_id: str
) -> sqlite3.Row | None:
    """The unfinished run for this workspace, or None.

    A run is "running" exactly when `finished_at IS NULL`, which is the
    same rule openapi.yaml's `state: running` renders. This is what makes
    PRD section 11's "Second Sync triggered during a Sync -> blocked with
    a message" answerable, and it is scoped to one workspace on purpose:
    syncing HR must not block syncing the manuals."""
    return conn.execute(
        "SELECT * FROM sync_run WHERE workspace_id = ? AND finished_at IS NULL "
        "ORDER BY started_at LIMIT 1",
        (workspace_id,),
    ).fetchone()


def finish_sync_run(
    conn: sqlite3.Connection,
    *,
    sync_run_id: str,
    finished_at: str | None = None,
    added: int = 0,
    changed: int = 0,
    unchanged: int = 0,
    failed: int = 0,
    removed: int = 0,
    skipped: int = 0,
) -> None:
    """Stamp a run finished and write its six counts.

    Separate from `insert_sync_run` because the row is created BEFORE the
    folder is scanned -- that is what makes the in-progress window cover
    the whole run rather than only its tail -- and the counts are not
    known until it ends."""
    conn.execute(
        "UPDATE sync_run SET finished_at = ?, added = ?, changed = ?, unchanged = ?, "
        "failed = ?, removed = ?, skipped = ? WHERE id = ?",
        (
            finished_at or utc_now(),
            added,
            changed,
            unchanged,
            failed,
            removed,
            skipped,
            sync_run_id,
        ),
    )


# --- sync_item ---------------------------------------------------------------


def insert_sync_item(
    conn: sqlite3.Connection,
    *,
    sync_run_id: str,
    file_name: str,
    result: str,
    document_id: str | None = None,
    reason: str | None = None,
    id: str | None = None,
) -> str:
    item_id = id or new_id()
    conn.execute(
        "INSERT INTO sync_item (id, sync_run_id, document_id, file_name, result, reason) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (item_id, sync_run_id, document_id, file_name, result, reason),
    )
    return item_id


def list_sync_items(conn: sqlite3.Connection, sync_run_id: str) -> list[sqlite3.Row]:
    """Every per-file row of one sync run, ordered by file name.

    That order is the file table in UX spec section 7.2, not an arbitrary
    one: the report is read by a human looking for a specific file."""
    return conn.execute(
        "SELECT * FROM sync_item WHERE sync_run_id = ? ORDER BY file_name",
        (sync_run_id,),
    ).fetchall()


# --- eval_run ----------------------------------------------------------------


def insert_eval_run(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    run_at: str | None = None,
    status: str = "completed",
    question_total: int = 0,
    groundedness: float | None = None,
    relevancy: float | None = None,
    refusal_pass: int = 0,
    refusal_total: int = 0,
    passed: bool = False,
    report_path: str | None = None,
    failed_question_number: int | None = None,
    failed_question_id: str | None = None,
    error: str | None = None,
    id: str | None = None,
) -> str:
    run_id = id or new_id()
    conn.execute(
        "INSERT INTO eval_run "
        "(id, workspace_id, run_at, status, question_total, groundedness, relevancy, "
        "refusal_pass, refusal_total, passed, report_path, failed_question_number, "
        "failed_question_id, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            workspace_id,
            run_at or utc_now(),
            status,
            question_total,
            groundedness,
            relevancy,
            refusal_pass,
            refusal_total,
            int(passed),
            report_path,
            failed_question_number,
            failed_question_id,
            error,
        ),
    )
    return run_id


def update_eval_run(
    conn: sqlite3.Connection,
    eval_run_id: str,
    *,
    status: str,
    groundedness: float | None = None,
    relevancy: float | None = None,
    refusal_pass: int = 0,
    refusal_total: int = 0,
    passed: bool = False,
    failed_question_number: int | None = None,
    failed_question_id: str | None = None,
    error: str | None = None,
) -> None:
    """Write a run's final or partial outcome without changing its start fields."""
    conn.execute(
        "UPDATE eval_run SET status = ?, groundedness = ?, relevancy = ?, "
        "refusal_pass = ?, refusal_total = ?, passed = ?, failed_question_number = ?, "
        "failed_question_id = ?, error = ? WHERE id = ?",
        (
            status,
            groundedness,
            relevancy,
            refusal_pass,
            refusal_total,
            int(passed),
            failed_question_number,
            failed_question_id,
            error,
            eval_run_id,
        ),
    )


def eval_run_progress(conn: sqlite3.Connection, eval_run_id: str) -> int:
    """Return how many question results have been saved for one run."""
    row = conn.execute(
        "SELECT COUNT(*) FROM eval_result WHERE eval_run_id = ?", (eval_run_id,)
    ).fetchone()
    return row[0]


def list_sync_runs(conn: sqlite3.Connection, workspace_id: str) -> list[sqlite3.Row]:
    """Every sync run for one workspace, newest first."""
    return conn.execute(
        "SELECT * FROM sync_run WHERE workspace_id = ? ORDER BY started_at DESC",
        (workspace_id,),
    ).fetchall()


# --- eval_result -------------------------------------------------------------


def insert_eval_result(
    conn: sqlite3.Connection,
    *,
    eval_run_id: str,
    question_id: str,
    kind: str,
    passed: bool,
    groundedness: float | None = None,
    relevancy: float | None = None,
    answer_kind: str | None = None,
    answer_text: str | None = None,
    sources_present: bool | None = None,
    error: str | None = None,
    id: str | None = None,
) -> str:
    result_id = id or new_id()
    conn.execute(
        "INSERT INTO eval_result "
        "(id, eval_run_id, question_id, kind, groundedness, relevancy, passed, "
        "answer_kind, answer_text, sources_present, error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            result_id,
            eval_run_id,
            question_id,
            kind,
            groundedness,
            relevancy,
            int(passed),
            answer_kind,
            answer_text,
            None if sources_present is None else int(sources_present),
            error,
        ),
    )
    return result_id


# --- eval_run / eval_result reads (ST-34, S3 Reports) -------------------------
#
# Raw row reads only, same split as get_workspace/list_workspaces above: no
# "which state" or "is this pass/fail" judgement lives here, that is
# ui/reports_screen.py's job. eval_run.workspace_id is ON DELETE CASCADE
# (db/schema.sql), so a plain JOIN can never orphan a row -- there is no
# eval_run whose workspace disappeared while it survived.


def list_eval_runs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every recorded evaluation run, newest first, with the workspace name
    UX spec 8.1's list wants ("date, workspace, and overall scores") --
    joined here rather than requiring the caller to look each one up."""
    return conn.execute(
        "SELECT eval_run.*, workspace.name AS workspace_name, "
        "COUNT(eval_result.id) AS completed_count "
        "FROM eval_run JOIN workspace ON workspace.id = eval_run.workspace_id "
        "LEFT JOIN eval_result ON eval_result.eval_run_id = eval_run.id "
        "GROUP BY eval_run.id, workspace.name "
        "ORDER BY eval_run.run_at DESC"
    ).fetchall()


def get_eval_run(conn: sqlite3.Connection, eval_run_id: str) -> sqlite3.Row | None:
    """One run by id, with its workspace name, or None (S3's detail 404)."""
    return conn.execute(
        "SELECT eval_run.*, workspace.name AS workspace_name, "
        "COUNT(eval_result.id) AS completed_count "
        "FROM eval_run JOIN workspace ON workspace.id = eval_run.workspace_id "
        "LEFT JOIN eval_result ON eval_result.eval_run_id = eval_run.id "
        "WHERE eval_run.id = ? GROUP BY eval_run.id, workspace.name",
        (eval_run_id,),
    ).fetchone()


def list_eval_results(conn: sqlite3.Connection, eval_run_id: str) -> list[sqlite3.Row]:
    """Every per-question row of one run, ordered by question_id. The
    fallback source for S3's per-question table when the JSON report file
    ST-32 also wrote is missing. Incremental runs persist the rich answer
    fields here so a partial report remains inspectable."""
    return conn.execute(
        "SELECT * FROM eval_result WHERE eval_run_id = ? ORDER BY question_id",
        (eval_run_id,),
    ).fetchall()


# --- answer_feedback (F-15) ---------------------------------------------


def upsert_answer_feedback(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    answer_key: str,
    question: str,
    answer_text: str,
    verdict: str,
    comment: str | None = None,
    id: str | None = None,
) -> None:
    """Write one verdict (plus optional comment) for one answer.

    IDEMPOTENT BY `answer_key`, ATOMICALLY. `ON CONFLICT(answer_key) DO
    UPDATE` rather than a SELECT-then-INSERT-or-UPDATE: two feedback POSTs
    for the same answer milliseconds apart (a double click, exactly the
    kind of race `app.py::Conversation.begin` was written to close for
    asking a question) would otherwise both see "no existing row" and both
    INSERT, and the schema's `UNIQUE (answer_key)` would turn the second
    into a raised `sqlite3.IntegrityError` instead of the update the
    caller wanted. The single statement lets SQLite's own conflict
    resolution serialize the two instead. `question` and `answer_text` are
    only ever written by the INSERT branch -- an update changes the
    verdict and comment on the same answer, never rewrites what was asked
    or answered."""
    conn.execute(
        "INSERT INTO answer_feedback "
        "(id, workspace_id, answer_key, question, answer_text, verdict, comment, "
        "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(answer_key) DO UPDATE SET "
        "verdict = excluded.verdict, comment = excluded.comment, "
        "updated_at = excluded.updated_at",
        (
            id or new_id(),
            workspace_id,
            answer_key,
            question,
            answer_text,
            verdict,
            comment,
            (now := utc_now()),
            now,
        ),
    )


def get_answer_feedback_by_keys(
    conn: sqlite3.Connection, answer_keys: Sequence[str]
) -> list[sqlite3.Row]:
    """Every feedback row whose `answer_key` is in `answer_keys`, one query
    rather than one per message -- what `ui/feedback.py::verdicts_for`
    reads to show "Thanks, feedback saved" against the right answers on
    S1. Empty input returns [] without touching the database: an empty
    `IN ()` is invalid SQL, and a conversation with no ANSWER/REFUSAL
    message yet (or ever) is the common case, not an edge one."""
    if not answer_keys:
        return []
    placeholders = ", ".join("?" for _ in answer_keys)
    return conn.execute(
        f"SELECT * FROM answer_feedback WHERE answer_key IN ({placeholders})",
        tuple(answer_keys),
    ).fetchall()


def list_answer_feedback(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Every feedback row across every workspace, newest first, with the
    workspace name joined in -- same shape as `list_eval_runs` above, for
    the same reason: S3's list wants a workspace name to show, not an id
    to look up. `answer_feedback.workspace_id` is ON DELETE CASCADE
    (db/schema.sql), so this plain JOIN can never orphan a row."""
    return conn.execute(
        "SELECT answer_feedback.*, workspace.name AS workspace_name "
        "FROM answer_feedback "
        "JOIN workspace ON workspace.id = answer_feedback.workspace_id "
        "ORDER BY answer_feedback.created_at DESC"
    ).fetchall()


# --- S6 login, roles and activity (docs/design/S6-auth-rbac.md) ----------


def upsert_user(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    username: str,
    email: str | None,
    display_name: str | None,
    roles: str,
) -> None:
    """Record who just signed in, keeping their first-seen date.

    `ON CONFLICT DO UPDATE` rather than delete-and-insert: the same person
    signing in again must not orphan their workspace grants, which point
    at this row."""
    now = utc_now()
    conn.execute(
        "INSERT INTO app_user (id, username, email, display_name, roles, "
        "created_at, last_login_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET username = excluded.username, "
        "email = excluded.email, display_name = excluded.display_name, "
        "roles = excluded.roles, last_login_at = excluded.last_login_at",
        (user_id, username, email, display_name, roles, now, now),
    )


def get_user(conn: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM app_user WHERE id = ?", (user_id,)).fetchone()


def list_users(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return list(conn.execute("SELECT * FROM app_user ORDER BY username"))


def create_session(
    conn: sqlite3.Connection, *, token_hash: str, user_id: str, expires_at: str
) -> None:
    now = utc_now()
    conn.execute(
        "INSERT INTO user_session (token_hash, user_id, created_at, expires_at, "
        "last_seen_at) VALUES (?, ?, ?, ?, ?)",
        (token_hash, user_id, now, expires_at, now),
    )


def get_session(conn: sqlite3.Connection, token_hash: str) -> sqlite3.Row | None:
    """The session row joined to its user, or None.

    The EXPIRY IS CHECKED IN SQL, not by the caller: a row whose
    `expires_at` has passed is not a session, and returning it "so the
    caller can check" is how an expired session gets used once."""
    return conn.execute(
        "SELECT s.token_hash, s.user_id, s.expires_at, s.last_seen_at, u.username, "
        "u.email, u.display_name, u.roles FROM user_session s JOIN app_user u "
        "ON u.id = s.user_id WHERE s.token_hash = ? AND s.expires_at > ?",
        (token_hash, utc_now()),
    ).fetchone()


def touch_session(conn: sqlite3.Connection, token_hash: str) -> None:
    conn.execute(
        "UPDATE user_session SET last_seen_at = ? WHERE token_hash = ?",
        (utc_now(), token_hash),
    )


def delete_session(conn: sqlite3.Connection, token_hash: str) -> None:
    conn.execute("DELETE FROM user_session WHERE token_hash = ?", (token_hash,))


def delete_sessions_for_user(conn: sqlite3.Connection, user_id: str) -> None:
    conn.execute("DELETE FROM user_session WHERE user_id = ?", (user_id,))


def delete_expired_sessions(conn: sqlite3.Connection) -> int:
    cursor = conn.execute("DELETE FROM user_session WHERE expires_at <= ?", (utc_now(),))
    return cursor.rowcount


def grant_workspace(conn: sqlite3.Connection, *, workspace_id: str, user_id: str) -> None:
    conn.execute(
        "INSERT INTO workspace_grant (workspace_id, user_id, granted_at) "
        "VALUES (?, ?, ?) ON CONFLICT(workspace_id, user_id) DO NOTHING",
        (workspace_id, user_id, utc_now()),
    )


def revoke_workspace(conn: sqlite3.Connection, *, workspace_id: str, user_id: str) -> None:
    conn.execute(
        "DELETE FROM workspace_grant WHERE workspace_id = ? AND user_id = ?",
        (workspace_id, user_id),
    )


def granted_workspace_ids(conn: sqlite3.Connection, user_id: str) -> set[str]:
    return {
        row["workspace_id"]
        for row in conn.execute(
            "SELECT workspace_id FROM workspace_grant WHERE user_id = ?", (user_id,)
        )
    }


def record_activity(
    conn: sqlite3.Connection,
    *,
    user_id: str | None,
    username: str,
    action: str,
    workspace_id: str | None = None,
    detail: str | None = None,
) -> None:
    """One line of the activity log. `detail` is a file name or a workspace
    name at most -- never a question, an answer or a document's text."""
    conn.execute(
        "INSERT INTO activity_event (id, user_id, username, action, workspace_id, "
        "detail, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_id(), user_id, username, action, workspace_id, detail, utc_now()),
    )


def list_activity(conn: sqlite3.Connection, limit: int = 200) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            "SELECT * FROM activity_event ORDER BY created_at DESC, rowid DESC LIMIT ?",
            (limit,),
        )
    )


# --- S6 saved chat history (law 09-08), ST-53 conversations ----------------
#
# Plain operations only -- no retention policy, no notion of "expired", no
# cutoff arithmetic, no ownership rule beyond the WHERE clause each caller
# asks for. What 0 or a negative retention setting MEANS, when a row
# counts as expired, how a cutoff is computed and how a title is derived
# all belong to `chat_history.py`, built on top of this module exactly as
# `workspaces.py` and `sync.py` are (module docstring above: business
# logic is not this module's job).
#
# EVERY read and write that names one conversation also names its owner
# (`user_id`), so no caller can reach someone else's row by knowing an id:
# a wrong owner simply matches nothing.


def upsert_conversation(
    conn: sqlite3.Connection,
    *,
    conversation_id: str,
    user_id: str,
    workspace_id: str,
    title: str | None,
    payload: str,
    updated_at: str,
) -> None:
    """Write one conversation's whole transcript.

    The FIRST write inserts the row, with `title` and `created_at`
    (= `updated_at`). Every later write for the same id replaces only
    `payload` and `updated_at` -- plus the title ONLY while it is still
    NULL (a migrated row, or one saved before any question): the title a
    person gave it by renaming must survive the next answer being saved,
    and `created_at` is when the conversation began, not when it last
    changed. `ON CONFLICT(id) DO
    UPDATE` for the same reason `upsert_answer_feedback` uses it: this runs
    on every settled answer, not only the first.

    The UPDATE half is scoped to the same owner and workspace: a row whose
    id somehow matched but belonged to someone else is left untouched
    rather than overwritten."""
    conn.execute(
        "INSERT INTO conversation "
        "(id, user_id, workspace_id, title, payload, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(id) DO UPDATE SET "
        "payload = excluded.payload, updated_at = excluded.updated_at, "
        "title = COALESCE(conversation.title, excluded.title) "
        "WHERE conversation.user_id = excluded.user_id "
        "AND conversation.workspace_id = excluded.workspace_id",
        (conversation_id, user_id, workspace_id, title, payload, updated_at, updated_at),
    )


def get_conversation(
    conn: sqlite3.Connection, *, conversation_id: str, user_id: str
) -> sqlite3.Row | None:
    """This person's conversation with this id, or None -- including when
    the id exists but belongs to somebody else. Whether it is too old to
    use is the caller's call, not this function's."""
    return conn.execute(
        "SELECT id, user_id, workspace_id, title, payload, created_at, updated_at "
        "FROM conversation WHERE id = ? AND user_id = ?",
        (conversation_id, user_id),
    ).fetchone()


def list_conversations(
    conn: sqlite3.Connection, *, user_id: str, workspace_id: str, newer_than: str
) -> list[sqlite3.Row]:
    """This person's conversations in this workspace updated after
    `newer_than`, newest first -- the history list. No payloads: a list
    needs a title and a date, not every transcript."""
    return list(
        conn.execute(
            "SELECT id, title, created_at, updated_at FROM conversation "
            "WHERE user_id = ? AND workspace_id = ? AND updated_at > ? "
            "ORDER BY updated_at DESC, id DESC",
            (user_id, workspace_id, newer_than),
        )
    )


def rename_conversation(
    conn: sqlite3.Connection, *, conversation_id: str, user_id: str, title: str
) -> int:
    """Set the title of this person's conversation. Returns 1 if it was
    theirs and existed, 0 otherwise -- the caller turns 0 into a 404.
    `updated_at` is left alone on purpose: renaming is not new
    conversation, and must not move it to the top of the list."""
    cursor = conn.execute(
        "UPDATE conversation SET title = ? WHERE id = ? AND user_id = ?",
        (title, conversation_id, user_id),
    )
    return cursor.rowcount


def delete_conversation(
    conn: sqlite3.Connection, *, conversation_id: str, user_id: str
) -> int:
    """Drop one of this person's conversations. Returns the row count."""
    cursor = conn.execute(
        "DELETE FROM conversation WHERE id = ? AND user_id = ?",
        (conversation_id, user_id),
    )
    return cursor.rowcount


def delete_conversations_in_workspace(
    conn: sqlite3.Connection, *, user_id: str, workspace_id: str
) -> int:
    """Every conversation one person has in one workspace (an admin
    revoking their access: those transcripts quote passages they should
    no longer hold). Returns the row count."""
    cursor = conn.execute(
        "DELETE FROM conversation WHERE user_id = ? AND workspace_id = ?",
        (user_id, workspace_id),
    )
    return cursor.rowcount


def delete_conversations_for_user(conn: sqlite3.Connection, *, user_id: str) -> int:
    """Every conversation belonging to one person, across every
    workspace. Returns the row count deleted."""
    cursor = conn.execute("DELETE FROM conversation WHERE user_id = ?", (user_id,))
    return cursor.rowcount


def delete_conversations_older_than(conn: sqlite3.Connection, *, cutoff: str) -> int:
    """Every conversation whose `updated_at` is at or before `cutoff` (an
    ISO-8601 UTC timestamp the caller computed), gone. Returns the row
    count. No idea here of what a retention window is -- `chat_history.py`
    computes the cutoff, including "delete everything" (retention 0)."""
    cursor = conn.execute("DELETE FROM conversation WHERE updated_at <= ?", (cutoff,))
    return cursor.rowcount


def _migrate_chat_history_to_conversation(conn: sqlite3.Connection) -> None:
    """ST-53: move every pre-ST-53 `chat_history` row into `conversation`,
    then DROP `chat_history` (YL's ruling, DECISIONS 2026-09-18).

    ONE TRANSACTION, COPY BEFORE DROP, COUNT CHECKED IN BETWEEN. This runs
    inside `ensure_schema`'s `BEGIN IMMEDIATE`, and `DROP TABLE` is
    transactional in SQLite, so the copy, the check and the drop commit
    together or not at all: a failure anywhere leaves `chat_history`
    exactly as it was.

    TITLES ARE COPIED AS NULL, on purpose (cold review). What a title is
    -- the first question, whitespace collapsed, cut to 80 characters -- is
    a rule, and rules live in `chat_history.py`, not here. A migrated
    conversation shows as untitled until its next save fills the title in
    (`upsert_conversation` sets a NULL title, never overwrites a real one)
    or the person renames it. An earlier version derived the title here and
    got the rule wrong: a 900-character first question became a
    900-character title the rename box could not even hold.

    A ROW WHOSE WORKSPACE NO LONGER EXISTS IS NOT COPIED. It could only
    exist if foreign keys were ever off; the cascade would already have
    removed it otherwise, and nothing could ever open it. Copying it would
    raise on the foreign key and, because `ensure_schema` runs before every
    write, stop every write in the app until the database was fixed by
    hand (cold review). It goes with the table instead.

    Idempotent: once the table is gone this returns at the first line, so
    it costs one catalogue lookup on every later `ensure_schema`.

    Undo, if it is ever needed, is written down in DECISIONS: recreate
    `chat_history` and fill it with each (user, workspace)'s most recent
    conversation -- the only row the old design could hold."""
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chat_history'"
    ).fetchone()
    if exists is None:
        return
    rows = conn.execute(
        "SELECT h.user_id, h.workspace_id, h.payload, h.updated_at FROM chat_history h "
        "WHERE EXISTS (SELECT 1 FROM workspace w WHERE w.id = h.workspace_id)"
    ).fetchall()
    for row in rows:
        conn.execute(
            "INSERT INTO conversation "
            "(id, user_id, workspace_id, title, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, NULL, ?, ?, ?)",
            (new_id(), row[0], row[1], row[2], row[3], row[3]),
        )
    copied = conn.execute(
        "SELECT COUNT(*) FROM chat_history h WHERE EXISTS ("
        "SELECT 1 FROM conversation c WHERE c.user_id = h.user_id "
        "AND c.workspace_id = h.workspace_id AND c.payload = h.payload)"
    ).fetchone()[0]
    if copied != len(rows):
        raise RuntimeError(
            f"chat_history migration found {copied} of {len(rows)} rows copied; "
            "refusing to drop the source table"
        )
    conn.execute("DROP TABLE chat_history")
