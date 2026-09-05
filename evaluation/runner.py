"""ST-32: the evaluation runner. One command, one dated report (F-08).

Ties together every piece ST-32's 2026-09-03 survey found already built,
imported rather than reimplemented:

- `ui.ports.build_ports` / `build_default_ports` -- the one composition
  root (DECISIONS 2026-09-03: a second, separately-wired `AgentPorts`
  would measure a different product than the one that ships).
- `evaluation.golden.load_golden_set` -- reads whatever
  `evaluation/golden/*.jsonl` currently holds.
- `evaluation.capture.ask_and_capture` -- runs one question and captures
  the section text the writer actually read.
- `evaluation.scoring.Scorer` -- G1's judge, injected so this module and
  its tests never need a real RAGAS import.
- `db.repo.insert_eval_run` / `insert_eval_result` -- done since ST-10.

WHAT "PASSED" MEANS PER ROW, because F-08 says the report lists the
failing questions and that has to mean something precise:

- **out-of-scope**: passed iff the answer's kind is REFUSAL (G2).
  `Answer.refusal` is derived from `kind` (agent/state.py), so this is
  reading a fact, not making a judgement call.
- **in-scope**: passed iff the answer's kind is ANSWER (a refusal or a
  clarification is not what the golden row's reference answer models)
  AND `groundedness >= config.eval_groundedness_threshold` (G1).
- **either kind**, if the question raised before an `Answer` came back:
  failed, recorded with the exception text and no score, rather than
  aborting the other fifty-nine questions.

G3 (sources on 100% of answers) is recorded as MEASURED, not assumed:
`Answer.__post_init__` already refuses to build a kind=ANSWER `Answer`
with an empty source list, so a violation cannot reach this report as
data -- but the report counts `sources_present` explicitly per answer
rather than resting on that invariant's word for it, because this
story's own brief asks for exactly that.

WHAT THIS MODULE DELIBERATELY DOES NOT DECIDE: the release gate's PROCESS
EXIT CODE. BUILD-PLAN splits that to ST-33 ("Gate script (PRD
thresholds) ... exits non-zero on any miss"), which reads this same
report and the `eval_run.passed` column and can apply its own policy
without this module changing. `run_evaluation` returns a `passed` flag
computed from G1-G3 because the DATA is cheap to compute and the DB
schema already has a column for it; `scripts/run_evaluation.py`'s own
process exit code reports only whether the RUN completed, not whether
the product's answers were good enough.
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent.ports import AgentPorts
from agent.state import AnswerKind
from config import get_settings
from db import repo
from evaluation.capture import ask_and_capture
from evaluation.golden import OUT_OF_SCOPE, GoldenRow, load_golden_set
from evaluation.scoring import Scorer


@dataclass(frozen=True)
class QuestionResult:
    """One golden row's outcome. `answer_kind` and every score are `None`
    when `error` is set -- the question never produced an `Answer` to
    judge."""

    question_id: str
    kind: str
    answer_kind: str | None
    passed: bool
    groundedness: float | None
    relevancy: float | None
    sources_present: bool | None
    error: str | None = None


@dataclass(frozen=True)
class EvalReport:
    """architecture 5.3: "one row per question out ... one dated
    report". `results` is that row-per-question half; the rest is the
    overall half F-08 also asks for, "per-question and overall scores
    with the run date"."""

    workspace_id: str
    run_at: str
    results: tuple[QuestionResult, ...]
    groundedness: float | None
    relevancy: float | None
    refusal_pass: int
    refusal_total: int
    sources_pass: int
    sources_total: int
    passed: bool
    failing_question_ids: tuple[str, ...]
    report_path: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "workspace_id": self.workspace_id,
            "run_at": self.run_at,
            "groundedness": self.groundedness,
            "relevancy": self.relevancy,
            "refusal_pass": self.refusal_pass,
            "refusal_total": self.refusal_total,
            "sources_pass": self.sources_pass,
            "sources_total": self.sources_total,
            "passed": self.passed,
            "failing_question_ids": list(self.failing_question_ids),
            "results": [
                {
                    "question_id": r.question_id,
                    "kind": r.kind,
                    "answer_kind": r.answer_kind,
                    "passed": r.passed,
                    "groundedness": r.groundedness,
                    "relevancy": r.relevancy,
                    "sources_present": r.sources_present,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


def _judge_row(
    row: GoldenRow, *, ports: AgentPorts, workspace_id: str, scorer: Scorer
) -> QuestionResult:
    captured = ask_and_capture(ports, workspace_id=workspace_id, question=row.question)

    if captured.error is not None:
        return QuestionResult(
            question_id=row.id,
            kind=row.kind,
            answer_kind=None,
            passed=False,
            groundedness=None,
            relevancy=None,
            sources_present=None,
            error=f"{type(captured.error).__name__}: {captured.error}",
        )

    answer = captured.answer
    if answer is None:  # pragma: no cover - captured.error is None here
        raise AssertionError("ask_and_capture returned neither an answer nor an error")
    answer_kind = answer.kind.value

    if row.kind == OUT_OF_SCOPE:
        # G2: the only thing that makes an out-of-scope row pass is a
        # refusal. A clarification is not a refusal either -- F-08 wants a
        # "clear not covered reply", not a question back.
        return QuestionResult(
            question_id=row.id,
            kind=row.kind,
            answer_kind=answer_kind,
            passed=answer.kind is AnswerKind.REFUSAL,
            groundedness=None,
            relevancy=None,
            sources_present=None,
        )

    # in-scope
    if answer.kind is not AnswerKind.ANSWER:
        # Refused or asked to clarify a question the golden row expects
        # answered. No sections were read, so there is nothing to score.
        return QuestionResult(
            question_id=row.id,
            kind=row.kind,
            answer_kind=answer_kind,
            passed=False,
            groundedness=None,
            relevancy=None,
            sources_present=False,
        )

    sources_present = len(answer.sources) > 0
    score = scorer.score(
        question=row.question, answer_text=answer.text, contexts=captured.contexts
    )
    threshold = get_settings().eval_groundedness_threshold
    return QuestionResult(
        question_id=row.id,
        kind=row.kind,
        answer_kind=answer_kind,
        passed=score.groundedness >= threshold,
        groundedness=score.groundedness,
        relevancy=score.relevancy,
        sources_present=sources_present,
    )


def _aggregate(
    workspace_id: str, run_at: str, results: tuple[QuestionResult, ...]
) -> EvalReport:
    grounded_scores = [r.groundedness for r in results if r.groundedness is not None]
    relevancy_scores = [r.relevancy for r in results if r.relevancy is not None]
    refusal_rows = [r for r in results if r.kind == OUT_OF_SCOPE]
    sourced_rows = [r for r in results if r.sources_present is not None]

    overall_groundedness = (
        sum(grounded_scores) / len(grounded_scores) if grounded_scores else None
    )
    overall_relevancy = (
        sum(relevancy_scores) / len(relevancy_scores) if relevancy_scores else None
    )
    refusal_pass = sum(1 for r in refusal_rows if r.passed)
    sources_pass = sum(1 for r in sourced_rows if r.sources_present)

    threshold = get_settings().eval_groundedness_threshold
    g1 = overall_groundedness is not None and overall_groundedness >= threshold
    g2 = bool(refusal_rows) and refusal_pass == len(refusal_rows)
    g3 = bool(sourced_rows) and sources_pass == len(sourced_rows)

    failing = tuple(r.question_id for r in results if not r.passed)

    return EvalReport(
        workspace_id=workspace_id,
        run_at=run_at,
        results=results,
        groundedness=overall_groundedness,
        relevancy=overall_relevancy,
        refusal_pass=refusal_pass,
        refusal_total=len(refusal_rows),
        sources_pass=sources_pass,
        sources_total=len(sourced_rows),
        passed=g1 and g2 and g3,
        failing_question_ids=failing,
    )


def _report_path(workspace_id: str, run_at: str, reports_dir: Path | None) -> Path:
    """architecture line 359: `data/reports/<workspace_id>/<run_at>.json`.
    `run_at` is an ISO-8601 timestamp (`:` in it), which is a legal
    filename character on Linux but not on Windows -- both machines this
    project runs on need one file name, so `:` is swapped for `-` in the
    file name only; the ISO value inside the JSON body is untouched."""
    base = reports_dir if reports_dir is not None else Path(get_settings().reports_path)
    safe_run_at = run_at.replace(":", "-")
    return base / workspace_id / f"{safe_run_at}.json"


def run_evaluation(
    *,
    workspace_id: str,
    ports: AgentPorts,
    scorer: Scorer,
    golden_dir: Path | None = None,
    db_path: str | Path | None = None,
    reports_dir: Path | None = None,
) -> EvalReport:
    """The one command's whole body. Runs every golden row through the
    real product, scores it, writes the dated JSON report AND the
    matching `eval_run` / `eval_result` rows from the SAME result list --
    so the file on disk and the database can never disagree about one
    run -- and returns the report.

    `workspace_id` must already exist in the database at `db_path`
    (`eval_run.workspace_id` is a foreign key, ON DELETE CASCADE); the
    caller supplies it rather than this module choosing one, because in
    V1 there is exactly one flagship workspace and picking it is an
    operator decision, not this runner's.

    `reports_dir` defaults to `config.reports_path`
    (`data/reports/`); tests pass `tmp_path` so a test run never writes
    into the real operator-controlled reports folder."""
    rows = load_golden_set(golden_dir)
    run_at = repo.utc_now()

    results = tuple(
        _judge_row(row, ports=ports, workspace_id=workspace_id, scorer=scorer)
        for row in rows
    )
    report = _aggregate(workspace_id, run_at, results)

    path = _report_path(workspace_id, run_at, reports_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_json(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    report = dataclasses.replace(report, report_path=str(path))

    with repo.session(db_path) as conn:
        run_id = repo.insert_eval_run(
            conn,
            workspace_id=workspace_id,
            run_at=run_at,
            groundedness=report.groundedness,
            relevancy=report.relevancy,
            refusal_pass=report.refusal_pass,
            refusal_total=report.refusal_total,
            passed=report.passed,
            report_path=str(path),
        )
        for r in results:
            repo.insert_eval_result(
                conn,
                eval_run_id=run_id,
                question_id=r.question_id,
                kind=r.kind,
                passed=r.passed,
                groundedness=r.groundedness,
                relevancy=r.relevancy,
            )

    return report
