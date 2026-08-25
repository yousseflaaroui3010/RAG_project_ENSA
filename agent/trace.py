"""Trace collector (ADR-09): what the agent did, per answer.

ADR-09 keeps this in-process on purpose -- no external observability
service, no account, no data leaving the machine (LD-06). F-10 renders it
in V1.1; V1 only has to carry it, which is ST-21's exit gate.

THE ONE DESIGN RULE HERE, and it is the reason this file exists at all
rather than three loose fields on the answer: **the trace is the counter,
not a copy of it.** `retries` is derived by counting the reword steps that
were actually recorded, and `searches` by reading the search steps that
were actually recorded. Nothing increments a separate integer.

That matters because two numbers describing the same thing drift, and both
of these have a consumer that would show the drift to a user: the F-04
retry ceiling is enforced against this count, and UX spec section 8 puts
"a subtle inline marker ... showing the count" on the answer bubble. A
private counter plus a display list is exactly the shape where the loop
runs three times and the marker says two. Here that cannot happen: the
number shown IS the number the loop counted.

Steps are append-only and ordered. `agent/state.py` accumulates them with
an `operator.add` reducer so a node cannot rewrite history, only add to it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class StepKind(StrEnum):
    """The vocabulary of trace steps: one value per node in section 5.2.

    A StrEnum rather than free strings because two consumers read these
    back -- the retry ceiling counts REWORD, the refusal discloses SEARCH
    (F-05) -- and a typo in a string literal would silently produce a
    trace that counts nothing."""

    SUMMARY = "summary"
    REWRITE = "rewrite"
    CLARIFY = "clarify"
    SEARCH = "search"
    GRADE = "grade"
    REWORD = "reword"
    ANSWER = "answer"
    REFUSAL = "refusal"


@dataclass(frozen=True)
class TraceStep:
    """One thing the agent did.

    `detail` is what F-10 shows next to the step: for a SEARCH it is the
    exact string that was searched, which is also what an honest refusal
    has to disclose (F-05: "states what it looked for").

    `files` is the files that step consulted, empty for the steps that
    consult none. It lives on the step rather than in one flat list on the
    trace so that F-10 can say WHICH search found which file, instead of
    handing the user an undifferentiated pile."""

    kind: StepKind
    detail: str
    files: tuple[str, ...] = ()


def searches_in(steps: Iterable[TraceStep]) -> tuple[str, ...]:
    """Every search string attempted, in order, retries included.

    A free function, not only a `Trace` property, because the nodes need
    this answer while the run is still in flight and the `Trace` is not
    built until the end. Two implementations of "which steps were
    searches" would be two things to keep in step; there is one."""
    return tuple(step.detail for step in steps if step.kind is StepKind.SEARCH)


def rewords_in(steps: Iterable[TraceStep]) -> int:
    """How many times the query was reworded (F-04).

    THE counter. The retry ceiling is enforced against this, the retry
    marker on the answer bubble shows this, and nothing anywhere
    increments an integer of its own."""
    return sum(1 for step in steps if step.kind is StepKind.REWORD)


@dataclass(frozen=True)
class Trace:
    """Everything F-10 needs about one answer: searches run, files
    consulted, retries used.

    Built once, in `agent.graph.ask`, from the steps the graph accumulated
    -- so no node can produce an answer that is missing its trace by
    forgetting to attach one."""

    trace_id: str
    steps: tuple[TraceStep, ...] = ()

    @property
    def searches(self) -> tuple[str, ...]:
        """Every search string attempted, in order, including the reworded
        retries. This is the openapi `Answer.searched` field and the list
        an honest refusal shows (F-05)."""
        return searches_in(self.steps)

    @property
    def files_consulted(self) -> tuple[str, ...]:
        """Distinct file names any step consulted, first-seen order.

        De-duplicated because a single search returning five chunks of one
        PDF consulted one file, not five, and F-10's promise is "the files
        consulted"."""
        seen: dict[str, None] = {}
        for step in self.steps:
            for name in step.files:
                seen.setdefault(name, None)
        return tuple(seen)

    @property
    def retries(self) -> int:
        """How many times the query was reworded (F-04).

        Derived, never stored. See the module docstring: this is the same
        number the retry ceiling is enforced against and the number UX
        spec section 8 renders on the answer bubble."""
        return rewords_in(self.steps)
