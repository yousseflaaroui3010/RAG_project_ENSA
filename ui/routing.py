"""F-12: propose the most relevant workspace instead of guessing.

PRD acceptance criterion: "Given no workspace is selected, when the user
asks a clearly technical question, then the system proposes the workspace
it judges most relevant and asks for confirmation before answering." This
module is the "judges most relevant" half; `app.py::_start_routing` and
`ui/conversation.py` turn its answer into the confirmation shown on S1.

SCORING RULE, recorded in DECISIONS.md: each workspace's score is its own
BEST (top-1) hit's DENSE E5 cosine similarity -- `vector_store.
dense_top1_similarity` -- not the hybrid RRF-fused score chat retrieval
uses. That started as the plan (reuse `vector_store.search`'s existing
hybrid path) and was proven wrong by running it: with three workspaces of
distinct vocabulary and one question that shared real words with only one
of them, the RRF-fused score picked a workspace that shared NO words with
the question at all. The reason is structural -- RRF turns a rank
POSITION into a number, and every workspace here is searched in total
isolation, so its own best hit is trivially close to rank 0 within that
one workspace's own small candidate lists almost regardless of how
relevant it actually is. That rank position is not comparable across
independently-searched collections. Cosine similarity on the unit-length
E5 vector alone IS comparable across collections (ADR-05 normalises every
dense vector the same way), which is what makes it usable here. See
`vector_store.dense_top1_similarity` for the full account.

NO LLM CALL, ever, for this: the F-12 design is explicit that routing must
cost no more than a search already does. The question is embedded ONCE
(dense only -- sparse/BM25 is not part of this score, so it is never
computed here) and the same vector is reused for every workspace's lookup.

WORKSPACES NEVER SYNCED SCORE NOTHING. `vector_store.CollectionNotFoundError`
is not a zero score, it is "cannot be scored" -- a workspace with no
collection is excluded from the ranking exactly as it is absent from
retrieval within it (`agent/retrieval.py`'s own docstring), not treated as
measured-and-lowest. A synced workspace with an empty collection (nothing
indexed yet) is excluded the same way: `dense_top1_similarity` returns
None for it rather than a fabricated score.

NO MINIMUM-SCORE THRESHOLD (a deliberate omission, recorded in
DECISIONS.md). Cosine similarity IS a calibrated, bounded number, unlike
the RRF score this module used to compare -- so a threshold would be
meaningful here in a way it would not have been before. It is still left
out: this project has no real evaluation run against the real E5 model to
pick a cutoff from, and a hand-picked number with no tuning data behind it
is exactly the kind of guess rule 4 (never guess a schema, field or
parameter) is written against by analogy. "No workspace looks relevant" is
already expressible without one: a workspace scores nothing at all only
when it was never synced or its collection is empty, which is the "no
guess" case the PRD's confirmation step exists for. A future story with a
real golden set for routing is the right place to add one.

NOTHING FROM A PASSAGE LEAVES THIS MODULE. `RouteCandidate` carries a
workspace id, its name and a bare score -- never a `SearchHit`, a
`chunk_text` or a `section_label`. F-12 forbids the confirmation from
leaking content across workspaces, and this is the type that reaches the
template."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import embeddings
import vector_store
from ui.screen import WorkspaceOption


@dataclass(frozen=True)
class RouteCandidate:
    """One workspace that had a hit, ready to rank and to show.

    No passage text and no `SearchHit` -- see the module docstring."""

    workspace_id: str
    name: str
    score: float


def propose_workspace(
    client: Any, *, options: list[WorkspaceOption], question: str
) -> list[RouteCandidate]:
    """Score every workspace against ONE question, ranked best first.

    Embeds `question` once (dense only) and reuses that one vector for
    every workspace's lookup via `vector_store.dense_top1_similarity` --
    see the module docstring for why the score is dense-only cosine
    similarity rather than the hybrid search's own fused score.

    Returns an empty list when no workspace could be scored at all (never
    synced, or synced with nothing indexed yet): the caller shows the
    plain "pick a workspace" message rather than a guess, per the F-12
    card. May raise whatever `embeddings.embed_query` raises -- callers
    that must not load the embedding model at all (evidence-only mode)
    check that BEFORE calling this, the same way `app.py::Runtime.ports()`
    does for chat."""
    dense_query = embeddings.embed_query(question)

    scored: list[RouteCandidate] = []
    for option in options:
        try:
            score = vector_store.dense_top1_similarity(
                client, workspace_id=option.id, dense_query=dense_query
            )
        except vector_store.CollectionNotFoundError:
            continue
        if score is None:
            continue
        scored.append(RouteCandidate(workspace_id=option.id, name=option.name, score=score))

    scored.sort(key=lambda candidate: candidate.score, reverse=True)
    return scored
