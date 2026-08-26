"""The `retrieve` port (ST-23): hybrid search, wired to the real store.

Architecture 5.2 box S, ADR-05's hybrid dense-plus-sparse retrieval. This
is a wiring file: `vector_store.search` already does the work, including
its own encoding, so there is nothing here to get subtly wrong except the
two things below -- and both are about what this file does NOT do.

IT DOES NOT OPEN A CLIENT. `build_retrieve` takes one and closes over it.
ADR-04 makes Qdrant embedded and single-process, and
`vector_store.open_store` raises on a second client for the same storage
path -- with a message about a lock folder that reads exactly like stale
state somebody should delete, which is how that mistake usually ends. So
the client's lifetime belongs to whoever composes the application (ST-51),
one per process, and the agent is handed one. `agent/ports.py` says the
same thing at the seam, for the same reason.

IT DOES NOT PASS A SEARCH DEPTH, and that is deliberate rather than an
omission. `vector_store.search` resolves `limit=None` to
`config.retrieval_depth_k` itself, and its docstring says why: "F-04
makes the depth operator-tunable; never hardcode it at a call site."
Passing the setting from here would be a SECOND place reading it, which
is the shape that drifts -- one caller updated, another not, and two
searches in the same product using different depths. The test asserts the
port passes no limit, and the integration test proves the operator's
setting is what actually governs the number of hits.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import vector_store
from vector_store import SearchHit


def build_retrieve(client: Any) -> Callable[[str, str], Sequence[SearchHit]]:
    """The `retrieve` port, bound to one Qdrant client.

    The returned function is what `AgentPorts.retrieve` expects:
    (workspace_id, query) -> hits. It takes the RAW query string, never a
    vector, because `vector_store.search` owns the encoding and ADR-05's
    `passage:`/`query:` asymmetry lives behind that seam. A caller that
    cannot hand over a vector cannot hand over one encoded the wrong way.

    `CollectionNotFoundError` is deliberately NOT caught. A workspace that
    has never been synced is not a workspace whose documents fail to cover
    the question, and turning it into "not covered here" would tell a user
    to rephrase when the real answer is "press Sync". The error already
    carries that sentence; it belongs to the caller."""

    def retrieve(workspace_id: str, query: str) -> Sequence[SearchHit]:
        return vector_store.search(
            client, workspace_id=workspace_id, query_text=query
        )

    return retrieve
