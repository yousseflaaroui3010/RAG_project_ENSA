"""The trace collector (ST-21, ADR-09): what F-10 will show.

F-10's promise is "the searches run, the files consulted, and the retries
used for that answer". Each of the three is derived from the recorded
steps rather than stored, so these tests are what stops the derivations
drifting apart from the steps they read.

The fixture is deliberately bigger than the property needs: a trace with
one search cannot tell an ordered list from an unordered one, and a trace
with one file cannot tell de-duplication from luck. That is the
"fixture too small for the property" shape this project has shipped
twice (BUILD-STATE, ST-14 and ST-16).
"""

from __future__ import annotations

from agent.trace import StepKind, Trace, TraceStep, rewords_in, searches_in

STEPS = (
    TraceStep(StepKind.SUMMARY, "no earlier turns in this session"),
    TraceStep(StepKind.REWRITE, "periode d'essai duree"),
    TraceStep(StepKind.SEARCH, "periode d'essai duree", ("code-du-travail.pdf",)),
    TraceStep(StepKind.GRADE, "passages do not address the question"),
    TraceStep(StepKind.REWORD, "essai cadre renouvellement"),
    TraceStep(
        StepKind.SEARCH,
        "essai cadre renouvellement",
        ("code-du-travail.pdf", "guide-cnss.docx"),
    ),
    TraceStep(StepKind.GRADE, "passages address the question"),
    TraceStep(StepKind.ANSWER, "answered from 2 source(s)"),
)
TRACE = Trace(trace_id="t-1", steps=STEPS)


def test_the_searches_are_listed_in_the_order_they_ran():
    """Order is the point: F-05 shows this list to a user as "what I
    looked for", and a reworded retry only makes sense after the search
    that provoked it."""
    assert TRACE.searches == ("periode d'essai duree", "essai cadre renouvellement")


def test_only_search_steps_count_as_searches():
    """The reworded query appears twice in the steps -- once as the REWORD
    that produced it, once as the SEARCH that used it. It is one search.
    A filter that matched on the text instead of the kind would double
    it."""
    assert TRACE.searches.count("essai cadre renouvellement") == 1


def test_files_consulted_are_de_duplicated_in_first_seen_order():
    """Two searches touched the labour code; it was consulted once. The
    CNSS guide came second and stays second."""
    assert TRACE.files_consulted == ("code-du-travail.pdf", "guide-cnss.docx")


def test_retries_counts_rewords_and_nothing_else():
    """Eight steps, two searches, one reword: the answer is 1, not 8 and
    not 2. A count of "steps after the first search" or "searches minus
    one" would agree with this trace by accident, which is why the next
    test exists."""
    assert TRACE.retries == 1


def test_a_trace_that_never_retried_reports_zero():
    """The zero case, asserted separately: `retries` is read by
    `route_after_grade` before any reword has happened, and a count that
    started at 1 would burn a retry on every question."""
    first_pass = Trace(trace_id="t-2", steps=STEPS[:4])

    assert first_pass.retries == 0
    assert first_pass.searches == ("periode d'essai duree",)


def test_an_empty_trace_answers_all_three_questions_without_raising():
    """A clarification never searches, so this is a real state and not a
    degenerate one -- it is what F-10 gets handed for a question the agent
    asked back about."""
    empty = Trace(trace_id="t-3")

    assert empty.searches == ()
    assert empty.files_consulted == ()
    assert empty.retries == 0


def test_the_free_functions_and_the_trace_properties_are_the_same_count():
    """The nodes call `rewords_in`/`searches_in` on a live list of steps
    while the run is still going; `Trace` exposes the same answers after.
    If those two ever disagreed, the ceiling would stop the loop at one
    number and the answer bubble would show another.

    HONEST ABOUT ITS OWN REACH, because a review pointed out that the
    docstring above oversells it: today `Trace.retries` is literally
    `return rewords_in(self.steps)`, so this comparison cannot fail and
    proves nothing about the current code. It is a REGRESSION guard, not
    a check: it exists to go red the day somebody gives `Trace` its own
    implementation of the count -- which is exactly how the two would come
    to disagree."""
    assert rewords_in(STEPS) == TRACE.retries
    assert searches_in(STEPS) == TRACE.searches
