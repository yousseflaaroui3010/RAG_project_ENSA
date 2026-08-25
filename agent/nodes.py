"""The nodes of architecture section 5.2, one function per box (ST-21).

Each node is built by a small factory that binds it to the `AgentPorts`
(see agent/ports.py), so the thinking arrives later from ST-22 to ST-25
while the flow, the ceiling and the trace are settled now.

Every node returns a PARTIAL state update, never a mutated state, and
every node records exactly one trace step. That second rule is what makes
the trace complete: a step that is not recorded is work F-10 cannot show
and the retry ceiling cannot count.

WHAT SECTION 5.2 HAS THAT THIS FILE DOES NOT, so a reader does not go
looking for it: the diagram's `P[Fetch parent sections for context]` box.
ADR-03's node list -- "summary, rewrite-and-split, clarification pause,
retrieval, grading, reword retry, answer, refusal" -- does not include it,
and a parent fetch changes no route: it is the answer step reading the
full section behind a hit it already has. It therefore belongs inside
ST-23's `retrieve` port or ST-24's `write_answer` port, whichever needs
the text. An empty pass-through node added now would be a box in a
picture, not a seam.
"""

from __future__ import annotations

from collections.abc import Callable

from agent.ports import AgentPorts
from agent.state import AgentState, AnswerKind, Source
from agent.trace import StepKind, TraceStep, rewords_in, searches_in
from config import get_settings
from vector_store import SearchHit

# Node names. The graph wires these and the routers return them, so they
# are written once here rather than as string literals in two files.
SUMMARIZE = "summarize"
REWRITE = "rewrite"
CLARIFY = "clarify"
RETRIEVE = "retrieve"
GRADE = "grade"
REWORD = "reword"
ANSWER = "answer"
REFUSE = "refuse"

# The honest refusal (F-05, PRD section 11: "plain language, no jargon,
# never fake success, always name a next step").
#
# ST-24 OWNS THE FINAL WORDING and this is not it -- it is the minimum
# that is true. The searches themselves are not pasted in here: they are
# on the answer object as `searched`, and UX spec section 8 gives the
# refusal variant its own design that "states what was searched". Putting
# the list in the prose as well would be the same facts in two places,
# free to disagree.
REFUSAL_TEXT = (
    "I could not find an answer to this question in this workspace. "
    "The searches I ran are listed with this message. You could rephrase "
    "the question, add the document that covers it to this workspace, or "
    "switch to the workspace that does."
)

# Trace details for the steps whose detail is not a search string.
_AMBIGUOUS = "ambiguous, asking one clarifying question"
_RELEVANT = "passages address the question"
_OFF_TOPIC = "passages do not address the question"
_NOTHING_FOUND = "no passages found"


def _spoken(value: str, port: str) -> str:
    """A port's string answer, refused if it is blank.

    FOUND BY RUNNING IT, not by reading it, and neither failure was
    visible to any other test in this story:

    * `clarify` returning "" is neither None ("clear") nor a question
      ("unclear"). Under a truthiness check the flow read it as clear,
      skipped the clarifying question and ANSWERED -- which is precisely
      the guessing F-06 exists to prevent, done silently.
    * `rewrite` or `reword` returning "" sent the empty string to the
      store as a search, and an honest refusal then disclosed `('',)` to
      the user as what it had looked for (F-05).

    A blank is always a broken port, never a meaningful value, so it fails
    here -- named, at the seam that produced it -- instead of three nodes
    later as a puzzling empty answer. ST-22 to ST-24 fill these ports in;
    this is the contract they are filling."""
    if not value or not value.strip():
        raise ValueError(
            f"the {port} port returned a blank string. Return real text, or "
            f"-- for clarify -- return None to mean 'the question is clear'."
        )
    return value


def _attempt_number(state: AgentState) -> int:
    """Which retry this is, 1-based, counted from the trace.

    The trace is the only counter (see agent/trace.py). A node that kept
    its own would be the second source of truth for the one number F-04
    puts a ceiling on."""
    return rewords_in(state["steps"]) + 1


def _sources_for(passages: tuple[SearchHit, ...]) -> tuple[Source, ...]:
    """One source per distinct file-and-section, first-seen order.

    Five chunks of Article 17 are one citation, not five. De-duplicating
    here rather than in the UI keeps the openapi `sources` array honest
    for the API caller too, who has no UI to tidy it up."""
    seen: dict[Source, None] = {}
    for hit in passages:
        seen.setdefault(Source(hit.source_file, hit.section_label), None)
    return tuple(seen)


def make_summarize(ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 box M: summarize the session context (F-07)."""

    def summarize(state: AgentState) -> dict:
        summary = ports.summarize(state["history"])
        detail = summary if summary else "no earlier turns in this session"
        return {
            "summary": summary,
            "steps": [TraceStep(StepKind.SUMMARY, detail)],
        }

    return summarize


def make_rewrite(ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 box R: rewrite and split, or find the question unclear.

    Both halves of the diagram's branch live here because they are one
    decision about one question. The clarifying question itself is not
    asked here -- `clarify` is a terminal node, and keeping the asking
    separate from the deciding is what lets ST-22 resume the flow after
    the user replies without re-deciding."""

    def rewrite(state: AgentState) -> dict:
        question, summary = state["question"], state["summary"]
        clarification = ports.clarify(question, summary)
        if clarification is not None:
            return {
                "clarification": _spoken(clarification, "clarify"),
                "steps": [TraceStep(StepKind.REWRITE, _AMBIGUOUS)],
            }
        query = _spoken(ports.rewrite(question, summary), "rewrite")
        return {
            "query": query,
            "clarification": None,
            "steps": [TraceStep(StepKind.REWRITE, query)],
        }

    return rewrite


def make_clarify(_ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 box C: ask exactly one clarifying question (F-06).

    Takes no port: the question was already decided in `rewrite`. This
    node exists to make the pause a real end state of the graph, because
    F-06's second criterion is that the flow RESUMES after the user
    answers -- ST-22 resumes it by asking again with the reply in hand."""

    def clarify(state: AgentState) -> dict:
        question = state["clarification"]
        return {
            "answer_kind": AnswerKind.CLARIFICATION,
            "answer_text": question,
            "answer_sources": (),
            "steps": [TraceStep(StepKind.CLARIFY, question)],
        }

    return clarify


def make_retrieve(ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 box S: hybrid search on child chunks.

    The step's detail is the exact string searched, which is what F-05
    discloses on a refusal and what F-10 lists. The files it touched ride
    on the same step, so the trace can say which search found which
    file."""

    def retrieve(state: AgentState) -> dict:
        query = state["query"]
        passages = tuple(ports.retrieve(state["workspace_id"], query))
        files = tuple(dict.fromkeys(hit.source_file for hit in passages))
        return {
            "passages": passages,
            "steps": [TraceStep(StepKind.SEARCH, query, files)],
        }

    return retrieve


def make_grade(ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 box G: do these passages address the question? (F-04)

    Empty results are judged here rather than sent to the grader. Two
    reasons, and the second is the load-bearing one: a search that found
    nothing needs no model to interpret, and a grader that answered "yes"
    to zero passages would hand the answer node nothing to cite -- which
    `Answer.__post_init__` refuses. Deciding it here turns a possible
    crash into the refusal the flow already has."""

    def grade(state: AgentState) -> dict:
        passages = state["passages"]
        if not passages:
            return {
                "relevant": False,
                "steps": [TraceStep(StepKind.GRADE, _NOTHING_FOUND)],
            }
        relevant = bool(ports.grade(state["question"], passages))
        detail = _RELEVANT if relevant else _OFF_TOPIC
        return {
            "relevant": relevant,
            "steps": [TraceStep(StepKind.GRADE, detail)],
        }

    return grade


def make_reword(ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 box RW: reword the query and search again (F-04)."""

    def reword(state: AgentState) -> dict:
        query = _spoken(
            ports.reword(state["question"], state["query"], _attempt_number(state)),
            "reword",
        )
        return {
            "query": query,
            "steps": [TraceStep(StepKind.REWORD, query)],
        }

    return reword


def make_answer(ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 boxes A and SRC: write the answer, attach the sources.

    The sources come from the passages the graph retrieved, not from the
    model's output. F-03 makes the source line the product's contract with
    the user; a citation the model composed could name a file that was
    never searched."""

    def answer(state: AgentState) -> dict:
        passages = state["passages"]
        text = _spoken(ports.write_answer(state["question"], passages), "write_answer")
        sources = _sources_for(passages)
        return {
            "answer_kind": AnswerKind.ANSWER,
            "answer_text": text,
            "answer_sources": sources,
            "steps": [TraceStep(StepKind.ANSWER, f"answered from {len(sources)} source(s)")],
        }

    return answer


def make_refuse(_ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 box REF: the honest refusal (F-05).

    Takes no port. Refusing is not a thing a model decides -- it is what
    the graph does when the grader has said no as many times as the
    ceiling allows, and no model is asked to talk it out of that."""

    def refuse(state: AgentState) -> dict:
        searched = len(searches_in(state["steps"]))
        return {
            "answer_kind": AnswerKind.REFUSAL,
            "answer_text": REFUSAL_TEXT,
            "answer_sources": (),
            "steps": [TraceStep(StepKind.REFUSAL, f"refused after {searched} search(es)")],
        }

    return refuse


def route_after_rewrite(state: AgentState) -> str:
    """Section 5.2: unclear -> ask; clear -> search.

    `is not None` rather than truthiness, matching `make_rewrite`, because
    the field is `str | None` and None is the only "clear" value.

    Labelled honestly: with `_spoken` in place a blank clarification can no
    longer reach this line, so NO TEST CAN TELL THE TWO SPELLINGS APART
    here -- mutating it survives the suite, and that means redundant, not
    untested. It stays because the two places that read this field should
    read it by the same rule; `_spoken` is where the blank is actually
    stopped."""
    return CLARIFY if state["clarification"] is not None else RETRIEVE


def route_after_grade(state: AgentState) -> str:
    """Section 5.2's three-way branch, and the only place the F-04 ceiling
    is enforced.

    The ceiling is read from config on every decision, never captured at
    build time, so an operator's `RETRY_CEILING` is what actually bounds
    the loop (docs/phase2/CLAUDE.md: "the retry ceiling comes from config,
    never hardcode it"). The count it is compared against is the trace's,
    so the number in the marker on the bubble and the number that stopped
    the loop are one number."""
    if state["relevant"]:
        return ANSWER
    if rewords_in(state["steps"]) < get_settings().retry_ceiling:
        return REWORD
    return REFUSE
