"""ST-21 exit gate: the graph runs end to end on a stub, and every answer
object carries its trace.

Reference: docs/phase2/Sanad_Architecture_v1.0.md section 5.2 (the flow),
ADR-03 (why it is a graph at all) and ADR-09 (the trace).

HOW THESE TESTS TRY NOT TO BE VACUOUS, which is this project's recurring
defect (BUILD-STATE lists six shipped examples). Three habits:

1. **Routes are asserted as an ordered list of trace steps, not as a
   count.** "It answered" is true of a great many broken graphs. "It ran
   summary, rewrite, search, grade, answer IN THAT ORDER" is true of one.
2. **Numbers are asserted at a value the code cannot have hardcoded.** The
   retry ceiling is exercised at 0, 1, 2 and 5 through config, so a
   mutation that ignores the setting and restores the default 2 has
   nowhere to hide (the ST-12 lesson).
3. **Ports record their calls, so "never called" is a real assertion.**
   A clarification that quietly searched anyway, or an empty result that
   still woke the grader, would pass a check on the returned object and
   fails here.
"""

from __future__ import annotations

import dataclasses

import pytest

import agent.nodes
from agent.graph import ask
from agent.ports import AgentPorts
from agent.state import AnswerKind, Turn
from agent.trace import StepKind
from config import get_settings
from vector_store import SearchHit

QUESTION = "Quelle est la duree de la periode d'essai ?"
ANSWER_TEXT = "Trois mois, renouvelable une fois."
# The full section behind a hit (architecture 5.2 box P). Longer than the
# chunk on purpose: the whole point of the parent fetch is that the model
# reads more than the 500 characters that matched.
PARENT_TEXT = (
    "Article 13. La periode d'essai est de trois mois pour les cadres, "
    "renouvelable une seule fois. Elle est de un mois et demi pour les "
    "employes et de quinze jours pour les ouvriers."
)

HIT = SearchHit(
    parent_id="p-1",
    source_file="code-du-travail.pdf",
    section_label="Article 13",
    chunk_text="La periode d'essai est de trois mois.",
    score=0.91,
)


class _Recorder:
    """A port that answers the same way every time and remembers every
    call, so a test can assert a port was NOT reached."""

    def __init__(self, result):
        self.result = result
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class _Script:
    """A port that answers differently on each call, then repeats its last
    answer. This is how a grader that says no once and yes the second time
    is expressed without a mock framework."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls: list[tuple] = []

    def __call__(self, *args):
        self.calls.append(args)
        index = min(len(self.calls) - 1, len(self.results) - 1)
        return self.results[index]


def _ports(**overrides) -> AgentPorts:
    """The stub the exit gate names: eight ports, none of them clever.

    Defaults describe the happy path -- clear question, one relevant
    passage, an answer written from it. Each test overrides the one port
    whose behaviour it is about, which keeps the thing under test visible
    in the test body instead of buried in a fixture."""
    base = AgentPorts(
        summarize=lambda history: "",
        clarify=lambda question, summary: None,
        rewrite=lambda question, summary: (question,),
        retrieve=lambda workspace_id, query: (HIT,),
        grade=lambda question, passages: True,
        reword=lambda question, previous, attempt: (f"{question} (reformulation {attempt})",),
        fetch_parents=lambda workspace_id, parent_ids: {pid: PARENT_TEXT for pid in parent_ids},
        write_answer=lambda question, passages, parents: ANSWER_TEXT,
    )
    return dataclasses.replace(base, **overrides)


def _with_settings(monkeypatch, **overrides):
    """Point the routers at non-default agent settings.

    `agent.nodes` is the module that reads the ceiling, so that is the
    name that gets patched -- see `route_after_grade`."""
    settings = get_settings().model_copy(update=overrides)
    monkeypatch.setattr(agent.nodes, "get_settings", lambda: settings)
    return settings


def _kinds(answer) -> list[StepKind]:
    return [step.kind for step in answer.trace.steps]


def _ask(**kwargs):
    return ask(workspace_id="ws-hr", question=QUESTION, **kwargs)


# --- exit gate 1: the graph runs end to end ---------------------------


def test_the_graph_runs_end_to_end_and_returns_a_sourced_answer():
    """Section 5.2's happy path, all of it, on stubs.

    Asserted field by field rather than as "it returned something": an
    answer whose text arrived but whose sources did not is exactly the
    failure F-03 exists to prevent, and it would pass a truthiness
    check."""
    answer = _ask(ports=_ports())

    assert answer.kind is AnswerKind.ANSWER
    assert answer.text == ANSWER_TEXT
    assert answer.sources[0].file_name == "code-du-travail.pdf"
    assert answer.sources[0].section_label == "Article 13"
    assert answer.refusal is False
    assert answer.retries == 0


def test_the_answer_path_runs_every_box_section_5_2_draws_in_order():
    """The route itself, as an ordered list.

    This is the test that notices a node being skipped. A graph that never
    graded, that answered before searching, or that skipped the parent
    fetch still returns a plausible answer object; it does not produce
    this sequence."""
    answer = _ask(ports=_ports())

    assert _kinds(answer) == [
        StepKind.SUMMARY,
        StepKind.REWRITE,
        StepKind.SEARCH,
        StepKind.GRADE,
        StepKind.PARENTS,
        StepKind.ANSWER,
    ]


# --- exit gate 2: every answer object carries its trace ---------------


@pytest.mark.parametrize(
    ("overrides", "expected_kind", "expected_last_step"),
    [
        ({}, AnswerKind.ANSWER, StepKind.ANSWER),
        (
            {"grade": lambda question, passages: False},
            AnswerKind.REFUSAL,
            StepKind.REFUSAL,
        ),
        (
            {"clarify": lambda question, summary: "Which contract type do you mean?"},
            AnswerKind.CLARIFICATION,
            StepKind.CLARIFY,
        ),
    ],
    ids=["answer", "refusal", "clarification"],
)
def test_every_outcome_carries_a_trace_of_its_own_run(
    overrides, expected_kind, expected_last_step
):
    """ADR-09 and ST-21's exit gate, for ALL THREE outcomes.

    A trace is only worth having if it describes THIS run, so the check is
    not "a trace exists": it is that the trace's last step is the outcome
    that was actually reached, and that its id is one this answer
    minted."""
    answer = _ask(ports=_ports(**overrides))

    assert answer.kind is expected_kind
    assert answer.trace_id
    assert answer.trace.steps, "an answer with an empty trace tells F-10 nothing"
    assert answer.trace.steps[-1].kind is expected_last_step
    assert answer.trace_id == answer.trace.trace_id


def test_two_questions_do_not_share_a_trace():
    """Traces are per answer (ADR-09: "the agent emits structured steps
    onto the answer object"). Module-level accumulation would show up
    here as the second answer inheriting the first one's searches."""
    first = _ask(ports=_ports())
    second = ask(workspace_id="ws-hr", question="Et le preavis ?", ports=_ports())

    assert first.trace_id != second.trace_id
    assert first.searched == (QUESTION,)
    assert second.searched == ("Et le preavis ?",)


# --- F-04: the retry ceiling ------------------------------------------


@pytest.mark.parametrize("ceiling", [0, 1, 2, 5])
def test_the_retry_count_never_exceeds_the_configured_ceiling(monkeypatch, ceiling):
    """F-04's binding criterion, at four values including zero.

    Run at one value this would be satisfied by a hardcoded literal. Run
    at 0 it also pins the boundary from the other side: a ceiling of zero
    means answer or refuse on the first search, and an off-by-one that
    allowed "one last try" shows up here and nowhere else."""
    _with_settings(monkeypatch, retry_ceiling=ceiling)
    grade = _Recorder(False)

    answer = _ask(ports=_ports(grade=grade))

    assert answer.kind is AnswerKind.REFUSAL
    assert answer.retries == ceiling
    assert len(answer.searched) == ceiling + 1
    assert len(grade.calls) == ceiling + 1


def test_a_relevant_first_search_rewords_nothing(monkeypatch):
    """The other side of the ceiling: it is a ceiling, not a quota."""
    _with_settings(monkeypatch, retry_ceiling=2)
    reword = _Recorder("never used")

    answer = _ask(ports=_ports(reword=reword))

    assert answer.retries == 0
    assert reword.calls == []


def test_a_retry_that_finds_relevant_passages_answers_from_them(monkeypatch):
    """Section 5.2's loop closing successfully: grade says no, the query
    is reworded, the SECOND search is the reworded one, and the answer is
    built from what it found.

    The last assertion is the one with teeth. A graph that reworded the
    query but searched the original string again would still answer, still
    report one retry, and be quietly useless."""
    _with_settings(monkeypatch, retry_ceiling=2)
    answer = _ask(ports=_ports(grade=_Script(False, True)))

    assert answer.kind is AnswerKind.ANSWER
    assert answer.retries == 1
    assert answer.searched == (QUESTION, f"{QUESTION} (reformulation 1)")
    assert _kinds(answer) == [
        StepKind.SUMMARY,
        StepKind.REWRITE,
        StepKind.SEARCH,
        StepKind.GRADE,
        StepKind.REWORD,
        StepKind.SEARCH,
        StepKind.GRADE,
        StepKind.PARENTS,
        StepKind.ANSWER,
    ]


def test_the_reword_port_is_told_which_attempt_it_is_on(monkeypatch):
    """So ST-23 can widen the search as attempts go on without counting
    anything itself. 1-based, and it must not restart."""
    _with_settings(monkeypatch, retry_ceiling=3)
    reword = _Script(("essai un",), ("essai deux",), ("essai trois",))

    _ask(ports=_ports(grade=lambda q, p: False, reword=reword))

    assert [call[2] for call in reword.calls] == [1, 2, 3]


def test_a_high_retry_ceiling_runs_to_completion(monkeypatch):
    """An operator raising the ceiling (F-04 says they may) must not hit
    the framework's own recursion limit.

    65 nodes run here. If a future langgraph brings its default super-step
    limit back down to the 25 the older docs describe, this test is where
    it surfaces -- as a red test rather than as a `GraphRecursionError` in
    front of a user. See the note in agent/graph.py."""
    _with_settings(monkeypatch, retry_ceiling=20)

    answer = _ask(ports=_ports(grade=lambda q, p: False))

    assert answer.kind is AnswerKind.REFUSAL
    assert answer.retries == 20
    assert len(answer.searched) == 21


# --- F-05: the honest refusal -----------------------------------------


def test_a_refusal_discloses_every_search_it_ran(monkeypatch):
    """F-05: the refusal "states what it looked for". The list is the
    queries in the order they ran, retries included -- not a summary, not
    the original question repeated."""
    _with_settings(monkeypatch, retry_ceiling=2)

    answer = _ask(ports=_ports(grade=lambda q, p: False))

    assert answer.refusal is True
    assert answer.searched == (
        QUESTION,
        f"{QUESTION} (reformulation 1)",
        f"{QUESTION} (reformulation 2)",
    )
    assert answer.text.strip()
    assert answer.sources == ()


def test_a_search_that_finds_nothing_refuses_without_waking_the_grader(monkeypatch):
    """No passages needs no judgement (and no model call). The assertion
    that matters is `grade.calls == []`: a grader answering "yes" to zero
    passages would send the flow to an answer node with nothing to
    cite."""
    _with_settings(monkeypatch, retry_ceiling=0)
    grade = _Recorder(True)

    answer = _ask(ports=_ports(retrieve=lambda ws, query: (), grade=grade))

    assert answer.kind is AnswerKind.REFUSAL
    assert grade.calls == []


# --- F-06: exactly one clarifying question ----------------------------


def test_an_ambiguous_question_asks_one_question_and_searches_nothing():
    """F-06: "the assistant asks exactly one clarifying question instead
    of guessing". Guessing, here, would be searching anyway and answering
    from whatever came back -- so the retrieve port must never be
    reached."""
    retrieve = _Recorder((HIT,))
    clarification = "Do you mean a fixed-term or an open-ended contract?"

    answer = _ask(
        ports=_ports(
            clarify=lambda question, summary: clarification,
            retrieve=retrieve,
        )
    )

    assert answer.kind is AnswerKind.CLARIFICATION
    assert answer.text == clarification
    assert retrieve.calls == []
    assert answer.searched == ()
    assert [k for k in _kinds(answer) if k is StepKind.CLARIFY] == [StepKind.CLARIFY]


# --- F-03: sources come from the passages, not from the model ---------


def test_five_chunks_of_two_sections_become_two_sources():
    """One citation per file-and-section, first-seen order. Five source
    cards pointing at the same article is noise the user has to read past,
    and openapi's `sources` array is served to API callers who have no UI
    to tidy it."""
    hits = (
        HIT,
        dataclasses.replace(HIT, parent_id="p-2", chunk_text="suite"),
        dataclasses.replace(HIT, parent_id="p-3", section_label="Article 14"),
        dataclasses.replace(HIT, parent_id="p-4", section_label="Article 14"),
        dataclasses.replace(HIT, parent_id="p-5"),
    )

    answer = _ask(ports=_ports(retrieve=lambda ws, query: hits))

    assert [(s.file_name, s.section_label) for s in answer.sources] == [
        ("code-du-travail.pdf", "Article 13"),
        ("code-du-travail.pdf", "Article 14"),
    ]


def test_the_trace_records_which_files_a_search_consulted():
    """F-10's third promise ("the files consulted"), de-duplicated: two
    chunks of one PDF consulted one file."""
    hits = (
        HIT,
        dataclasses.replace(HIT, parent_id="p-2"),
        dataclasses.replace(HIT, parent_id="p-3", source_file="guide-cnss.docx"),
    )

    answer = _ask(ports=_ports(retrieve=lambda ws, query: hits))

    assert answer.trace.files_consulted == ("code-du-travail.pdf", "guide-cnss.docx")


def test_the_string_that_is_searched_is_the_rewritten_query():
    """Section 5.2 puts "rewrite and split" before the search, so the
    trace -- and therefore the refusal disclosure -- must show what was
    actually sent to the store, not what the user typed."""
    retrieve = _Recorder((HIT,))

    answer = _ask(
        ports=_ports(
            rewrite=lambda question, summary: ("duree periode essai cadres",),
            retrieve=retrieve,
        )
    )

    assert [call[1] for call in retrieve.calls] == ["duree periode essai cadres"]
    assert answer.searched == ("duree periode essai cadres",)


# --- F-07 seam and the session id -------------------------------------


def test_the_session_summary_reaches_the_step_that_rewrites_the_question():
    """ST-25 fills the summary in; ST-21 only has to prove the wire exists.
    Asserted at both ends: the history reaches `summarize`, and what
    `summarize` returned reaches `rewrite`."""
    history = (Turn(question="Periode d'essai ?", answer="Trois mois."),)
    summarize = _Recorder("the user is asking about trial periods")
    rewrite = _Recorder(("renouvellement periode essai",))

    _ask(ports=_ports(summarize=summarize, rewrite=rewrite), history=history)

    assert summarize.calls == [(history,)]
    assert rewrite.calls == [(QUESTION, "the user is asking about trial periods")]


# --- 5.2 "rewrite and SPLIT query": one question, several searches -----


def test_a_split_question_runs_one_search_per_sub_query():
    """Architecture 5.2's box is "Rewrite and split query" and ADR-03
    keeps the reference implementation's sub-queries. "How long is a trial
    period and can it be renewed?" is two searches.

    The trace records them SEPARATELY rather than as one joined-up line,
    because F-05 discloses what was searched and "duree essai |
    renouvellement essai" is not a search anybody ran."""
    retrieve = _Recorder((HIT,))

    answer = _ask(
        ports=_ports(
            rewrite=lambda question, summary: ("duree essai", "renouvellement essai"),
            retrieve=retrieve,
        )
    )

    assert [call[1] for call in retrieve.calls] == ["duree essai", "renouvellement essai"]
    assert answer.searched == ("duree essai", "renouvellement essai")
    assert answer.kind is AnswerKind.ANSWER


def test_a_chunk_found_by_two_sub_queries_reaches_the_model_once():
    """The same article matching both halves of a split question comes
    back twice with two different fusion scores, so de-duplicating on the
    whole hit object would keep both.

    ASSERTED ON WHAT THE ANSWER WRITER RECEIVED, and that correction is
    the point of this test. The first version asserted on
    `answer.sources`, which `_sources_for` de-duplicates a second time on
    (file, label) -- so the duplicate collapsed before the assertion could
    see it and the test passed with the merge broken. That is the "keyed
    so duplicates collapse" shape from the prove-it skill, caught by
    injecting the mutation rather than by reading the test.

    The real cost of a duplicate is here anyway: the model reads the same
    passage twice, and passage text is the scarcest thing in the prompt.

    The fixture makes the scores differ ON PURPOSE. With equal scores the
    two hits would be equal objects and a plain `set` would pass."""
    same_chunk_again = dataclasses.replace(HIT, score=0.42)
    other = dataclasses.replace(
        HIT, parent_id="p-2", section_label="Article 14", chunk_text="Le preavis..."
    )
    batches = {"q1": (HIT, other), "q2": (same_chunk_again,)}
    write = _Recorder(ANSWER_TEXT)

    answer = _ask(
        ports=_ports(
            rewrite=lambda question, summary: ("q1", "q2"),
            retrieve=lambda workspace_id, query: batches[query],
            write_answer=write,
        )
    )

    passages = write.calls[0][1]
    assert [hit.chunk_text for hit in passages] == [HIT.chunk_text, "Le preavis..."]
    assert [(s.file_name, s.section_label) for s in answer.sources] == [
        ("code-du-travail.pdf", "Article 13"),
        ("code-du-travail.pdf", "Article 14"),
    ]


def test_a_reword_may_split_differently_and_every_query_is_searched(monkeypatch):
    """The retry path carries the same plural shape as the first pass: a
    reword that decides the question needs two searches gets two."""
    _with_settings(monkeypatch, retry_ceiling=1)
    retrieve = _Recorder((HIT,))

    answer = _ask(
        ports=_ports(
            grade=lambda question, passages: False,
            reword=lambda question, previous, attempt: ("essai cadres", "essai ouvriers"),
            retrieve=retrieve,
        )
    )

    assert answer.searched == (QUESTION, "essai cadres", "essai ouvriers")
    assert answer.retries == 1, "two sub-queries are still ONE retry"


def test_the_reword_port_sees_the_queries_it_is_replacing(monkeypatch):
    """It is handed the previous queries, plural, so a widening strategy
    can see what was already tried."""
    _with_settings(monkeypatch, retry_ceiling=1)
    reword = _Recorder(("plus large",))

    _ask(
        ports=_ports(
            grade=lambda question, passages: False,
            rewrite=lambda question, summary: ("essai", "renouvellement"),
            reword=reword,
        )
    )

    assert reword.calls[0][1] == ("essai", "renouvellement")


# --- 5.2 box P: fetch the parent sections ------------------------------


def test_the_answer_is_written_from_parent_sections_not_from_the_chunks():
    """Architecture 5.2 puts `P[Fetch parent sections for context]`
    between grading and answering, and 7.5 explains why: the searched unit
    is a 500-character child, the READ unit is the section it came from.

    Asserted on what the port actually received, not on the answer text:
    a graph that fetched the sections and then handed the model only the
    chunks would look identical from the outside."""
    fetch = _Recorder({"p-1": PARENT_TEXT})
    write = _Recorder(ANSWER_TEXT)

    answer = _ask(ports=_ports(fetch_parents=fetch, write_answer=write))

    assert fetch.calls == [("ws-hr", ("p-1",))]
    assert write.calls[0][2] == {"p-1": PARENT_TEXT}
    assert answer.kind is AnswerKind.ANSWER


def test_four_chunks_of_one_section_fetch_that_section_once():
    """The parent is asked for once even when four of its children
    matched. Re-reading one JSON file four times per answer is the kind of
    cost ST-17's review already flagged on the write path."""
    hits = tuple(
        dataclasses.replace(HIT, chunk_text=f"extrait {n}") for n in range(4)
    ) + (dataclasses.replace(HIT, parent_id="p-2", chunk_text="autre"),)
    fetch = _Recorder({"p-1": PARENT_TEXT, "p-2": "Article 14..."})

    _ask(ports=_ports(retrieve=lambda ws, query: hits, fetch_parents=fetch))

    assert fetch.calls == [("ws-hr", ("p-1", "p-2"))]


def test_a_section_the_store_cannot_produce_is_visible_in_the_trace():
    """A parent that is missing means the store has drifted from the index
    -- `parent_store.get_parent` says so itself ("the workspace may need a
    re-sync"). One absent section must not fail the whole answer, and must
    not vanish either: the trace says how many of how many loaded."""
    hits = (HIT, dataclasses.replace(HIT, parent_id="p-2", chunk_text="autre"))

    answer = _ask(
        ports=_ports(
            retrieve=lambda ws, query: hits,
            fetch_parents=lambda ws, ids: {"p-1": PARENT_TEXT},
        )
    )

    assert answer.kind is AnswerKind.ANSWER
    parents_step = next(s for s in answer.trace.steps if s.kind is StepKind.PARENTS)
    assert parents_step.detail == "loaded 1 of 2 section(s)"


def test_a_parent_nobody_asked_for_stops_the_answer():
    """The one failure a sourced-answer product cannot absorb: a section
    from a workspace the question was not asked in (PRD F-01 makes
    isolation structural). A port returning an id the graph never
    requested is exactly that shape, so it raises rather than being
    quietly ignored."""
    with pytest.raises(ValueError, match="nobody asked for"):
        _ask(
            ports=_ports(
                fetch_parents=lambda ws, ids: {"p-1": PARENT_TEXT, "p-999": "leaked"}
            )
        )


def test_no_readable_section_at_all_refuses_instead_of_answering():
    """The floor under box P, and it was missing until a review asked what
    "loaded 0 of 5" does.

    It answered: the model got an empty context, and the answer still
    carried a source list built from the chunk metadata -- a citation to
    documents whose text nothing had read. F-03 calls the source line the
    product's contract with the user, so this refuses.

    The refusal says something DIFFERENT from "not covered here", because
    a different thing happened: the passages were found and the sections
    could not be read, and the next step is a Sync, not a rephrase."""
    answer = _ask(ports=_ports(fetch_parents=lambda ws, ids: {}))

    assert answer.kind is AnswerKind.REFUSAL
    assert answer.sources == ()
    assert "Sync" in answer.text
    assert answer.text != agent.nodes.REFUSAL_TEXT
    assert _kinds(answer)[-2:] == [StepKind.PARENTS, StepKind.REFUSAL]


def test_some_sections_readable_still_answers():
    """The other side of that floor, so it cannot degenerate into "any
    missing section blocks the answer". Four of five is an answer; the
    trace carries the shortfall."""
    hits = (HIT, dataclasses.replace(HIT, parent_id="p-2", chunk_text="autre"))

    answer = _ask(
        ports=_ports(
            retrieve=lambda ws, query: hits,
            fetch_parents=lambda ws, ids: {"p-1": PARENT_TEXT},
        )
    )

    assert answer.kind is AnswerKind.ANSWER


def test_a_refusal_never_fetches_a_parent(monkeypatch):
    """Box P sits on the ANSWER branch only. Refusing after three failed
    searches should not go and read sections nobody is going to cite."""
    _with_settings(monkeypatch, retry_ceiling=1)
    fetch = _Recorder({})

    answer = _ask(ports=_ports(grade=lambda q, p: False, fetch_parents=fetch))

    assert answer.kind is AnswerKind.REFUSAL
    assert fetch.calls == []


# --- the port contract itself ------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "port"),
    [
        ({"clarify": lambda question, summary: "  "}, "clarify"),
        ({"rewrite": lambda question, summary: ("",)}, "rewrite"),
        ({"grade": lambda q, p: False, "reword": lambda q, prev, n: ("",)}, "reword"),
        ({"write_answer": lambda question, passages, parents: "\n"}, "write_answer"),
    ],
    ids=["clarify", "rewrite", "reword", "write_answer"],
)
def test_a_port_that_returns_a_blank_string_fails_loudly_and_by_name(
    monkeypatch, overrides, port
):
    """Found by running the graph, not by reading it, and no other test in
    this file could see either half:

    a `clarify` port returning "" was read as "the question is clear", so
    the agent skipped the clarifying question and ANSWERED -- the guessing
    F-06 forbids, done in silence. A blank `rewrite` or `reword` sent the
    empty string to the store as a search, and the refusal then disclosed
    `('',)` to the user as what it had looked for.

    The error names the port, because the fix is always in the port and
    never in the graph."""
    _with_settings(monkeypatch, retry_ceiling=1)

    with pytest.raises(ValueError, match=f"the {port} port returned a blank"):
        _ask(ports=_ports(**overrides))


@pytest.mark.parametrize(
    ("overrides", "port"),
    [
        ({"rewrite": lambda question, summary: ()}, "rewrite"),
        ({"grade": lambda q, p: False, "reword": lambda q, prev, n: []}, "reword"),
    ],
    ids=["rewrite", "reword"],
)
def test_a_port_that_returns_no_queries_at_all_fails_loudly(monkeypatch, overrides, port):
    """The plural version of the blank string, and it was an UNTESTED
    guard until a mutation survived: deleting the check changed nothing,
    because no test made a port return an empty sequence.

    What it prevents: the graph searches nothing, grades nothing, and
    refuses while disclosing to the user that it looked for nothing at
    all (F-05)."""
    _with_settings(monkeypatch, retry_ceiling=1)

    with pytest.raises(ValueError, match=f"the {port} port returned no queries"):
        _ask(ports=_ports(**overrides))


def test_a_port_that_raises_is_not_papered_over():
    """PRD section 11: "answering service unreachable -> clear error and a
    retry action; NO FABRICATED FALLBACK ANSWER". The graph's job is to
    let it through; turning it into an HTTP 503 is the API layer's
    (openapi documents that response on /ask)."""

    def unreachable(question, passages, parents):
        raise ConnectionError("the answering model is unreachable")

    with pytest.raises(ConnectionError, match="unreachable"):
        _ask(ports=_ports(write_answer=unreachable))


def test_a_split_wider_than_the_configured_limit_is_refused(monkeypatch):
    """The retry ceiling bounds how many ROUNDS run; this bounds how wide
    a round is. Without it a rewrite returning forty phrases costs
    (ceiling + 1) x 40 real searches for one question, and F-05 reads all
    forty back to the user as "what I looked for".

    Run at a non-default limit so a mutation that ignores the setting and
    hardcodes the default cannot pass."""
    _with_settings(monkeypatch, max_sub_queries=3)
    four = ("a", "b", "c", "d")

    with pytest.raises(ValueError, match="4 sub-queries and the configured limit is 3"):
        _ask(ports=_ports(rewrite=lambda question, summary: four))


def test_a_split_exactly_at_the_limit_is_allowed(monkeypatch):
    """The boundary from the other side. Asserted because "3 is too many"
    and "4 is too many" are different rules and only one of them is
    written down."""
    _with_settings(monkeypatch, max_sub_queries=3)

    answer = _ask(ports=_ports(rewrite=lambda question, summary: ("a", "b", "c")))

    assert len(answer.searched) == 3


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("", "at least 1 character"),
        ("   \n ", "at least 1 character"),
        ("x" * 2001, "at most 2000 characters"),
    ],
    ids=["empty", "whitespace", "too-long"],
)
def test_a_question_outside_the_contract_is_refused_at_the_front_door(
    question, expected
):
    """openapi AskRequest bounds the question at 1..2000 characters, and
    ADR-13 has the UI calling this function IN-PROCESS -- so the route's
    validation is not in this path.

    Before this check a blank question did fail, but three nodes later and
    with the message "the rewrite port returned a blank string", which
    sends whoever reads it to ST-22's code for a fault the caller
    committed."""
    with pytest.raises(ValueError, match=expected):
        ask(workspace_id="ws-hr", question=question, ports=_ports())


def test_a_question_exactly_at_the_length_limit_is_accepted():
    """The boundary from the allowed side: 2000 is in, 2001 is out."""
    answer = ask(workspace_id="ws-hr", question="x" * 2000, ports=_ports())

    assert answer.kind is AnswerKind.ANSWER


def test_a_session_id_is_echoed_back_when_given_and_minted_when_not():
    """openapi AskRequest: "echo a previous session_id to keep
    conversation memory ... omit it to start clean"."""
    echoed = _ask(ports=_ports(), session_id="session-42")
    minted = _ask(ports=_ports())
    second_minted = _ask(ports=_ports())

    assert echoed.session_id == "session-42"
    assert minted.session_id
    assert minted.session_id != second_minted.session_id
