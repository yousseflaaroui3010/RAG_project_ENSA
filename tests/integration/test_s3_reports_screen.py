"""ST-34 exit gate: every S3 state demonstrated through the real app --
real routes, real templates, a real evaluation run written by
`evaluation.runner.run_evaluation` (ST-32), read back by the real
`/reports` routes. No Qdrant and no `ports_factory` needed: S3 never
calls `agent.graph.ask`, it only reads `eval_run`/`eval_result` rows and
the JSON file `run_evaluation` already wrote -- `Runtime(ports_factory=
lambda: None, ...)` is the same lightweight, lifespan-skipping shape
`test_s1_chat_screen.py` uses for routes that never touch the model.

Running and Partial are seeded through the same public repository writes
the evaluator uses, then exercised through the real list, detail, and
export routes."""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path

from fastapi.testclient import TestClient

from agent.ports import AgentPorts
from app import Runtime, create_app
from db import repo
from evaluation.runner import run_evaluation
from evaluation.scoring import ScoreResult
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
            "id": "g-in-fake-001", "question": IN_QUESTION,
            "reference_answer": "Trois mois.", "source_file": "code.pdf",
            "source_article": "Article 1", "kind": "in_scope",
            "workspace": "hr", "corpus_probe": "periode d'essai", "notes": None,
        },
        {
            "id": "g-out-fake-001", "question": OUT_QUESTION,
            "reference_answer": "Le corpus ne couvre pas ce sujet.",
            "source_file": None, "source_article": None, "kind": "out_of_scope",
            "workspace": "hr", "corpus_probe": "extraterrestre", "notes": None,
        },
    ]
    (tmp_path / "fake.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows), encoding="utf-8"
    )


def _ports() -> AgentPorts:
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
        return ScoreResult(groundedness=1.0, relevancy=0.8)


def _app(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    runtime = Runtime(ports_factory=lambda: None, db_path=db_path)
    return TestClient(create_app(runtime)), db_path


def _seed_report(tmp_path, db_path) -> str:
    """One real run, via the real ST-32 runner -- returns its eval_run id."""
    _write_golden(tmp_path)
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
        row = conn.execute(
            "SELECT id FROM eval_run WHERE workspace_id = ?", (ws_id,)
        ).fetchone()
    return row["id"], report.report_path


def _seed_incomplete_report(tmp_path, db_path, *, status: str) -> str:
    report_path = tmp_path / f"{status}.json"
    report_path.write_text(
        json.dumps(
            {
                "status": status,
                "question_total": 3,
                "grounded_pass": 1,
                "grounded_total": 1,
                "sources_pass": 1,
                "sources_total": 1,
                "results": [
                    {
                        "question_id": "g-in-fake-001",
                        "kind": "in_scope",
                        "answer_kind": "answer",
                        "answer_text": ANSWER_TEXT,
                        "passed": True,
                        "groundedness": 1.0,
                        "relevancy": 0.8,
                        "sources_present": True,
                        "error": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with repo.session(db_path) as conn:
        ws_id = repo.create_workspace(
            conn, name=f"ws-{status}", folder_path=str(tmp_path)
        )
        run_id = repo.insert_eval_run(
            conn,
            workspace_id=ws_id,
            status="running",
            question_total=3,
            report_path=str(report_path),
        )
        repo.insert_eval_result(
            conn,
            eval_run_id=run_id,
            question_id="g-in-fake-001",
            kind="in_scope",
            answer_kind="answer",
            answer_text=ANSWER_TEXT,
            passed=True,
            groundedness=1.0,
            relevancy=0.8,
            sources_present=True,
        )
        if status == "partial":
            repo.update_eval_run(
                conn,
                run_id,
                status="partial",
                groundedness=1.0,
                relevancy=0.8,
                failed_question_number=2,
                failed_question_id="g-in-fake-002",
                error="RuntimeError: judge unavailable",
            )
    return run_id


# --- Empty -------------------------------------------------------------------


def test_no_reports_shows_the_empty_state_and_the_cli_command(tmp_path):
    client, _db_path = _app(tmp_path)

    page = client.get("/reports")

    assert page.status_code == 200
    assert "No evaluation reports yet" in page.text
    assert "uv run python scripts/run_evaluation.py" in page.text


def test_reports_nav_link_is_real_and_reaches_the_screen_with_no_workspace(tmp_path):
    """The shell's nav must never 404 -- reports are read across every
    workspace (UX spec 8.1), including a database with none at all."""
    client, _db_path = _app(tmp_path)

    page = client.get("/")  # -> redirected to /workspaces, no workspace exists
    assert page.status_code == 200  # TestClient follows the redirect

    reports_page = client.get("/reports")
    assert reports_page.status_code == 200
    assert 'aria-current="page"' in reports_page.text


# --- Populated (list + detail) -----------------------------------------------


def test_a_recorded_run_appears_in_the_list_with_a_real_pass_fail_badge(tmp_path):
    client, db_path = _app(tmp_path)
    eval_run_id, _path = _seed_report(tmp_path, db_path)

    page = client.get("/reports")

    assert page.status_code == 200
    assert "ws-eval" in page.text
    assert f"/reports/{eval_run_id}" in page.text
    assert "Pass" in page.text  # text label, never colour alone (UX spec 8.4)


def test_report_list_shows_the_sources_score(tmp_path):
    client, db_path = _app(tmp_path)
    _seed_report(tmp_path, db_path)

    page = client.get("/reports")

    table_body = page.text.partition("<tbody>")[2].partition("</tbody>")[0]
    cells = re.findall(r"<td(?: [^>]*)?>(.*?)</td>", table_body, re.DOTALL)
    assert "1/1" in cells[4]


def test_report_list_uses_the_grounded_row_count_not_answer_average(tmp_path):
    client, db_path = _app(tmp_path)
    _eval_run_id, path = _seed_report(tmp_path, db_path)
    report_path = Path(path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["grounded_pass"] = 0
    report["grounded_total"] = 1
    report_path.write_text(json.dumps(report), encoding="utf-8")

    page = client.get("/reports")

    assert "0/1 fully grounded" in page.text
    assert "100.0%" not in page.text


def test_running_report_shows_real_progress_and_refreshes_without_script(tmp_path):
    client, db_path = _app(tmp_path)
    eval_run_id = _seed_incomplete_report(tmp_path, db_path, status="running")

    page = client.get("/reports")

    assert page.status_code == 200
    assert f'data-eval-status="{eval_run_id}"' in page.text
    assert f'data-report-focus="run-{eval_run_id}"' in page.text
    assert "Running 1/3" in page.text
    assert 'role="status"' in page.text
    assert 'aria-live="polite"' in page.text
    assert '<meta http-equiv="refresh" content="2">' in page.text


def test_running_report_detail_labels_unfinished_gates_as_not_final(tmp_path):
    client, db_path = _app(tmp_path)
    eval_run_id = _seed_incomplete_report(tmp_path, db_path, status="running")

    page = client.get(f"/reports/{eval_run_id}")

    assert "Evaluation running: 1/3 questions completed." in page.text
    assert page.text.count("Not final") == 3
    assert 'data-report-refresh="true"' in page.text


def test_partial_report_names_the_failure_and_keeps_completed_questions(tmp_path):
    client, db_path = _app(tmp_path)
    eval_run_id = _seed_incomplete_report(tmp_path, db_path, status="partial")

    page = client.get(f"/reports/{eval_run_id}")

    assert "Partial: stopped at question 2 of 3" in page.text
    assert "g-in-fake-002" in page.text
    assert "RuntimeError: judge unavailable" in page.text
    assert "g-in-fake-001" in page.text
    assert page.text.count("Not final") == 3
    assert '<meta http-equiv="refresh"' not in page.text
    assert 'data-report-focus="back"' in page.text
    assert 'data-report-focus="export"' in page.text

    exported = client.get(f"/reports/{eval_run_id}/export")
    assert "Overall: PARTIAL" in exported.text
    assert "Progress: 1/3 questions completed" in exported.text
    assert "Stopped at question: 2 (g-in-fake-002)" in exported.text
    assert "Error: RuntimeError: judge unavailable" in exported.text


def test_partial_detail_uses_durable_rows_when_json_snapshot_is_stale(tmp_path):
    client, db_path = _app(tmp_path)
    eval_run_id = _seed_incomplete_report(tmp_path, db_path, status="partial")
    with repo.session(db_path) as conn:
        report_path = Path(repo.get_eval_run(conn, eval_run_id)["report_path"])
    stale = json.loads(report_path.read_text(encoding="utf-8"))
    stale["status"] = "running"
    stale["results"] = []
    report_path.write_text(json.dumps(stale), encoding="utf-8")

    page = client.get(f"/reports/{eval_run_id}")

    assert "out of date" in page.text
    assert "g-in-fake-001" in page.text
    assert "Yes" in page.text


def test_the_detail_page_shows_all_three_gates_and_every_question(tmp_path):
    client, db_path = _app(tmp_path)
    eval_run_id, _path = _seed_report(tmp_path, db_path)

    page = client.get(f"/reports/{eval_run_id}")

    assert page.status_code == 200
    assert "G1 Groundedness" in page.text
    assert "G2 Honest refusals" in page.text
    assert "G3 Sources on every answer" in page.text
    assert "g-in-fake-001" in page.text
    assert "g-out-fake-001" in page.text
    assert "Export as Markdown for the report annex" in page.text


# --- Error: recorded run, file missing ---------------------------------------


def test_a_missing_report_file_degrades_instead_of_blanking_the_page(tmp_path):
    client, db_path = _app(tmp_path)
    eval_run_id, path = _seed_report(tmp_path, db_path)
    os.remove(path)

    page = client.get(f"/reports/{eval_run_id}")

    assert page.status_code == 200
    assert "unavailable" in page.text.lower()
    assert path in page.text  # ErrorPanel shows the exact offending path
    # the summary scores (from the DB row, unaffected) still render
    assert "G1 Groundedness" in page.text
    assert "g-in-fake-001" in page.text  # DB degrade still lists every question


# --- Error: unknown id --------------------------------------------------


def test_an_unknown_report_id_is_a_404_naming_the_id(tmp_path):
    client, _db_path = _app(tmp_path)

    page = client.get("/reports/does-not-exist")

    assert page.status_code == 404
    assert "does-not-exist" in page.text


# --- Export --------------------------------------------------------------


def test_export_downloads_a_markdown_file_usable_in_the_annex(tmp_path):
    client, db_path = _app(tmp_path)
    eval_run_id, _path = _seed_report(tmp_path, db_path)

    response = client.get(f"/reports/{eval_run_id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.startswith("# Sanad evaluation report")
    assert "g-in-fake-001" in response.text


def test_export_of_an_unknown_id_is_a_404_not_an_empty_file(tmp_path):
    client, _db_path = _app(tmp_path)

    response = client.get("/reports/does-not-exist/export")

    assert response.status_code == 404


# --- F-15 answer feedback (V2, Low) -----------------------------------------
#
# The S3 half of the brief: a "reviewable" list, independent of the eval-run
# section above (ui/reports_screen.py's module note). Rows are written
# directly through db.repo.upsert_answer_feedback rather than via
# POST /chat/feedback -- the write path itself is exercised end to end in
# test_s1_chat_screen.py; this file is only about what S3 RENDERS from
# whatever is already stored, matching how _seed_incomplete_report above
# seeds eval_run/eval_result directly rather than running a real evaluation.


def _seed_feedback(
    db_path,
    *,
    workspace_name: str = "ws-feedback",
    verdict: str = "down",
    question: str = IN_QUESTION,
    comment: str | None = "Cited the wrong article.",
    created_at: str | None = None,
) -> None:
    with repo.session(db_path) as conn:
        ws_id = repo.create_workspace(conn, name=workspace_name, folder_path=str(db_path.parent))
        repo.upsert_answer_feedback(
            conn,
            workspace_id=ws_id,
            answer_key=repo.new_id(),
            question=question,
            answer_text=ANSWER_TEXT,
            verdict=verdict,
            comment=comment,
        )
        if created_at is not None:
            conn.execute(
                "UPDATE answer_feedback SET created_at = ? WHERE workspace_id = ?",
                (created_at, ws_id),
            )


def test_no_feedback_shows_the_empty_state(tmp_path):
    client, _db_path = _app(tmp_path)

    page = client.get("/reports")

    assert page.status_code == 200
    assert "No feedback yet" in page.text


def test_a_stored_feedback_row_shows_workspace_verdict_question_and_comment(tmp_path):
    client, db_path = _app(tmp_path)
    _seed_feedback(
        db_path,
        workspace_name="ws-feedback-visible",
        verdict="down",
        question=IN_QUESTION,
        comment="Cited the wrong article.",
    )

    page = client.get("/reports")
    visible = html.unescape(page.text)

    assert page.status_code == 200
    assert "No feedback yet" not in page.text
    assert "ws-feedback-visible" in page.text
    assert "Not helpful" in page.text
    assert IN_QUESTION in visible
    assert "Cited the wrong article." in page.text


def test_feedback_rows_are_listed_newest_first(tmp_path):
    """`page.index()` on the whole page is not enough here: the shell's own
    workspace selector (app.py's `_active`/`screen.workspace_options`)
    ALSO lists both workspace names, alphabetically, on every screen --
    "ws-a-newest" would sort before "ws-b-oldest" there regardless of
    feedback order, and a first version of this test compared indices on
    the whole page and passed even with `ORDER BY ... ASC` mutated in.
    Isolating the feedback section (everything after its own heading) is
    what makes this test about the FEEDBACK table's order, not the shell's."""
    client, db_path = _app(tmp_path)
    _seed_feedback(
        db_path, workspace_name="ws-oldest", created_at="2020-01-01T00:00:00+00:00"
    )
    _seed_feedback(
        db_path, workspace_name="ws-newest", created_at="2030-01-01T00:00:00+00:00"
    )

    page = client.get("/reports").text
    feedback_section = page.split(">Answer feedback<")[1]

    assert feedback_section.index("ws-newest") < feedback_section.index("ws-oldest")


def test_feedback_comment_containing_script_is_escaped_on_reports(tmp_path):
    """The same hostile-markup discipline test_s1_chat_screen.py's trace
    disclosure test applies to a comment a user typed: it must render as
    text, never as markup, wherever Reports shows it."""
    client, db_path = _app(tmp_path)
    hostile = "<script>alert('x')</script> not helpful"
    _seed_feedback(db_path, comment=hostile)

    page = client.get("/reports").text

    assert "<script>alert" not in page
    assert "&lt;script&gt;" in page


def test_a_missing_comment_shows_a_dash_not_a_blank_cell(tmp_path):
    """Isolated to the feedback section, not the whole page: the page
    `<title>` itself carries an unrelated em dash ("Reports — Sanad",
    base.html), so a whole-page check would pass even if the comment cell
    rendered Python's `None` literally instead -- the first version of
    this test did exactly that and missed it."""
    client, db_path = _app(tmp_path)
    _seed_feedback(db_path, verdict="up", comment=None)

    page = client.get("/reports").text
    feedback_section = page.split(">Answer feedback<")[1]

    assert "—" in feedback_section
    assert "None" not in feedback_section
