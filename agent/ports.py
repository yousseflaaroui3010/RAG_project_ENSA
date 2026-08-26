"""The eight seams the agent graph is wired to (ST-21).

ST-21 builds the SHAPE of the answering flow: the order of the nodes, the
branch to a clarifying question, the retry loop and its ceiling, the
refusal path, and the trace. It deliberately builds none of the thinking.
Every place the flow needs a model or a store is one function on this
object, and every one of them belongs to a story that has not been built
yet:

| Port            | Owner  | What it becomes                               |
|-----------------|--------|-----------------------------------------------|
| `summarize`     | ST-25  | session memory summary (F-07)                 |
| `clarify`       | ST-22  | "is this ambiguous?" -> one question (F-06)   |
| `rewrite`       | ST-22  | rewrite-and-SPLIT into one or more queries    |
| `retrieve`      | ST-23  | hybrid search over `vector_store` (ADR-05)    |
| `grade`         | ST-23  | do these passages address the question? F-04  |
| `reword`        | ST-23  | the retry's new phrasing (F-04)               |
| `fetch_parents` | ST-24  | full section text behind each hit (5.2 box P) |
| `write_answer`  | ST-24  | the answer text, from those sections (F-03)   |

THERE ARE NO DEFAULTS, and that is the whole point of the file. A stub
that answers plausibly is the most dangerous object in a project like this
one: wire it in as a default and the day someone forgets to pass real
ports, Sanad invents an answer instead of failing. `AgentPorts` has eight
required fields, so a caller who has not built the real thing yet cannot
get a running graph by accident -- only by writing the fake out loud,
which is what `tests/unit/test_agent_graph.py` does.

`fetch_parents` is the one port with a REAL implementation already in the
repo: `agent.stores.parent_texts` is a thin call over `parent_store`, and
`tests/unit/test_agent_stores.py` exercises it against a real parent store
on disk. It is a store read, not a model call, so there was nothing to
defer -- ST-24 wires it in rather than writing it.

The types are plain callables rather than a class to subclass, because
each port is replaced by exactly one story and a story should be able to
drop in one function without inheriting seven it does not own yet.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from agent.state import Turn
from vector_store import SearchHit

# The session summary handed to the rewrite step. "" when there is no
# earlier turn to summarize -- an empty string, never None, so no node has
# to branch on the shape of it.
Summarize = Callable[[tuple[Turn, ...]], str]

# Returns the ONE clarifying question to ask (F-06 is explicit: exactly
# one), or None when the question is clear enough to search. None is the
# "carry on" answer, which keeps the ambiguous case the noisy one.
Clarify = Callable[[str, str], str | None]

# (question, summary) -> the queries to search for.
#
# A SEQUENCE, not one string, because architecture 5.2 calls this box
# "Rewrite and split query" and ADR-03 keeps the reference implementation's
# sub-queries. "How long is a trial period and can it be renewed?" is two
# searches; forcing it into one string would have made the split
# unrepresentable and quietly turned ST-22 into rewrite-only.
# One query is the ordinary case and stays a one-element sequence.
Rewrite = Callable[[str, str], Sequence[str]]

# (workspace_id, query) -> the child chunks found, for ONE query. The graph
# calls this once per query and merges. ST-23 fulfils it with
# `vector_store.search`, which takes the raw question and does its own
# encoding, so nothing on this side of the seam ever holds a vector.
Retrieve = Callable[[str, str], Sequence[SearchHit]]

# (question, passages) -> do these passages actually address it? (F-04)
Grade = Callable[[str, tuple[SearchHit, ...]], bool]

# (question, previous_queries, attempt) -> the reworded queries. `attempt`
# is 1 for the first retry, so a strategy can widen the search as attempts
# go on without counting anything itself.
Reword = Callable[[str, tuple[str, ...], int], Sequence[str]]

# (workspace_id, parent_ids) -> {parent_id: the full section text}.
#
# Architecture 5.2's box P, "fetch parent sections for context". Search the
# small thing, read the big thing: a hit is a 500-character child chunk and
# the model answers from the section it came out of. The workspace id is in
# the signature because `parent_store` keys on it -- which is also why this
# could never have been folded into `write_answer`, whose signature has no
# workspace in it.
#
# A parent that cannot be loaded is OMITTED rather than faked. The graph
# records the shortfall in the trace, so a store that has drifted from the
# index is visible instead of silently shrinking the context.
FetchParents = Callable[[str, tuple[str, ...]], Mapping[str, str]]

# (question, passages, parent_texts) -> the answer text, written from
# those sections only (F-03). Sources are attached by the graph, from the
# same passages, so the model cannot invent a citation.
WriteAnswer = Callable[[str, tuple[SearchHit, ...], Mapping[str, str]], str]


@dataclass(frozen=True)
class AgentPorts:
    """Everything the graph needs that the graph does not do itself."""

    summarize: Summarize
    clarify: Clarify
    rewrite: Rewrite
    retrieve: Retrieve
    grade: Grade
    reword: Reword
    fetch_parents: FetchParents
    write_answer: WriteAnswer
