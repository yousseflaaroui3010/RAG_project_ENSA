"""S6 Reports dashboard: the numbers behind the tiles, lines and grid.

A chart that draws the wrong run, or the right run against the wrong
threshold, looks exactly as confident as a correct one. These pin the
decisions -- which run, which ratio, which outcome, where each point sits
-- so the template only has to draw what it is handed.
"""

from __future__ import annotations

import dataclasses

import pytest

from config import get_settings
from ui.reports_screen import (
    SPARK_HEIGHT,
    FeedbackRow,
    QuestionRow,
    ReportSummary,
    dashboard,
    question_groups,
)

BASE = ReportSummary(
    id="run",
    workspace_id="ws",
    workspace_name="HR",
    run_at="2026-09-10T10:00:00+00:00",
    groundedness=None,
    groundedness_label="",
    sources_label="",
    relevancy=None,
    refusal_pass=20,
    refusal_total=20,
    passed=True,
    status="completed",
    question_total=60,
    completed_count=60,
    status_label="Pass",
    status_tone="positive",
    status_shape="filled-circle",
    failed_question_number=None,
    failed_question_id=None,
    error=None,
    report_path=None,
    grounded_pass=38,
    grounded_total=40,
    sources_pass=38,
    sources_total=38,
)


def run(**changes) -> ReportSummary:
    return dataclasses.replace(BASE, **changes)


def feedback(verdict: str) -> FeedbackRow:
    return FeedbackRow(
        id=verdict, workspace_id="ws", workspace_name="HR", created_at="2026-09-10",
        verdict=verdict,
        verdict_label="", question="q", comment_label="—",
    )


def test_no_completed_run_means_no_dashboard_even_with_running_or_partial_runs():
    reports = [run(id="a", status="running"), run(id="b", status="partial")]

    assert dashboard(reports, []) is None


def test_the_tiles_describe_the_latest_completed_run_by_date_not_list_order():
    newest = run(id="new", run_at="2026-09-13T10:00:00+00:00", grounded_pass=36)
    older = run(id="old", run_at="2026-09-01T10:00:00+00:00", grounded_pass=40)
    running = run(id="live", run_at="2026-09-14T10:00:00+00:00", status="running")

    d = dashboard([older, running, newest], [])

    assert d.latest.id == "new"
    assert d.gates[0].value_label == "36/40"


@pytest.mark.parametrize(("grounded", "passed"), [(36, True), (35, False)])
def test_g1_passes_exactly_at_the_configured_threshold(grounded, passed):
    assert get_settings().eval_groundedness_threshold == 0.90, "fixture assumes 90%"

    g1 = dashboard([run(grounded_pass=grounded)], []).gates[0]

    assert g1.passed is passed
    assert g1.threshold_label == "90%"


def test_g2_and_g3_need_every_question():
    d = dashboard([run(refusal_pass=19, sources_pass=38)], [])

    assert [g.code for g in d.gates] == ["G1", "G2", "G3"]
    assert d.gates[1].passed is False
    assert d.gates[2].passed is True


def test_missing_counts_say_not_judged_instead_of_drawing_a_ratio():
    g3 = dashboard([run(sources_pass=None, sources_total=None)], []).gates[2]

    assert (g3.ratio, g3.passed, g3.value_label) == (None, None, "—")


def test_one_completed_run_draws_no_trend_line():
    assert all(g.spark is None for g in dashboard([run()], []).gates)


def test_the_trend_line_places_each_run_by_its_ratio_oldest_first():
    runs = [
        run(id="1", run_at="2026-09-01", grounded_pass=40),
        run(id="2", run_at="2026-09-02", grounded_pass=0),
        run(id="3", run_at="2026-09-03", grounded_pass=20),
    ]

    spark = dashboard(runs, []).gates[0].spark

    ys = [float(pair.split(",")[1]) for pair in spark.points.split()]
    assert ys[0] < ys[2] < ys[1], "100% must sit highest, 0% lowest, 50% between"
    assert ys[1] == SPARK_HEIGHT - 5 and ys[0] == 5
    assert spark.run_count == 3
    assert [m[2] for m in spark.marks] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert [m[3] for m in spark.marks] == ["100%", "0%", "50%"]
    assert (spark.last_x, spark.last_y) == (spark.marks[-1][0], spark.marks[-1][1])


def test_the_threshold_line_sits_at_the_threshold_and_is_absent_at_100_percent():
    runs = [run(id="1", run_at="2026-09-01"), run(id="2", run_at="2026-09-02")]

    d = dashboard(runs, [])

    assert d.gates[0].spark.threshold_y == pytest.approx(SPARK_HEIGHT - 5 - 0.9 * 30)
    assert d.gates[1].spark.threshold_y is None


def test_runs_without_counts_are_skipped_by_the_line_not_drawn_as_zero():
    runs = [
        run(id="1", run_at="2026-09-01", sources_pass=38),
        run(id="2", run_at="2026-09-02", sources_pass=None, sources_total=None),
        run(id="3", run_at="2026-09-03", sources_pass=19),
    ]

    spark = dashboard(runs, []).gates[2].spark

    assert spark.run_count == 2
    assert [m[3] for m in spark.marks] == ["100%", "50%"]


def test_the_feedback_tile_counts_helpful_answers():
    tile = dashboard([run()], [feedback("up"), feedback("down"), feedback("up")]).feedback

    assert (tile.helpful, tile.total) == (2, 3)
    assert tile.ratio == pytest.approx(2 / 3)
    assert dashboard([run()], []).feedback.ratio is None


def _question(qid: str, kind_label: str, passed: bool) -> QuestionRow:
    return QuestionRow(
        question_id=qid, kind_label=kind_label, answer_kind=None, passed=passed,
        groundedness_label="", relevancy_label="", sources_label="", error=None,
    )


def test_the_question_map_groups_in_scope_first_in_table_order_with_pass_counts():
    questions = [
        _question("g-out-001", "Out of scope", True),
        _question("g-in-002", "In scope", False),
        _question("g-in-001", "In scope", True),
    ]

    groups = question_groups(questions)

    assert [g.kind_label for g in groups] == ["In scope", "Out of scope"]
    assert [q.question_id for q in groups[0].questions] == ["g-in-002", "g-in-001"]
    assert (groups[0].passed, groups[1].passed) == (1, 1)
