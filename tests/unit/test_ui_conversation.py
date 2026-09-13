"""The rules behind the S1 screen, tested without a browser (ST-27).

Everything here is a decision the template must not make: which message
variant, which text is highlighted, whether the disclaimer line appears,
what a cancelled run leaves behind. The screen itself is exercised end to
end in `tests/integration/test_s1_chat_screen.py`; this file is where the
rules can be pushed at one at a time.
"""

from __future__ import annotations

import contextlib
import threading
import time

import pytest

import ui.runs
from agent.ports import AgentPorts
from agent.querying import ClarificationContext
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
from ui.runs import Run, RunCancelled, Stage
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
    *,
    disclaimer: bool = False,
) -> Answer:
    return Answer(
        kind=kind,
        text=text,
        sources=sources,
        session_id="session-1",
        trace=Trace(trace_id="trace-1", steps=steps),
        disclaimer=disclaimer,
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


# --- F-10: the trace disclosure ----------------------------------------


def test_message_for_carries_the_files_the_trace_actually_consulted():
    """F-10: "the files consulted", de-duplicated and in first-seen order
    -- straight off `Trace.files_consulted` (agent/trace.py), not
    recomputed here. Two searches, the second repeating the first file and
    adding a second, so de-dup and order both have something to fail."""
    answer = _answer(
        AnswerKind.ANSWER,
        "Trois mois.",
        (Source(FILE, LABEL),),
        (
            TraceStep(StepKind.SEARCH, "essai cadre", (FILE,)),
            TraceStep(StepKind.REWORD, "again"),
            TraceStep(
                StepKind.SEARCH,
                "essai cadre renouvellement",
                (FILE, "reglement-interieur.pdf"),
            ),
        ),
    )
    message = message_for(answer, [_hit(SECTION[:40])], {PARENT: SECTION})
    assert message.has_trace is True
    assert message.searched == ("essai cadre", "essai cadre renouvellement")
    assert message.files_consulted == (FILE, "reglement-interieur.pdf")
    assert message.retries == 1


def test_a_message_built_by_hand_has_no_trace():
    """USER, ERROR and INTERRUPTED messages never go through `message_for`
    and so never got a real `Answer.trace` behind them -- `has_trace`
    defaults False rather than a real message ever forging one."""
    assert error_message(RuntimeError("boom"), "Q?").has_trace is False


# --- F-09, criteria 2 and 3 -------------------------------------------


def test_the_disclaimer_line_appears_on_a_legal_workspace():
    message = message_for(
        _answer(
            AnswerKind.ANSWER,
            "Trois mois.",
            (Source(FILE, LABEL),),
            disclaimer=True,
        ),
        [_hit(SECTION[:30])],
        {PARENT: SECTION},
    )
    assert message.disclaimer is True


def test_an_unflagged_workspace_shows_no_disclaimer_anywhere():
    """Criterion 3 is as binding as criterion 2, and it is the half a
    default of True would pass silently."""
    message = message_for(
        _answer(AnswerKind.ANSWER, "Trois mois.", (Source(FILE, LABEL),)),
        [_hit(SECTION[:30])],
        {PARENT: SECTION},
    )
    assert message.disclaimer is False


def test_a_refusal_from_a_legal_workspace_carries_the_disclaimer():
    """OpenAPI does not exempt refusals: every Answer response from a
    legal workspace carries the same F-09 flag."""
    message = message_for(
        _answer(AnswerKind.REFUSAL, "Not found here.", disclaimer=True)
    )
    assert message.disclaimer is True


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


def _inert_ports(*, summarize=None) -> AgentPorts:
    return AgentPorts(
        summarize=summarize or (lambda memory: ""),
        clarify=lambda question, summary: None,
        rewrite=lambda question, summary: (question,),
        retrieve=lambda workspace_id, query: (),
        grade=lambda question, passages: False,
        reword=lambda question, previous, attempt: (question,),
        fetch_parents=lambda workspace_id, parent_ids: {},
        write_answer=lambda question, passages, parents: "unused",
    )


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


def test_completed_memory_rolls_forward_without_resending_old_turns():
    old_turn = Turn(question="Quelle duree ?", answer="Trois mois.")
    conversation = Conversation(
        workspace_id="ws-1",
        session_id="session-1",
        summary="The contract concerns trial periods.",
        turns=[old_turn],
    )
    run = _run("Et combien de renouvellements ?")

    assert conversation.begin(run, run.question) is True
    assert run.session_id == "session-1"
    assert run.previous_summary == "The contract concerns trial periods."
    assert run.history == (old_turn,)

    run.updated_summary = "A manager has a three-month trial, renewable once."
    run._answer = _answer(  # noqa: SLF001
        AnswerKind.ANSWER, "Une fois.", (Source(FILE, LABEL),)
    )
    run.reading.cited = (_hit(SECTION[:30]),)
    run.reading.parents = {PARENT: SECTION}
    run._done = True  # noqa: SLF001
    conversation.settle()

    assert conversation.summary == "A manager has a three-month trial, renewable once."
    assert conversation.turns == [
        Turn(question="Et combien de renouvellements ?", answer="Une fois.")
    ]


@pytest.mark.parametrize(
    "failure",
    [RuntimeError("later stage failed"), RunCancelled("cancelled during checking")],
)
def test_failed_or_cancelled_run_keeps_uncommitted_memory_for_retry(failure):
    old_turn = Turn(question="Quelle duree ?", answer="Trois mois.")
    conversation = Conversation(
        workspace_id="ws-1", summary="Trial periods.", turns=[old_turn]
    )
    run = _run()
    assert conversation.begin(run, run.question) is True
    run.updated_summary = "This must not be committed."
    run.fail(failure)

    conversation.settle()

    assert conversation.summary == "Trial periods."
    assert conversation.turns == [old_turn]


def test_cancelled_before_start_never_calls_the_session_summarizer():
    summary_calls = []
    ports = _inert_ports(
        summarize=lambda memory: summary_calls.append(memory) or ""
    )
    run = _run()

    run.cancel()
    run.start(ports)
    for _ in range(100):
        if run.done:
            break
        time.sleep(0.01)

    assert run.done, "the cancelled run never stopped"
    assert isinstance(run.error, RunCancelled)
    assert summary_calls == []


def test_ports_context_stays_open_for_the_whole_question(monkeypatch):
    entered = threading.Event()
    ask_started = threading.Event()
    release = threading.Event()
    exited = threading.Event()

    @contextlib.contextmanager
    def ports_context():
        entered.set()
        try:
            yield _inert_ports()
        finally:
            exited.set()

    def blocked_ask(**kwargs):
        ask_started.set()
        release.wait(timeout=10)
        return _answer(AnswerKind.REFUSAL, "Not covered here.")

    monkeypatch.setattr(ui.runs, "ask", blocked_ask)
    run = _run()
    run.start_with(ports_context())

    assert entered.wait(10)
    assert ask_started.wait(10)
    assert not exited.is_set()
    release.set()
    for _ in range(100):
        if run.done:
            break
        time.sleep(0.01)

    assert run.done
    assert exited.wait(10)


class _FirstBoundaryLock:
    """Pause on the worker's first lock release and record its stage."""

    def __init__(self, run: Run) -> None:
        self._lock = threading.Lock()
        self._run = run
        self._seen_worker = False
        self.reached = threading.Event()
        self.release = threading.Event()
        self.stage_at_boundary = None

    def __enter__(self):
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._lock.release()
        if threading.current_thread().name == "sanad-ask" and not self._seen_worker:
            self._seen_worker = True
            self.stage_at_boundary = self._run.stage
            self.reached.set()
            self.release.wait(timeout=10)


def test_preparing_stage_and_cancel_check_are_one_boundary():
    summary_calls = []
    run = _run()
    boundary = _FirstBoundaryLock(run)
    run._lock = boundary  # noqa: SLF001 -- controlled race probe
    run.start(
        _inert_ports(
            summarize=lambda memory: summary_calls.append(memory) or ""
        )
    )

    assert boundary.reached.wait(10), "the worker never reached preparation"
    run.cancel()
    boundary.release.set()
    for _ in range(100):
        if run.done:
            break
        time.sleep(0.01)

    assert boundary.stage_at_boundary is Stage.PREPARING
    assert summary_calls, "Cancel arrived after preparation began, so that stage finishes"
    assert isinstance(run.error, RunCancelled)


def test_cancel_before_answer_publication_cannot_publish_the_answer(monkeypatch):
    reached = threading.Event()
    release = threading.Event()

    def controlled_ask(**kwargs):
        reached.set()
        release.wait(timeout=10)
        return _answer(AnswerKind.REFUSAL, "Not covered here.")

    monkeypatch.setattr(ui.runs, "ask", controlled_ask)
    run = _run()
    run.start(_inert_ports())
    assert reached.wait(10), "the run never reached its final hand-off"

    run.cancel()
    release.set()
    for _ in range(100):
        if run.done:
            break
        time.sleep(0.01)

    assert run.done, "the cancelled run never settled"
    assert run.answer is None
    assert isinstance(run.error, RunCancelled)


def test_a_clarification_is_saved_then_consumed_by_exactly_one_reply():
    original = "Parlez-moi de cette procedure."
    conversation = Conversation(workspace_id="ws-1")
    first = _run(original)
    first._answer = _answer(AnswerKind.CLARIFICATION, "Which procedure?")  # noqa: SLF001
    first._done = True  # noqa: SLF001
    conversation.run = first

    conversation.settle()
    reply = _run("La procedure de licenciement.")
    assert conversation.begin(reply, reply.question) is True

    assert reply.clarification_context == ClarificationContext(
        original=original, asked="Which procedure?"
    )
    assert conversation.pending_clarification is None


@pytest.mark.parametrize(
    "failure",
    [RunCancelled("cancelled during searching"), RuntimeError("model unavailable")],
)
def test_a_failed_clarification_reply_can_be_submitted_again(failure):
    context = ClarificationContext(
        original="Parlez-moi de cette procedure.", asked="Quelle procedure ?"
    )
    conversation = Conversation(
        workspace_id="ws-1", pending_clarification=context
    )
    reply = _run("La procedure de licenciement.")
    assert conversation.begin(reply, reply.question) is True
    reply.fail(failure)

    conversation.settle()

    assert conversation.pending_clarification == context


def test_a_new_conversation_drops_a_pending_clarification():
    conversation = Conversation(
        workspace_id="ws-1",
        pending_clarification=ClarificationContext(
            original="Which original question?", asked="Which subject?"
        ),
    )

    conversation.reset()

    assert conversation.pending_clarification is None


class _SlowDone(Run):
    """A run whose `done` read is slow enough to open the race window.

    THIS CLASS IS THE TEST. A first version of the settle test below released
    16 threads off a `threading.Barrier` and asserted the outcome -- and
    it PASSED with the locks taken out, because CPython does not switch
    threads inside a check that does no I/O and allocates nothing. It was
    hoping for an unlucky interleaving, which is the weak form: green
    whether the code is right or wrong.

    A barrier INSIDE the critical section is not the fix either: with the
    lock in place, the first thread would hold it and wait for a second
    thread that is blocked on that same lock, and the correct code would
    deadlock.

    Sleeping inside the `done` read is what works. Both critical sections
    begin by reading it, so:
      * WITHOUT the lock every thread sleeps at once, all of them see the
        same stale answer, and all of them act on it;
      * WITH the lock the sleep happens while the lock is held, so the
        others queue and see the state the winner left behind.
    The difference is deterministic rather than lucky."""

    @property
    def done(self) -> bool:
        time.sleep(0.02)
        return True


class _SlowMessages(list):
    """Release the interpreter between begin's empty check and its claim."""

    def append(self, item) -> None:
        time.sleep(0.02)
        super().append(item)


def _finished(question: str = "Quelle duree ?") -> _SlowDone:
    run = _SlowDone(question=question, workspace_id="ws-1", session_id=None)
    run._answer = _answer(  # noqa: SLF001
        AnswerKind.ANSWER, "Trois mois.", (Source(FILE, LABEL),)
    )
    run.reading.cited = (_hit(SECTION[:30]),)
    run.reading.parents = {PARENT: SECTION}
    return run


def _run_together(target, threads: int = 8) -> None:
    workers = [threading.Thread(target=target) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)


def test_two_threads_settling_the_same_run_append_it_once():
    """The race a cold review found, driven rather than argued.

    Starlette runs a plain `def` route on a threadpool, so the 700ms poll
    and a browser refresh really do call `settle` at the same instant.
    Written as read-check-clear, both passed the check and the answer
    appeared TWICE -- once in the transcript and once in `turns`, which
    then fed a duplicated exchange back as F-07 memory.

    Proven discriminating: removing the lock from `settle` turns this
    red."""
    conversation = Conversation(workspace_id="ws-1")
    conversation.run = _finished()

    _run_together(conversation.settle)

    assert len(conversation.messages) == 1
    assert len(conversation.turns) == 1


def test_two_threads_asking_at_once_start_exactly_one_run():
    """The second race: a double-clicked Send.

    Both requests passed a `busy` check and both assigned
    `conversation.run`. The first worker kept going, spent a real provider
    call, and had its answer silently discarded by the second. The user
    saw one answer and paid for two.

    `begin` returning False is the whole contract: exactly one caller may
    be told to start a thread. `_SlowMessages` opens the exact window after
    the empty check; without the lock all callers enter it before any sets
    `run`, while with the lock the winner completes the claim first.

    Proven discriminating: removing the lock from `begin` turns this
    red."""
    conversation = Conversation(workspace_id="ws-1")
    conversation.messages = _SlowMessages()
    claimed: list[bool] = []
    guard = threading.Lock()

    def ask_together() -> None:
        won = conversation.begin(_run(), "Quelle duree ?")
        with guard:
            claimed.append(won)

    _run_together(ask_together)

    assert sum(claimed) == 1, "exactly one caller may start the run"
    assert len(conversation.messages) == 1, "and only its question is shown"


def test_a_finished_run_must_be_saved_before_the_next_question_can_replace_it():
    """A fast answer remains owned by settle instead of being overwritten."""
    conversation = Conversation(workspace_id="ws-1")
    first = _finished("one")
    conversation.run = first
    second = _run("two")

    assert conversation.begin(second, "two") is False
    assert conversation.run is first

    conversation.settle()
    assert conversation.messages[-1].text == "Trois mois."
    assert conversation.begin(second, "two") is True


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
    conversation = Conversation(
        workspace_id="ws-1", session_id="old-session", summary="old summary"
    )
    abandoned = _run()
    conversation.run = abandoned
    conversation.messages.append(error_message(RuntimeError("x"), "q"))
    conversation.turns.append(Turn(question="q", answer="a"))
    conversation.reset()
    assert conversation.messages == []
    assert conversation.turns == []
    assert conversation.summary == ""
    assert conversation.session_id is None
    assert conversation.run is None
    assert abandoned.cancelled is True
