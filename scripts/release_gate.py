"""ST-33 release gate: exits non-zero on any PRD threshold miss (G1-G3),
printing the failing question ids (F-08; BUILD-PLAN line 94: "Gate exits
non-zero on any miss + lists failing questions; dispatch manual only").

    uv run python scripts/release_gate.py --report data/reports/<ws>/<run>.json
    uv run python scripts/release_gate.py --workspace-id <id>   # latest report

Reads an ST-32 evaluation report already on disk. Never runs the
evaluation itself and never spends a model credit -- ADR-12 keeps the
credit spend in `scripts/run_evaluation.py`, dispatched separately and
manually; this script is the cheap, repeatable half that can run as many
times as needed against the same report.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

# Flat-layout app (pyproject.toml [tool.uv] package = false): running this
# file directly puts scripts/ on sys.path, not the repo root -- see
# scripts/run_evaluation.py and scripts/corpus.py for the same line.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import get_settings  # noqa: E402
from evaluation.gate import evaluate_report  # noqa: E402


def _latest_report(workspace_id: str, reports_dir: Path | None = None) -> Path:
    """The most recent report for `workspace_id`. Report file names are the
    run's ISO-8601 timestamp with `:` swapped for `-` (`evaluation.runner.
    _report_path`), which still sorts lexicographically in run order, so
    the last name sorted is the last report written."""
    base = reports_dir if reports_dir is not None else Path(get_settings().reports_path)
    candidates = sorted((base / workspace_id).glob("*.json"))
    if not candidates:
        raise FileNotFoundError(
            f"no evaluation report found under {base / workspace_id}; "
            "run scripts/run_evaluation.py first"
        )
    return candidates[-1]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--report", help="path to an evaluation report JSON file")
    group.add_argument(
        "--workspace-id", help="find the latest report for this workspace under REPORTS_PATH"
    )
    args = parser.parse_args(argv)

    try:
        report_path = (
            Path(args.report) if args.report else _latest_report(args.workspace_id)
        )
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        print(f"cannot run the release gate: {exc}")
        return 1

    try:
        verdict = evaluate_report(report)
    except KeyError as exc:
        print(f"cannot run the release gate: report is missing field {exc}")
        return 1

    threshold = get_settings().eval_groundedness_threshold
    print(f"gate report: {report_path}")
    print(
        f"G1 groundedness {'PASS' if verdict.g1_passed else 'FAIL'} "
        f"(got {report.get('groundedness')}, need >= {threshold})"
    )
    print(
        f"G2 refusals     {'PASS' if verdict.g2_passed else 'FAIL'} "
        f"({report.get('refusal_pass')}/{report.get('refusal_total')})"
    )
    print(
        f"G3 sources      {'PASS' if verdict.g3_passed else 'FAIL'} "
        f"({report.get('sources_pass')}/{report.get('sources_total')})"
    )

    if verdict.passed:
        print("RELEASE GATE: PASS")
        return 0

    print("RELEASE GATE: FAIL")
    print(f"failing questions: {', '.join(verdict.failing_question_ids)}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
