"""ST-16 exit gate: an HR query never returns manuals chunks, and every
search hit resolves to its parent by id.

Reference: docs/phase2/Sanad_Architecture_v1.0.md section 7.5 (one Qdrant
collection per workspace, `ws_<workspace_id>_children`, points carrying a
dense and a sparse vector plus `parent_id` / `source_file` /
`section_label` / `chunk_text`), ADR-04 (embedded Qdrant, single process),
PRD F-01 (workspace isolation is absolute) and F-03 (every answer names its
source).

Every test runs against a REAL embedded Qdrant under `tmp_path`. A mocked
client would test the mock, and the three things that actually bite in this
module -- a rejected point id, a lock on the storage path, and how a filter
behaves on delete -- are all behaviours of the real library that no fake
would reproduce. The two ENCODERS are faked, because they download
hundreds of megabytes and neither of them is what this file is about; the
fakes are deterministic and text-dependent, so ranking still means
something.
"""

from __future__ import annotations

import hashlib
import json
import uuid

import pytest

import chunking
import embeddings
import parent_store
import vector_store
from chunking import Child
from config import get_settings

WS_HR = "11111111-1111-1111-1111-111111111111"
WS_MANUALS = "22222222-2222-2222-2222-222222222222"

# From architecture section 7.5, written out rather than built from the
# module's own constants. Assembling the expected name from
# `vector_store._COLLECTION_PREFIX` would make this agree with the code by
# construction and pass even if the convention drifted from the spec.
HR_COLLECTION = f"ws_{WS_HR}_children"

SPARSE_VOCABULARY = 10_000


def _words(text: str) -> list[str]:
    """Lower-cased word bag, with the E5 instruction prefixes removed.

    The prefixes are stripped for the same reason the real model does not
    treat them as content: they say how to read the text, they are not part
    of it. Leaving them in would put a token in every passage that no query
    can ever match, which is noise in a fixture, not realism."""
    for prefix in (
        get_settings().embedding_passage_prefix,
        get_settings().embedding_query_prefix,
    ):
        if text.startswith(prefix):
            text = text[len(prefix) :]
    return [w for w in text.lower().replace("'", " ").split() if w]


def _slot(word: str, modulo: int) -> int:
    return int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16) % modulo


def _fake_dense(prefixed_texts):
    """A deterministic bag-of-words embedding of the configured width.

    Not a random vector: two texts sharing words come back close together,
    so a search over this returns the passage a reader would expect, and a
    test asserting on WHICH chunk came first is asserting on something
    real. Unit length, because `vector_store` creates its collection with
    cosine distance."""
    dim = get_settings().embedding_dense_dim
    vectors = []
    for text in prefixed_texts:
        vector = [0.0] * dim
        for word in _words(text):
            vector[_slot(word, dim)] += 1.0
        length = sum(x * x for x in vector) ** 0.5 or 1.0
        vectors.append([x / length for x in vector])
    return vectors


class _FakeSparseModel:
    """BM25-shaped, and asymmetric in the same direction as the real one.

    The document side weights terms, the query side does not. Keeping the
    asymmetry in the fake matters: a symmetric fake would let this whole
    file pass while `vector_store` fed query vectors into the index."""

    def embed(self, documents, **_kwargs):
        return [_RawSparse(*self._terms(text, weight=1.75)) for text in documents]

    def query_embed(self, query, **_kwargs):
        return iter([_RawSparse(*self._terms(query, weight=1.0))])

    @staticmethod
    def _terms(text, weight):
        slots = sorted({_slot(word, SPARSE_VOCABULARY) for word in _words(text)})
        return slots, [weight] * len(slots)


class _RawSparse:
    def __init__(self, indices, values):
        self.indices = indices
        self.values = values


@pytest.fixture
def encoders(monkeypatch):
    """Both encoder seams replaced at once.

    Patched at `embeddings._encode` and `embeddings._load_sparse_model`,
    which are the same seams ST-15's own tests use. Nothing in
    `vector_store` is patched, so every line of it under test is the real
    one."""
    monkeypatch.setattr(embeddings, "_encode", _fake_dense)
    monkeypatch.setattr(embeddings, "_load_sparse_model", lambda _n: _FakeSparseModel())


@pytest.fixture
def store(tmp_path, encoders):
    """A real embedded Qdrant plus a real parent store, both under tmp_path.

    Yields a small helper rather than a bare client because every call in
    this module takes the same two path arguments, and a fixture that hands
    back a tuple leads to tests that are mostly plumbing."""
    parents_path = tmp_path / "parents"
    with vector_store.open_store(tmp_path / "qdrant") as client:
        yield _Store(client, parents_path)


class _Store:
    """Test-side convenience: binds the client and the parent path."""

    def __init__(self, client, parents_path):
        self.client = client
        self.parents = parents_path

    def index(self, workspace_id, markdown, source_file):
        """Do what ST-17 will do: chunk, embed, write both stores."""
        result = chunking.chunk_document(markdown, source_file=source_file)
        parent_store.save_parents(
            workspace_id=workspace_id, parents=result.parents, base_path=self.parents
        )
        vector_store.upsert_children(
            self.client,
            workspace_id=workspace_id,
            children=result.children,
            dense_vectors=embeddings.embed_children(result.children),
        )
        return result

    def search(self, workspace_id, query, limit=None):
        return vector_store.search(
            self.client, workspace_id=workspace_id, query_text=query, limit=limit
        )

    def count(self, workspace_id):
        return self.client.count(vector_store.collection_name(workspace_id)).count


HR_DOCUMENT = """# Article 12 - Conges payes

Le salarie a droit a dix-huit jours ouvrables de conges payes par an.

# Article 13 - Periode d'essai

La periode d'essai des cadres dure trois mois, renouvelable une fois.
"""

# Sized on purpose, not padded for length: long enough that
# `parent_split_above_chars` (4,000) cuts it into several parents and
# `chunk_child_size_chars` (500) gives each of those several children. A
# smaller fixture cannot tell a per-parent numbering apart from a
# document-wide one, which is how a vacuous test got past the first
# mutation round.
MULTI_PARENT_DOCUMENT = "".join(
    f"# Article {n} - Disposition\n\n{'Le contenu de cet article. ' * 120}\n\n"
    for n in range(6)
)

MANUALS_DOCUMENT = """# Chapitre 4 - Entretien de la presse hydraulique

Purger le circuit hydraulique tous les dix-huit cycles de production.

# Chapitre 5 - Remplacement des courroies

La courroie principale se remplace apres trois mois d'utilisation continue.
"""


# --- the exit gate ----------------------------------------------------


def test_an_hr_query_never_returns_a_manuals_chunk(store):
    """ST-16's exit gate, and PRD F-01 in one assertion.

    The two fixture documents SHARE vocabulary on purpose ("dix-huit",
    "trois mois"), so a query that leaked across workspaces would score a
    manuals chunk highly rather than merely returning it last. A pair of
    unrelated documents would let a broken filter pass by luck.

    Asserted in both directions, because a store that hid one workspace
    from the other by accident of insertion order would satisfy only one."""
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")
    store.index(WS_MANUALS, MANUALS_DOCUMENT, "manuel-atelier.pdf")

    hr_hits = store.search(WS_HR, "combien de jours de conges apres trois mois ?")
    manuals_hits = store.search(WS_MANUALS, "quand purger le circuit hydraulique ?")

    assert hr_hits, "the HR workspace returned nothing at all"
    assert manuals_hits, "the manuals workspace returned nothing at all"
    assert {hit.source_file for hit in hr_hits} == {"code-du-travail.pdf"}
    assert {hit.source_file for hit in manuals_hits} == {"manuel-atelier.pdf"}


def test_isolation_holds_when_both_workspaces_hold_the_same_file_name(store):
    """The case a per-workspace collection makes safe and a shared one does
    not. Chunking derives parent ids from the file NAME and position, so
    two workspaces holding `policy.md` derive identical parent ids and
    identical child point ids. In one shared collection the second sync
    would overwrite the first workspace's chunks; in two collections they
    never meet."""
    store.index(WS_HR, "# Politique\n\nLes conges sont de dix-huit jours.", "policy.md")
    store.index(WS_MANUALS, "# Politique\n\nLa presse exige un graissage.", "policy.md")

    hr_hits = store.search(WS_HR, "conges")
    manuals_hits = store.search(WS_MANUALS, "graissage")

    assert "dix-huit" in hr_hits[0].chunk_text
    assert "graissage" in manuals_hits[0].chunk_text
    assert store.count(WS_HR) == 1
    assert store.count(WS_MANUALS) == 1


def test_every_search_hit_resolves_to_its_full_parent(store):
    """The other half of the exit gate: "parents resolve by id".

    This is the whole point of the parent/child design -- search the small
    thing, read the big thing -- so it is asserted as a real round trip
    through both stores, not as "the payload has a parent_id key". The
    parent's text must CONTAIN the chunk that matched: a parent that
    resolves but does not hold the retrieved passage is a citation pointing
    at the wrong place."""
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")

    hits = store.search(WS_HR, "duree de la periode d'essai des cadres")

    assert hits
    for hit in hits:
        parent = parent_store.get_parent(
            workspace_id=WS_HR, parent_id=hit.parent_id, base_path=store.parents
        )
        assert hit.chunk_text in parent.text
        assert parent.source_file == hit.source_file


# --- section 7.5, held to the letter ----------------------------------


def test_the_collection_is_named_the_way_section_7_5_says(store):
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")

    assert vector_store.collection_name(WS_HR) == HR_COLLECTION
    assert store.client.collection_exists(HR_COLLECTION)


def test_the_payload_carries_exactly_the_four_named_fields(store):
    """Exact set equality, not a subset check. The payload is a signed
    contract that ST-21's agent reads; a field quietly added here is a
    field nothing downstream knows to expect, and a missing one is a
    citation that cannot be rendered."""
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")

    points, _ = store.client.scroll(HR_COLLECTION, limit=1, with_payload=True)

    assert set(points[0].payload) == {
        "parent_id",
        "source_file",
        "section_label",
        "chunk_text",
    }


def test_a_section_with_no_heading_stores_a_null_label_not_the_string_none(store):
    """`section_label=None` is legal (a preamble, or a TXT file with no
    headings). It must survive as JSON null: the UI decides whether to show
    a section in the citation by testing this field, and the string "None"
    is truthy."""
    store.index(WS_HR, "Un texte sans aucun titre.", "notes.txt")

    points, _ = store.client.scroll(
        vector_store.collection_name(WS_HR), limit=1, with_payload=True
    )

    assert points[0].payload["section_label"] is None


def test_the_collection_is_built_at_the_configured_width(store):
    """A collection holds its vector width forever, so a mismatch between
    `embedding_dense_dim` and what is on disk is a re-index, not a
    restart. Read from the live collection rather than from the call."""
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")

    info = store.client.get_collection(HR_COLLECTION)
    dense = info.config.params.vectors["dense"]

    assert dense.size == get_settings().embedding_dense_dim
    assert "sparse" in info.config.params.sparse_vectors


# --- the library traps, pinned so they cannot come back ---------------


def test_a_child_point_id_is_a_uuid_because_qdrant_refuses_anything_else(store):
    """qdrant-client 1.18 rejects a non-UUID point id outright: `ValueError:
    Point id X is not a valid UUID`. Children arrive from chunking with no
    id at all, so one is derived.

    Both halves asserted: that the derived value really parses as a UUID,
    and -- the part that matters -- that the raw alternative really is
    refused. Without the second, a future change to `_child_point_id` that
    returned a readable string would pass this test and fail at the first
    real sync."""
    from qdrant_client import models

    point_id = vector_store._child_point_id("parent-abc", 0)
    assert uuid.UUID(point_id)

    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")
    with pytest.raises(ValueError, match="not a valid UUID"):
        store.client.upsert(
            HR_COLLECTION,
            points=[
                models.PointStruct(
                    id="parent-abc-0", vector={"dense": [0.0] * 768}, payload={}
                )
            ],
        )


def test_re_indexing_the_same_document_overwrites_instead_of_duplicating(store):
    """Derived point ids, for the reason ST-14 derived parent ids.

    With random ids every re-sync would insert a second copy of every
    unchanged chunk: the collection grows without bound and retrieval
    returns the same passage twice, which reads to a user as the assistant
    repeating itself."""
    first = store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")
    before = store.count(WS_HR)

    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")

    assert before == len(first.children)
    assert store.count(WS_HR) == before


def test_positions_restart_at_zero_for_every_parent(store):
    """The first version of the test below was VACUOUS and a mutation
    proved it: replacing the per-parent counter with a document-wide
    `enumerate` survived the whole suite.

    The reason is the ST-14 lesson repeated -- the fixture was too small
    for the property it claimed to check. `HR_DOCUMENT` merges into ONE
    parent holding ONE child, and for a single child the two numberings
    are both 0, so the comparison could not tell them apart. The fixture
    below is sized to produce several parents with several children each,
    and this test states the property directly instead of inferring it."""
    result = chunking.chunk_document(MULTI_PARENT_DOCUMENT, source_file="code.pdf")
    positions = vector_store._positions_within_parents(result.children)

    by_parent: dict[str, list[int]] = {}
    for child, position in zip(result.children, positions, strict=True):
        by_parent.setdefault(child.parent_id, []).append(position)

    assert len(by_parent) > 1, "fixture must produce more than one parent"
    assert all(len(v) > 1 for v in by_parent.values()), "parents need >1 child each"
    for parent_id, numbering in by_parent.items():
        assert numbering == list(range(len(numbering))), parent_id


def test_a_child_point_id_does_not_depend_on_how_the_caller_batches(store):
    """Derived from the child's position within ITS PARENT, not within the
    document. A resumed or partial sync that upserts one parent's children
    alone must land on the same points, or it duplicates everything it
    already wrote.

    Runs on the multi-parent fixture for the reason above: on a
    single-parent document this assertion is true no matter which
    numbering the code uses."""
    result = chunking.chunk_document(MULTI_PARENT_DOCUMENT, source_file="code.pdf")
    assert len(result.parents) > 1, "fixture must produce more than one parent"
    whole_document = [
        vector_store._child_point_id(child.parent_id, position)
        for child, position in zip(
            result.children,
            vector_store._positions_within_parents(result.children),
            strict=True,
        )
    ]

    per_parent = []
    for parent in result.parents:
        batch = [c for c in result.children if c.parent_id == parent.id]
        per_parent.extend(
            vector_store._child_point_id(child.parent_id, position)
            for child, position in zip(
                batch, vector_store._positions_within_parents(batch), strict=True
            )
        )

    assert sorted(whole_document) == sorted(per_parent)
    assert len(set(whole_document)) == len(whole_document), "ids collided"


def test_a_second_client_on_the_same_path_is_refused_with_a_reason(store, tmp_path):
    """Embedded Qdrant allows one client per storage path and raises a
    RuntimeError about a lock folder, which reads like a stale lock and
    invites deleting it. ADR-04 chose embedded mode knowing it is
    single-process; the fix is always to pass the open client down.

    The message is asserted because the message is the point: a raw
    RuntimeError sends the reader to the wrong fix."""
    with pytest.raises(vector_store.StoreAlreadyOpenError) as caught:
        with vector_store.open_store(tmp_path / "qdrant"):
            pass

    assert "ADR-04" in str(caught.value)


def test_the_lock_is_released_when_the_store_closes(tmp_path, encoders):
    """The other side of the check above. A guard that never releases turns
    one bad path into a process that can never open the store again, which
    is worse than the RuntimeError it replaced."""
    path = tmp_path / "qdrant"
    with vector_store.open_store(path) as client:
        vector_store.ensure_collection(client, workspace_id=WS_HR)
    with vector_store.open_store(path) as client:
        assert client.collection_exists(HR_COLLECTION)


def test_the_lock_is_released_even_when_the_body_raises(tmp_path, encoders):
    path = tmp_path / "qdrant"
    with pytest.raises(RuntimeError, match="deliberate"):
        with vector_store.open_store(path):
            raise RuntimeError("deliberate")
    with vector_store.open_store(path):
        pass


def test_search_really_issues_a_hybrid_query(store):
    """Added because a mutation SURVIVED: deleting the sparse prefetch from
    `search` outright broke nothing any test could see.

    The reason no behavioural test could catch it is worth writing down.
    Both fakes in this file rank by word overlap, so on any fixture here
    the dense side alone returns what the hybrid returns -- the sparse
    branch is real but redundant, and a test asserting on RESULTS cannot
    separate them. Section 7.5 nonetheless specifies a hybrid, and a
    regression that silently dropped half of it would ship.

    So this asserts the SHAPE of the query sent to Qdrant, and it is
    honest about what that is worth: it proves both branches are issued
    against the right named vectors and fused with RRF. It does NOT prove
    the sparse branch improves retrieval on real text -- that needs the
    real models and a real corpus, and it belongs to ST-18's spike."""
    from qdrant_client import models

    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")
    captured = {}
    real = store.client.query_points

    def spy(*args, **kwargs):
        captured.update(kwargs)
        return real(*args, **kwargs)

    store.client.query_points = spy
    store.search(WS_HR, "conges payes")

    prefetch = captured["prefetch"]
    assert [p.using for p in prefetch] == ["dense", "sparse"]
    assert isinstance(prefetch[1].query, models.SparseVector)
    assert prefetch[1].query.indices, "the sparse branch carried an empty vector"
    assert captured["query"].fusion == models.Fusion.RRF


def test_a_failed_open_does_not_strand_the_lock(tmp_path, encoders):
    """Found by reading the diff, not by a test.

    The claim on the storage path was taken before the client was built
    and released only in the `finally` around the yield, so an open that
    failed DURING construction kept the claim forever. One bad path would
    then make the store unopenable for the life of the process -- worse
    than the RuntimeError the guard replaced, and it would look identical
    to a genuine double-open.

    Forced here by putting a FILE where the storage directory has to go.
    The assertion that matters is the second attempt: it must fail the
    same way as the first, not with StoreAlreadyOpenError."""
    blocked = tmp_path / "qdrant"
    blocked.write_text("not a directory", encoding="utf-8")

    for _ in range(2):
        with pytest.raises(OSError):
            with vector_store.open_store(blocked):
                pass

    assert str(blocked.resolve()) not in vector_store._open_paths


def test_dropping_a_collection_reports_an_unknown_count_not_zero(store):
    """`points_deleted` is None after a collection drop because Qdrant does
    not say how many points it held. Zero would be a number a caller could
    compare against and act on, and it would be wrong every time."""
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")

    dropped = vector_store.delete_workspace(
        store.client, workspace_id=WS_HR, parent_base_path=store.parents
    )
    absent = vector_store.delete_workspace(
        store.client, workspace_id=WS_MANUALS, parent_base_path=store.parents
    )

    assert dropped.points_deleted is None
    assert dropped.parents_deleted > 0
    assert absent.points_deleted == 0


def test_indexed_text_and_queries_use_opposite_sides_of_bm25(store, monkeypatch):
    """The asymmetry, checked where it is USED rather than where it is
    defined. `embeddings` proves the two functions call the two methods;
    this proves `vector_store` calls the two functions on the right sides.
    Nothing else would notice `search` reaching for the document encoder."""
    calls: list[str] = []
    monkeypatch.setattr(
        embeddings,
        "embed_sparse_passages",
        lambda texts: (calls.append("passages"), _sparse_batch(texts))[1],
    )
    monkeypatch.setattr(
        embeddings,
        "embed_sparse_query",
        lambda text: (calls.append("query"), _sparse_one(text))[1],
    )

    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")
    assert calls == ["passages"]

    store.search(WS_HR, "conges payes")
    assert calls == ["passages", "query"]


def _sparse_batch(texts):
    return [
        embeddings.SparseVector(indices=raw.indices, values=[float(v) for v in raw.values])
        for raw in _FakeSparseModel().embed(list(texts))
    ]


def _sparse_one(text):
    raw = next(iter(_FakeSparseModel().query_embed(text)))
    return embeddings.SparseVector(
        indices=raw.indices, values=[float(v) for v in raw.values]
    )


# --- the deletion unit -------------------------------------------------


def test_deleting_a_document_removes_its_vectors_and_its_parents_together(store):
    """The defect ST-14 predicted and wrote into BUILD-STATE: the two stores
    must go as ONE unit, or a search hit resolves to a parent file that is
    no longer there.

    Both stores asserted after the call, and the OTHER document in the same
    workspace asserted intact, so a delete that took the whole workspace
    still fails."""
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")
    keep = store.index(WS_HR, "# Note\n\nUn autre document.", "note.md")

    removed = vector_store.delete_document(
        store.client,
        workspace_id=WS_HR,
        source_file="code-du-travail.pdf",
        parent_base_path=store.parents,
    )

    assert removed.points_deleted > 0
    assert removed.parents_deleted > 0
    assert (
        list((store.parents / WS_HR).glob("*.json"))
        and len(list((store.parents / WS_HR).glob("*.json"))) == len(keep.parents)
    )
    assert store.count(WS_HR) == len(keep.children)
    assert {h.source_file for h in store.search(WS_HR, "conges trois mois")} == {
        "note.md"
    }


def test_a_shrinking_document_leaves_no_orphan_parent_or_vector(store):
    """The exact scenario BUILD-STATE carries forward from ST-14: a document
    that shrinks from many parents to few leaves the tail behind, because
    derived ids for the removed positions are simply never rewritten.

    Delete-then-index is what ST-17 will do, and this proves the pair is
    sufficient: every surviving vector resolves to a parent that exists,
    and no parent file survives from the longer version."""
    long_document = "".join(
        f"# Article {n}\n\n{'Le contenu de cet article. ' * 90}\n\n" for n in range(10)
    )
    short_document = "".join(
        f"# Article {n}\n\n{'Le contenu de cet article. ' * 90}\n\n" for n in range(4)
    )
    long_result = store.index(WS_HR, long_document, "code.pdf")

    vector_store.delete_document(
        store.client,
        workspace_id=WS_HR,
        source_file="code.pdf",
        parent_base_path=store.parents,
    )
    short_result = store.index(WS_HR, short_document, "code.pdf")

    assert len(long_result.parents) > len(short_result.parents), "fixture is not shrinking"
    on_disk = {p.stem for p in (store.parents / WS_HR).glob("*.json")}
    assert on_disk == {p.id for p in short_result.parents}
    points, _ = store.client.scroll(
        vector_store.collection_name(WS_HR), limit=1000, with_payload=True
    )
    assert points
    for point in points:
        parent_store.get_parent(
            workspace_id=WS_HR,
            parent_id=point.payload["parent_id"],
            base_path=store.parents,
        )


def test_re_indexing_without_deleting_really_does_strand_the_tail(store):
    """The control for the test above.

    Without it, `delete_document` could be a no-op and the shrink test
    would still pass -- it would just be asserting that a document indexes
    correctly. This runs the same shrink with the delete REMOVED and shows
    the orphans appear, which is what makes the delete the thing under
    test rather than scenery."""
    long_document = "".join(
        f"# Article {n}\n\n{'Le contenu de cet article. ' * 90}\n\n" for n in range(10)
    )
    short_document = "".join(
        f"# Article {n}\n\n{'Le contenu de cet article. ' * 90}\n\n" for n in range(4)
    )
    long_result = store.index(WS_HR, long_document, "code.pdf")
    short_result = store.index(WS_HR, short_document, "code.pdf")

    on_disk = {p.stem for p in (store.parents / WS_HR).glob("*.json")}
    stranded = on_disk - {p.id for p in short_result.parents}

    assert stranded, "expected orphaned parents when the delete is skipped"
    assert stranded <= {p.id for p in long_result.parents}


def test_deleting_a_document_that_was_never_indexed_is_not_an_error(store):
    """Deletion is what a caller runs to reach a known end state, and it is
    re-run after partial failures and crashes. "Already gone" is success."""
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")

    removed = vector_store.delete_document(
        store.client,
        workspace_id=WS_HR,
        source_file="never-existed.pdf",
        parent_base_path=store.parents,
    )

    assert (removed.points_deleted, removed.parents_deleted) == (0, 0)
    assert store.count(WS_HR) > 0


def test_deleting_from_a_workspace_that_has_no_collection_is_not_an_error(store):
    """A workspace deleted before its first sync has neither store. That is
    a normal path, not a fault."""
    removed = vector_store.delete_document(
        store.client,
        workspace_id=WS_MANUALS,
        source_file="anything.pdf",
        parent_base_path=store.parents,
    )
    assert (removed.points_deleted, removed.parents_deleted) == (0, 0)


def test_an_unreadable_parent_file_is_reported_and_does_not_block_the_delete(store):
    """One damaged file must not be able to stop the cleanup of the other
    nine hundred, and must not vanish silently either -- the same shape
    ST-12 settled on for `ScanResult.unreadable`. Silently skipping it
    would let the store accumulate litter nobody can see."""
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")
    damaged = store.parents / WS_HR / "cccccccc-0000-0000-0000-00000000000c.json"
    damaged.write_text("{not json", encoding="utf-8")

    removed = vector_store.delete_document(
        store.client,
        workspace_id=WS_HR,
        source_file="code-du-travail.pdf",
        parent_base_path=store.parents,
    )

    assert removed.parents_deleted > 0
    assert removed.unreadable_parent_files == [damaged.name]
    assert damaged.exists(), "a file we could not read must not be deleted blind"


def test_a_parent_file_without_a_source_file_field_is_reported_not_crashed(store):
    """Valid JSON, wrong shape. `list_parent_ids` reads a field that may not
    be there, and a KeyError inside a deletion sweep is the same failure as
    a crash: the rest of the document never gets cleaned up."""
    directory = store.parents / WS_HR
    directory.mkdir(parents=True)
    (directory / "dddddddd-0000-0000-0000-00000000000d.json").write_text(
        json.dumps({"id": "dddddddd-0000-0000-0000-00000000000d", "text": "x"}),
        encoding="utf-8",
    )

    listing = parent_store.list_parent_ids(
        workspace_id=WS_HR, source_file="anything.pdf", base_path=store.parents
    )

    assert listing.ids == []
    assert listing.unreadable == ["dddddddd-0000-0000-0000-00000000000d.json"]


def test_deleting_a_workspace_takes_both_stores_and_leaves_the_other(store):
    """PRD F-01: deleting a workspace removes its derived data. Isolation
    applies to deletion as much as to reading -- wiping HR must not touch
    the manuals."""
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")
    manuals = store.index(WS_MANUALS, MANUALS_DOCUMENT, "manuel-atelier.pdf")

    vector_store.delete_workspace(
        store.client, workspace_id=WS_HR, parent_base_path=store.parents
    )

    assert not store.client.collection_exists(HR_COLLECTION)
    assert not (store.parents / WS_HR).exists()
    assert store.count(WS_MANUALS) == len(manuals.children)
    assert (store.parents / WS_MANUALS).is_dir()


# --- loud failures -----------------------------------------------------


def test_searching_a_workspace_that_never_synced_says_so(store):
    """Distinct from "the collection is there and empty", which is what a
    workspace with an empty folder looks like. One means "run a Sync", the
    other means "the Sync ran and found nothing"; collapsing them sends the
    user to fix the wrong thing."""
    with pytest.raises(vector_store.CollectionNotFoundError) as caught:
        store.search(WS_HR, "conges payes")

    assert WS_HR in str(caught.value)


def test_an_empty_collection_returns_no_hits_rather_than_raising(store):
    vector_store.ensure_collection(store.client, workspace_id=WS_HR)
    assert store.search(WS_HR, "conges payes") == []


def test_a_short_vector_list_is_refused_instead_of_zipped_short(store):
    """`zip(strict=True)` catches this too, but only after the collection
    has been created and the sparse model has run. Checking first means the
    error names the real fault instead of arriving as a zip complaint."""
    children = [
        Child(text="article 5", parent_id="p1", source_file="code.pdf"),
        Child(text="article 6", parent_id="p1", source_file="code.pdf"),
    ]

    with pytest.raises(vector_store.VectorCountError) as caught:
        vector_store.upsert_children(
            store.client,
            workspace_id=WS_HR,
            children=children,
            dense_vectors=[[0.0] * 768],
        )

    assert "1 dense vectors for 2 children" in str(caught.value)


def test_upserting_nothing_is_a_no_op_and_creates_no_collection(store):
    """A document whose only section was blank produces no children. That is
    a normal outcome of a normal sync, not a fault -- and it must not leave
    an empty collection behind that makes an unsynced workspace look
    synced."""
    written = vector_store.upsert_children(
        store.client, workspace_id=WS_HR, children=[], dense_vectors=[]
    )

    assert written == 0
    assert not store.client.collection_exists(HR_COLLECTION)


def test_a_failed_upsert_leaves_no_collection_behind(store):
    """Found by reading the diff after the suite was green, not by a test.

    The first version created the collection and THEN encoded, so a batch
    containing a whitespace-only window (which `chunking._windows` will
    happily produce -- it keeps any truthy window) raised with an empty
    collection already on disk. That is not harmless: `search` uses "the
    collection exists" to tell "never synced" from "synced and found
    nothing", so a half-failed sync would answer that question wrongly for
    good, and the user would be told to look at their folder instead of
    re-running Sync."""
    children = [
        Child(text="article 5", parent_id="p1", source_file="code.pdf"),
        Child(text="   ", parent_id="p1", source_file="code.pdf"),
    ]

    with pytest.raises(embeddings.EmptyTextError):
        vector_store.upsert_children(
            store.client,
            workspace_id=WS_HR,
            children=children,
            dense_vectors=[[0.0] * 768, [0.0] * 768],
        )

    assert not store.client.collection_exists(HR_COLLECTION)


def test_ensure_collection_twice_does_not_wipe_what_is_already_indexed(store):
    """Sync calls it on every run."""
    store.index(WS_HR, HR_DOCUMENT, "code-du-travail.pdf")
    before = store.count(WS_HR)

    vector_store.ensure_collection(store.client, workspace_id=WS_HR)

    assert store.count(WS_HR) == before


# --- config wiring -----------------------------------------------------


def test_the_search_depth_comes_from_config(store, monkeypatch):
    """F-04 makes retrieval depth operator-tunable; CLAUDE.md forbids
    hardcoding it a second time at a call site. Run at a NON-default value
    so a mutation restoring the plausible literal 5 fails here -- the ST-12
    lesson about mutations that restore a DEFAULT rather than remove
    behaviour."""
    store.index(WS_HR, "# T\n\n" + ("Le contenu du texte. " * 400), "long.md")
    settings = get_settings().model_copy(update={"retrieval_depth_k": 2})
    monkeypatch.setattr(vector_store, "get_settings", lambda: settings)

    assert len(store.search(WS_HR, "contenu")) == 2


def test_an_explicit_limit_overrides_the_configured_depth(store, monkeypatch):
    store.index(WS_HR, "# T\n\n" + ("Le contenu du texte. " * 400), "long.md")
    settings = get_settings().model_copy(update={"retrieval_depth_k": 2})
    monkeypatch.setattr(vector_store, "get_settings", lambda: settings)

    assert len(store.search(WS_HR, "contenu", limit=3)) == 3


def test_the_storage_path_comes_from_config(tmp_path, encoders, monkeypatch):
    """Run at a non-default path, for the same reason as above: a mutation
    restoring the literal "data/qdrant/" must fail here and not quietly
    write into the developer's real store."""
    configured = tmp_path / "somewhere-else"
    settings = get_settings().model_copy(update={"qdrant_storage_path": str(configured)})
    monkeypatch.setattr(vector_store, "get_settings", lambda: settings)

    with vector_store.open_store() as client:
        vector_store.ensure_collection(client, workspace_id=WS_HR)

    assert configured.is_dir()
    assert any(configured.iterdir())
