"""ST-32 exit gate: one command's machinery, proven on a fake model.

Real credits are never spent by this file (docs/phase2/ENGINEERING-RULES.md: no API
keys in tests). Every port is a scripted fake, exactly like
`tests/unit/test_agent_graph.py`'s `_ports()`; `FakeScorer` satisfies
`evaluation.scoring.Scorer` with no model call at all, proving the runner,
the capture seam, and the DB/report persistence end to end. The judge
itself (`evaluation.scoring.LLMJudgeScorer`) is proven separately below
against `tests.fake_chat.ScriptedChat`, the project's standard scripted
double (docs/phase2/ENGINEERING-RULES.md: "no API keys in tests, fixtures, or CI").
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

import evaluation.runner as runner_module
from agent.ports import AgentPorts, AnswerNotCoveredError
from config import get_settings
from db import repo
from evaluation.capture import ask_and_capture
from evaluation.golden import GoldenRow, load_golden_set
from evaluation.runner import (
    EvalReport,
    EvaluationPartialError,
    EvaluationWorkspaceNotFoundError,
    QuestionResult,
    _aggregate,
    run_evaluation,
)
from evaluation.scoring import JudgeReplyError, LLMJudgeScorer, ScoreResult
from tests.fake_chat import ScriptedChat
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
LABELED_CONTEXT = f"[code.pdf -- Article 1]\n{PARENT_TEXT}"
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


def _write_partial_golden(tmp_path) -> None:
    _write_golden(tmp_path)
    path = tmp_path / "fake.jsonl"
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    second_in_scope = {**rows[0], "id": "g-in-fake-002"}
    rows.insert(1, second_in_scope)
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")


def _write_golden_out_first(tmp_path) -> None:
    _write_golden(tmp_path)
    path = tmp_path / "fake.jsonl"
    rows = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
    ]
    path.write_text(
        "\n".join(json.dumps(row) for row in reversed(rows)), encoding="utf-8"
    )


def _ports(
    *,
    out_of_scope_answerable: bool = False,
    raise_on: str | None = None,
    parent_text: str = PARENT_TEXT,
) -> AgentPorts:
    """Only the in-scope question grades as relevant, so the out-of-scope
    question exhausts the retry ceiling and the graph's own routing
    refuses it -- no port here fakes a refusal directly. Setting
    `out_of_scope_answerable` flips that, to exercise the failure path
    where a false-answer slips through."""

    def grade(question: str, _passages: object) -> bool:
        if question == IN_QUESTION:
            return True
        return out_of_scope_answerable

    def retrieve(_workspace_id: str, query: str):
        if raise_on == "retrieve":
            raise RuntimeError("the store is unreachable")
        return (HIT_A, HIT_B)

    def write_answer(_question: str, _passages, _parents):
        if raise_on == "write_answer":
            raise RuntimeError("the model timed out")
        if raise_on == "not_covered":
            raise AnswerNotCoveredError("the sections do not answer it")
        if raise_on == "interrupt":
            raise KeyboardInterrupt
        return ANSWER_TEXT

    return AgentPorts(
        summarize=lambda _history: "",
        clarify=lambda _question, _summary: None,
        rewrite=lambda question, _summary: (question,),
        retrieve=retrieve,
        grade=grade,
        reword=lambda _question, previous, _attempt: previous,
        fetch_parents=lambda _workspace_id, parent_ids: {
            pid: parent_text for pid in parent_ids
        },
        write_answer=write_answer,
    )


class FakeScorer:
    def __init__(self, groundedness: float = 1.0, relevancy: float = 0.8):
        self.groundedness = groundedness
        self.relevancy = relevancy
        self.calls: list[tuple] = []

    def score(self, *, question: str, answer_text: str, contexts) -> ScoreResult:
        self.calls.append((question, answer_text, tuple(contexts)))
        return ScoreResult(groundedness=self.groundedness, relevancy=self.relevancy)


class BlockingScorer(FakeScorer):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def score(self, *, question: str, answer_text: str, contexts) -> ScoreResult:
        self.started.set()
        self.release.wait(timeout=10)
        return super().score(
            question=question, answer_text=answer_text, contexts=contexts
        )


class FailingScorer(FakeScorer):
    def __init__(self):
        super().__init__()
        self.call_count = 0

    def score(self, *, question: str, answer_text: str, contexts) -> ScoreResult:
        self.call_count += 1
        if self.call_count == 2:
            raise RuntimeError("judge stopped at secret-value")
        return super().score(
            question=question, answer_text=answer_text, contexts=contexts
        )


def _workspace(tmp_path) -> tuple[str, object]:
    db_path = tmp_path / "sanad.db"
    with repo.session(db_path) as conn:
        ws_id = repo.create_workspace(conn, name="ws-eval", folder_path=str(tmp_path))
    return ws_id, db_path


# --- evaluation.golden ---------------------------------------------------


def test_load_golden_set_reads_every_row_of_every_file(tmp_path):
    _write_golden(tmp_path)
    rows = load_golden_set(tmp_path)
    assert {r.id for r in rows} == {"g-in-fake-001", "g-out-fake-001"}
    assert all(isinstance(r, GoldenRow) for r in rows)


def test_load_golden_set_raises_on_an_empty_folder(tmp_path):
    with pytest.raises(ValueError, match="no golden-set rows"):
        load_golden_set(tmp_path)


# --- evaluation.capture ---------------------------------------------------


def test_capture_dedupes_chunks_and_preserves_the_writer_source_label():
    ports = _ports()
    captured = ask_and_capture(ports, workspace_id="ws-hr", question=IN_QUESTION)
    assert captured.error is None
    assert captured.answer is not None
    assert captured.contexts == (LABELED_CONTEXT,)


def test_capture_is_empty_on_a_refusal():
    ports = _ports()
    captured = ask_and_capture(ports, workspace_id="ws-hr", question=OUT_QUESTION)
    assert captured.error is None
    assert captured.answer is not None
    assert captured.answer.refusal
    assert captured.contexts == ()


def test_capture_keeps_the_labeled_context_when_the_writer_declines():
    captured = ask_and_capture(
        _ports(raise_on="not_covered"),
        workspace_id="ws-hr",
        question=IN_QUESTION,
    )

    assert captured.error is None
    assert captured.answer is not None
    assert captured.answer.refusal
    assert captured.contexts == (LABELED_CONTEXT,)


def test_capture_records_the_error_instead_of_raising():
    ports = _ports(raise_on="write_answer")
    captured = ask_and_capture(ports, workspace_id="ws-hr", question=IN_QUESTION)
    assert captured.answer is None
    assert isinstance(captured.error, RuntimeError)


def test_capture_lets_ctrl_c_through_instead_of_recording_a_failed_row():
    """Ctrl+C lands mid-answer far more often than anywhere else, because
    answering is where the time goes. Swallowed here, it became one failed
    row and the run later reported itself completed."""
    with pytest.raises(KeyboardInterrupt):
        ask_and_capture(
            _ports(raise_on="interrupt"), workspace_id="ws-hr", question=IN_QUESTION
        )


def test_ctrl_c_during_an_answer_ends_the_run_partial_not_completed(tmp_path):
    _write_golden(tmp_path)
    ws_id, db_path = _workspace(tmp_path)

    with pytest.raises(KeyboardInterrupt):
        run_evaluation(
            workspace_id=ws_id,
            ports=_ports(raise_on="interrupt"),
            scorer=FakeScorer(),
            golden_dir=tmp_path,
            db_path=db_path,
            reports_dir=tmp_path / "reports",
        )

    with repo.session(db_path) as conn:
        run = repo.list_eval_runs(conn)[0]
        assert run["status"] == "partial"
        assert run["failed_question_number"] == 1


def test_ctrl_c_between_the_final_file_and_the_registry_leaves_no_completed_file(
    tmp_path, monkeypatch
):
    """Review of d790e05: the "completed" file is written before the
    registry agrees. A Ctrl+C in between left a full report saying
    completed -- which the release gate passes -- while Reports said
    Running. The file must end Partial instead."""
    _write_golden(tmp_path)
    ws_id, db_path = _workspace(tmp_path)
    real_save = runner_module._save_run_state

    def interrupt_on_completed(db, run_id, report):
        if report.status == "completed":
            raise KeyboardInterrupt
        return real_save(db, run_id, report)

    monkeypatch.setattr(runner_module, "_save_run_state", interrupt_on_completed)

    with pytest.raises(KeyboardInterrupt):
        run_evaluation(
            workspace_id=ws_id,
            ports=_ports(),
            scorer=FakeScorer(),
            golden_dir=tmp_path,
            db_path=db_path,
            reports_dir=tmp_path / "reports",
        )

    (report_file,) = (tmp_path / "reports").rglob("*.json")
    assert json.loads(report_file.read_text(encoding="utf-8"))["status"] == "partial"
    with repo.session(db_path) as conn:
        assert repo.list_eval_runs(conn)[0]["status"] == "partial"


def test_capture_format_error_becomes_one_failed_row_instead_of_stopping_batch():
    captured = ask_and_capture(
        _ports(parent_text=" "), workspace_id="ws-hr", question=IN_QUESTION
    )

    assert captured.answer is None
    assert isinstance(captured.error, ValueError)
    assert "no section text" in str(captured.error)


# --- evaluation.scoring ----------------------------------------------------


def test_llm_judge_scorer_parses_the_two_scores_in_either_order():
    """Order-independent by design (evaluation/scoring.py's `_GROUNDEDNESS`
    / `_RELEVANCY` docstring): a model naming RELEVANCY first must parse
    the same as one naming GROUNDEDNESS first, and the prompt sent is the
    registry entry, not an inline string."""
    chat = ScriptedChat("RELEVANCY: 0.80\nGROUNDEDNESS: 0.95")
    scorer = LLMJudgeScorer(chat)

    result = scorer.score(
        question=IN_QUESTION, answer_text=ANSWER_TEXT, contexts=(PARENT_TEXT,)
    )

    assert result == ScoreResult(groundedness=0.95, relevancy=0.80)
    system, user = chat.calls[0]
    assert "GROUNDEDNESS" in system  # came from prompts/eval-judge/PROMPT.md
    assert IN_QUESTION in user
    assert ANSWER_TEXT in user
    assert PARENT_TEXT in user


def test_llm_judge_scorer_raises_loudly_on_an_unparseable_reply():
    """A confused reply must never be silently read as a score -- the same
    rule `agent.grading.GraderReplyError` enforces for the relevance
    grader, and for the same reason: a 0.00-1.00 number looks exactly as
    confident whether or not anything computed it."""
    chat = ScriptedChat("I cannot judge this without more context.")
    scorer = LLMJudgeScorer(chat)

    with pytest.raises(JudgeReplyError, match="GROUNDEDNESS"):
        scorer.score(
            question=IN_QUESTION, answer_text=ANSWER_TEXT, contexts=(PARENT_TEXT,)
        )


# --- evaluation.runner: happy path -----------------------------------------


def test_a_clean_run_passes_all_three_gates_and_persists_both_places(tmp_path):
    _write_golden(tmp_path)
    ws_id, db_path = _workspace(tmp_path)
    settings = get_settings()

    report = run_evaluation(
        workspace_id=ws_id,
        ports=_ports(),
        scorer=FakeScorer(groundedness=1.0, relevancy=0.8),
        golden_dir=tmp_path,
        db_path=db_path,
        reports_dir=tmp_path / "reports",
    )

    assert report.refusal_pass == report.refusal_total == 1
    assert report.sources_pass == report.sources_total == 1
    assert report.groundedness == pytest.approx(1.0)
    assert report.relevancy == pytest.approx(0.8)
    assert report.grounded_pass == report.grounded_total == 1
    assert report.grounded_pass / report.grounded_total >= settings.eval_groundedness_threshold
    assert report.passed is True
    assert report.failing_question_ids == ()
    assert report.status == "completed"
    assert report.question_total == 2

    # the report file
    assert report.report_path is not None
    on_disk = json.loads(open(report.report_path, encoding="utf-8").read())
    assert on_disk["workspace_id"] == ws_id
    assert on_disk["passed"] is True
    assert on_disk["status"] == "completed"
    assert not Path(f"{report.report_path}.tmp").exists()
    assert {r["question_id"] for r in on_disk["results"]} == {
        "g-in-fake-001",
        "g-out-fake-001",
    }
    saved = {r["question_id"]: r for r in on_disk["results"]}
    assert saved["g-in-fake-001"]["answer_text"] == ANSWER_TEXT
    assert saved["g-out-fake-001"]["answer_text"]

    # the database
    conn = repo.get_connection(db_path)
    run_row = conn.execute(
        "SELECT * FROM eval_run WHERE workspace_id = ?", (ws_id,)
    ).fetchone()
    assert run_row is not None
    assert bool(run_row["passed"]) is True
    assert run_row["status"] == "completed"
    assert run_row["question_total"] == 2
    result_rows = conn.execute(
        "SELECT * FROM eval_result WHERE eval_run_id = ?", (run_row["id"],)
    ).fetchall()
    assert len(result_rows) == 2
    conn.close()


def test_running_row_is_visible_before_the_first_question_finishes(tmp_path):
    _write_golden(tmp_path)
    ws_id, db_path = _workspace(tmp_path)
    scorer = BlockingScorer()
    finished: list[EvalReport] = []

    thread = threading.Thread(
        target=lambda: finished.append(
            run_evaluation(
                workspace_id=ws_id,
                ports=_ports(),
                scorer=scorer,
                golden_dir=tmp_path,
                db_path=db_path,
                reports_dir=tmp_path / "reports",
            )
        )
    )
    thread.start()
    assert scorer.started.wait(timeout=10)
    try:
        with repo.session(db_path) as conn:
            runs = repo.list_eval_runs(conn)
            assert len(runs) == 1
            assert runs[0]["status"] == "running"
            assert runs[0]["question_total"] == 2
            assert repo.eval_run_progress(conn, runs[0]["id"]) == 0
    finally:
        scorer.release.set()
        thread.join(timeout=10)

    assert not thread.is_alive()
    assert finished[0].status == "completed"


def test_running_totals_are_current_after_each_committed_question(tmp_path):
    _write_golden_out_first(tmp_path)
    ws_id, db_path = _workspace(tmp_path)
    scorer = BlockingScorer()
    thread = threading.Thread(
        target=lambda: run_evaluation(
            workspace_id=ws_id,
            ports=_ports(),
            scorer=scorer,
            golden_dir=tmp_path,
            db_path=db_path,
            reports_dir=tmp_path / "reports",
        )
    )

    thread.start()
    assert scorer.started.wait(timeout=10)
    try:
        with repo.session(db_path) as conn:
            run = repo.list_eval_runs(conn)[0]
            assert repo.eval_run_progress(conn, run["id"]) == 1
            assert run["refusal_pass"] == 1
            assert run["refusal_total"] == 1
    finally:
        scorer.release.set()
        thread.join(timeout=10)

    assert not thread.is_alive()


def test_fatal_question_failure_keeps_prior_rows_and_marks_partial(
    tmp_path, monkeypatch
):
    _write_partial_golden(tmp_path)
    ws_id, db_path = _workspace(tmp_path)
    monkeypatch.setattr(get_settings(), "cloud_api_key", "secret-value")

    with pytest.raises(EvaluationPartialError) as raised:
        run_evaluation(
            workspace_id=ws_id,
            ports=_ports(),
            scorer=FailingScorer(),
            golden_dir=tmp_path,
            db_path=db_path,
            reports_dir=tmp_path / "reports",
        )

    report = raised.value.report
    assert report.status == "partial"
    assert report.question_total == 3
    assert report.failed_question_number == 2
    assert report.failed_question_id == "g-in-fake-002"
    assert "secret-value" not in (report.error or "")
    assert len(report.results) == 1

    with repo.session(db_path) as conn:
        run = repo.list_eval_runs(conn)[0]
        assert run["status"] == "partial"
        assert run["failed_question_number"] == 2
        assert run["failed_question_id"] == "g-in-fake-002"
        assert "secret-value" not in run["error"]
        assert repo.eval_run_progress(conn, run["id"]) == 1
        saved = repo.list_eval_results(conn, run["id"])
        assert saved[0]["answer_text"] == ANSWER_TEXT

    on_disk = json.loads(open(report.report_path, encoding="utf-8").read())
    assert on_disk["status"] == "partial"
    assert on_disk["failed_question_number"] == 2
    assert [row["question_id"] for row in on_disk["results"]] == ["g-in-fake-001"]
    assert not Path(f"{report.report_path}.tmp").exists()


def test_report_write_failure_marks_the_run_partial_and_keeps_saved_row(
    tmp_path, monkeypatch
):
    _write_golden(tmp_path)
    ws_id, db_path = _workspace(tmp_path)
    real_write = runner_module._write_report
    calls = 0

    def fail_second_write(report, path):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("report disk unavailable")
        real_write(report, path)

    monkeypatch.setattr(runner_module, "_write_report", fail_second_write)

    with pytest.raises(EvaluationPartialError) as raised:
        run_evaluation(
            workspace_id=ws_id,
            ports=_ports(),
            scorer=FakeScorer(),
            golden_dir=tmp_path,
            db_path=db_path,
            reports_dir=tmp_path / "reports",
        )

    assert raised.value.__cause__ is None
    assert raised.value.report.status == "partial"
    assert raised.value.report.failed_question_number == 1
    with repo.session(db_path) as conn:
        run = repo.list_eval_runs(conn)[0]
        assert run["status"] == "partial"
        assert repo.eval_run_progress(conn, run["id"]) == 1
    saved = json.loads(
        Path(raised.value.report.report_path).read_text(encoding="utf-8")
    )
    assert saved["status"] == "partial"
    assert len(saved["results"]) == 1


def _result(
    question_id: str,
    *,
    groundedness: float | None,
    answer_kind: str = "answer",
    kind: str = "in_scope",
    sources_present: bool | None = True,
) -> QuestionResult:
    return QuestionResult(
        question_id=question_id,
        kind=kind,
        answer_kind=answer_kind,
        answer_text="saved output",
        passed=groundedness == 1.0 if kind == "in_scope" else answer_kind == "refusal",
        groundedness=groundedness,
        relevancy=1.0 if groundedness is not None else None,
        sources_present=sources_present,
    )


def test_g1_counts_fully_grounded_answers_instead_of_averaging_partial_scores():
    results = tuple(
        [_result(f"g-in-{number:03}", groundedness=1.0) for number in range(8)]
        + [_result("g-in-008", groundedness=0.95), _result("g-in-009", groundedness=0.95)]
        + [
            _result(
                "g-out-001",
                kind="out_of_scope",
                answer_kind="refusal",
                groundedness=None,
                sources_present=None,
            )
        ]
    )

    report = _aggregate("ws-1", "2026-09-10T00:00:00+00:00", results)

    assert report.groundedness == pytest.approx(0.99)
    assert (report.grounded_pass, report.grounded_total) == (8, 10)
    assert report.passed is False


def test_g1_passes_at_exactly_nine_fully_grounded_answers_out_of_ten():
    results = tuple(
        [_result(f"g-in-{number:03}", groundedness=1.0) for number in range(9)]
        + [_result("g-in-009", groundedness=0.1)]
        + [
            _result(
                "g-out-001",
                kind="out_of_scope",
                answer_kind="refusal",
                groundedness=None,
                sources_present=None,
            )
        ]
    )

    report = _aggregate("ws-1", "2026-09-10T00:00:00+00:00", results)

    assert report.groundedness == pytest.approx(0.91)
    assert (report.grounded_pass, report.grounded_total) == (9, 10)
    assert report.passed is True


def test_an_in_scope_refusal_fails_g1_without_becoming_a_g3_source_miss():
    results = (
        _result("g-in-001", groundedness=1.0),
        _result(
            "g-in-002",
            groundedness=None,
            answer_kind="refusal",
            sources_present=None,
        ),
        _result(
            "g-out-001",
            kind="out_of_scope",
            answer_kind="refusal",
            groundedness=None,
            sources_present=None,
        ),
    )

    report = _aggregate("ws-1", "2026-09-10T00:00:00+00:00", results)

    assert (report.sources_pass, report.sources_total) == (1, 1)
    assert report.passed is False


# --- evaluation.runner: failure path ----------------------------------------


def test_a_false_answer_on_an_out_of_scope_row_fails_g2_and_is_named(tmp_path):
    _write_golden(tmp_path)
    ws_id, db_path = _workspace(tmp_path)

    report = run_evaluation(
        workspace_id=ws_id,
        ports=_ports(out_of_scope_answerable=True),
        scorer=FakeScorer(),
        golden_dir=tmp_path,
        db_path=db_path,
        reports_dir=tmp_path / "reports",
    )

    assert report.refusal_pass == 0
    assert report.refusal_total == 1
    assert report.sources_pass == report.sources_total == 2
    assert report.passed is False
    assert "g-out-fake-001" in report.failing_question_ids
    # the in-scope row is unaffected
    assert "g-in-fake-001" not in report.failing_question_ids


def test_a_question_that_raises_is_recorded_as_a_failing_row_not_a_crash(tmp_path):
    _write_golden(tmp_path)
    ws_id, db_path = _workspace(tmp_path)

    report = run_evaluation(
        workspace_id=ws_id,
        ports=_ports(raise_on="retrieve"),
        scorer=FakeScorer(),
        golden_dir=tmp_path,
        db_path=db_path,
        reports_dir=tmp_path / "reports",
    )

    assert len(report.results) == 2
    failed = {r.question_id: r for r in report.results}
    assert failed["g-in-fake-001"].error is not None
    assert failed["g-in-fake-001"].passed is False
    assert "g-in-fake-001" in report.failing_question_ids
    assert report.passed is False


def test_an_unknown_workspace_stops_before_any_question_or_score(tmp_path):
    _write_golden(tmp_path)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    scorer = FakeScorer()

    with pytest.raises(EvaluationWorkspaceNotFoundError, match="missing-workspace"):
        run_evaluation(
            workspace_id="missing-workspace",
            ports=_ports(),
            scorer=scorer,
            golden_dir=tmp_path,
            db_path=db_path,
            reports_dir=tmp_path / "reports",
        )

    assert scorer.calls == []
    assert not (tmp_path / "reports").exists()
