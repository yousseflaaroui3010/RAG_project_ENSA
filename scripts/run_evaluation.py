"""ST-32 exit gate: one command, one dated evaluation report (F-08).

    uv run python scripts/run_evaluation.py --workspace-id <id>

Spends real model credits -- one chat call per question the graph answers,
plus one judge call per answered question (`evaluation.scoring.
LLMJudgeScorer`) -- so ADR-12 keeps this a manual, by-hand command, never
something CI runs on its own. `--workspace-id` must already exist in the
registry database (`db.repo.list_workspaces` lists them).

ONE MODEL, TWO JOBS. `build_chat_model()` is called exactly once here and
handed to both `ui.ports.build_ports` (the answering path) and
`evaluation.scoring.build_llm_judge_scorer` (the judge) -- the same
configured model does both, rather than two separately-built clients that
could silently drift onto different settings.

G1's number here is NOT RAGAS. `evaluation/scoring.py`'s module docstring
and docs/journal/DECISIONS.md (2026-09-05) record why: ragas 0.4.3 cannot
be imported against this project's dependencies at all, and the report
this command writes says so in its own words rather than implying an
equivalence nothing here has (see `evaluation.runner.EvalReport`).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

# Flat-layout app (pyproject.toml [tool.uv] package = false): running this
# file directly (`uv run python scripts/run_evaluation.py`) puts scripts/
# on sys.path, not the repo root, so a root-level import below would raise
# ModuleNotFoundError -- found by actually running this command while
# proving ST-33's gate end to end, not by reading. `scripts/corpus.py`
# already carries the same line for the same reason.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import vector_store  # noqa: E402
from agent.chat import ChatUnavailableError, build_chat_model  # noqa: E402
from evaluation.runner import run_evaluation  # noqa: E402
from evaluation.scoring import build_llm_judge_scorer  # noqa: E402
from ui.ports import build_ports  # noqa: E402


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace-id", required=True, help="an existing workspace id"
    )
    args = parser.parse_args(argv)

    try:
        model = build_chat_model()
    except ChatUnavailableError as exc:
        print(f"cannot run the evaluation: {exc}")
        return 1

    scorer = build_llm_judge_scorer(model)

    with vector_store.open_store() as client:
        ports = build_ports(client, model)
        report = run_evaluation(workspace_id=args.workspace_id, ports=ports, scorer=scorer)

    print(f"report written to {report.report_path}")
    print(
        f"groundedness={report.groundedness} relevancy={report.relevancy} "
        f"(both judged by our own model, not an independent metric -- see "
        f"evaluation/scoring.py) "
        f"refusals={report.refusal_pass}/{report.refusal_total} "
        f"sources={report.sources_pass}/{report.sources_total} "
        f"passed={report.passed}"
    )
    if report.failing_question_ids:
        print(f"failing questions: {', '.join(report.failing_question_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
