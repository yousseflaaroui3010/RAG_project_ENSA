"""ST-32 exit gate: one command's machinery, proven on a fake model.

Real credits are never spent by this file (docs/phase2/CLAUDE.md: no API
keys in tests). Every port is a scripted fake, exactly like
`tests/unit/test_agent_graph.py`'s `_ports()`, and `FakeScorer` satisfies
`evaluation.scoring.Scorer` with no RAGAS import anywhere in this module
-- proving the runner, the capture seam, and the DB/report persistence
end to end while `evaluation.scoring.build_ragas_scorer` stays the one
thing this story could not prove live (see that module's docstring).
"""

from __future__ import annotations

import json

import pytest

from agent.ports import AgentPorts
from config import get_settings
from db import repo
from evaluation.capture import ask_and_capture
from evaluation.golden import GoldenRow, load_golden_set
from evaluation.runner import run_evaluation
from evaluation.scoring import ScoreResult, ScorerUnavailableError, build_ragas_scorer
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


def _ports(*, out_of_scope_answerable: bool = False, raise_on: str | None = None) -> AgentPorts:
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
        return ANSWER_TEXT

    return AgentPorts(
        summarize=lambda _history: "",
        clarify=lambda _question, _summary: None,
        rewrite=lambda question, _summary: (question,),
        retrieve=retrieve,
        grade=grade,
        reword=lambda _question, previous, _attempt: previous,
        fetch_parents=lambda _workspace_id, parent_ids: {pid: PARENT_TEXT for pid in parent_ids},
        write_answer=write_answer,
    )


class FakeScorer:
    def __init__(self, groundedness: float = 0.95, relevancy: float = 0.8):
        self.groundedness = groundedness
        self.relevancy = relevancy
        self.calls: list[tuple] = []

    def score(self, *, question: str, answer_text: str, contexts) -> ScoreResult:
        self.calls.append((question, answer_text, tuple(contexts)))
        return ScoreResult(groundedness=self.groundedness, relevancy=self.relevancy)


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


def test_capture_dedupes_two_chunks_of_one_section_into_one_context():
    ports = _ports()
    captured = ask_and_capture(ports, workspace_id="ws-hr", question=IN_QUESTION)
    assert captured.error is None
    assert captured.answer is not None
    assert captured.contexts == (PARENT_TEXT,)


def test_capture_is_empty_on_a_refusal():
    ports = _ports()
    captured = ask_and_capture(ports, workspace_id="ws-hr", question=OUT_QUESTION)
    assert captured.error is None
    assert captured.answer is not None
    assert captured.answer.refusal
    assert captured.contexts == ()


def test_capture_records_the_error_instead_of_raising():
    ports = _ports(raise_on="write_answer")
    captured = ask_and_capture(ports, workspace_id="ws-hr", question=IN_QUESTION)
    assert captured.answer is None
    assert isinstance(captured.error, RuntimeError)


# --- evaluation.scoring ----------------------------------------------------


def test_build_ragas_scorer_raises_until_the_dependency_is_resolved():
    """This assertion is currently TRUE, not aspirational: `import ragas`
    itself fails on this project's pinned langchain-community (see
    evaluation/scoring.py's docstring). Proven by running it, not assumed."""
    with pytest.raises(ScorerUnavailableError, match="ragas"):
        build_ragas_scorer()


# --- evaluation.runner: happy path -----------------------------------------


def test_a_clean_run_passes_all_three_gates_and_persists_both_places(tmp_path):
    _write_golden(tmp_path)
    ws_id, db_path = _workspace(tmp_path)
    settings = get_settings()

    report = run_evaluation(
        workspace_id=ws_id,
        ports=_ports(),
        scorer=FakeScorer(groundedness=0.95, relevancy=0.8),
        golden_dir=tmp_path,
        db_path=db_path,
        reports_dir=tmp_path / "reports",
    )

    assert report.refusal_pass == report.refusal_total == 1
    assert report.sources_pass == report.sources_total == 1
    assert report.groundedness == pytest.approx(0.95)
    assert report.relevancy == pytest.approx(0.8)
    assert report.groundedness >= settings.eval_groundedness_threshold
    assert report.passed is True
    assert report.failing_question_ids == ()

    # the report file
    assert report.report_path is not None
    on_disk = json.loads(open(report.report_path, encoding="utf-8").read())
    assert on_disk["workspace_id"] == ws_id
    assert on_disk["passed"] is True
    assert {r["question_id"] for r in on_disk["results"]} == {
        "g-in-fake-001",
        "g-out-fake-001",
    }

    # the database
    conn = repo.get_connection(db_path)
    run_row = conn.execute(
        "SELECT * FROM eval_run WHERE workspace_id = ?", (ws_id,)
    ).fetchone()
    assert run_row is not None
    assert bool(run_row["passed"]) is True
    result_rows = conn.execute(
        "SELECT * FROM eval_result WHERE eval_run_id = ?", (run_row["id"],)
    ).fetchall()
    assert len(result_rows) == 2
    conn.close()


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
