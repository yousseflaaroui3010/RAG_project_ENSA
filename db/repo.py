"""Sanad SQLite data access layer.

Hard technical rule (docs/phase2/CLAUDE.md, architecture section 7.4):
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
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from config import get_settings

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


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
    or an empty database file for a path that was never meant to exist."""
    conn = sqlite3.connect(str(db_path))
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
        init_db(conn)
        conn.commit()
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    """Apply db/schema.sql to `conn`. Safe to call repeatedly: every
    CREATE TABLE uses IF NOT EXISTS.

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


# --- eval_run ----------------------------------------------------------------


def insert_eval_run(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    run_at: str | None = None,
    groundedness: float | None = None,
    relevancy: float | None = None,
    refusal_pass: int = 0,
    refusal_total: int = 0,
    passed: bool = False,
    report_path: str | None = None,
    id: str | None = None,
) -> str:
    run_id = id or new_id()
    conn.execute(
        "INSERT INTO eval_run "
        "(id, workspace_id, run_at, groundedness, relevancy, refusal_pass, refusal_total, "
        "passed, report_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            run_id,
            workspace_id,
            run_at or utc_now(),
            groundedness,
            relevancy,
            refusal_pass,
            refusal_total,
            int(passed),
            report_path,
        ),
    )
    return run_id


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
    id: str | None = None,
) -> str:
    result_id = id or new_id()
    conn.execute(
        "INSERT INTO eval_result "
        "(id, eval_run_id, question_id, kind, groundedness, relevancy, passed) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (result_id, eval_run_id, question_id, kind, groundedness, relevancy, int(passed)),
    )
    return result_id
