"""The agent graph (ST-21): architecture section 5.2, wired end to end.

ADR-03 makes the answering flow a LangGraph graph rather than a
hand-rolled loop, "because a graph also makes the F-04 retry ceiling and
the F-05 refusal path explicit and testable". That is what this file is:
the boxes of section 5.2 as nine nodes, three branches, and one entry
point.

    summarize -> rewrite -> ( clarify                                    )
                          -> retrieve -> grade -> ( fetch_parents -> answer )
                                                -> ( reword -> retrieve ... )
                                                -> ( refuse               )

`ask` is the only place an `Answer` is built. Every node writes a draft
into the state and the trace accumulates beside it; `ask` puts the two
together at the end. So "every answer object carries its trace" -- ST-21's
exit gate -- is true because there is no other way to make one, not
because nine nodes each remembered to attach it.

ONE THING THIS FILE DELIBERATELY DOES NOT DO, because the first draft did
it and running it proved the reason wrong. LangGraph stops a graph after a
maximum number of super-steps, and this graph's length grows with the
operator's retry ceiling: about 5 nodes plus 3 per retry (F-04 invites an
operator to raise that ceiling). The documented default of 25 would have
made a ceiling of 7 crash with an opaque `GraphRecursionError`, so `ask`
was written to derive its own limit from the ceiling.

MEASURED on the pinned version instead of trusted: langgraph 1.2.9's
default is `DEFAULT_RECURSION_LIMIT = 10007`
(`langgraph/_internal/_config.py:32`), and a ceiling of 50 -- 155 nodes --
ran to completion untouched. Two honest limits on that sentence: the
ceiling-50 run was a ONE-OFF measurement in a session scratchpad, not a
check that runs (the highest ceiling any test uses is 20), and the
constant is `int(getenv("LANGGRAPH_DEFAULT_RECURSION_LIMIT", "10007"))`,
so an environment that sets that variable low would break a high-ceiling
run -- and `test_a_high_retry_ceiling_runs_to_completion` would fail for
a reason its own name does not mention. The "25" is old documentation. A
hand-computed limit would therefore have been a SECOND, LOWER bound whose
only possible effect is to cut a legitimate run short the day someone adds
a node to section 5.2, which is precisely the failure it was invented to
prevent. It is gone. The retry ceiling bounds the loop; the framework's
own limit is the backstop, three orders of magnitude away.
`test_a_high_retry_ceiling_runs_to_completion` pins that: it needs 65
nodes, so it turns red if a future langgraph brings the default back down.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent import nodes
from agent.ports import AgentPorts
from agent.state import AgentState, Answer, Source, Turn
from agent.trace import Trace, TraceStep
from config import get_settings


def _new_id() -> str:
    """A session id and a trace id.

    `db.repo.new_id` is the same one line, and this deliberately does not
    import it: its docstring scopes it to "the `uuid` columns" of the
    SQLite schema, and neither of these is a column today -- the trace has
    nowhere to be stored (see the ADR-09 escalation in DECISIONS) and the
    session lives for one conversation. Reaching into `db` for it would
    make the answering module unimportable without SQLite and the schema
    file, and architecture section 4 keeps `agent` and `db` apart. Second
    copy of one stdlib call; the core law allows two."""
    return str(uuid.uuid4())


def build_graph(ports: AgentPorts) -> CompiledStateGraph:
    """Compile section 5.2 into a runnable graph.

    Takes the ports rather than reading a module-level default, because
    there is no default: see agent/ports.py for why a stub that answers
    plausibly is the most dangerous object in this project."""
    builder = StateGraph(AgentState)

    builder.add_node(nodes.SUMMARIZE, nodes.make_summarize(ports))
    builder.add_node(nodes.REWRITE, nodes.make_rewrite(ports))
    builder.add_node(nodes.CLARIFY, nodes.make_clarify(ports))
    builder.add_node(nodes.RETRIEVE, nodes.make_retrieve(ports))
    builder.add_node(nodes.GRADE, nodes.make_grade(ports))
    builder.add_node(nodes.FETCH_PARENTS, nodes.make_fetch_parents(ports))
    builder.add_node(nodes.REWORD, nodes.make_reword(ports))
    builder.add_node(nodes.ANSWER, nodes.make_answer(ports))
    builder.add_node(nodes.REFUSE, nodes.make_refuse(ports))

    builder.add_edge(START, nodes.SUMMARIZE)
    builder.add_edge(nodes.SUMMARIZE, nodes.REWRITE)
    builder.add_conditional_edges(
        nodes.REWRITE,
        nodes.route_after_rewrite,
        {nodes.CLARIFY: nodes.CLARIFY, nodes.RETRIEVE: nodes.RETRIEVE},
    )
    builder.add_edge(nodes.RETRIEVE, nodes.GRADE)
    builder.add_conditional_edges(
        nodes.GRADE,
        nodes.route_after_grade,
        {
            nodes.FETCH_PARENTS: nodes.FETCH_PARENTS,
            nodes.REWORD: nodes.REWORD,
            nodes.REFUSE: nodes.REFUSE,
        },
    )
    builder.add_conditional_edges(
        nodes.FETCH_PARENTS,
        nodes.route_after_parents,
        {nodes.ANSWER: nodes.ANSWER, nodes.REFUSE: nodes.REFUSE},
    )
    builder.add_edge(nodes.REWORD, nodes.RETRIEVE)
    builder.add_edge(nodes.CLARIFY, END)
    builder.add_edge(nodes.ANSWER, END)
    builder.add_edge(nodes.REFUSE, END)

    return builder.compile()


def initial_state(
    *,
    workspace_id: str,
    question: str,
    session_id: str,
    history: tuple[Turn, ...],
) -> AgentState:
    """Every key the nodes read, present from the start.

    A `TypedDict` is a dict at runtime, so a key left out here is a
    `KeyError` inside a node halfway through a run rather than a type
    error anywhere. Written once, in one place, for that reason."""
    return AgentState(
        workspace_id=workspace_id,
        session_id=session_id,
        question=question,
        history=history,
        summary="",
        queries=(),
        passages=(),
        relevant=False,
        parents={},
        parents_unreadable=False,
        clarification=None,
        steps=[],
        answer_kind=None,
        answer_text="",
        answer_sources=(),
    )


def ask(
    *,
    workspace_id: str,
    question: str,
    ports: AgentPorts,
    session_id: str | None = None,
    history: Sequence[Turn] = (),
) -> Answer:
    """Run one question through the graph and return one answer object.

    `session_id` is echoed back so the caller can pass it to the next
    question and keep in-session memory (F-07, openapi AskRequest); omit
    it to start a clean conversation, which mints a new one.

    The graph is compiled per call. That is a few milliseconds of Python
    with no I/O in it, and it keeps this function stateless -- a long-lived
    compiled graph would be a shared object with the ports baked in, and
    ST-51 wiring a real one is a different decision from ST-21's."""
    settings = get_settings()
    asked = question.strip()
    # openapi AskRequest bounds the question at 1..2000 characters, and
    # ADR-13 has the UI calling this function IN-PROCESS -- so the route's
    # validation is not in that path and without this the contract holds
    # only for HTTP callers. A blank question did eventually fail before
    # this check, but three nodes later and with the wrong message: "the
    # rewrite port returned a blank string", which sends whoever reads it
    # to ST-22's code for a fault the caller committed.
    if len(asked) < settings.question_min_length:
        raise ValueError(
            f"a question must be at least {settings.question_min_length} "
            f"character(s) (openapi AskRequest.question). Nothing was asked."
        )
    if len(asked) > settings.question_max_length:
        raise ValueError(
            f"a question may be at most {settings.question_max_length} "
            f"characters (openapi AskRequest.question); this one is "
            f"{len(asked)}."
        )

    session = session_id or _new_id()
    graph = build_graph(ports)
    final: dict = graph.invoke(
        initial_state(
            workspace_id=workspace_id,
            question=asked,
            session_id=session,
            history=tuple(history),
        )
    )

    kind = final["answer_kind"]
    if kind is None:
        # Not reachable through the edges above: all three terminal nodes
        # set a kind. It is checked anyway because the alternative failure
        # is an `Answer` built from an empty draft, which is a blank
        # message bubble in front of a user (PRD section 11: never fake
        # success).
        raise RuntimeError(
            "the agent graph finished without reaching answer, refusal or "
            "clarification. This is a wiring bug in agent/graph.py, not a "
            "condition a caller can cause."
        )

    steps: tuple[TraceStep, ...] = tuple(final["steps"])
    sources: tuple[Source, ...] = tuple(final["answer_sources"])
    return Answer(
        kind=kind,
        text=final["answer_text"],
        sources=sources,
        session_id=final["session_id"],
        trace=Trace(trace_id=_new_id(), steps=steps),
    )
