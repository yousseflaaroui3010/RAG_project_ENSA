"""ST-33: the release gate. Proves each of the three PRD gates (G1
groundedness, G2 refusals, G3 sources) can independently FAIL, then that a
clean report PASSES -- one passing test proves nothing about the other two
(docs/phase2/CLAUDE.md / this project's own rule).

`evaluation.gate.evaluate_report` takes a parsed report dict, the exact
shape `evaluation.runner.EvalReport.to_json()` writes. A hand-built dict is
used rather than a live `run_evaluation` call because a G3-only miss is
structurally unreachable through the real pipeline (`Answer.__post_init__`
refuses to build a sourceless kind=ANSWER `Answer` at all) -- so proving
this gate catches it needs a fixture, and a fixture also makes the CLI
tests below immune to accidentally exercising a real model.
"""

from __future__ import annotations

import json

from config import get_settings
from evaluation.gate import evaluate_report
from scripts.release_gate import main as gate_main

THRESHOLD = get_settings().eval_groundedness_threshold
ABOVE = min(1.0, THRESHOLD + 0.05)
BELOW = max(0.0, THRESHOLD - 0.20)


def _clean_report() -> dict:
    """One in-scope row, one out-of-scope row, both fully passing all
    three gates -- the baseline every failure test mutates one field of."""
    return {
        "workspace_id": "ws-1",
        "run_at": "2026-09-05T10:00:00+00:00",
        "groundedness": ABOVE,
        "relevancy": 0.8,
        "refusal_pass": 1,
        "refusal_total": 1,
        "sources_pass": 1,
        "sources_total": 1,
        "passed": True,
        "failing_question_ids": [],
        "results": [
            {
                "question_id": "g-in-001",
                "kind": "in_scope",
                "answer_kind": "answer",
                "passed": True,
                "groundedness": ABOVE,
                "relevancy": 0.8,
                "sources_present": True,
                "error": None,
            },
            {
                "question_id": "g-out-001",
                "kind": "out_of_scope",
                "answer_kind": "refusal",
                "passed": True,
                "groundedness": None,
                "relevancy": None,
                "sources_present": None,
                "error": None,
            },
        ],
    }


# --- the clean pass ----------------------------------------------------------


def test_a_clean_report_passes_all_three_gates_and_names_no_failures():
    verdict = evaluate_report(_clean_report())

    assert verdict.g1_passed is True
    assert verdict.g2_passed is True
    assert verdict.g3_passed is True
    assert verdict.passed is True
    assert verdict.failing_question_ids == ()


# --- G1: groundedness ---------------------------------------------------------


def test_g1_fails_when_overall_groundedness_is_below_threshold():
    report = _clean_report()
    report["groundedness"] = BELOW
    report["results"][0]["groundedness"] = BELOW
    report["results"][0]["passed"] = False

    verdict = evaluate_report(report)

    assert verdict.g1_passed is False
    assert verdict.g1_failing == ("g-in-001",)
    assert verdict.passed is False
    # isolated: G2 and G3 are untouched by this row's groundedness miss
    assert verdict.g2_passed is True
    assert verdict.g3_passed is True
    assert verdict.failing_question_ids == ("g-in-001",)


def test_g1_fails_when_groundedness_is_missing_entirely():
    """An empty/never-scored report must not read as a pass by `None >=
    threshold` accidentally being true -- it never is in Python, but the
    explicit `is not None` guard is what makes that a decision, not luck."""
    report = _clean_report()
    report["groundedness"] = None

    verdict = evaluate_report(report)

    assert verdict.g1_passed is False
    assert verdict.passed is False


# --- G2: refusals --------------------------------------------------------------


def test_g2_fails_when_an_out_of_scope_question_is_not_refused():
    report = _clean_report()
    report["refusal_pass"] = 0
    report["results"][1]["passed"] = False
    report["results"][1]["answer_kind"] = "answer"

    verdict = evaluate_report(report)

    assert verdict.g2_passed is False
    assert verdict.g2_failing == ("g-out-001",)
    assert verdict.passed is False
    # isolated: G1 and G3 are untouched
    assert verdict.g1_passed is True
    assert verdict.g3_passed is True


def test_g2_fails_rather_than_vacuously_passing_on_zero_out_of_scope_rows():
    report = _clean_report()
    report["refusal_pass"] = 0
    report["refusal_total"] = 0

    verdict = evaluate_report(report)

    assert verdict.g2_passed is False


# --- G3: sources -----------------------------------------------------------


def test_g3_fails_when_an_answer_is_missing_its_source():
    report = _clean_report()
    report["sources_pass"] = 0
    report["results"][0]["sources_present"] = False

    verdict = evaluate_report(report)

    assert verdict.g3_passed is False
    assert verdict.g3_failing == ("g-in-001",)
    assert verdict.passed is False
    # isolated: G1 and G2 are untouched -- this row's groundedness/refusal
    # fields are both still fully passing, only its sourcing is not
    assert verdict.g1_passed is True
    assert verdict.g2_passed is True


def test_g3_fails_rather_than_vacuously_passing_on_zero_sourced_rows():
    report = _clean_report()
    report["sources_pass"] = 0
    report["sources_total"] = 0

    verdict = evaluate_report(report)

    assert verdict.g3_passed is False


# --- a row can miss more than one gate at once --------------------------------


def test_a_refused_in_scope_row_is_named_under_both_g1_and_g3():
    report = _clean_report()
    report["groundedness"] = None
    report["results"][0]["passed"] = False
    report["results"][0]["answer_kind"] = "refusal"
    report["results"][0]["groundedness"] = None
    report["results"][0]["sources_present"] = False

    verdict = evaluate_report(report)

    assert "g-in-001" in verdict.g1_failing
    assert "g-in-001" in verdict.g3_failing
    # named once, not twice, in the combined list
    assert verdict.failing_question_ids.count("g-in-001") == 1


# --- the CLI wrapper -----------------------------------------------------------


def test_cli_exits_zero_and_prints_pass_on_a_clean_report(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(_clean_report()), encoding="utf-8")

    exit_code = gate_main(["--report", str(report_path)])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert "RELEASE GATE: PASS" in out


def test_cli_exits_one_and_lists_the_failing_question_on_a_g2_miss(tmp_path, capsys):
    report = _clean_report()
    report["refusal_pass"] = 0
    report["results"][1]["passed"] = False
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")

    exit_code = gate_main(["--report", str(report_path)])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "RELEASE GATE: FAIL" in out
    assert "g-out-001" in out


def test_latest_report_picks_the_lexicographically_last_run(tmp_path):
    """Report file names are the run's ISO-8601 timestamp with `:` swapped
    for `-` (`evaluation.runner._report_path`), which still sorts in run
    order as a string -- exercised directly rather than through `main`, so
    this test does not depend on the operator's real `data/reports/`."""
    from scripts.release_gate import _latest_report

    reports_dir = tmp_path / "reports"
    ws_dir = reports_dir / "ws-1"
    ws_dir.mkdir(parents=True)
    (ws_dir / "2026-09-01T00-00-00.json").write_text(
        json.dumps({**_clean_report(), "groundedness": BELOW}), encoding="utf-8"
    )
    (ws_dir / "2026-09-05T00-00-00.json").write_text(
        json.dumps(_clean_report()), encoding="utf-8"
    )

    latest = _latest_report("ws-1", reports_dir=reports_dir)

    assert latest.name == "2026-09-05T00-00-00.json"


def test_cli_reports_a_missing_report_file_as_a_clean_failure_not_a_crash(tmp_path, capsys):
    missing = tmp_path / "does-not-exist.json"

    exit_code = gate_main(["--report", str(missing)])

    out = capsys.readouterr().out
    assert exit_code == 1
    assert "cannot run the release gate" in out
