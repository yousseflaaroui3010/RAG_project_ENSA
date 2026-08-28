"""The nodes of architecture section 5.2, one function per box (ST-21).

Each node is built by a small factory that binds it to the `AgentPorts`
(see agent/ports.py), so the thinking arrives later from ST-22 to ST-25
while the flow, the ceiling and the trace are settled now.

Every node returns a PARTIAL state update, never a mutated state, and
every node records at least one trace step. That second rule is what makes
the trace complete: a step that is not recorded is work F-10 cannot show
and the retry ceiling cannot count.

TWO THINGS THAT LOOK LIKE OVER-BUILDING FOR A SKELETON AND ARE NOT, both
added after a review read this file against the signed documents:

1. **The retrieve node loops over SEVERAL queries.** 5.2's box is "rewrite
   and SPLIT query" and ADR-03 keeps the reference implementation's
   sub-queries. A single-string query made the split unrepresentable, so
   ST-22 would have inherited a node it could not fill without reshaping
   the graph. One query is a one-element tuple; nothing else changes.
2. **The parent fetch is its own node and its own port.** 5.2 puts
   `P[Fetch parent sections for context]` between grading and answering,
   and it cannot be folded into a neighbour: `parent_store.get_parent`
   needs a workspace id, and no other port's signature carries one. It is
   the difference between the model reading a 500-character chunk and
   reading the article that chunk came out of.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from agent.ports import AgentPorts, AnswerNotCoveredError
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
FETCH_PARENTS = "fetch_parents"
REWORD = "reword"
ANSWER = "answer"
REFUSE = "refuse"

# The honest refusal (F-05, PRD section 11: "plain language, no jargon,
# never fake success, always name a next step").
#
# FINAL WORDING, settled by ST-24, which owns it. Four decisions in four
# sentences, all of them checkable against a signed document:
#
# * "and I will not guess" is in there because UX spec 6.2 asks for the
#   refusal to be "styled as a legitimate outcome, not a failure", and
#   copy that only apologises undercuts a design that does not. This
#   sentence says a choice was made, which is the product's whole claim.
# * The searches are NOT pasted into the prose. They are on the answer
#   object as `searched`, and 6.2 gives the refusal variant its own design
#   that "states what was searched" -- the same facts in two places are
#   two places free to disagree.
# * All three next steps PRD F-05 names are offered (rephrase, add the
#   document, switch workspace), because which one is right depends on
#   something the product cannot see: whether the document exists at all.
# * Interface copy is English for V1 (PRD section 5), even though the
#   documents and the question are usually French. This is interface copy,
#   not answer content; the answer itself follows the question's language,
#   which is the answer-writer prompt's rule.
REFUSAL_TEXT = (
    "I could not answer this from the documents in this workspace, and I "
    "will not guess. The searches I ran are listed with this message. You "
    "could rephrase the question, add the document that covers it to this "
    "workspace, or switch to the workspace that holds it."
)

# The other refusal, and it is a different fact about the world: the
# search DID find matching passages and not one of their sections could be
# read back. Saying "not covered here" then would be false, and PRD
# section 11's rule for every failure row is "never fake success, always
# name a next step" -- the next step here is a Sync, not a rephrase.
REFUSAL_TEXT_UNREADABLE = (
    "I found passages that match your question but could not read the "
    "sections they come from, so I cannot answer from them and will not "
    "guess. This usually means the stored sections are out of step with "
    "the search index. Run a Sync on this workspace and ask again."
)

# Trace details for the steps whose detail is not a search string.
_AMBIGUOUS = "ambiguous, asking one clarifying question"
_RELEVANT = "passages address the question"
_OFF_TOPIC = "passages do not address the question"
_NOTHING_FOUND = "no passages found"
# The third way a question ends in a refusal, and the only one the trace
# has to distinguish for a reader: the sections WERE read and none of them
# answers the question. The user-facing text is the same as any other "not
# covered here", because the user's next step is the same; the mechanism
# differs and the trace is where a mechanism belongs (F-10).
_NOT_IN_SECTIONS = "refused: sections read, none of them answers the question"


def _spoken(value: str, port: str) -> str:
    """A port's string answer, refused if it is blank.

    FOUND BY RUNNING IT, not by reading it, and neither failure was
    visible to any other test in this story:

    * `clarify` returning "" is neither None ("clear") nor a question
      ("unclear"). Under a truthiness check the flow read it as clear,
      skipped the clarifying question and ANSWERED -- which is precisely
      the guessing F-06 exists to prevent, done silently.
    * a blank query went to the store as a search, and an honest refusal
      then disclosed `('',)` to the user as what it had looked for (F-05).

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


def _queries(values: Sequence[str], port: str) -> tuple[str, ...]:
    """A port's set of search queries, refused if it is empty, blank, or
    wider than the configured split.

    An empty sequence is the plural version of the blank string above: the
    graph would search nothing, grade nothing, and refuse while disclosing
    that it had looked for nothing at all.

    The WIDTH cap is the other half, and the retry ceiling does not cover
    it: the ceiling bounds how many rounds run, nothing bounded how wide a
    round is. A rewrite port returning forty phrases costs
    (ceiling + 1) x 40 real searches for one question, and F-05 then reads
    all forty back to the user as "what I looked for"."""
    queries = tuple(values)
    if not queries:
        raise ValueError(
            f"the {port} port returned no queries. Section 5.2 splits a "
            f"question into one or MORE searches; one is a one-element "
            f"sequence, none is a broken port."
        )
    cap = get_settings().max_sub_queries
    if len(queries) > cap:
        raise ValueError(
            f"the {port} port returned {len(queries)} sub-queries and the "
            f"configured limit is {cap} (config.max_sub_queries). Splitting "
            f"a question is not the same as searching for everything it "
            f"mentions; raise the setting if the split is genuinely wider."
        )
    return tuple(_spoken(query, port) for query in queries)


def _attempt_number(state: AgentState) -> int:
    """Which retry this is, 1-based, counted from the trace.

    The trace is the only counter (see agent/trace.py). A node that kept
    its own would be the second source of truth for the one number F-04
    puts a ceiling on."""
    return rewords_in(state["steps"]) + 1


def _merge_hits(batches: Sequence[Sequence[SearchHit]]) -> tuple[SearchHit, ...]:
    """Hits from several queries, de-duplicated, IN QUERY ORDER.

    Identity is (parent_id, chunk_text), NOT the whole hit: the same chunk
    found by two sub-queries comes back with two different fusion scores,
    so equality on the object would keep both and the model would read the
    same passage twice.

    ORDER IS QUERY ORDER, NOT SCORE ORDER, and this needs saying because
    an earlier version of this docstring claimed "best-ranked first",
    which was false the moment there were two queries -- being found
    earlier is not being ranked higher. It is left unsorted deliberately:
    `SearchHit.score` comes out of Qdrant's Reciprocal Rank Fusion, which
    is a rank-based score computed WITHIN one query, so scores from two
    different searches are not on a comparable scale and sorting by them
    would be a second quiet wrongness rather than a fix. Fusing several
    sub-query rankings honestly is retrieval work and belongs to ST-23,
    which owns the hybrid search. Until then: whoever trims this list to
    "the top N" is trimming by query order, and this docstring is the
    warning."""
    seen: dict[tuple[str, str], SearchHit] = {}
    for batch in batches:
        for hit in batch:
            seen.setdefault((hit.parent_id, hit.chunk_text), hit)
    return tuple(seen.values())


def _sources_for(passages: tuple[SearchHit, ...]) -> tuple[Source, ...]:
    """One source per distinct file-and-section, first-seen order.

    Five chunks of Article 17 are one citation, not five. De-duplicating
    here rather than in the UI keeps the openapi `sources` array honest
    for the API caller too, who has no UI to tidy it up."""
    seen: dict[Source, None] = {}
    for hit in passages:
        seen.setdefault(Source(hit.source_file, hit.section_label), None)
    return tuple(seen)


def _refusal_draft(text: str, detail: str) -> dict:
    """The state update that makes a question end in an honest refusal.

    TWO NODES produce one: `refuse`, which is the routed end of the F-04
    loop, and `answer`, when the writer reads the sections and declines
    (F-05). One helper rather than two literals, because the pair that
    matters is `answer_kind` and `answer_sources`: a refusal that kept a
    source list would be an unsourced claim wearing citations, and the
    second copy of that pairing is exactly where it would go wrong."""
    return {
        "answer_kind": AnswerKind.REFUSAL,
        "answer_text": text,
        "answer_sources": (),
        "steps": [TraceStep(StepKind.REFUSAL, detail)],
    }


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
        queries = _queries(ports.rewrite(question, summary), "rewrite")
        return {
            "queries": queries,
            "clarification": None,
            "steps": [TraceStep(StepKind.REWRITE, " | ".join(queries))],
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
    """Section 5.2 box S: hybrid search on child chunks, once per query.

    ONE TRACE STEP PER QUERY, each carrying the exact string searched and
    the files it touched. That is what F-05 discloses on a refusal and
    what F-10 lists, and it is why the split is recorded as two searches
    rather than one joined-up line: the user asked one question, the agent
    ran two searches, and the trace should say so."""

    def retrieve(state: AgentState) -> dict:
        workspace_id = state["workspace_id"]
        batches: list[Sequence[SearchHit]] = []
        steps: list[TraceStep] = []
        for query in state["queries"]:
            hits = tuple(ports.retrieve(workspace_id, query))
            batches.append(hits)
            files = tuple(dict.fromkeys(hit.source_file for hit in hits))
            steps.append(TraceStep(StepKind.SEARCH, query, files))
        return {"passages": _merge_hits(batches), "steps": steps}

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


def make_fetch_parents(ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 box P: fetch the parent sections for context.

    Search the small thing, read the big thing: the graded hits are
    500-character child chunks, and the answer is written from the full
    sections they came out of (architecture 7.5). Each parent is asked for
    ONCE even when four chunks of it matched.

    A parent the store cannot produce is omitted, and the step records
    "loaded 4 of 5" so the shortfall is visible rather than a context that
    quietly shrank. A port returning an id NOBODY ASKED FOR is a different
    thing entirely -- the wrong workspace, or a mixed-up store -- and that
    raises, because the one failure a sourced-answer product cannot absorb
    is answering out of a section that belongs to someone else's
    workspace.

    AND THERE IS A FLOOR AT ZERO, which is not the same rule as the one
    above and was missing until a review asked what "loaded 0 of 5" does.
    It answered, handing the model an empty context while attaching five
    source citations built from the chunk metadata -- an answer citing five
    documents whose text was never read. F-03 calls the source line the
    product's contract with the user, so that case routes to a refusal
    instead, with its own wording: the passages were found, the sections
    could not be read, and the next step is a Sync."""

    def fetch_parents(state: AgentState) -> dict:
        wanted = tuple(dict.fromkeys(hit.parent_id for hit in state["passages"]))
        parents = dict(ports.fetch_parents(state["workspace_id"], wanted))
        unexpected = set(parents) - set(wanted)
        if unexpected:
            raise ValueError(
                f"the fetch_parents port returned {len(unexpected)} section(s) "
                f"nobody asked for ({sorted(unexpected)[:3]}). A parent the "
                f"graph did not request cannot be cited by any hit it holds, "
                f"and may belong to another workspace (PRD F-01)."
            )
        files = tuple(
            dict.fromkeys(
                hit.source_file for hit in state["passages"] if hit.parent_id in parents
            )
        )
        return {
            "parents": parents,
            # Computed once, here, and read by both the router and the
            # refusal node. Recomputing the same condition in two places
            # is how a refusal ends up carrying the wrong explanation.
            "parents_unreadable": bool(wanted) and not parents,
            "steps": [
                TraceStep(
                    StepKind.PARENTS,
                    f"loaded {len(parents)} of {len(wanted)} section(s)",
                    files,
                )
            ],
        }

    return fetch_parents


def make_reword(ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 box RW: reword the query and search again (F-04)."""

    def reword(state: AgentState) -> dict:
        queries = _queries(
            ports.reword(state["question"], state["queries"], _attempt_number(state)),
            "reword",
        )
        return {
            "queries": queries,
            "steps": [TraceStep(StepKind.REWORD, " | ".join(queries))],
        }

    return reword


def make_answer(ports: AgentPorts) -> Callable[[AgentState], dict]:
    """Section 5.2 boxes A and SRC: write the answer, attach the sources.

    The sources come from the passages the graph retrieved, not from the
    model's output. F-03 makes the source line the product's contract with
    the user; a citation the model composed could name a file that was
    never searched.

    ONE TUPLE DOES BOTH JOBS, and that is the point of this node. `cited`
    is the passages whose section the store could actually produce, and it
    is BOTH what the writer is shown AND what the sources are built from.
    An earlier version passed every passage to the writer and cited every
    passage, which was right whenever box P loaded everything and quietly
    wrong the moment it did not: "loaded 4 of 5" answered from four
    sections and printed five source cards, so one card pointed at a
    document whose text nothing had read. That is the same defect the floor
    at zero already refuses, surviving in the partial case -- and it could
    not be fixed by filtering in two places, because two filters agreeing
    is a convention and one filter is a fact.

    THE DECLINE (F-05). `write_answer` may raise `AnswerNotCoveredError`:
    the sections were read and they do not answer the question. Writing
    prose that says so instead would produce an `Answer` of kind `answer`,
    with `refusal` false and source cards attached, whose text refuses --
    which the evaluation's out-of-scope half would score as a non-refusal
    and a reader would have no way to tell from a real answer."""

    def answer(state: AgentState) -> dict:
        parents = state["parents"]
        cited = tuple(hit for hit in state["passages"] if hit.parent_id in parents)
        try:
            text = _spoken(
                ports.write_answer(state["question"], cited, parents),
                "write_answer",
            )
        except AnswerNotCoveredError:
            return _refusal_draft(REFUSAL_TEXT, _NOT_IN_SECTIONS)
        sources = _sources_for(cited)
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
        unreadable = state["parents_unreadable"]
        if unreadable:
            return _refusal_draft(
                REFUSAL_TEXT_UNREADABLE, "refused: passages found, no section readable"
            )
        return _refusal_draft(REFUSAL_TEXT, f"refused after {searched} search(es)")

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


def route_after_parents(state: AgentState) -> str:
    """The floor under box P: no readable section, no answer.

    Partial is fine and deliberate -- four sections of five still answers,
    and the trace says so. Zero is not: the model would be handed an empty
    context while the answer still carried a source list built from the
    chunks, which is a citation to a document nothing read (F-03)."""
    return REFUSE if state["parents_unreadable"] else ANSWER


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
        return FETCH_PARENTS
    if rewords_in(state["steps"]) < get_settings().retry_ceiling:
        return REWORD
    return REFUSE
