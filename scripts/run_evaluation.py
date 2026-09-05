"""ST-32 exit gate: one command, one dated evaluation report (F-08).

    uv run python scripts/run_evaluation.py --workspace-id <id>

Spends real model credits -- one chat call per question the graph answers,
plus RAGAS's own judge calls -- so ADR-12 keeps this a manual, by-hand
command, never something CI runs on its own. `--workspace-id` must already
exist in the registry database (`db.repo.list_workspaces` lists them).

THIS COMMAND CANNOT PRODUCE A REAL REPORT YET. `evaluation.scoring.
build_ragas_scorer` always raises `ScorerUnavailableError`: ragas 0.4.3
cannot even be imported against this project's pinned langchain-community,
and even past that there are two unmade decisions about which adapter
carries this project's Gemini model and its local embedder into RAGAS. See
that module's docstring and docs/journal/BUILD-STATE.md's ST-32 entry.
Checking that FIRST, before opening the Qdrant store, means a run that
cannot be scored never spends a single model credit finding that out.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

import vector_store
from evaluation.runner import run_evaluation
from evaluation.scoring import ScorerUnavailableError, build_ragas_scorer
from ui.ports import build_default_ports


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-id", required=True, help="an existing workspace id"
    )
    args = parser.parse_args(argv)

    try:
        scorer = build_ragas_scorer()
    except ScorerUnavailableError as exc:
        print(f"cannot run the evaluation: {exc}", file=sys.stderr)
        return 1

    with vector_store.open_store() as client:
        ports = build_default_ports(client)
        report = run_evaluation(workspace_id=args.workspace_id, ports=ports, scorer=scorer)

    print(f"report written to {report.report_path}")
    print(
        f"groundedness={report.groundedness} relevancy={report.relevancy} "
        f"refusals={report.refusal_pass}/{report.refusal_total} "
        f"sources={report.sources_pass}/{report.sources_total} "
        f"passed={report.passed}"
    )
    if report.failing_question_ids:
        print(f"failing questions: {', '.join(report.failing_question_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
