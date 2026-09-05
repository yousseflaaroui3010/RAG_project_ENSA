"""Which state the S3 Reports screen is in, and the view-model pieces its
templates read (ST-34).

Mirrors `ui/screen.py` and `ui/workspaces_screen.py`'s own reasoning:
decide state and shape data here, in a module a test can call without an
HTTP request, rather than in `{% if %}` chains spread across a template.
`app.py` decides which run is being looked at; this decides how to
describe it.

WHAT THIS SCREEN IS: read-only over runs `scripts/run_evaluation.py`
(ST-32) already wrote. UX spec 8.3's own empty-state copy -- "one line
pointing to HOW to run an evaluation" -- says the same thing: the screen
points at the command, it does not offer a button that starts one.

PARKED, named so it is not silently reinvented later: UX spec 8.3's
Loading state ("Evaluation running with a question counter... required,
not optional") has no backing signal anywhere in this codebase, checked
by reading rather than assumed absent. `evaluation.runner.run_evaluation`
computes every golden question in memory and writes the dated JSON file
plus the matching `eval_run`/`eval_result` rows in ONE `with
repo.session()` block, only after the last question is judged --
db/schema.sql's `eval_run` table (read directly) carries no
started_at/finished_at pair the way `sync_run` does, so there is no
"a run is in flight" row this screen could ever observe, even in
principle, without runner.py gaining incremental persistence first.
`scripts/run_evaluation.py`'s own docstring records ADR-12: this is a
manual, credit-spending, by-hand command. Building a live progress
counter is a decision for whoever next owns evaluation/runner.py (ST-32
or ST-33's line in BUILD-PLAN), not this screen -- see BUILD-STATE.

UX spec 8.3's Error clause ("the run failed at question N, partial
results kept and labelled partial") has the identical gap: `run_evaluation`
writes nothing at all until every question is judged, so a killed process
leaves zero rows, never a partial one. What IS real and reachable, and is
built here instead: a recorded run whose `report_path` file has been
moved or deleted after the fact (`data/` is git-ignored per
docs/phase2/CLAUDE.md, so this happens the moment someone tidies it).
The summary scores still come from the database and stay accurate; only
the richer per-question detail (`answer_kind`, `sources_present`, `error`)
lives in the file alone and degrades to the DB's narrower columns.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from config import get_settings
from db import repo
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
class ReportSummary:
    """One row of the report list (UX spec 8.1: date, workspace, overall
    scores) and the header of the detail page. Labels are formatted here,
    not in the template, for the same reason `workspaces_screen.FileRow`
    carries `size_label` alongside `size_bytes`.

    NO G3 (SOURCES) FIELD HERE, and that is a real gap rather than an
    oversight: db/schema.sql's `eval_run` table has no `sources_pass` or
    `sources_total` column, and `eval_result` has no `sources_present`
    either -- `evaluation.runner.run_evaluation` writes both numbers ONLY
    into the JSON report file (`EvalReport.to_json`'s top level), never
    into the database. Checked by reading `db/repo.insert_eval_run`'s own
    parameter list, not assumed. So a `ReportSummary` built from the DB
    alone (the list page's cheap read, every row) can show G1 and G2 but
    never G3; the detail page reads the file for the real number, and
    `_score_rows` reports G3 as unjudged rather than guessing when even
    the file is unavailable -- see `ScoreRow.passed`."""

    id: str
    workspace_id: str
    workspace_name: str
    run_at: str
    groundedness: float | None
    groundedness_label: str
    relevancy: float | None
    refusal_pass: int
    refusal_total: int
    passed: bool
    report_path: str | None


def _summary(row: Any) -> ReportSummary:
    return ReportSummary(
        id=row["id"],
        workspace_id=row["workspace_id"],
        workspace_name=row["workspace_name"],
        run_at=row["run_at"],
        groundedness=row["groundedness"],
        groundedness_label=_pct(row["groundedness"]),
        relevancy=row["relevancy"],
        refusal_pass=row["refusal_pass"],
        refusal_total=row["refusal_total"],
        passed=bool(row["passed"]),
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
    sources_pass: int | None,
    sources_total: int | None,
) -> list[ScoreRow]:
    """G1/G2/G3 (PRD section 3), recomputed from the same stored numbers
    `evaluation.runner._aggregate` used to decide `passed` in the first
    place -- that function is private to ST-32's module, so this is the
    one other place this exact condition is written; see its own
    docstring for the definition this must not drift from."""
    threshold = get_settings().eval_groundedness_threshold
    g1_pass = summary.groundedness is not None and summary.groundedness >= threshold
    g2_pass = summary.refusal_total > 0 and summary.refusal_pass == summary.refusal_total
    g3_pass = (
        None
        if sources_total is None or sources_pass is None
        else (sources_total > 0 and sources_pass == sources_total)
    )
    g3_value = "—" if sources_total is None else f"{sources_pass}/{sources_total}"
    g3_threshold = "—" if sources_total is None else f"{sources_total}/{sources_total}"
    return [
        ScoreRow(
            metric="G1 Groundedness",
            value_label=summary.groundedness_label,
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
    questions: list[QuestionRow]
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
        rows = data["results"]
        sources_pass = data["sources_pass"]
        sources_total = data["sources_total"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError):
        return None
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
        questions=questions, sources_pass=sources_pass, sources_total=sources_total
    )


def _questions_from_db(rows: list[Any]) -> list[QuestionRow]:
    """The degrade: `eval_result` columns alone (see db/schema.sql), used
    only when the JSON file the run also wrote cannot be read."""
    return [
        QuestionRow(
            question_id=r["question_id"],
            kind_label=_kind_label(r["kind"]),
            answer_kind=None,
            passed=bool(r["passed"]),
            groundedness_label=_pct(r["groundedness"]),
            relevancy_label=_pct(r["relevancy"]),
            sources_label="\u2014",
            error=None,
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
    file_error: str | None = None
    if file_report is None:
        file_error = (
            f"The full report file is missing or unreadable at "
            f"{summary.report_path or '(no path recorded)'}. Showing the "
            f"summary scores above and the pass/fail recorded in the "
            f"database below instead -- answer kind, sources-present and "
            f"error detail live only in the missing file, so G3 (sources) "
            f"cannot be judged until it is restored."
        )
        questions = _questions_from_db(db_rows)
        sources_pass: int | None = None
        sources_total: int | None = None
    else:
        questions = file_report.questions
        sources_pass = file_report.sources_pass
        sources_total = file_report.sources_total

    return ReportDetail(
        summary=summary,
        score_rows=_score_rows(summary, sources_pass=sources_pass, sources_total=sources_total),
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
    lines = [
        f"# Sanad evaluation report \u2014 {detail.summary.workspace_name}",
        "",
        f"Run at: {detail.summary.run_at}",
        f"Overall: {'PASS' if detail.summary.passed else 'FAIL'}",
        "",
        "| Metric | Value | Threshold | Outcome |",
        "|---|---|---|---|",
    ]
    for row in detail.score_rows:
        lines.append(
            f"| {row.metric} | {row.value_label} | {row.threshold_label} | "
            f"{_outcome(row.passed)} |"
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
