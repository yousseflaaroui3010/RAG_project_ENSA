"""Composing the real agent for the running app (ADR-13).

ADR-13 has the UI calling `agent.graph.ask` IN-PROCESS: there is no HTTP
client here and no service boundary to cross. So "wiring the UI to the
agent" is exactly this file -- build the eight callables of `AgentPorts`
once for the process and hand them to every question.

THE EIGHT REAL PORTS are built by their story-owned factories. ST-25's
`build_summarize` supplies in-session memory; ST-22's `build_query_planning`
supplies `clarify` and `rewrite`; ST-23 and ST-24 supply `build_retrieve`,
`build_grade`, `build_reword`, `parent_texts` and `build_write_answer`.
Nothing is reimplemented here.

WHY THE QDRANT CLIENT IS PASSED IN rather than opened here: embedded
Qdrant is single-process by design (ADR-04) and `vector_store.open_store`
raises on a second client for the same path, with an error about a lock
folder that reads like stale state somebody should delete. One client is
opened in the app's lifespan and closed with it; this module never opens
one, so importing it costs nothing and a test can pass its own.
"""

from __future__ import annotations

from typing import Any

from agent.answering import build_write_answer
from agent.chat import ChatModel, build_chat_model
from agent.grading import build_grade, build_reword
from agent.ports import AgentPorts
from agent.querying import build_query_planning
from agent.retrieval import build_retrieve
from agent.stores import parent_texts
from agent.summarizing import build_summarize


def build_ports(client: Any, model: ChatModel, *, parents_path: Any = None) -> AgentPorts:
    """Every seam the graph needs, for one process.

    `parents_path` mirrors `agent.stores.parent_texts`'s own `base_path`
    and exists for tests; the app passes nothing and the configured store
    path is used."""
    clarify, rewrite = build_query_planning(model)
    return AgentPorts(
        summarize=build_summarize(model),
        clarify=clarify,
        rewrite=rewrite,
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
