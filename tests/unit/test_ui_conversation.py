"""The rules behind the S1 screen, tested without a browser (ST-27).

Everything here is a decision the template must not make: which message
variant, which text is highlighted, whether the disclaimer line appears,
what a cancelled run leaves behind. The screen itself is exercised end to
end in `tests/integration/test_s1_chat_screen.py`; this file is where the
rules can be pushed at one at a time.
"""

from __future__ import annotations

import threading

import pytest

from agent.state import Answer, AnswerKind, Source, Turn
from agent.trace import StepKind, Trace, TraceStep
from ui.conversation import (
    Conversation,
    MessageKind,
    UncitableSourceError,
    error_message,
    merge_spans,
    message_for,
    segments_for,
)
from ui.runs import Run, RunCancelled
from vector_store import SearchHit

SECTION = (
    "Article 13 : La periode d'essai est de trois mois pour les cadres. "
    "Elle est de un mois et demi pour les employes. "
    "Le renouvellement doit etre notifie par ecrit."
)
FILE = "code-du-travail.pdf"
LABEL = "Article 13"
PARENT = "parent-13"


def _hit(chunk: str, *, parent_id: str = PARENT, label: str | None = LABEL) -> SearchHit:
    return SearchHit(
        parent_id=parent_id,
        source_file=FILE,
        section_label=label,
        chunk_text=chunk,
        score=0.9,
    )


def _answer(
    kind: AnswerKind,
    text: str,
    sources: tuple[Source, ...] = (),
    steps: tuple[TraceStep, ...] = (),
) -> Answer:
    return Answer(
        kind=kind,
        text=text,
        sources=sources,
        session_id="session-1",
        trace=Trace(trace_id="trace-1", steps=steps),
    )


# --- the highlight ----------------------------------------------------


def test_overlapping_spans_are_collapsed_into_one():
    """Children overlap by `chunk_child_overlap_chars` BY DESIGN, so two
    chunks of one section routinely share text. Left uncollapsed the
    template opens a second <mark> inside an open one and the highlight
    runs to the end of the section."""
    assert merge_spans([(0, 10), (5, 20)]) == [(0, 20)]
    assert merge_spans([(30, 40), (0, 10)]) == [(0, 10), (30, 40)]
    assert merge_spans([(5, 5)]) == []


def test_cutting_a_section_into_segments_loses_no_text():
    """The property that matters most and is easiest to break: whatever
    the spans, joining the segments must give back the section exactly.
    A highlight that silently drops a clause would show the reader a
    passage the model never saw."""
    segments = segments_for(SECTION, [(10, 25), (40, 60)])
    assert "".join(segment.text for segment in segments) == SECTION


def test_the_marked_segment_is_the_retrieved_chunk_and_nothing_else():
    chunk = "La periode d'essai est de trois mois pour les cadres."
    start = SECTION.index(chunk)
    segments = segments_for(SECTION, [(start, start + len(chunk))])
    cited = [segment.text for segment in segments if segment.cited]
    assert cited == [chunk]


def test_a_chunk_that_is_not_in_its_section_is_shown_unmarked_not_guessed():
    """A store rebuilt under different chunking settings, or drifted from
    the index, gives a chunk that is not a substring of its parent. The
    passage is then shown whole and the viewer says so -- a highlight
    drawn over the wrong sentence is worse than none, because the reader
    cannot tell it is wrong."""
    message = message_for(
        _answer(AnswerKind.ANSWER, "Trois mois.", (Source(FILE, LABEL),)),
        [_hit("text that this section does not contain")],
        {PARENT: SECTION},
    )
    passage = message.sources[0].passages[0]
    assert passage.highlighted is False
    assert passage.text == SECTION
    assert not any(segment.cited for segment in passage.segments)


# --- the four message variants (UX spec 6.2) --------------------------


def test_an_answer_becomes_the_answer_variant_with_its_source_cards():
    chunk = "Le renouvellement doit etre notifie par ecrit."
    message = message_for(
        _answer(AnswerKind.ANSWER, "Trois mois.", (Source(FILE, LABEL),)),
        [_hit(chunk)],
        {PARENT: SECTION},
    )
    assert message.kind is MessageKind.ANSWER
    card = message.sources[0]
    assert card.file_name == FILE
    assert card.section_label == LABEL
    assert card.passages[0].highlighted is True


def test_a_refusal_becomes_the_refusal_variant_and_discloses_its_searches():
    """F-05 and UX spec 6.2: the refusal states what was searched. It is
    NOT the error variant -- design principle 2 makes that distinction the
    product's whole argument."""
    answer = _answer(
        AnswerKind.REFUSAL,
        "I could not find this in the workspace.",
        (),
        (TraceStep(StepKind.SEARCH, "periode d'essai", (FILE,)),),
    )
    message = message_for(answer)
    assert message.kind is MessageKind.REFUSAL
    assert message.kind is not MessageKind.ERROR
    assert message.searched == ("periode d'essai",)
    assert message.sources == ()


def test_a_clarification_becomes_its_own_variant_and_invents_no_choices():
    """UX spec 6.2 offers choices only "where the system can offer them".
    ST-22 owns the clarify port and is unbuilt, so nothing can offer any.
    The React reference fills the gap with three plausible guesses
    (`ChatScreen.tsx:163`); this asserts the gap stays honest."""
    message = message_for(
        _answer(AnswerKind.CLARIFICATION, "Do you mean managers or workers?")
    )
    assert message.kind is MessageKind.CLARIFICATION
    assert message.choices == ()


def test_the_retry_marker_shows_the_count_the_loop_actually_ran():
    answer = _answer(
        AnswerKind.ANSWER,
        "Trois mois.",
        (Source(FILE, LABEL),),
        (
            TraceStep(StepKind.SEARCH, "essai"),
            TraceStep(StepKind.REWORD, "again"),
            TraceStep(StepKind.REWORD, "again"),
        ),
    )
    message = message_for(answer, [_hit(SECTION[:40])], {PARENT: SECTION})
    assert message.retries == 2


# --- F-09, criteria 2 and 3 -------------------------------------------


def test_the_disclaimer_line_appears_on_a_legal_workspace():
    message = message_for(
        _answer(AnswerKind.ANSWER, "Trois mois.", (Source(FILE, LABEL),)),
        [_hit(SECTION[:30])],
        {PARENT: SECTION},
        legal_workspace=True,
    )
    assert message.disclaimer is True


def test_an_unflagged_workspace_shows_no_disclaimer_anywhere():
    """Criterion 3 is as binding as criterion 2, and it is the half a
    default of True would pass silently."""
    message = message_for(
        _answer(AnswerKind.ANSWER, "Trois mois.", (Source(FILE, LABEL),)),
        [_hit(SECTION[:30])],
        {PARENT: SECTION},
        legal_workspace=False,
    )
    assert message.disclaimer is False


def test_a_refusal_on_a_legal_workspace_carries_no_disclaimer():
    """The line disclaims legal CONTENT. A refusal quotes none, so
    attaching it there would put a legal caveat on the sentence "I found
    nothing"."""
    message = message_for(
        _answer(AnswerKind.REFUSAL, "Not found here."), legal_workspace=True
    )
    assert message.disclaimer is False


# --- the invariant under the source cards -----------------------------


def test_a_source_with_no_recorded_passage_is_refused_loudly():
    """A card that opens onto nothing is the one thing F-03's source line
    promises cannot happen, so this raises rather than rendering an empty
    viewer. Unreachable in practice: `answer.sources` and the recorded
    passages are built from the same tuple. Asserted anyway, because that
    argument is a reading of the code and this is a check."""
    with pytest.raises(UncitableSourceError, match="code-du-travail"):
        message_for(
            _answer(AnswerKind.ANSWER, "Trois mois.", (Source(FILE, LABEL),)),
            [_hit("chunk", parent_id="a-different-parent")],
            {PARENT: SECTION},
        )


def test_two_sections_under_one_label_both_reach_the_viewer():
    """`_sources_for` de-duplicates by file and label, so a long article
    split across two parents is ONE card. Showing only the first passage
    would hide half of what the model read."""
    second = "Article 13 (suite) : la duree ne peut etre allongee."
    message = message_for(
        _answer(AnswerKind.ANSWER, "Trois mois.", (Source(FILE, LABEL),)),
        [_hit(SECTION[:30]), _hit(second[:20], parent_id="parent-13b")],
        {PARENT: SECTION, "parent-13b": second},
    )
    assert len(message.sources) == 1
    assert len(message.sources[0].passages) == 2


# --- settling a finished run ------------------------------------------


def _run(question: str = "Quelle duree ?") -> Run:
    return Run(question=question, workspace_id="ws-1", session_id=None)


def test_a_cancelled_run_is_marked_incomplete_and_is_not_an_answer():
    """Criterion 8: the partial text is visibly marked incomplete and no
    control presents it as a finished answer. There IS no partial text in
    V1 -- nothing streams -- and the message says so instead of rendering
    an empty bubble labelled incomplete."""
    conversation = Conversation(workspace_id="ws-1")
    run = _run()
    run.fail(RunCancelled("cancelled during writing"))
    conversation.run = run
    conversation.settle()

    message = conversation.messages[-1]
    assert message.kind is MessageKind.INTERRUPTED
    assert message.sources == ()
    assert "no partial text" in message.text


def test_a_failed_run_becomes_an_error_panel_naming_the_exact_value():
    """UX spec 5: "`ErrorPanel` always shows the offending value ... Never
    a bare 'something went wrong'"."""
    conversation = Conversation(workspace_id="ws-1")
    run = _run("Combien de jours ?")
    run.fail(RuntimeError("GEMINI_API_KEY is not set"))
    conversation.run = run
    conversation.settle()

    message = conversation.messages[-1]
    assert message.kind is MessageKind.ERROR
    assert "GEMINI_API_KEY is not set" in message.error.value
    assert "Combien de jours ?" in message.error.attempted


def test_only_a_real_answer_enters_the_conversation_memory():
    """F-07 holds completed exchanges. Feeding "I could not find this"
    back as history would teach the next turn a fact about the corpus that
    the corpus does not contain."""
    conversation = Conversation(workspace_id="ws-1")
    run = _run()
    run._answer = _answer(AnswerKind.REFUSAL, "Not covered here.")  # noqa: SLF001
    run._done = True  # noqa: SLF001
    conversation.run = run
    conversation.settle()
    assert conversation.turns == []

    answered = _run("Et pour les cadres ?")
    answered._answer = _answer(  # noqa: SLF001
        AnswerKind.ANSWER, "Trois mois.", (Source(FILE, LABEL),)
    )
    answered._done = True  # noqa: SLF001
    answered.reading.cited = (_hit(SECTION[:30]),)
    answered.reading.parents = {PARENT: SECTION}
    conversation.run = answered
    conversation.settle()
    assert conversation.turns == [Turn(question="Et pour les cadres ?", answer="Trois mois.")]


def test_two_threads_settling_the_same_run_append_it_once():
    """The race a cold review found, driven rather than argued.

    Starlette runs a plain `def` route on a threadpool, so the 700ms poll
    and a browser refresh really do call `settle` at the same instant.
    Written as read-check-clear, both passed the check and the answer
    appeared TWICE -- once in the transcript and once in `turns`, which
    then fed a duplicated exchange back as F-07 memory.

    A barrier is what makes this a test rather than a coincidence: every
    thread is held until all of them have arrived, so they enter the
    critical section together instead of politely one after another."""
    conversation = Conversation(workspace_id="ws-1")
    run = _run()
    run._answer = _answer(  # noqa: SLF001
        AnswerKind.ANSWER, "Trois mois.", (Source(FILE, LABEL),)
    )
    run._done = True  # noqa: SLF001
    run.reading.cited = (_hit(SECTION[:30]),)
    run.reading.parents = {PARENT: SECTION}
    conversation.run = run

    threads = 16
    barrier = threading.Barrier(threads)

    def settle_together() -> None:
        barrier.wait(timeout=5)
        conversation.settle()

    workers = [threading.Thread(target=settle_together) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)

    assert len(conversation.messages) == 1
    assert len(conversation.turns) == 1


def test_two_threads_asking_at_once_start_exactly_one_run():
    """The second race: a double-clicked Send.

    Both requests passed a `busy` check and both assigned
    `conversation.run`. The first worker kept going, spent a real provider
    call, and had its answer silently discarded by the second. The user
    saw one answer and paid for two.

    `begin` returning False is the whole contract: exactly one caller may
    be told to start a thread."""
    conversation = Conversation(workspace_id="ws-1")
    threads = 16
    barrier = threading.Barrier(threads)
    claimed: list[bool] = []
    guard = threading.Lock()

    def ask_together() -> None:
        barrier.wait(timeout=5)
        won = conversation.begin(_run(), "Quelle duree ?")
        with guard:
            claimed.append(won)

    workers = [threading.Thread(target=ask_together) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)

    assert sum(claimed) == 1, "exactly one caller may start the run"
    assert len(conversation.messages) == 1, "and only its question is shown"


def test_a_finished_run_does_not_block_the_next_question():
    """The control probe for the test above. Without it, `begin` could
    simply always return False after the first call and both assertions
    would still pass -- a chat screen that answers one question ever."""
    conversation = Conversation(workspace_id="ws-1")
    first = _run()
    assert conversation.begin(first, "one") is True
    first.fail(RuntimeError("done"))
    conversation.settle()
    assert conversation.begin(_run(), "two") is True


def test_settling_twice_does_not_double_the_transcript():
    """Every render calls `settle`, and the page is rendered on the poll,
    on the redirect and on a refresh. A second call must be a no-op or one
    answer appears three times."""
    conversation = Conversation(workspace_id="ws-1")
    run = _run()
    run.fail(RuntimeError("boom"))
    conversation.run = run
    conversation.settle()
    conversation.settle()
    conversation.settle()
    assert len(conversation.messages) == 1


def test_a_new_conversation_drops_the_session_so_memory_starts_clean():
    conversation = Conversation(workspace_id="ws-1", session_id="old-session")
    conversation.messages.append(error_message(RuntimeError("x"), "q"))
    conversation.turns.append(Turn(question="q", answer="a"))
    conversation.reset()
    assert conversation.messages == []
    assert conversation.turns == []
    assert conversation.session_id is None
