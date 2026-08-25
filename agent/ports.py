"""The seven seams the agent graph is wired to (ST-21).

ST-21 builds the SHAPE of the answering flow: the order of the nodes, the
branch to a clarifying question, the retry loop and its ceiling, the
refusal path, and the trace. It deliberately builds none of the thinking.
Every place the flow needs a model or the vector store is one function on
this object, and every one of them belongs to a story that has not been
built yet:

| Port           | Owner  | What it becomes                                |
|----------------|--------|------------------------------------------------|
| `summarize`    | ST-25  | session memory summary (F-07)                  |
| `clarify`      | ST-22  | "is this ambiguous?" -> one question (F-06)    |
| `rewrite`      | ST-22  | rewrite-and-split into a search query          |
| `retrieve`     | ST-23  | hybrid search over `vector_store` (ADR-05)     |
| `grade`        | ST-23  | do these passages address the question? (F-04) |
| `reword`       | ST-23  | the retry's new phrasing (F-04)                |
| `write_answer` | ST-24  | the answer text, from passages only (F-03)     |

THERE ARE NO DEFAULTS, and that is the whole point of the file. A stub
that answers plausibly is the most dangerous object in a project like this
one: wire it in as a default and the day someone forgets to pass real
ports, Sanad invents an answer instead of failing. `AgentPorts` has seven
required fields, so a caller who has not built the real thing yet cannot
get a running graph by accident -- only by writing the fake out loud, which
is what `tests/unit/test_agent_graph.py` does.

The types are plain callables rather than a class to subclass, because
each port is replaced by exactly one story and a story should be able to
drop in one function without inheriting six it does not own yet.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
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

# (question, summary) -> the string actually searched for. Section 5.2's
# "rewrite and split"; V1 returns one query.
Rewrite = Callable[[str, str], str]

# (workspace_id, query) -> the child chunks found. ST-23 fulfils this with
# `vector_store.search`, which takes the raw question and does its own
# encoding, so nothing on this side of the seam ever holds a vector.
Retrieve = Callable[[str, str], Sequence[SearchHit]]

# (question, passages) -> do these passages actually address it? (F-04)
Grade = Callable[[str, tuple[SearchHit, ...]], bool]

# (question, previous_query, attempt) -> the reworded query. `attempt` is
# 1 for the first retry, so a grader-driven strategy can widen the search
# as attempts go on without counting anything itself.
Reword = Callable[[str, str, int], str]

# (question, passages) -> the answer text, written from those passages
# only (F-03). Sources are attached by the graph, from the same passages,
# so the model cannot invent a citation.
WriteAnswer = Callable[[str, tuple[SearchHit, ...]], str]


@dataclass(frozen=True)
class AgentPorts:
    """Everything the graph needs that the graph does not do itself."""

    summarize: Summarize
    clarify: Clarify
    rewrite: Rewrite
    retrieve: Retrieve
    grade: Grade
    reword: Reword
    write_answer: WriteAnswer
