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
