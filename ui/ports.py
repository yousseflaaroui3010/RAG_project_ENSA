"""Composing the real agent for the running app (ADR-13).

ADR-13 has the UI calling `agent.graph.ask` IN-PROCESS: there is no HTTP
client here and no service boundary to cross. So "wiring the UI to the
agent" is exactly this file -- build the eight callables of `AgentPorts`
once for the process and hand them to every question.

THE FIVE REAL PORTS are ST-23's and ST-24's, built by their own factories:
`build_retrieve`, `build_grade`, `build_reword`, `parent_texts` and
`build_write_answer`. Nothing is reimplemented here.

THE THREE STUBS ARE WRITTEN OUT LOUD, and that is the rule agent/ports.py
exists to enforce: "a stub that answers plausibly is the most dangerous
object in a project like this one ... a caller who has not built the real
thing yet cannot get a running graph by accident -- only by writing the
fake out loud." `summarize` and `clarify` and `rewrite` belong to ST-25
and ST-22. Each one below says whose it is and what it costs today.

WHY THE QDRANT CLIENT IS PASSED IN rather than opened here: embedded
Qdrant is single-process by design (ADR-04) and `vector_store.open_store`
raises on a second client for the same path, with an error about a lock
folder that reads like stale state somebody should delete. One client is
opened in the app's lifespan and closed with it; this module never opens
one, so importing it costs nothing and a test can pass its own.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agent.answering import build_write_answer
from agent.chat import ChatModel, build_chat_model
from agent.grading import build_grade, build_reword
from agent.ports import AgentPorts
from agent.retrieval import build_retrieve
from agent.state import Turn
from agent.stores import parent_texts


def _no_summary(_history: tuple[Turn, ...]) -> str:
    """ST-25's `summarize`, stubbed.

    Returns the empty string, which agent/ports.py documents as the
    "no earlier turn to summarize" value, so no node has to branch on the
    shape of it.

    WHAT THIS COSTS TODAY, stated rather than left for someone to discover:
    F-07's in-session memory does not work. `Conversation` really does
    collect the completed turns and really does pass them to `ask`, so the
    history reaching this seam is genuine -- but this function throws it
    away, so a follow-up question like "and can it be renewed?" is searched
    with no idea what "it" was. ST-25 closes it; nothing here fakes it."""
    return ""


def _never_ambiguous(_question: str, _summary: str) -> str | None:
    """ST-22's `clarify`, stubbed.

    None is the "carry on" answer (agent/ports.py), so every question goes
    straight to search.

    WHAT THIS COSTS TODAY: the clarification message variant can never
    appear in the running app. The screen renders it correctly -- proven
    against the real graph in tests, with a clarify port that returns a
    question -- but until ST-22 fills this seam, nothing live will produce
    one. Deliberately NOT papered over with a keyword rule of this story's
    invention: F-06 is ST-22's to design, and a guess here would be a
    second, wrong implementation to delete later."""
    return None


def _question_as_query(question: str, _summary: str) -> Sequence[str]:
    """ST-22's `rewrite`, stubbed: search for exactly what was asked.

    A one-element sequence, which agent/ports.py calls "the ordinary
    case". WHAT THIS COSTS TODAY: no rewriting and no splitting, so
    "How long is a trial period and can it be renewed?" is one search
    instead of two."""
    return (question,)


def build_ports(client: Any, model: ChatModel, *, parents_path: Any = None) -> AgentPorts:
    """Every seam the graph needs, for one process.

    `parents_path` mirrors `agent.stores.parent_texts`'s own `base_path`
    and exists for tests; the app passes nothing and the configured store
    path is used."""
    return AgentPorts(
        summarize=_no_summary,
        clarify=_never_ambiguous,
        rewrite=_question_as_query,
        retrieve=build_retrieve(client),
        grade=build_grade(model),
        reword=build_reword(model),
        fetch_parents=lambda workspace_id, parent_ids: parent_texts(
            workspace_id, parent_ids, base_path=parents_path
        ),
        write_answer=build_write_answer(model),
    )


def build_default_ports(client: Any) -> AgentPorts:
    """The ports the running server uses.

    `build_chat_model` reads the provider settings and raises
    `ChatUnavailableError` when cloud mode has no key or the mode is not
    one of the two names. That exception is allowed OUT of here on
    purpose, rather than being swallowed into a null model: UX spec 11
    routes "answering service unreachable" to an `ErrorPanel` on S1 with a
    retry and "no fabricated fallback", and `app.py` catches it there.

    Not caught at startup either, which would be the other tempting move.
    A server that refuses to boot without an API key means an operator
    cannot open the screen, read the empty state, or see WHICH setting is
    missing -- and the sentence naming it is already written inside that
    exception."""
    return build_ports(client, build_chat_model())
