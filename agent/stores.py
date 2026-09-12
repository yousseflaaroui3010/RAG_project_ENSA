"""The agent's read side of the derived stores (ST-21).

One function, and it is the real implementation of the `fetch_parents`
port: architecture 5.2's box P, "fetch parent sections for context".

WHY THIS ONE PORT IS NOT DEFERRED like the other seven. The rest need a
model, so they belong to ST-22 to ST-25 and `agent/ports.py` refuses to
default them. This one is a store read against `parent_store`, which ST-16
already built and tested. Deferring it would have meant deferring the only
piece of box P that exists, and the graph would have gone on answering
from 500-character chunks while the docstrings claimed it read sections.

The module is a thin ADAPTER on purpose:
* it does not open, cache or hold anything -- `parent_store` owns the
  files, and this only names them;
* it turns ST-16's one-at-a-time API into the mapping the port promises;
* it is the only place that decides what a MISSING parent means.

That last decision, stated plainly: a parent the store cannot find is
LEFT OUT of the mapping, with a warning logged. It is not faked and it is
not fatal. `parent_store.get_parent`'s own error text says why it happens
-- "its chunk may have been indexed before the parent was written, or the
workspace may need a re-sync" -- so one absent section is a store that has
drifted from the index by one file, and refusing the whole answer over it
would be worse for the user than answering from the four sections that ARE
there. The graph records "loaded 4 of 5" in the trace, so the shortfall is
visible rather than silent.

A CORRUPT parent is the opposite case and is deliberately NOT caught: it
means a file that exists and does not say what it should, which is the
condition `parent_store` raises `CorruptParentError` for, and answering
around it would risk citing a section that is not the section it claims to
be.

An UNAVAILABLE parent (issue #50, fixed on the other side of this seam in
`parent_store.py`) is ALSO deliberately not caught here, and for a related
but distinct reason. `parent_store.get_parent` now retries an OS-level read
failure a few times before giving up, so by the time `ParentUnavailableError`
reaches this module the lock has already outlasted a genuine transient hold
(antivirus, OneDrive sync -- this repo lives under OneDrive). Treating it
like a missing parent and quietly omitting the section would let an answer
under-cite without saying why; letting it propagate means the question fails
loudly with a message that says "retry", which the S1 error panel already
renders with a Retry action -- no UI change needed for that to work. It used
to arrive here as `CorruptParentError`, which said "do not trust this file"
about a file whose content was never even read; it no longer does.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path

import parent_store

logger = logging.getLogger(__name__)


def parent_texts(
    workspace_id: str,
    parent_ids: Iterable[str],
    *,
    base_path: str | Path | None = None,
) -> dict[str, str]:
    """Full section text for each id that the store can produce.

    Keyed by parent id, so a caller can look up the section behind a hit
    without matching on text. Ids the store does not have are absent from
    the result; the caller is expected to notice the difference in length
    rather than be told twice.

    `base_path` exists for tests and mirrors `parent_store`'s own
    parameter; production passes nothing and the configured store path is
    used."""
    texts: dict[str, str] = {}
    for parent_id in dict.fromkeys(parent_ids):
        try:
            parent = parent_store.get_parent(
                workspace_id=workspace_id, parent_id=parent_id, base_path=base_path
            )
        except parent_store.ParentNotFoundError:
            logger.warning(
                "parent %s is missing from workspace %s; answering without that "
                "section. The workspace may need a re-sync.",
                parent_id,
                workspace_id,
            )
            continue
        if not parent.text or not parent.text.strip():
            # A SECTION THAT LOADS AS NOTHING IS NOT A SECTION THAT LOADED,
            # and treating it as one is worse than treating it as missing.
            # `parent_store` only checks the `text` field is PRESENT, so a
            # blank one arrives here as a successful read -- and every
            # count downstream then believes it: the trace says "loaded 5
            # of 5", `route_after_parents` sees a full mapping, the model
            # is handed a headed block with nothing under it, and the
            # document is printed as a source card. That is a citation to
            # text nothing read, which is the one thing F-03's source line
            # promises cannot happen.
            #
            # Omitting it instead puts the case back on the machinery that
            # already handles a section the store cannot produce: the
            # shortfall shows in the trace, the citation is dropped with
            # it, and zero readable sections still routes to the Sync
            # refusal.
            logger.warning(
                "parent %s in workspace %s loaded with no text; answering "
                "without that section. The workspace may need a re-sync.",
                parent_id,
                workspace_id,
            )
            continue
        texts[parent_id] = parent.text
    return texts
