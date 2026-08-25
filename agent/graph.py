"""The agent graph (ST-21): architecture section 5.2, wired end to end.

ADR-03 makes the answering flow a LangGraph graph rather than a
hand-rolled loop, "because a graph also makes the F-04 retry ceiling and
the F-05 refusal path explicit and testable". That is what this file is:
eight boxes from section 5.2, two branches, and one entry point.

    summarize -> rewrite -> ( clarify                                )
                          -> retrieve -> grade -> ( answer           )
                                                -> ( reword -> retrieve ... )
                                                -> ( refuse           )

`ask` is the only place an `Answer` is built. Every node writes a draft
into the state and the trace accumulates beside it; `ask` puts the two
together at the end. So "every answer object carries its trace" -- ST-21's
exit gate -- is true because there is no other way to make one, not
because eight nodes each remembered to attach it.

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
runs to completion untouched. The "25" is old documentation. A
hand-computed limit would therefore have been a SECOND, LOWER bound whose
only possible effect is to cut a legitimate run short the day someone adds
a node to section 5.2, which is precisely the failure it was invented to
prevent. It is gone. The retry ceiling bounds the loop; the framework's
own limit is the backstop, three orders of magnitude away.
`test_a_high_retry_ceiling_runs_to_completion` pins that: it needs 65
nodes, so it turns red if a future langgraph brings the default back down.
"""

from __future__ import annotations

from collections.abc import Sequence

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agent import nodes
from agent.ports import AgentPorts
from agent.state import AgentState, Answer, Source, Turn
from agent.trace import Trace, TraceStep
from db import repo


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
            nodes.ANSWER: nodes.ANSWER,
            nodes.REWORD: nodes.REWORD,
            nodes.REFUSE: nodes.REFUSE,
        },
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
        query="",
        passages=(),
        relevant=False,
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
    session = session_id or repo.new_id()
    graph = build_graph(ports)
    final: dict = graph.invoke(
        initial_state(
            workspace_id=workspace_id,
            question=question,
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
        trace=Trace(trace_id=repo.new_id(), steps=steps),
    )
