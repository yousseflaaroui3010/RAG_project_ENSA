"""What the agent passes between nodes, and what it hands back (ST-21).

Two things live here and they are deliberately different shapes:

`Answer` is the OUTPUT CONTRACT. It mirrors the `Answer` schema in
docs/phase2/openapi.yaml, which is the contract of record. It is frozen,
it validates itself, and it carries its trace.

`AgentState` is the SCRATCHPAD the graph writes while it works. It is a
plain TypedDict because that is what LangGraph reads, and every node
returns a partial update of it rather than mutating it.

THE INVARIANT THAT IS ENFORCED HERE RATHER THAN ASKED FOR POLITELY:
an answer with no sources cannot exist. docs/phase2/CLAUDE.md states it as
"an answer object without at least one source does not render as final",
openapi states it as "non-empty whenever kind is answer (application
invariant, G3)", and F-03 makes the source line "the product's contract
with the user". A rule written in three documents and checked in none is a
rule that ships broken once. `Answer.__post_init__` raises, so the failure
is a crash in a test rather than an unsourced claim in front of a jury.

A KNOWN AMBIGUITY IN THE SIGNED CONTRACT, recorded rather than silently
resolved (CLAUDE.md rule 1). openapi line 223 says "refusal false implies
sources is non-empty", and openapi line 512 says sources are "non-empty
whenever kind is answer". Those two agree for the answer/refusal pair the
sentence was written about, and disagree about the third kind: a
clarification is not a refusal, so `refusal` is false, yet it has retrieved
nothing and can cite nothing. This module enforces the line-512 reading
(kind == answer implies sources) because it is the one G3 measures, and
flags the other for a human. See BUILD-STATE.
"""

from __future__ import annotations

import operator
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, TypedDict

from agent.trace import Trace, TraceStep
from vector_store import SearchHit


class AnswerKind(StrEnum):
    """openapi `Answer.kind`, verbatim. UX spec section 8 renders one
    message variant per value, which is why a clarification is a kind of
    answer here rather than a separate return type: the chat transcript
    holds all three the same way."""

    ANSWER = "answer"
    REFUSAL = "refusal"
    CLARIFICATION = "clarification"


@dataclass(frozen=True)
class Source:
    """openapi `Source`: the file name, plus the section label when the
    document gave us one (F-03). Frozen and hashable so the answer node
    can de-duplicate five chunks of one article into one source card."""

    file_name: str
    section_label: str | None = None


@dataclass(frozen=True)
class Turn:
    """One completed exchange, for in-session memory (F-07).

    ST-25 owns what gets summarized out of these; ST-21 only carries them
    so the summary seam has something real to be handed."""

    question: str
    answer: str


@dataclass(frozen=True)
class Answer:
    """One outcome of one question: an answer, an honest refusal, or a
    single clarifying question.

    Mirrors openapi `Answer`. Two of that schema's eight fields are
    PROPERTIES here rather than stored values -- `searched` and `refusal`
    -- because storing them would mean two places could disagree about
    what happened. `searched` reads the trace, and the trace is what the
    graph actually did.

    `trace` is the whole collector, not just its id. The API layer (ST-51)
    serializes `trace_id` alone, per openapi's "stored trace reference";
    the object in the process keeps the steps so F-10 and the evaluation
    runner can read them without a round trip."""

    kind: AnswerKind
    text: str
    sources: tuple[Source, ...]
    session_id: str
    trace: Trace
    # F-09's line is wired by ST-26 from the workspace's legal flag. It is
    # False here and no test in this story claims otherwise: a default that
    # nobody has exercised is not a feature.
    disclaimer: bool = False

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError(
                f"an answer of kind {self.kind} has no text. Every one of the "
                f"three UX spec section 8 message variants renders text; an "
                f"empty bubble is not one of them."
            )
        if self.kind is AnswerKind.ANSWER and not self.sources:
            raise ValueError(
                "an answer with no sources cannot be final (openapi Answer: "
                "sources non-empty whenever kind is answer; PRD F-03). Route "
                "it to the refusal path instead of citing nothing."
            )

    @property
    def refusal(self) -> bool:
        """openapi `Answer.refusal`. Derived from the kind so the boolean
        and the variant the UI renders cannot contradict each other."""
        return self.kind is AnswerKind.REFUSAL

    @property
    def searched(self) -> tuple[str, ...]:
        """openapi `Answer.searched`: "the search strings attempted, always
        disclosed on refusals" (F-05)."""
        return self.trace.searches

    @property
    def trace_id(self) -> str:
        return self.trace.trace_id

    @property
    def retries(self) -> int:
        """What UX spec section 8's inline marker shows on the bubble."""
        return self.trace.retries


class AgentState(TypedDict):
    """The graph's working state (architecture section 5.2).

    `steps` is the only accumulating field: `operator.add` appends what
    each node returns instead of overwriting, so the trace is append-only
    by construction and a node cannot erase an earlier step. Everything
    else is last-write-wins, which is what "the current query" means.

    The three `answer_*` fields are a DRAFT, not an `Answer`. Only
    `agent.graph.ask` builds the real object, and it is the only place the
    trace gets attached -- which is what makes "every answer object carries
    its trace" a property of the design rather than of every node
    remembering to do it."""

    workspace_id: str
    session_id: str
    question: str
    history: tuple[Turn, ...]
    summary: str
    query: str
    passages: tuple[SearchHit, ...]
    relevant: bool
    clarification: str | None
    steps: Annotated[list[TraceStep], operator.add]
    answer_kind: AnswerKind | None
    answer_text: str
    answer_sources: tuple[Source, ...]
