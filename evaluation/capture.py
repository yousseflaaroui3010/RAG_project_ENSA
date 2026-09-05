"""Captures the sections the writer actually read, per question (ST-32).

RAGAS scores an answer against the passages it was GIVEN. Neither
`agent.state.Answer` nor its `Trace` carries passage text --
`Answer.sources` is `(file_name, section_label)` only -- so the runner has
to capture the text while the graph runs. That is the same problem
`ui/runs.py` solved for the trace panel, at the same seam:
`write_answer` is called with exactly the passages the answer was written
from (`agent/nodes.py::make_answer`'s one `cited` tuple, reused for both
the writer's input and the source list).

REUSES `ui.runs.Run.observed`, deliberately not a second copy of it.
`Run` is built for the interactive chat screen -- stage hints, cancel, a
worker thread -- and this module ignores all three; the one part it needs
is `observed()`'s `dataclasses.replace` over the frozen `AgentPorts`, and
the `reading` it records. The DECISIONS row for this story (2026-09-03)
already rejected a second, separately-wired copy of `AgentPorts` itself
because the evaluation must measure the product it decorates, not a
lookalike; the same argument applies one level down, to the one function
that already answers "which passages was this written from" correctly.
"""

from __future__ import annotations

from dataclasses import dataclass

from agent.graph import ask
from agent.ports import AgentPorts
from agent.state import Answer
from ui.runs import Run


@dataclass(frozen=True)
class Captured:
    """One golden question's outcome, with what the writer actually read.

    `contexts` is the deduplicated parent-section TEXT behind
    `Run.reading.cited`, in first-seen order -- what RAGAS calls
    "retrieved contexts". Empty on a refusal or a clarification: neither
    reaches `write_answer`, so `Run.reading` stays at its default (see
    `ui/runs.py::Reading`)."""

    answer: Answer | None
    error: BaseException | None
    contexts: tuple[str, ...]


def ask_and_capture(
    ports: AgentPorts, *, workspace_id: str, question: str
) -> Captured:
    """Run one question through the real graph and capture what the
    writer was shown.

    A `Run` is constructed only to reuse `observed()`; nothing here calls
    `.start()` or `.cancel()`, so its thread and stage/cancel machinery
    never engage. Every exception `ask` can raise is caught here, the same
    way `Run._work` catches it for the live app (PRD section 11: a hung or
    crashed question must not take the rest of the batch down with it) --
    one bad question becomes one failed row, not an aborted 60-question
    run."""
    run = Run(question=question, workspace_id=workspace_id, session_id=None)
    observed_ports = run.observed(ports)
    try:
        answer = ask(
            workspace_id=workspace_id, question=question, ports=observed_ports
        )
    except BaseException as exc:  # noqa: BLE001 -- see ui/runs.py::Run._work
        return Captured(answer=None, error=exc, contexts=())

    parents = run.reading.parents
    seen: dict[str, None] = {}
    for hit in run.reading.cited:
        if hit.parent_id in parents:
            seen.setdefault(hit.parent_id, None)
    contexts = tuple(parents[parent_id] for parent_id in seen)
    return Captured(answer=answer, error=None, contexts=contexts)
