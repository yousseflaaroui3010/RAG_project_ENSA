"""Put an evaluation report measured elsewhere onto this server's Reports
screen, labelled as such.

    uv run python scripts/import_report.py \\
        --report docs/evals/release-v3.1.0-2026-09-19.json \\
        --workspace-id <id> --note "<where it was measured>"

Why this exists: an evaluation writes to the database of the machine that
ran it, so a run made on a laptop never reaches a hosted server's Reports
screen. Re-running it there costs model credit (ADR-12). When the
documents are the same, importing the saved report is the honest cheap
path -- but ONLY with `--note`: the note is stored in the report file and
every screen showing the run shows it (ui/reports_screen.py `_provenance`),
so the scores are never presented as measured on this workspace as it
stands.

Never spends a model credit. Refuses to import the same run twice into
one workspace, and copies the database aside before writing.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

# Flat-layout app: running this file directly puts scripts/ on sys.path,
# not the repo root -- same line as scripts/release_gate.py.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from db import repo  # noqa: E402
from evaluation.runner import _report_path  # noqa: E402


class ImportRefusedError(Exception):
    """A reason not to write anything, phrased for the operator."""


def _backup(db_path: Path) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = db_path.with_name(f"{db_path.name}.before-import-{stamp}")
    source = sqlite3.connect(db_path)
    try:
        copy = sqlite3.connect(target)
        try:
            source.backup(copy)
        finally:
            copy.close()
    finally:
        source.close()
    return target


def import_report(
    *,
    report: Path,
    workspace_id: str,
    note: str,
    db_path: Path | None = None,
    reports_dir: Path | None = None,
) -> tuple[str, Path, Path]:
    """Returns (new eval_run id, report file written, database backup)."""
    note = note.strip()
    if not note:
        raise ImportRefusedError("--note is required: say where this run was measured.")
    data = json.loads(report.read_text(encoding="utf-8"))
    if data.get("status") != "completed":
        raise ImportRefusedError("only a completed run can be imported.")
    results = data["results"]
    if len(results) != data["question_total"]:
        raise ImportRefusedError(
            f"the report lists {len(results)} results for {data['question_total']} questions."
        )
    db = Path(db_path if db_path is not None else get_settings().sqlite_db_path)
    if not db.is_file():
        # repo.session would create a fresh empty database here and the
        # import would "succeed" into a file the server never reads.
        raise ImportRefusedError(f"no database at {db}.")
    run_at = data["run_at"]
    with repo.session(db) as conn:
        if repo.get_workspace(conn, workspace_id) is None:
            raise ImportRefusedError(f"no workspace with id {workspace_id}.")
        already = conn.execute(
            "SELECT id FROM eval_run WHERE workspace_id = ? AND run_at = ?",
            (workspace_id, run_at),
        ).fetchone()
        if already is not None:
            raise ImportRefusedError(
                f"this run is already on this workspace (eval_run {already['id']})."
            )

    backup = _backup(db)
    target = _report_path(workspace_id, run_at, reports_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot = {**data, "workspace_id": workspace_id, "provenance": note}
    target.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        with repo.session(db) as conn:
            run_id = repo.insert_eval_run(
                conn,
                workspace_id=workspace_id,
                run_at=run_at,
                status="completed",
                question_total=data["question_total"],
                groundedness=data["groundedness"],
                relevancy=data["relevancy"],
                refusal_pass=data["refusal_pass"],
                refusal_total=data["refusal_total"],
                passed=bool(data["passed"]),
                report_path=str(target),
            )
            for r in results:
                repo.insert_eval_result(
                    conn,
                    eval_run_id=run_id,
                    question_id=r["question_id"],
                    kind=r["kind"],
                    passed=bool(r["passed"]),
                    groundedness=r["groundedness"],
                    relevancy=r["relevancy"],
                    answer_kind=r["answer_kind"],
                    answer_text=r["answer_text"],
                    sources_present=r["sources_present"],
                    error=r["error"],
                )
    except Exception:
        # The rows rolled back with the session; do not leave an orphan
        # report file that looks like a run nobody can open.
        target.unlink(missing_ok=True)
        raise
    return run_id, target, backup


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--note", required=True)
    args = parser.parse_args(argv)
    try:
        run_id, target, backup = import_report(
            report=args.report, workspace_id=args.workspace_id, note=args.note
        )
    except ImportRefusedError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    print(f"imported eval_run {run_id}")
    print(f"report file   {target}")
    print(f"db backup     {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
