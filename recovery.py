"""Recover durable runs left open when the previous process stopped."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def recover_abandoned_runs(
    *, db_path: str | Path | None = None
) -> RecoveryResult:
    """Settle every persisted Running row before this process accepts work."""
    recovered_sync = 0
    recovered_eval = 0
    finished_at = repo.utc_now()
    with repo.session(db_path) as conn:
        sync_rows = conn.execute(
            "SELECT id FROM sync_run WHERE finished_at IS NULL"
        ).fetchall()
        for run in sync_rows:
            recovered_sync += finish_abandoned_sync_run(
                conn, run["id"], finished_at=finished_at
            )

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
