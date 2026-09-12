"""Recover durable runs left open when the previous process stopped."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import vector_store
from db import repo

ABANDONED_ERROR = "The previous Sanad process stopped before this run finished."
SYNC_RESULTS = ("added", "changed", "unchanged", "failed", "removed", "skipped")


@dataclass(frozen=True)
class RecoveryResult:
    sync_runs: int
    evaluation_runs: int


def finish_abandoned_sync_run(conn, sync_run_id: str, *, finished_at: str) -> bool:
    """Finish one still-open Sync from the item rows it already saved."""
    run = repo.get_sync_run(conn, sync_run_id)
    if run is None or run["finished_at"] is not None:
        return False
    counts = {
        result: conn.execute(
            "SELECT COUNT(*) FROM sync_item WHERE sync_run_id = ? AND result = ?",
            (sync_run_id, result),
        ).fetchone()[0]
        for result in SYNC_RESULTS
    }
    repo.finish_sync_run(
        conn,
        sync_run_id=sync_run_id,
        finished_at=finished_at,
        **counts,
    )
    return True


def _index_is_open_elsewhere(qdrant_storage_path: str | Path | None) -> bool:
    """True when another process already holds the embedded Qdrant store.

    `scripts/run_evaluation.py` is a separate process from this one and
    holds the store open for its whole run. Opening and closing it again
    here is cheap and side-effect free (`vector_store.open_store` only
    creates the directory if it is missing) and is the only reliable way
    to tell "the evaluator is mid-run" apart from "the last process died
    with a Running row still in the table" -- the two look identical from
    the database alone."""
    try:
        with vector_store.open_store(qdrant_storage_path):
            pass
    except vector_store.StoreAlreadyOpenError:
        return True
    return False


def recover_abandoned_runs(
    *,
    db_path: str | Path | None = None,
    qdrant_storage_path: str | Path | None = None,
) -> RecoveryResult:
    """Settle every persisted Running row before this process accepts work.

    Sync only ever runs inside this app process (`api/service.py`'s
    background thread), so a Running sync row found at startup was left by
    a previous instance of THIS process and is always truly abandoned.

    Evaluation runs are different: `scripts/run_evaluation.py` is a
    separate, long-running command-line process, and its Running row is
    only abandoned if that process is not still alive. The one thing that
    tells the two apart is whether the embedded vector store can be
    opened: the evaluator holds it for its entire run, so a
    `StoreAlreadyOpenError` here means the "Running" evaluation is real
    and must be left untouched, not settled as Partial out from under it."""
    recovered_sync = 0
    recovered_eval = 0
    finished_at = repo.utc_now()
    index_busy = _index_is_open_elsewhere(qdrant_storage_path)
    with repo.session(db_path) as conn:
        sync_rows = conn.execute(
            "SELECT id FROM sync_run WHERE finished_at IS NULL"
        ).fetchall()
        for run in sync_rows:
            recovered_sync += finish_abandoned_sync_run(
                conn, run["id"], finished_at=finished_at
            )

        if not index_busy:
            eval_rows = conn.execute(
                "SELECT id, question_total FROM eval_run WHERE status = 'running'"
            ).fetchall()
            for run in eval_rows:
                completed = repo.eval_run_progress(conn, run["id"])
                repo.update_eval_run(
                    conn,
                    run["id"],
                    status="partial",
                    failed_question_number=(
                        min(completed + 1, run["question_total"])
                        if run["question_total"]
                        else None
                    ),
                    error=ABANDONED_ERROR,
                )
                recovered_eval += 1
    return RecoveryResult(sync_runs=recovered_sync, evaluation_runs=recovered_eval)
