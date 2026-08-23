"""Sanad vector store (ST-16, second half).

Implements the Qdrant side of architecture section 7.5: Qdrant in embedded
mode at `qdrant_storage_path`, ONE COLLECTION PER WORKSPACE named
`ws_<workspace_id>_children`, points carrying a 768-dim dense E5 vector and
a sparse BM25 vector, with `parent_id`, `source_file`, `section_label` and
`chunk_text` in the payload.

Isolation (PRD F-01) is structural here, exactly as it is in
`parent_store.py`: an HR question searches the HR collection, and the
manuals chunks are not in it. It is not a filter somebody has to remember
to add to a query -- a forgotten filter leaks, a collection that does not
contain a point cannot return it. The two derived stores therefore isolate
the same way for the same reason, which is what makes them safe to delete
together.

Only CHILDREN are stored here. Parents are on disk in `parent_store.py`,
and a search hit is traded for its full section by `parent_id`. Search the
small thing, read the big thing.

Three things about the libraries that no type signature and no passing test
will tell you, all found by running them against qdrant-client 1.18.0 /
fastembed 0.8.0 rather than by reading a doc page:

1. Qdrant REJECTS a non-UUID point id outright: `ValueError: Point id X is
   not a valid UUID`. Children have no id of their own, so this module
   derives one -- see `_child_point_id`.
2. FastEmbed's BM25 is asymmetric and silent about it. That trap is
   contained in `embeddings.py`, which is why nothing here loads an
   encoder; this module never sees a string it has to decide how to encode.
3. A second `QdrantClient` on the same storage path raises RuntimeError.
   ADR-04 already says single-process, and `open_store` is what turns that
   from a convention into an error with a reason attached.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import embeddings
import parent_store
from config import get_settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from chunking import Child

# Collection naming, from section 7.5 verbatim. Split into a prefix and a
# suffix rather than written as one f-string in three places so that the
# spec's shape lives in exactly one spot.
_COLLECTION_PREFIX = "ws_"
_COLLECTION_SUFFIX = "_children"

# Qdrant names each vector when a point carries more than one. These are
# internal to the collection and never leave this module.
_DENSE_VECTOR = "dense"
_SPARSE_VECTOR = "sparse"

# Payload keys, section 7.5. `chunk_text` is stored even though the parent
# holds the same text: the retrieval grader (F-05) scores the passage that
# actually matched, and re-deriving which window of a 4,000-character parent
# produced a hit is not something a search result should have to do.
_PAYLOAD_PARENT_ID = "parent_id"
_PAYLOAD_SOURCE_FILE = "source_file"
_PAYLOAD_SECTION_LABEL = "section_label"
_PAYLOAD_CHUNK_TEXT = "chunk_text"

# Namespace for deriving child point ids, built the same way
# `chunking._PARENT_ID_NAMESPACE` is, so the value is reproducible from
# something a reader can check rather than pasted in as a magic UUID.
_CHILD_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "children.sanad.local")

# NUL, for the same reason chunking uses it: it cannot appear in a parent id
# or an index, so no pair of inputs can be spelled two ways.
_CHILD_ID_SEPARATOR = "\x00"

# Paths currently held open by `open_store`, so a second one gets a Sanad
# error naming ADR-04 instead of a Qdrant RuntimeError about a lock file.
_open_paths: set[str] = set()


class VectorStoreError(Exception):
    """Base for every vector-store failure, so callers catch this rather
    than whatever qdrant-client happens to raise this release."""


class StoreAlreadyOpenError(VectorStoreError):
    """Raised when a second client is opened on a storage path this process
    already holds.

    Qdrant's embedded mode allows exactly one client per path and raises a
    RuntimeError about a lock folder, which reads like a stale-lock problem
    and invites deleting the lock. It is not: ADR-04 chose embedded mode
    knowing it is single-process, and the fix is always to pass the open
    client down, never to open a second one."""


class CollectionNotFoundError(VectorStoreError):
    """Raised when a workspace has no collection yet.

    Distinct from "the collection is there and empty", which is what a
    workspace whose folder is empty looks like. One means "call
    `ensure_collection`, this workspace has never synced"; the other means
    "the sync ran and found nothing". Collapsing them sends the user to
    fix the wrong thing."""


class VectorCountError(VectorStoreError):
    """Raised when the children and their vectors do not line up.

    `upsert_children` zips three lists together. A silent length mismatch
    would attach every vector to the wrong chunk from the mismatch onward,
    so a search would return confidently wrong citations while everything
    still looked healthy. `embeddings.EmbeddingCountError` guards the same
    seam from the other side; this is the one that catches a caller who
    built the two lists separately."""

    def __init__(self, children: int, vectors: int, kind: str):
        super().__init__(
            f"got {vectors} {kind} vectors for {children} children; they must "
            f"align by index"
        )


@dataclass(frozen=True)
class SearchHit:
    """One retrieved child chunk, with everything needed to cite it.

    Mirrors the section 7.5 payload plus the fusion score. `parent_id` is
    the point of the whole design: the answering model reads
    `parent_store.get_parent(...)`, not this text."""

    parent_id: str
    source_file: str
    section_label: str | None
    chunk_text: str
    score: float


@dataclass(frozen=True)
class StoreDeletion:
    """What a delete actually removed from both derived stores.

    Both counts are returned rather than a bare success because they are
    how a caller notices the two stores drifting apart: a document whose
    vectors went but whose parents did not is the exact failure these
    functions exist to prevent.

    `points_deleted` is None, not 0, when the number is genuinely unknown
    -- dropping a whole collection does not report how many points it
    held. A 0 there would be a number a caller could compare against and
    act on, and it would be wrong."""

    points_deleted: int | None
    parents_deleted: int
    unreadable_parent_files: list[str]


def collection_name(workspace_id: str) -> str:
    """The section 7.5 collection name for a workspace.

    Public because ST-17 and any operator poking at `data/qdrant/` need to
    map a workspace to its collection without re-deriving the convention."""
    return f"{_COLLECTION_PREFIX}{workspace_id}{_COLLECTION_SUFFIX}"


def _child_point_id(parent_id: str, index_in_parent: int) -> str:
    """A child's point id, derived rather than random.

    Qdrant refuses anything that is not a UUID or an unsigned integer, and
    children arrive from `chunking.py` with no id at all, so one has to be
    made. Making it DERIVED rather than random is the same decision ST-14
    made for parents, for the same reason: re-syncing a changed document
    must overwrite its points in place. With random ids, every re-sync
    would insert a second copy of every unchanged chunk, and the collection
    would grow without bound while retrieval returned the same passage
    twice.

    Derived from the parent and the child's position WITHIN that parent,
    not its position in the document. That makes the id independent of how
    the caller batches: upserting one parent's children alone yields the
    same ids as upserting the whole document, so a resumed or partial sync
    lands on the same points instead of duplicating them."""
    name = f"{parent_id}{_CHILD_ID_SEPARATOR}{index_in_parent}"
    return str(uuid.uuid5(_CHILD_ID_NAMESPACE, name))


def _positions_within_parents(children: Sequence[Child]) -> list[int]:
    """Each child's index among the children of ITS parent.

    A running count keyed on `parent_id` rather than `enumerate`, which is
    what makes `_child_point_id` batch-independent. Deliberately does not
    require the children to be grouped or sorted: it counts occurrences, so
    an interleaved list still numbers each parent's children 0, 1, 2..."""
    seen: dict[str, int] = {}
    positions: list[int] = []
    for child in children:
        position = seen.get(child.parent_id, 0)
        positions.append(position)
        seen[child.parent_id] = position + 1
    return positions


@contextmanager
def open_store(storage_path: str | Path | None = None) -> Iterator[Any]:
    """Open the one Qdrant client this process is allowed (ADR-04).

    A context manager rather than a module-level singleton so the client is
    always closed, and so tests can run against a `tmp_path` without a
    global to reset between them. The client is passed explicitly into
    every other function here for the same reason: a module that reaches
    for an ambient client is a module that opens a second one the first
    time two code paths run at once."""
    from qdrant_client import QdrantClient

    configured = get_settings().qdrant_storage_path
    path = str(storage_path if storage_path is not None else configured)
    resolved = str(Path(path).resolve())
    if resolved in _open_paths:
        raise StoreAlreadyOpenError(
            f"a Qdrant client is already open on {resolved}. Embedded Qdrant "
            f"is single-process by design (ADR-04): pass the open client down "
            f"instead of opening a second one."
        )
    # The path is claimed BEFORE the directory and the client are made, and
    # released again if either fails. Claiming it after would let two racing
    # opens both get past the check; releasing only in the `finally` below
    # would strand the claim forever when the client cannot be constructed
    # at all -- and a lock that is never released turns one bad path into a
    # process that can never open the store again, which is worse than the
    # RuntimeError it replaced.
    _open_paths.add(resolved)
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        client = QdrantClient(path=path)
    except BaseException:
        _open_paths.discard(resolved)
        raise
    try:
        yield client
    finally:
        _open_paths.discard(resolved)
        client.close()


def ensure_collection(client: Any, *, workspace_id: str) -> str:
    """Create this workspace's collection if it is not there, and return
    its name.

    Idempotent because Sync calls it on every run, and a second call must
    not wipe an indexed workspace. Checked with `collection_exists` rather
    than by catching the create error: "already exists" and "the storage is
    broken" both raise, and only one of them is fine.

    Dimensions and distance come from config, not from literals: a
    collection is created ONCE and then holds its width forever, so a
    mismatch between `embedding_dense_dim` and what is on disk is a
    re-index, not a restart."""
    from qdrant_client import models

    name = collection_name(workspace_id)
    if client.collection_exists(name):
        return name
    settings = get_settings()
    client.create_collection(
        name,
        vectors_config={
            _DENSE_VECTOR: models.VectorParams(
                size=settings.embedding_dense_dim,
                # Cosine because `embeddings._encode` normalises to unit
                # length, which is what E5 expects (ADR-05).
                distance=models.Distance.COSINE,
            )
        },
        sparse_vectors_config={_SPARSE_VECTOR: models.SparseVectorParams()},
    )
    return name


def upsert_children(
    client: Any,
    *,
    workspace_id: str,
    children: Sequence[Child],
    dense_vectors: Sequence[Sequence[float]],
) -> int:
    """Write children into the workspace's collection; return how many.

    Takes the DENSE vectors from the caller because embedding is the slow,
    model-bound step that ST-17 will want to batch and report progress on.
    It does NOT take the sparse vectors: those are computed here, through
    `embeddings.embed_sparse_passages`, so there is exactly one route by
    which document-side sparse vectors can enter the store. A caller
    holding a sparse vector could pass a query-side one by mistake, and
    nothing would ever raise -- see the asymmetry note in `embeddings.py`.

    An empty list is a no-op rather than an error: a document whose only
    section was blank produces no children, and that is a normal outcome of
    a normal sync, not a fault."""
    from qdrant_client import models

    if len(dense_vectors) != len(children):
        raise VectorCountError(len(children), len(dense_vectors), "dense")
    if not children:
        return 0

    # Encoded BEFORE the collection is created, not after. A batch with a
    # whitespace-only window in it raises here, and doing that first means a
    # failed sync leaves NO collection behind. An empty collection is not
    # harmless: `search` uses "the collection exists" to tell "this
    # workspace has never synced" from "the sync ran and found nothing",
    # and a half-failed sync would answer that question wrongly forever.
    sparse_vectors = embeddings.embed_sparse_passages([c.text for c in children])
    if len(sparse_vectors) != len(children):
        raise VectorCountError(len(children), len(sparse_vectors), "sparse")

    name = ensure_collection(client, workspace_id=workspace_id)

    positions = _positions_within_parents(children)
    points = [
        models.PointStruct(
            id=_child_point_id(child.parent_id, position),
            vector={
                _DENSE_VECTOR: list(dense),
                _SPARSE_VECTOR: models.SparseVector(
                    indices=sparse.indices, values=sparse.values
                ),
            },
            payload={
                _PAYLOAD_PARENT_ID: child.parent_id,
                _PAYLOAD_SOURCE_FILE: child.source_file,
                _PAYLOAD_SECTION_LABEL: child.section_label,
                _PAYLOAD_CHUNK_TEXT: child.text,
            },
        )
        for child, position, dense, sparse in zip(
            children, positions, dense_vectors, sparse_vectors, strict=True
        )
    ]
    client.upsert(name, points=points)
    return len(points)


def search(
    client: Any,
    *,
    workspace_id: str,
    query_text: str,
    limit: int | None = None,
) -> list[SearchHit]:
    """Hybrid search within ONE workspace.

    Takes the raw question, not vectors. That is deliberate and it is the
    isolation-and-asymmetry guarantee in one line: a caller cannot hand
    this function a query encoded the wrong way, because a caller never
    encodes anything. Dense and sparse are prefetched separately and fused
    with Reciprocal Rank Fusion, which combines two rankings without
    needing their scores to be on the same scale -- a cosine similarity and
    a BM25 score are not comparable numbers.

    `limit` defaults to `config.retrieval_depth_k` (F-04 makes the depth
    operator-tunable; never hardcode it at a call site)."""
    from qdrant_client import models

    name = collection_name(workspace_id)
    if not client.collection_exists(name):
        raise CollectionNotFoundError(
            f"workspace {workspace_id!r} has no collection {name!r}. It has "
            f"never been synced; run a Sync before searching it."
        )

    depth = get_settings().retrieval_depth_k if limit is None else limit
    dense_query = embeddings.embed_query(query_text)
    sparse_query = embeddings.embed_sparse_query(query_text)

    response = client.query_points(
        name,
        prefetch=[
            models.Prefetch(query=dense_query, using=_DENSE_VECTOR, limit=depth),
            models.Prefetch(
                query=models.SparseVector(
                    indices=sparse_query.indices, values=sparse_query.values
                ),
                using=_SPARSE_VECTOR,
                limit=depth,
            ),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=depth,
        with_payload=True,
    )
    return [
        SearchHit(
            parent_id=point.payload[_PAYLOAD_PARENT_ID],
            source_file=point.payload[_PAYLOAD_SOURCE_FILE],
            section_label=point.payload.get(_PAYLOAD_SECTION_LABEL),
            chunk_text=point.payload[_PAYLOAD_CHUNK_TEXT],
            score=point.score,
        )
        for point in response.points
    ]


def delete_document(
    client: Any,
    *,
    workspace_id: str,
    source_file: str,
    parent_base_path: str | Path | None = None,
) -> StoreDeletion:
    """Remove one document's vectors AND its parent files, as one unit.

    This function exists because the alternative is the defect ST-14
    predicted and wrote down: a document that shrinks from ten parents to
    six leaves parents 6..9 on disk, and if the two stores are cleaned up
    in two separate places, one of them eventually is not. A vector whose
    parent file is gone resolves a search hit to nothing, which is the one
    failure a sourced-answer product cannot absorb.

    The ORDER is the safety property, not an implementation detail. The
    parent ids are read first, from the parent store, because it is the
    authority on what is on disk and stays readable even if the collection
    is damaged. Then the VECTORS go, then the parents. A crash between
    those two leaves parent files with nothing pointing at them: wasted
    disk, invisible to search, and cleaned up by simply running this again.
    The other order leaves live vectors pointing at deleted files, which is
    a broken citation served to a user. Both orders can fail; only one of
    them fails safely.

    Deleting a document that was never indexed is not an error, for the
    reason `parent_store.delete_parents` gives: this is what you run to
    reach a known end state, and it gets re-run after partial failures."""
    from qdrant_client import models

    listing = parent_store.list_parent_ids(
        workspace_id=workspace_id, source_file=source_file, base_path=parent_base_path
    )

    points_deleted = 0
    name = collection_name(workspace_id)
    if client.collection_exists(name):
        selector = models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key=_PAYLOAD_SOURCE_FILE,
                        match=models.MatchValue(value=source_file),
                    )
                ]
            )
        )
        # Counted before the delete because Qdrant's delete reports an
        # operation status, not a row count, and a caller comparing
        # vectors-removed against parents-removed is exactly how the two
        # stores drifting apart becomes visible.
        points_deleted = client.count(name, count_filter=selector.filter).count
        client.delete(name, points_selector=selector)

    parents_deleted = parent_store.delete_parents(
        workspace_id=workspace_id, parent_ids=listing.ids, base_path=parent_base_path
    )
    return StoreDeletion(
        points_deleted=points_deleted,
        parents_deleted=parents_deleted,
        unreadable_parent_files=listing.unreadable,
    )


def delete_workspace(
    client: Any,
    *,
    workspace_id: str,
    parent_base_path: str | Path | None = None,
) -> StoreDeletion:
    """Drop a workspace's whole collection and all of its parent files.

    PRD F-01: deleting a workspace removes its derived data and leaves the
    user's source folder untouched -- nothing here goes near the workspace
    folder, only `data/`.

    Same one-unit rule and same safe ordering as `delete_document`:
    vectors first, parents second, so a crash between them leaves orphan
    files rather than live vectors citing files that are gone. Nothing has
    to be read first here, because dropping the collection takes every
    point in it and clearing the directory takes every parent in it.

    `points_deleted` comes back as None when a collection was dropped;
    see `StoreDeletion`."""
    name = collection_name(workspace_id)
    dropped = False
    if client.collection_exists(name):
        client.delete_collection(name)
        dropped = True
    parents_deleted = parent_store.delete_workspace_parents(
        workspace_id=workspace_id, base_path=parent_base_path
    )
    return StoreDeletion(
        points_deleted=None if dropped else 0,
        parents_deleted=parents_deleted,
        unreadable_parent_files=[],
    )
