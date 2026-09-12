"""Which state the S3 Reports screen is in, and the view-model pieces its
templates read (ST-34).

Mirrors `ui/screen.py` and `ui/workspaces_screen.py`'s own reasoning:
decide state and shape data here, in a module a test can call without an
HTTP request, rather than in `{% if %}` chains spread across a template.
`app.py` decides which run is being looked at; this decides how to
describe it.

This screen is read-only over runs started by `scripts/run_evaluation.py`.
The runner commits one row per completed question, so this module can show
real Running progress and preserve a Partial run without inventing a timer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from config import get_settings
from db import repo
from evaluation import FULLY_GROUNDED_SCORE
from evaluation.golden import OUT_OF_SCOPE


class ReportsScreenState(StrEnum):
    NO_REPORTS = "no_reports"
    LIST = "list"


def screen_state(*, report_count: int) -> ReportsScreenState:
    """The one value the template branches on for the top-level layout."""
    if report_count == 0:
        return ReportsScreenState.NO_REPORTS
    return ReportsScreenState.LIST


def _pct(value: float | None) -> str:
    return "\u2014" if value is None else f"{value * 100:.1f}%"


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "\u2014"
    return "Yes" if value else "No"


@dataclass(frozen=True)
class _GateCounts:
    grounded_pass: int
    grounded_total: int
    sources_pass: int
    sources_total: int


def _gate_counts(report_path: str | None) -> _GateCounts | None:
    """Read the gate counts that the database does not store."""
    if not report_path:
        return None
    try:
        data = json.loads(Path(report_path).read_text(encoding="utf-8"))
        values = (
            data["grounded_pass"],
            data["grounded_total"],
            data["sources_pass"],
            data["sources_total"],
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if any(isinstance(value, bool) or not isinstance(value, int) for value in values):
        return None
    return _GateCounts(*values)


@dataclass(frozen=True)
class ReportSummary:
    """One row of the report list (UX spec 8.1: date, workspace, overall
    scores) and the header of the detail page. Labels are formatted here,
    not in the template, for the same reason `workspaces_screen.FileRow`
    carries `size_label` alongside `size_bytes`.

    G1 and G3 counts are read from the atomic JSON snapshot because the
    summary table does not duplicate those totals. Each question's rich
    fields also live in SQLite, so detail can still be recovered if that
    snapshot is missing; old rows without those fields remain Not judged."""

    id: str
    workspace_id: str
    workspace_name: str
    run_at: str
    groundedness: float | None
    groundedness_label: str
    sources_label: str
    relevancy: float | None
    refusal_pass: int
    refusal_total: int
    passed: bool | None
    status: str
    question_total: int
    completed_count: int
    status_label: str
    status_tone: str
    status_shape: str
    failed_question_number: int | None
    failed_question_id: str | None
    error: str | None
    report_path: str | None

    @property
    def is_running(self) -> bool:
        return self.status == "running"

    @property
    def is_partial(self) -> bool:
        return self.status == "partial"


def _summary(row: Any) -> ReportSummary:
    counts = _gate_counts(row["report_path"])
    status = row["status"]
    completed_count = row["completed_count"]
    question_total = row["question_total"]
    if status == "running":
        status_label = f"Running {completed_count}/{question_total}"
        tone, shape = "neutral", "hollow-circle"
        passed = None
    elif status == "partial":
        status_label = f"Partial {completed_count}/{question_total}"
        tone, shape = "danger", "filled-square"
        passed = None
    else:
        passed = bool(row["passed"])
        status_label = "Pass" if passed else "Fail"
        tone = "positive" if passed else "danger"
        shape = "filled-circle" if passed else "filled-square"
    return ReportSummary(
        id=row["id"],
        workspace_id=row["workspace_id"],
        workspace_name=row["workspace_name"],
        run_at=row["run_at"],
        groundedness=row["groundedness"],
        groundedness_label=(
            f"{counts.grounded_pass}/{counts.grounded_total} fully grounded"
            if counts is not None
            else _pct(row["groundedness"])
        ),
        sources_label=(
            f"{counts.sources_pass}/{counts.sources_total}"
            if counts is not None
            else "\u2014"
        ),
        relevancy=row["relevancy"],
        refusal_pass=row["refusal_pass"],
        refusal_total=row["refusal_total"],
        passed=passed,
        status=status,
        question_total=question_total,
        completed_count=completed_count,
        status_label=status_label,
        status_tone=tone,
        status_shape=shape,
        failed_question_number=row["failed_question_number"],
        failed_question_id=row["failed_question_id"],
        error=row["error"],
        report_path=row["report_path"],
    )


def list_reports(*, db_path: str | Path | None = None) -> list[ReportSummary]:
    with repo.session(db_path) as conn:
        return [_summary(r) for r in repo.list_eval_runs(conn)]


@dataclass(frozen=True)
class ScoreRow:
    """UX spec 5's `ScoreRow`: "metric name, value, threshold, pass or
    fail." The threshold sits next to the value always -- 8.2: "a score
    without its threshold means nothing to a jury." `passed` is `None`
    for "cannot be judged" (G3 with no report file to read it from),
    rendered as a third, neutral outcome -- never guessed as a Pass or a
    Fail, and never colour alone either way (UX spec 8.4)."""

    metric: str
    value_label: str
    threshold_label: str
    passed: bool | None


def _score_rows(
    summary: ReportSummary,
    *,
    grounded_pass: int | None,
    grounded_total: int | None,
    sources_pass: int | None,
    sources_total: int | None,
) -> list[ScoreRow]:
    """G1/G2/G3 (PRD section 3), shown from the stored pass counts."""
    threshold = get_settings().eval_groundedness_threshold
    g1_pass = (
        None
        if grounded_total is None or grounded_pass is None
        else (grounded_total > 0 and grounded_pass / grounded_total >= threshold)
    )
    g2_pass = summary.refusal_total > 0 and summary.refusal_pass == summary.refusal_total
    g3_pass = (
        None
        if sources_total is None or sources_pass is None
        else sources_pass == sources_total
    )
    if summary.status != "completed":
        g1_pass = g2_pass = g3_pass = None
    g1_value = (
        "—"
        if grounded_total is None
        else f"{grounded_pass}/{grounded_total} fully grounded"
    )
    g3_value = "—" if sources_total is None else f"{sources_pass}/{sources_total}"
    g3_threshold = "—" if sources_total is None else f"{sources_total}/{sources_total}"
    return [
        ScoreRow(
            metric="G1 Groundedness",
            value_label=g1_value,
            threshold_label=f">= {_pct(threshold)}",
            passed=g1_pass,
        ),
        ScoreRow(
            metric="G2 Honest refusals",
            value_label=f"{summary.refusal_pass}/{summary.refusal_total}",
            threshold_label=f"{summary.refusal_total}/{summary.refusal_total}",
            passed=g2_pass,
        ),
        ScoreRow(
            metric="G3 Sources on every answer",
            value_label=g3_value,
            threshold_label=g3_threshold,
            passed=g3_pass,
        ),
    ]


@dataclass(frozen=True)
class QuestionRow:
    """One row of S3's per-question table (UX spec 8.1). `answer_kind` is
    `None` when this came from the DB degrade, never from a real answer
    with no kind -- see `_questions_from_db`."""

    question_id: str
    kind_label: str
    answer_kind: str | None
    passed: bool
    groundedness_label: str
    relevancy_label: str
    sources_label: str
    error: str | None


def _kind_label(kind: str) -> str:
    return "Out of scope" if kind == OUT_OF_SCOPE else "In scope"


@dataclass(frozen=True)
class _FileReport:
    status: str
    questions: list[QuestionRow]
    grounded_pass: int
    grounded_total: int
    sources_pass: int
    sources_total: int


def _report_from_file(report_path: str) -> _FileReport | None:
    """The rich source: `EvalReport.to_json`'s own shape (ST-32) --
    `results` carries `answer_kind`, `sources_present` and `error` per
    question, and the top level carries the aggregate `sources_pass`/
    `sources_total` that never reaches the database (see
    `ReportSummary`'s docstring). Returns None on any read/parse failure
    so the caller can degrade to the DB rather than crash the whole
    detail page over one moved file."""
    try:
        data = json.loads(Path(report_path).read_text(encoding="utf-8"))
        status = data.get("status", "completed")
        rows = data["results"]
        grounded_pass = data.get("grounded_pass")
        grounded_total = data.get("grounded_total")
        sources_pass = data["sources_pass"]
        sources_total = data["sources_total"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
    if not isinstance(grounded_pass, int) or not isinstance(grounded_total, int):
        in_scope = [r for r in rows if r.get("kind") != OUT_OF_SCOPE]
        grounded_pass = sum(
            r.get("groundedness") == FULLY_GROUNDED_SCORE for r in in_scope
        )
        grounded_total = len(in_scope)
    questions = [
        QuestionRow(
            question_id=r["question_id"],
            kind_label=_kind_label(r["kind"]),
            answer_kind=r["answer_kind"],
            passed=bool(r["passed"]),
            groundedness_label=_pct(r["groundedness"]),
            relevancy_label=_pct(r["relevancy"]),
            sources_label=_yes_no(r["sources_present"]),
            error=r["error"],
        )
        for r in rows
    ]
    return _FileReport(
        status=status,
        questions=questions,
        grounded_pass=grounded_pass,
        grounded_total=grounded_total,
        sources_pass=sources_pass,
        sources_total=sources_total,
    )


def _questions_from_db(rows: list[Any]) -> list[QuestionRow]:
    """The durable fallback when the matching JSON snapshot is unavailable."""
    return [
        QuestionRow(
            question_id=r["question_id"],
            kind_label=_kind_label(r["kind"]),
            answer_kind=r["answer_kind"],
            passed=bool(r["passed"]),
            groundedness_label=_pct(r["groundedness"]),
            relevancy_label=_pct(r["relevancy"]),
            sources_label=_yes_no(
                None if r["sources_present"] is None else bool(r["sources_present"])
            ),
            error=r["error"],
        )
        for r in rows
    ]


@dataclass(frozen=True)
class ReportDetail:
    summary: ReportSummary
    score_rows: list[ScoreRow]
    questions: list[QuestionRow]
    file_error: str | None


def report_detail(
    eval_run_id: str, *, db_path: str | Path | None = None
) -> ReportDetail | None:
    """None means "no such run" -- S3's detail 404, `ErrorPanel` showing
    the id the operator followed a link to (UX spec 5)."""
    with repo.session(db_path) as conn:
        row = repo.get_eval_run(conn, eval_run_id)
        if row is None:
            return None
        summary = _summary(row)
        db_rows = repo.list_eval_results(conn, eval_run_id)

    file_report = _report_from_file(summary.report_path) if summary.report_path else None
    stale_file = file_report is not None and (
        file_report.status != summary.status
        or len(file_report.questions) != summary.completed_count
    )
    if stale_file:
        file_report = None
    file_error: str | None = None
    if file_report is None:
        file_error = (
            f"The full report file is missing, unreadable, or out of date at "
            f"{summary.report_path or '(no path recorded)'}. Showing the "
            f"durable database copy below instead. Older runs may not carry "
            f"answer kind, sources-present, or error detail; any gate without "
            f"enough stored evidence is labelled not judged."
        )
        questions = _questions_from_db(db_rows)
        grounded_rows = [r for r in db_rows if r["kind"] != OUT_OF_SCOPE]
        grounded_pass = sum(
            r["groundedness"] == FULLY_GROUNDED_SCORE for r in grounded_rows
        )
        grounded_total = len(grounded_rows)
        answer_rows = [r for r in db_rows if r["answer_kind"] == "answer"]
        rich_rows = [
            r
            for r in db_rows
            if r["answer_kind"] is not None
            or r["answer_text"] is not None
            or r["sources_present"] is not None
            or r["error"] is not None
        ]
        if rich_rows:
            sources_pass = sum(bool(r["sources_present"]) for r in answer_rows)
            sources_total = len(answer_rows)
        else:
            sources_pass = sources_total = None
    else:
        questions = file_report.questions
        grounded_pass = file_report.grounded_pass
        grounded_total = file_report.grounded_total
        sources_pass = file_report.sources_pass
        sources_total = file_report.sources_total

    return ReportDetail(
        summary=summary,
        score_rows=_score_rows(
            summary,
            grounded_pass=grounded_pass,
            grounded_total=grounded_total,
            sources_pass=sources_pass,
            sources_total=sources_total,
        ),
        questions=questions,
        file_error=file_error,
    )


def _outcome(passed: bool | None) -> str:
    if passed is None:
        return "Not judged"
    return "Pass" if passed else "Fail"


def export_markdown(detail: ReportDetail) -> str:
    """UX spec 8.2: "Export produces a file suitable for the written
    report annex." Markdown, not a bespoke format, because the annex is a
    written document a human pastes this straight into -- headings and
    pipe tables render as-is in nearly every editor that produces one."""
    overall = (
        detail.summary.status.upper()
        if detail.summary.status != "completed"
        else ("PASS" if detail.summary.passed else "FAIL")
    )
    lines = [
        f"# Sanad evaluation report \u2014 {detail.summary.workspace_name}",
        "",
        f"Run at: {detail.summary.run_at}",
        f"Overall: {overall}",
    ]
    if detail.summary.status != "completed":
        lines.append(
            f"Progress: {detail.summary.completed_count}/{detail.summary.question_total} "
            "questions completed"
        )
    if detail.summary.is_partial:
        lines.extend(
            [
                f"Stopped at question: {detail.summary.failed_question_number} "
                f"({detail.summary.failed_question_id})",
                f"Error: {detail.summary.error}",
            ]
        )
    lines += [
        "",
        "| Metric | Value | Threshold | Outcome |",
        "|---|---|---|---|",
    ]
    for row in detail.score_rows:
        outcome = (
            "Not final"
            if detail.summary.status != "completed"
            else _outcome(row.passed)
        )
        lines.append(
            f"| {row.metric} | {row.value_label} | {row.threshold_label} | "
            f"{outcome} |"
        )
    lines += [
        "",
        "| Question | Kind | Outcome | Groundedness | Relevancy | Sources | Error |",
        "|---|---|---|---|---|---|---|",
    ]
    for q in detail.questions:
        error_cell = (q.error or "").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {q.question_id} | {q.kind_label} | "
            f"{'Pass' if q.passed else 'Fail'} | {q.groundedness_label} | "
            f"{q.relevancy_label} | {q.sources_label} | {error_cell} |"
        )
    if detail.file_error:
        lines += ["", f"> {detail.file_error}"]
    return "\n".join(lines) + "\n"
