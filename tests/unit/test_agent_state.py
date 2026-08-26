"""The answer contract (ST-21): an answer without sources cannot exist.

Reference: docs/phase2/openapi.yaml `Answer` ("sources: non-empty whenever
kind is answer -- application invariant, G3"), docs/phase2/CLAUDE.md ("an
answer object without at least one source does not render as final"), and
PRD F-03 ("every answer cites file name and section label").

The rule is written in three documents. These tests are the fourth place,
and the only one that can fail.
"""

from __future__ import annotations

import pytest

from agent.state import Answer, AnswerKind, Source
from agent.trace import StepKind, Trace, TraceStep

TRACE = Trace(
    trace_id="t-1",
    steps=(
        TraceStep(StepKind.SEARCH, "periode d'essai"),
        TraceStep(StepKind.REWORD, "duree essai cadre"),
        TraceStep(StepKind.SEARCH, "duree essai cadre"),
    ),
)
SOURCE = Source(file_name="code-du-travail.pdf", section_label="Article 13")


def _answer(**overrides) -> Answer:
    fields = {
        "kind": AnswerKind.ANSWER,
        "text": "Trois mois.",
        "sources": (SOURCE,),
        "session_id": "s-1",
        "trace": TRACE,
    }
    return Answer(**{**fields, **overrides})


def test_an_answer_with_no_sources_cannot_be_built():
    """G3, enforced at the only place an answer is made. The message names
    the route out, because the caller's fix is not "add a source" -- it is
    to refuse instead."""
    with pytest.raises(ValueError, match="no sources"):
        _answer(sources=())


def test_a_refusal_and_a_clarification_may_carry_no_sources():
    """The counterpart, so the rule cannot degenerate into "everything
    needs a source". A refusal that had to cite something would have to
    cite the passages it just judged irrelevant."""
    refusal = _answer(kind=AnswerKind.REFUSAL, text="Not covered here.", sources=())
    clarification = _answer(
        kind=AnswerKind.CLARIFICATION, text="Which contract?", sources=()
    )

    assert refusal.sources == ()
    assert clarification.sources == ()


@pytest.mark.parametrize("text", ["", "   ", "\n\t "], ids=["empty", "spaces", "blank"])
def test_an_answer_with_no_text_cannot_be_built(text):
    """UX spec 6.2 gives each assistant variant a text body. Whitespace
    is checked as well as emptiness because a model returning "\\n" is the
    realistic version of this failure, and it is truthy."""
    with pytest.raises(ValueError, match="no text"):
        _answer(kind=AnswerKind.REFUSAL, text=text, sources=())


def test_the_refusal_flag_is_read_off_the_kind():
    """openapi carries `kind` and `refusal` separately, so the API can
    serve both. They are one value here: a refusal whose flag said False
    would render as an answer with no sources."""
    assert _answer().refusal is False
    assert _answer(kind=AnswerKind.REFUSAL, sources=()).refusal is True
    assert _answer(kind=AnswerKind.CLARIFICATION, sources=()).refusal is False


def test_the_answer_reads_its_searches_and_retries_off_its_trace():
    """openapi `searched` and UX spec 6.2's retry marker both come
    from the trace, not from fields somebody could set independently."""
    answer = _answer()

    assert answer.searched == ("periode d'essai", "duree essai cadre")
    assert answer.retries == 1
    assert answer.trace_id == "t-1"
