"""ui/reports_screen.py: the S3 view-model helpers (ST-34).

The list/detail SHAPING is tested here, off the real database wherever
that is enough (`_score_rows`, `export_markdown`); `report_detail`'s two
branches (JSON file present / missing) are proven against a REAL run
written by `evaluation.runner.run_evaluation` -- the same fixture
`tests/unit/test_evaluation_runner.py` already exercises, reused rather
than hand-built twice (core law: two copies is fine, three needs a
written reason -- a THIRD hand-rolled `eval_run`/report-JSON fixture is
what this file declines to add).
"""

from __future__ import annotations

import json
import os
import re

from agent.ports import AgentPorts
from db import repo
from evaluation.runner import run_evaluation
from evaluation.scoring import ScoreResult
from ui.reports_screen import (
    QuestionRow,
    ReportsScreenState,
    ScoreRow,
    export_markdown,
    list_reports,
    report_detail,
    screen_state,
)
from vector_store import SearchHit

IN_QUESTION = "Quelle est la duree de la periode d'essai ?"
OUT_QUESTION = "Un extraterrestre a-t-il des droits ?"

HIT_A = SearchHit(
    parent_id="p-1", source_file="code.pdf", section_label="Article 1",
    chunk_text="chunk a", score=0.9,
)
HIT_B = SearchHit(
    parent_id="p-1", source_file="code.pdf", section_label="Article 1",
    chunk_text="chunk b", score=0.8,
)
PARENT_TEXT = "Article 1. Texte complet de la section sur la periode d'essai."
ANSWER_TEXT = "Trois mois, renouvelable une fois."


def _write_golden(tmp_path) -> None:
    rows = [
        {
            "id": "g-in-fake-001",
            "question": IN_QUESTION,
            "reference_answer": "Trois mois.",
            "source_file": "code.pdf",
            "source_article": "Article 1",
            "kind": "in_scope",
            "workspace": "hr",
            "corpus_probe": "periode d'essai",
            "notes": None,
        },
        {
            "id": "g-out-fake-001",
            "question": OUT_QUESTION,
            "reference_answer": "Le corpus ne couvre pas ce sujet.",
            "source_file": None,
            "source_article": None,
            "kind": "out_of_scope",
            "workspace": "hr",
            "corpus_probe": "extraterrestre",
            "notes": None,
        },
    ]
    path = tmp_path / "fake.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def _ports() -> AgentPorts:
    """Copied from tests/unit/test_evaluation_runner.py's own `_ports`
    (the proven-working shape, HIT_A/HIT_B/PARENT_TEXT and all): only the
    in-scope question grades as relevant, so the out-of-scope one exhausts
    the retry ceiling and the graph refuses it on its own routing, never a
    port faking a refusal directly."""

    def grade(question: str, _passages: object) -> bool:
        return question == IN_QUESTION

    return AgentPorts(
        summarize=lambda _history: "",
        clarify=lambda _question, _summary: None,
        rewrite=lambda question, _summary: (question,),
        retrieve=lambda _workspace_id, _query: (HIT_A, HIT_B),
        grade=grade,
        reword=lambda _question, previous, _attempt: previous,
        fetch_parents=lambda _workspace_id, parent_ids: {pid: PARENT_TEXT for pid in parent_ids},
        write_answer=lambda _q, _p, _pp: ANSWER_TEXT,
    )


class _FakeScorer:
    def score(self, *, question, answer_text, contexts):
        return ScoreResult(groundedness=0.95, relevancy=0.8)


def _run(tmp_path, *, corrupt_file: bool = False, delete_file: bool = False):
    """One real evaluation run, written the same way ST-32's own tests
    prove it -- returns (eval_run_id, db_path)."""
    _write_golden(tmp_path)
    db_path = tmp_path / "sanad.db"
    with repo.session(db_path) as conn:
        ws_id = repo.create_workspace(conn, name="ws-eval", folder_path=str(tmp_path))
    report = run_evaluation(
        workspace_id=ws_id,
        ports=_ports(),
        scorer=_FakeScorer(),
        golden_dir=tmp_path,
        db_path=db_path,
        reports_dir=tmp_path / "reports",
    )
    with repo.session(db_path) as conn:
        run_row = conn.execute(
            "SELECT id FROM eval_run WHERE workspace_id = ?", (ws_id,)
        ).fetchone()
    eval_run_id = run_row["id"]
    if delete_file:
        os.remove(report.report_path)
    elif corrupt_file:
        with open(report.report_path, "w", encoding="utf-8") as f:
            f.write("not json at all {{{")
    return eval_run_id, db_path


# --- screen_state ------------------------------------------------------------


def test_no_reports_is_the_empty_state():
    assert screen_state(report_count=0) is ReportsScreenState.NO_REPORTS


def test_any_report_at_all_is_the_list_state():
    assert screen_state(report_count=1) is ReportsScreenState.LIST
    assert screen_state(report_count=9) is ReportsScreenState.LIST


# --- list_reports --------------------------------------------------------


def test_list_reports_is_empty_before_any_run(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    assert list_reports(db_path=db_path) == []


def test_list_reports_carries_the_workspace_name_and_formatted_scores(tmp_path):
    _run_id, db_path = _run(tmp_path)
    rows = list_reports(db_path=db_path)
    assert len(rows) == 1
    row = rows[0]
    assert row.workspace_name == "ws-eval"
    assert row.groundedness_label == "95.0%"
    assert row.refusal_pass == row.refusal_total == 1
    assert row.passed is True


# --- report_detail: found, file present ---------------------------------


def test_report_detail_reads_the_rich_per_question_data_from_the_file(tmp_path):
    eval_run_id, db_path = _run(tmp_path)
    detail = report_detail(eval_run_id, db_path=db_path)

    assert detail is not None
    assert detail.file_error is None
    assert all(isinstance(q, QuestionRow) for q in detail.questions)
    by_id = {q.question_id: q for q in detail.questions}
    # answer_kind is only ever populated from the file, never the DB
    # degrade -- proof that this path really read the JSON.
    assert by_id["g-in-fake-001"].answer_kind == "answer"
    assert by_id["g-out-fake-001"].answer_kind == "refusal"

    assert all(isinstance(s, ScoreRow) for s in detail.score_rows)
    by_metric = {s.metric: s for s in detail.score_rows}
    assert by_metric["G1 Groundedness"].passed is True
    assert by_metric["G2 Honest refusals"].passed is True
    assert by_metric["G3 Sources on every answer"].passed is True


# --- report_detail: found, file missing (the reachable "error" case) ----


def test_report_detail_degrades_to_the_database_when_the_file_is_missing(tmp_path):
    eval_run_id, db_path = _run(tmp_path, delete_file=True)
    detail = report_detail(eval_run_id, db_path=db_path)

    assert detail is not None
    assert detail.file_error is not None
    assert "missing" in detail.file_error.lower()
    # the summary (from the DB row itself) is unaffected
    assert detail.summary.groundedness_label == "95.0%"
    # the degrade: real pass/fail per question, but no answer_kind/sources
    by_id = {q.question_id: q for q in detail.questions}
    assert len(by_id) == 2
    assert by_id["g-in-fake-001"].answer_kind is None
    assert by_id["g-in-fake-001"].sources_label == "—"
    # G3 has no source of truth left when the file is gone -- neither
    # eval_run nor eval_result stores sources_pass/total (schema read
    # directly) -- so it reports "not judged" rather than a guess.
    by_metric = {s.metric: s for s in detail.score_rows}
    assert by_metric["G3 Sources on every answer"].passed is None
    assert by_metric["G1 Groundedness"].passed is True  # unaffected


def test_report_detail_degrades_when_the_file_is_present_but_corrupt(tmp_path):
    eval_run_id, db_path = _run(tmp_path, corrupt_file=True)
    detail = report_detail(eval_run_id, db_path=db_path)

    assert detail is not None
    assert detail.file_error is not None
    assert len(detail.questions) == 2


# --- report_detail: not found ---------------------------------------------


def test_report_detail_returns_none_for_an_unknown_id(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    assert report_detail("does-not-exist", db_path=db_path) is None


# --- export_markdown -------------------------------------------------------


def test_export_markdown_carries_the_gate_table_and_every_question(tmp_path):
    eval_run_id, db_path = _run(tmp_path)
    detail = report_detail(eval_run_id, db_path=db_path)

    text = export_markdown(detail)

    assert "# Sanad evaluation report" in text
    assert "ws-eval" in text
    assert "G1 Groundedness" in text
    assert "G2 Honest refusals" in text
    assert "G3 Sources on every answer" in text
    assert "g-in-fake-001" in text
    assert "g-out-fake-001" in text
    assert "Overall: PASS" in text


def test_export_markdown_carries_the_file_error_note_when_degraded(tmp_path):
    eval_run_id, db_path = _run(tmp_path, delete_file=True)
    detail = report_detail(eval_run_id, db_path=db_path)

    text = export_markdown(detail)

    assert detail.file_error in text


def test_export_markdown_escapes_a_pipe_in_an_error_cell(tmp_path):
    """A `|` in an error message would otherwise break the Markdown
    table's own column count -- the one thing an annex-pasted table must
    never silently do."""
    eval_run_id, db_path = _run(tmp_path)
    detail = report_detail(eval_run_id, db_path=db_path)
    # Force a synthetic error containing a pipe onto one row, the same
    # shape run_evaluation itself writes for a raised exception.
    poisoned = detail.questions[0].__class__(
        question_id=detail.questions[0].question_id,
        kind_label=detail.questions[0].kind_label,
        answer_kind=detail.questions[0].answer_kind,
        passed=False,
        groundedness_label=detail.questions[0].groundedness_label,
        relevancy_label=detail.questions[0].relevancy_label,
        sources_label=detail.questions[0].sources_label,
        error="RuntimeError: a | poisoned | message",
    )
    from dataclasses import replace

    poisoned_detail = replace(detail, questions=[poisoned, *detail.questions[1:]])

    text = export_markdown(poisoned_detail)
    row_line = next(line for line in text.splitlines() if poisoned.question_id in line)

    # COUNT THE COLUMN SEPARATORS, NOT EVERY PIPE CHARACTER. `export_markdown`
    # escapes a pipe in the error text as `\|`, which is the correct and
    # LOSSLESS fix: GFM renders `\|` as a literal pipe inside the cell and does
    # not split the column. But `\|` still CONTAINS a `|`, so a bare
    # `.count("|")` counts the escaped one too and fails a function that is
    # behaving correctly. The first version of this assertion did exactly that.
    # What the test means is "the error text added no COLUMN BREAK", so it now
    # counts pipes that are not preceded by a backslash.
    separators = len(re.findall(r"(?<!\\)\|", row_line))
    assert separators == 8, (  # 7 columns -> 8 separators
        f"the error text broke the column count: {separators} separators, "
        f"expected 8. Row: {row_line!r}"
    )
    assert "\\|" in row_line, "the pipe in the error text should be escaped, not dropped"
