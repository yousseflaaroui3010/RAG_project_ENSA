"""ST-17 exit gate: PRD F-02's four criteria on real fixtures, all six
`sync_item.result` values correct, and a second Sync blocked.

Reference: docs/phase2/Sanad_Architecture_v1.0.md section 5.1 (the Sync
flow, branch by branch), docs/phase2/Sanad_PRD_v1.0.md F-02 and section 11
(the failure table), and docs/phase2/Sanad_UX_Spec_v1.0.md section 7.2
(the file table: reason is empty for Added, Changed and Unchanged, and
carries text for Failed, Skipped and Removed).

Everything here runs for real: a real SQLite registry, a real embedded
Qdrant under `tmp_path`, real files with real bytes, the real conversion
ladder including a genuinely encrypted PDF. The ONLY fakes are the two
encoders, because they download 1.1GB of weights and this file is not
about them.

Those fakes are deliberately NOT shared with test_vector_store.py's, and
that is a decision rather than an oversight. That file fakes ranking
faithfully because it is testing retrieval quality; this one needs
vectors that are the right width and deterministic, because it is testing
that the stages are wired together in the right order. One shared fake
would have to satisfy both and would become a second implementation
nobody owns.
"""

from __future__ import annotations

import hashlib

import pymupdf
import pytest

import change_detection
import conversion
import embeddings
import parent_store
import sync
import vector_store
import workspaces as ws
from config import get_settings
from db import repo
from sync import DocumentStatus, SyncResult

SPARSE_VOCABULARY = 10_000


# --- encoder fakes ----------------------------------------------------------


def _words(text: str) -> list[str]:
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
    """Bag-of-words vectors of the configured width, unit length for the
    cosine distance the collection is created with. Word-dependent so a
    search for text that was indexed actually finds it -- F-02 criterion
    1 says a synced file is questionable, and a random vector could not
    show that."""
    dim = get_settings().embedding_dense_dim
    vectors = []
    for text in prefixed_texts:
        vector = [0.0] * dim
        for word in _words(text):
            vector[_slot(word, dim)] += 1.0
        length = sum(x * x for x in vector) ** 0.5 or 1.0
        vectors.append([x / length for x in vector])
    return vectors


class _RawSparse:
    def __init__(self, indices, values):
        self.indices = indices
        self.values = values


class _FakeSparseModel:
    def embed(self, documents, **_kwargs):
        return [_RawSparse(*self._terms(text)) for text in documents]

    def query_embed(self, query, **_kwargs):
        return iter([_RawSparse(*self._terms(query))])

    @staticmethod
    def _terms(text):
        slots = sorted({_slot(word, SPARSE_VOCABULARY) for word in _words(text)})
        return slots, [1.0] * len(slots)


@pytest.fixture(autouse=True)
def encoders(monkeypatch):
    """Both encoder seams, replaced for every test in this file. Nothing
    in `sync` itself is patched, so every line of it under test is real."""
    monkeypatch.setattr(embeddings, "_encode", _fake_dense)
    monkeypatch.setattr(embeddings, "_load_sparse_model", lambda _name: _FakeSparseModel())


# --- corpus builders --------------------------------------------------------

# Long enough that each article survives `parent_merge_below_chars` (2,000)
# as its own parent. ST-16 learned this the hard way: four short articles
# merged into ONE parent, and every assertion about which parent a hit
# resolved to stopped measuring anything while still passing.
_PADDING = (
    "Les dispositions du present article s'appliquent a l'ensemble des "
    "salaries lies par un contrat de travail, sous reserve des exceptions "
    "prevues par voie reglementaire et des accords collectifs en vigueur. "
)


def _article(number: int, title: str, body: str) -> str:
    return f"# Article {number} - {title}\n\n{body}\n\n{_PADDING * 12}\n\n"


def _labour_code(*articles: str) -> str:
    return "".join(articles)


HR_TEXT = _labour_code(
    _article(12, "Periode d'essai", "La periode d'essai est de trois mois."),
    _article(20, "Duree du travail", "La duree normale est de dix heures par jour."),
    _article(35, "Conges payes", "Le salarie a droit a trente jours de conges."),
)


def _locked_pdf(path):
    """A real AES-256 encrypted PDF: PRD F-02 criterion 3's literal case.

    Built rather than committed, and not mocked, because the trap it
    covers is a real library behaviour -- pymupdf OPENS this file without
    complaint and only `needs_pass` tells the truth."""
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Confidentiel", fontsize=20)
    doc.save(path, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()
    return path


# --- fixtures ---------------------------------------------------------------


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "sanad.db"
    repo.ensure_schema(path)
    return path


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "hr_docs"
    path.mkdir()
    return path


@pytest.fixture
def workspace(db_path, folder):
    return ws.create_workspace(name="HR", folder_path=str(folder), db_path=db_path)


@pytest.fixture
def parents_path(tmp_path):
    return tmp_path / "parents"


@pytest.fixture
def store(tmp_path):
    """The one Qdrant client, opened per test against its own tmp_path.

    Passed INTO `sync_workspace` rather than letting it open its own,
    which is both what ADR-04 requires of a caller that already holds one
    and what lets a test search the store afterwards."""
    with vector_store.open_store(tmp_path / "qdrant") as client:
        yield client


@pytest.fixture
def run_sync(db_path, workspace, store, parents_path):
    def _run(workspace_id=None):
        return sync.sync_workspace(
            workspace_id=workspace_id or workspace.id,
            db_path=db_path,
            client=store,
            parent_base_path=parents_path,
        )

    return _run


def _write(folder, name, text):
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def _results(report):
    return {item.file_name: item.result for item in report.items}


def _reason(report, file_name):
    return next(i.reason for i in report.items if i.file_name == file_name)


def _documents(db_path, workspace_id):
    conn = repo.get_connection(db_path)
    try:
        return {r["file_name"]: r for r in repo.list_documents(conn, workspace_id)}
    finally:
        conn.close()


def _search(store, workspace_id, question):
    return vector_store.search(store, workspace_id=workspace_id, query_text=question)


# --- F-02 criterion 1: new files are Added, with a page count, and
# --- afterwards their content is questionable -------------------------------


def test_new_files_are_reported_added(folder, run_sync):
    _write(folder, "code.md", HR_TEXT)
    _write(folder, "guide.md", _article(1, "Objet", "Ce guide explique la procedure."))

    report = run_sync()

    assert _results(report) == {
        "code.md": SyncResult.ADDED,
        "guide.md": SyncResult.ADDED,
    }


def test_added_pdf_carries_its_page_count(folder, run_sync, db_path, workspace):
    """F-02 criterion 1 promises the page count, and `document.page_count`
    is the column it lands in. Two pages, so a hardcoded 1 would fail."""
    path = folder / "note.pdf"
    doc = pymupdf.open()
    for number in (1, 2):
        page = doc.new_page()
        page.insert_text((72, 100), f"Chapitre {number}", fontsize=24)
        page.insert_text((72, 140), f"Texte de la page {number}.", fontsize=11)
    doc.save(path)
    doc.close()

    run_sync()

    assert _documents(db_path, workspace.id)["note.pdf"]["page_count"] == 2


def test_a_synced_file_becomes_questionable(
    folder, run_sync, store, workspace, parents_path
):
    """The end-to-end claim of the whole story: after Sync, a question
    finds the passage AND that passage resolves to a parent that really
    contains it. Asserted as a round trip through both derived stores,
    not as "a point exists"."""
    _write(folder, "code.md", HR_TEXT)

    run_sync()

    hits = _search(store, workspace.id, "quelle est la duree normale du travail")
    assert hits, "a synced document returned no search hits"
    assert hits[0].source_file == "code.md"
    assert "dix heures par jour" in hits[0].chunk_text

    parent = parent_store.get_parent(
        workspace_id=workspace.id,
        parent_id=hits[0].parent_id,
        base_path=parents_path,
    )
    assert hits[0].chunk_text in parent.text


# --- F-02 criterion 2: an unchanged file is Unchanged and not reprocessed ---


def test_unchanged_file_is_reported_unchanged(folder, run_sync):
    _write(folder, "code.md", HR_TEXT)
    run_sync()

    report = run_sync()

    assert _results(report) == {"code.md": SyncResult.UNCHANGED}


def test_unchanged_file_is_not_reconverted(folder, run_sync, monkeypatch):
    """"Not reprocessed" is a claim about work NOT done, so it is measured
    at the converter rather than inferred from the report row."""
    _write(folder, "code.md", HR_TEXT)
    calls: list[str] = []
    real = conversion.convert_file
    monkeypatch.setattr(
        conversion, "convert_file", lambda path: (calls.append(str(path)), real(path))[1]
    )

    run_sync()
    assert len(calls) == 1

    run_sync()
    assert len(calls) == 1, "an unchanged file was converted a second time"


# --- F-02 criterion 3: a broken file is Failed with a reason, and every
# --- other file completes ---------------------------------------------------


def test_password_protected_file_is_failed_and_never_blocks_the_batch(
    folder, run_sync
):
    _locked_pdf(folder / "confidentiel.pdf")
    _write(folder, "code.md", HR_TEXT)
    _write(folder, "guide.md", _article(1, "Objet", "Ce guide explique tout."))

    report = run_sync()

    assert _results(report) == {
        "confidentiel.pdf": SyncResult.FAILED,
        "code.md": SyncResult.ADDED,
        "guide.md": SyncResult.ADDED,
    }
    assert _reason(report, "confidentiel.pdf")


def test_a_failing_stage_costs_one_row_not_the_batch(folder, run_sync, monkeypatch):
    """The containment that `conversion.convert_file` cannot provide,
    because the stages after it CAN raise. One exploding file must leave
    the other two Added."""
    _write(folder, "a.md", HR_TEXT)
    _write(folder, "boom.md", HR_TEXT)
    _write(folder, "z.md", HR_TEXT)
    real = embeddings.embed_children

    def explode(children):
        if children and children[0].source_file == "boom.md":
            raise RuntimeError("the embedder fell over")
        return real(children)

    monkeypatch.setattr(embeddings, "embed_children", explode)

    report = run_sync()

    assert _results(report) == {
        "a.md": SyncResult.ADDED,
        "boom.md": SyncResult.FAILED,
        "z.md": SyncResult.ADDED,
    }
    assert "the embedder fell over" in _reason(report, "boom.md")


def test_an_unreadable_file_leaves_its_existing_passages_alone(
    folder, run_sync, store, workspace, db_path, monkeypatch
):
    """A file we could not READ this run is not evidence that last run's
    chunks are wrong. Its row must stay `active` and its passages must
    keep answering, or one locked file silently unpublishes a document."""
    _write(folder, "code.md", HR_TEXT)
    run_sync()

    # The same seam test_change_detection.py patches, for the reason given
    # there: on Windows an owner cannot chmod away their own read access,
    # and swapping the file for a directory makes `scan_folder` skip it
    # before it ever reads, which passes for the wrong reason.
    real = change_detection.compute_fingerprint

    def fake(path):
        if path.name == "code.md":
            raise change_detection.UnreadableFileError(path.name, "permission denied")
        return real(path)

    monkeypatch.setattr(change_detection, "compute_fingerprint", fake)

    report = run_sync()

    assert _results(report) == {"code.md": SyncResult.FAILED}
    assert _reason(report, "code.md")
    assert _documents(db_path, workspace.id)["code.md"]["status"] == DocumentStatus.ACTIVE
    monkeypatch.undo()
    assert _search(store, workspace.id, "duree normale du travail")


# --- F-02 criterion 4: a removed file is Removed and its passages stop
# --- appearing in answers ---------------------------------------------------


def test_removed_file_is_reported_removed_and_stops_answering(
    folder, run_sync, store, workspace
):
    _write(folder, "code.md", HR_TEXT)
    _write(folder, "guide.md", _article(1, "Objet", "Le guide reste en place."))
    run_sync()
    assert _search(store, workspace.id, "duree normale du travail")

    (folder / "code.md").unlink()
    report = run_sync()

    assert _results(report)["code.md"] == SyncResult.REMOVED
    hits = _search(store, workspace.id, "duree normale du travail")
    assert all(hit.source_file != "code.md" for hit in hits)


def test_removed_file_takes_its_parent_files_with_it(
    folder, run_sync, workspace, parents_path
):
    """The two stores go as one unit. A parent left behind is a citation
    that resolves to nothing the moment a stale vector survives."""
    _write(folder, "code.md", HR_TEXT)
    run_sync()
    assert list((parents_path / workspace.id).glob("*.json"))

    (folder / "code.md").unlink()
    run_sync()

    assert not list((parents_path / workspace.id).glob("*.json"))


def test_removed_document_row_survives_as_removed(
    folder, run_sync, db_path, workspace
):
    """Kept, not deleted: `change_detection` needs `removed` to re-ingest
    the file if it comes back, and deleting the row would NULL the
    document_id on every past report row that mentioned it."""
    _write(folder, "code.md", HR_TEXT)
    run_sync()
    (folder / "code.md").unlink()

    run_sync()

    assert _documents(db_path, workspace.id)["code.md"]["status"] == (
        DocumentStatus.REMOVED
    )


def test_a_removed_file_is_not_reported_again_on_the_next_sync(folder, run_sync):
    """A phantom row on every future run would make the report useless."""
    _write(folder, "code.md", HR_TEXT)
    run_sync()
    (folder / "code.md").unlink()
    run_sync()

    report = run_sync()

    assert _results(report) == {}


def test_a_file_that_comes_back_is_added_into_its_existing_row(
    folder, run_sync, db_path, workspace
):
    """The UNIQUE (workspace_id, file_name) trap. A returning file is NEW
    yet already owns a row, so an INSERT here raises IntegrityError -- and
    identical bytes must still re-ingest, because its chunks are gone."""
    _write(folder, "code.md", HR_TEXT)
    run_sync()
    (folder / "code.md").unlink()
    run_sync()
    _write(folder, "code.md", HR_TEXT)

    report = run_sync()

    assert _results(report) == {"code.md": SyncResult.ADDED}
    row = _documents(db_path, workspace.id)["code.md"]
    assert row["status"] == DocumentStatus.ACTIVE


# --- the changed branch -----------------------------------------------------


def test_edited_file_is_reported_changed(folder, run_sync):
    _write(folder, "code.md", HR_TEXT)
    run_sync()
    _write(folder, "code.md", HR_TEXT + _article(99, "Ajout", "Nouvelle regle."))

    report = run_sync()

    assert _results(report) == {"code.md": SyncResult.CHANGED}


def test_a_shrinking_document_leaves_no_stranded_parents(
    folder, run_sync, workspace, parents_path
):
    """ST-14 predicted this and ST-16 proved delete-then-index clears it;
    ST-17 is the caller that has to actually run the delete. A document
    cut from three articles to one must not leave the other two readable
    on disk."""
    _write(folder, "code.md", HR_TEXT)
    run_sync()
    before = len(list((parents_path / workspace.id).glob("*.json")))
    assert before >= 3, "fixture too small to show stranded parents"

    _write(folder, "code.md", _article(12, "Periode d'essai", "Trois mois."))
    run_sync()

    after = list((parents_path / workspace.id).glob("*.json"))
    assert len(after) < before


def test_a_changed_file_does_not_answer_with_its_old_text(
    folder, run_sync, store, workspace
):
    """The reason the delete happens BEFORE conversion: old chunks
    describe text that is no longer in the file, and citing them sends the
    user looking for a passage that is not there."""
    _write(folder, "code.md", HR_TEXT)
    run_sync()

    _write(
        folder,
        "code.md",
        _article(12, "Periode d'essai", "La periode d'essai est de six mois."),
    )
    run_sync()

    hits = _search(store, workspace.id, "dix heures par jour")
    assert all("dix heures par jour" not in hit.chunk_text for hit in hits)


def test_an_interrupted_write_never_leaves_a_vector_without_its_parent(
    folder, run_sync, store, workspace, parents_path, monkeypatch
):
    """The write order is a safety property, so it gets a test that can
    tell the two orders apart rather than a comment claiming it.

    The second of the two writes is made to fail. Parents first (correct)
    means the crash happens before any vector exists, so every vector in
    the store still resolves. Vectors first would leave points whose
    parent file was never written -- a search hit that resolves to
    nothing, which is the one failure a sourced-answer product cannot
    absorb. Swap the two calls in `_ingest` and this test goes red."""
    _write(folder, "code.md", HR_TEXT)

    def explode(**_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(parent_store, "save_parents", explode)

    report = run_sync()

    assert _results(report) == {"code.md": SyncResult.FAILED}
    name = vector_store.collection_name(workspace.id)
    points = (
        store.scroll(name, limit=1000, with_payload=True)[0]
        if store.collection_exists(name)
        else []
    )
    for point in points:
        # Raises ParentNotFoundError if the citation is broken.
        parent_store.get_parent(
            workspace_id=workspace.id,
            parent_id=point.payload["parent_id"],
            base_path=parents_path,
        )


# --- skipped ----------------------------------------------------------------


def test_unsupported_file_type_is_skipped_with_a_reason(folder, run_sync):
    _write(folder, "deck.pptx", "not really a deck")
    _write(folder, "code.md", HR_TEXT)

    report = run_sync()

    assert _results(report)["deck.pptx"] == SyncResult.SKIPPED
    assert _reason(report, "deck.pptx") == change_detection.UNSUPPORTED_TYPE_REASON


def test_unsupported_file_gets_no_document_row(folder, run_sync, db_path, workspace):
    """Nothing was fingerprinted and nothing was ingested, so there is no
    honest row to write -- only a report row."""
    _write(folder, "deck.pptx", "not really a deck")

    run_sync()

    assert "deck.pptx" not in _documents(db_path, workspace.id)


def test_a_file_with_no_readable_text_is_skipped(folder, run_sync, db_path, workspace):
    """The F-16 binding shape: nothing to index, and not the user's
    fault."""
    _write(folder, "empty.md", "   \n\n  ")

    report = run_sync()

    assert _results(report) == {"empty.md": SyncResult.SKIPPED}
    assert _reason(report, "empty.md")
    assert _documents(db_path, workspace.id)["empty.md"]["status"] == (
        DocumentStatus.SKIPPED
    )


def test_a_sync_that_indexed_nothing_still_counts_as_synced(
    folder, run_sync, store, workspace
):
    """"Never synced" and "synced, found nothing" are different answers
    and the user acts on them differently.

    `upsert_children` returns before creating the collection when there
    are no children, so a run where every file was skipped would leave no
    collection at all and `search` would report a workspace that has just
    been synced as never synced."""
    _write(folder, "empty.md", "   ")
    _write(folder, "deck.pptx", "x")

    run_sync()

    assert _search(store, workspace.id, "duree du travail") == []


def test_a_sync_of_an_empty_folder_still_counts_as_synced(
    folder, run_sync, store, workspace
):
    report = run_sync()

    assert report.items == []
    assert _search(store, workspace.id, "duree du travail") == []


def test_a_missing_folder_creates_no_collection(
    db_path, tmp_path, store, parents_path
):
    """The other side: nothing partially ingested (PRD section 11), so a
    folder-level failure must not leave a collection behind claiming the
    workspace has been synced."""
    missing = tmp_path / "not_there"
    workspace = ws.create_workspace(
        name="Gone", folder_path=str(missing), db_path=db_path
    )

    with pytest.raises(change_detection.FolderNotFoundError):
        sync.sync_workspace(
            workspace_id=workspace.id,
            db_path=db_path,
            client=store,
            parent_base_path=parents_path,
        )

    assert not store.collection_exists(vector_store.collection_name(workspace.id))


# --- all six, and the report contract --------------------------------------


def test_all_six_result_values_in_one_run(folder, run_sync, db_path, workspace):
    """The exit gate's "six statuses correct", in a single report."""
    _write(folder, "unchanged.md", HR_TEXT)
    _write(folder, "changed.md", HR_TEXT)
    _write(folder, "gone.md", HR_TEXT)
    run_sync()

    _write(folder, "changed.md", HR_TEXT + _article(99, "Ajout", "Nouvelle regle."))
    (folder / "gone.md").unlink()
    _write(folder, "added.md", HR_TEXT)
    _write(folder, "empty.md", "   ")
    _locked_pdf(folder / "locked.pdf")

    report = run_sync()

    assert _results(report) == {
        "added.md": SyncResult.ADDED,
        "changed.md": SyncResult.CHANGED,
        "unchanged.md": SyncResult.UNCHANGED,
        "locked.pdf": SyncResult.FAILED,
        "gone.md": SyncResult.REMOVED,
        "empty.md": SyncResult.SKIPPED,
    }
    assert report.counts == {
        SyncResult.ADDED: 1,
        SyncResult.CHANGED: 1,
        SyncResult.UNCHANGED: 1,
        SyncResult.FAILED: 1,
        SyncResult.REMOVED: 1,
        SyncResult.SKIPPED: 1,
    }


def test_reason_is_empty_for_clean_outcomes_and_present_for_the_rest(
    folder, run_sync
):
    """UX spec section 7.2, stated exactly: the reason column is empty for
    Added, Changed and Unchanged, and carries text for Failed, Skipped and
    Removed. The Removed half is the one a reader assumes is null."""
    _write(folder, "unchanged.md", HR_TEXT)
    _write(folder, "changed.md", HR_TEXT)
    _write(folder, "gone.md", HR_TEXT)
    run_sync()
    _write(folder, "changed.md", HR_TEXT + _article(99, "Ajout", "Regle."))
    (folder / "gone.md").unlink()
    _write(folder, "added.md", HR_TEXT)
    _write(folder, "empty.md", "   ")
    _locked_pdf(folder / "locked.pdf")

    report = run_sync()

    quiet = {SyncResult.ADDED, SyncResult.CHANGED, SyncResult.UNCHANGED}
    for item in report.items:
        if item.result in quiet:
            assert item.reason is None, f"{item.file_name} carried a reason"
        else:
            assert item.reason, f"{item.file_name} had no reason"


def test_the_run_row_records_the_same_counts_as_the_report(
    folder, run_sync, db_path
):
    """The report object and the persisted row are two descriptions of one
    run, and the UI reads the row."""
    _write(folder, "a.md", HR_TEXT)
    _write(folder, "empty.md", "   ")

    report = run_sync()

    conn = repo.get_connection(db_path)
    try:
        row = repo.get_sync_run(conn, report.sync_run_id)
    finally:
        conn.close()
    assert row["added"] == 1
    assert row["skipped"] == 1
    assert row["finished_at"] == report.finished_at


def test_every_report_row_is_persisted_as_a_sync_item(folder, run_sync, db_path):
    _write(folder, "a.md", HR_TEXT)
    _write(folder, "deck.pptx", "x")
    _write(folder, "empty.md", "  ")

    report = run_sync()

    conn = repo.get_connection(db_path)
    try:
        rows = repo.list_sync_items(conn, report.sync_run_id)
    finally:
        conn.close()
    # Compared as ORDERED LISTS, not as dicts keyed on file name. A dict
    # on either side silently collapses two rows for one file into one,
    # and that is exactly the defect this file could not see: every other
    # helper here keys by name, so a run that reported `code.md` twice
    # passed the whole suite.
    assert [(r["file_name"], r["result"]) for r in rows] == [
        (item.file_name, str(item.result)) for item in report.items
    ]


def test_each_file_gets_exactly_one_report_row(folder, run_sync, monkeypatch):
    """Rule 1 of this module's docstring, stated as a count.

    An ingested file whose type is later narrowed out of
    `supported_document_extensions` used to land in BOTH the unsupported
    list and the REMOVED sweep, so one file produced a Skipped row and a
    Removed row in the same run -- and the Removed branch deleted its
    vectors and parent files while the Skipped row told the user nothing
    had happened to it."""
    _write(folder, "code.md", HR_TEXT)
    run_sync()

    narrowed = get_settings().model_copy(
        update={"supported_document_extensions": ("pdf",)}
    )
    monkeypatch.setattr(change_detection, "get_settings", lambda: narrowed)

    report = run_sync()

    names = [item.file_name for item in report.items]
    assert names == ["code.md"], f"one file produced {len(names)} rows: {names}"
    assert report.counts[SyncResult.SKIPPED] == 1
    assert report.counts[SyncResult.REMOVED] == 0


def test_report_rows_are_ordered_by_file_name(folder, run_sync):
    """UX spec 7.2's table is read by a human hunting one file."""
    for name in ("zeta.md", "alpha.md", "mid.md"):
        _write(folder, name, HR_TEXT)

    report = run_sync()

    names = [item.file_name for item in report.items]
    assert names == sorted(names)


# --- double sync ------------------------------------------------------------


def test_a_second_sync_is_blocked_while_one_is_running(
    folder, db_path, workspace, store, parents_path
):
    """PRD section 11: blocked with a message, first run keeps going. The
    second Sync is attempted from INSIDE the first, at the one moment it
    is genuinely mid-run, rather than by hand-writing a half-finished row
    -- a fabricated row would prove the query works and nothing about the
    guard."""
    _write(folder, "code.md", HR_TEXT)
    blocked: list[Exception] = []
    real = conversion.convert_file

    def convert_and_reenter(path):
        try:
            sync.sync_workspace(
                workspace_id=workspace.id,
                db_path=db_path,
                client=store,
                parent_base_path=parents_path,
            )
        except sync.SyncInProgressError as exc:
            blocked.append(exc)
        return real(path)

    conversion.convert_file = convert_and_reenter
    try:
        report = sync.sync_workspace(
            workspace_id=workspace.id,
            db_path=db_path,
            client=store,
            parent_base_path=parents_path,
        )
    finally:
        conversion.convert_file = real

    assert len(blocked) == 1, "the second sync was not blocked"
    assert blocked[0].sync_run_id == report.sync_run_id
    # ...and the first run kept going.
    assert _results(report) == {"code.md": SyncResult.ADDED}


def test_a_finished_run_does_not_block_the_next_sync(folder, run_sync):
    _write(folder, "code.md", HR_TEXT)
    run_sync()

    run_sync()  # must not raise


def test_syncing_one_workspace_does_not_block_another(
    db_path, tmp_path, store, parents_path, workspace, folder
):
    """The guard is per workspace. Blocking HR because the manuals are
    syncing would be a bug the PRD row does not ask for."""
    other_folder = tmp_path / "manuals"
    other_folder.mkdir()
    other = ws.create_workspace(
        name="Manuals", folder_path=str(other_folder), db_path=db_path
    )
    _write(folder, "code.md", HR_TEXT)
    _write(other_folder, "manual.md", HR_TEXT)

    with repo.session(db_path) as conn:
        repo.insert_sync_run(conn, workspace_id=workspace.id)

    report = sync.sync_workspace(
        workspace_id=other.id,
        db_path=db_path,
        client=store,
        parent_base_path=parents_path,
    )

    assert _results(report) == {"manual.md": SyncResult.ADDED}


# --- failure at the folder level -------------------------------------------


def test_a_missing_folder_raises_and_ingests_nothing(
    db_path, tmp_path, store, parents_path
):
    """PRD section 11: exact path plus a fix hint, nothing partially
    ingested. It propagates because a folder-level failure has no file to
    hang a report row on."""
    missing = tmp_path / "not_there"
    workspace = ws.create_workspace(
        name="Gone", folder_path=str(missing), db_path=db_path
    )

    with pytest.raises(change_detection.FolderNotFoundError) as caught:
        sync.sync_workspace(
            workspace_id=workspace.id,
            db_path=db_path,
            client=store,
            parent_base_path=parents_path,
        )

    assert str(missing) in str(caught.value)


def test_a_failed_run_does_not_leave_the_workspace_blocked(
    db_path, tmp_path, store, parents_path
):
    """The guard must not be able to lock a workspace out with its own
    wreckage: the run row is finished in a `finally`, so the next Sync
    gets as far as the same honest error rather than a "still running"
    that will never clear."""
    missing = tmp_path / "not_there"
    workspace = ws.create_workspace(
        name="Gone", folder_path=str(missing), db_path=db_path
    )

    for _ in range(2):
        with pytest.raises(change_detection.FolderNotFoundError):
            sync.sync_workspace(
                workspace_id=workspace.id,
                db_path=db_path,
                client=store,
                parent_base_path=parents_path,
            )

    conn = repo.get_connection(db_path)
    try:
        assert repo.get_running_sync_run(conn, workspace.id) is None
    finally:
        conn.close()


def test_an_unknown_workspace_leaves_no_sync_run_behind(db_path, store, parents_path):
    with pytest.raises(ws.WorkspaceNotFoundError):
        sync.sync_workspace(
            workspace_id="11111111-1111-1111-1111-111111111111",
            db_path=db_path,
            client=store,
            parent_base_path=parents_path,
        )

    conn = repo.get_connection(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) c FROM sync_run").fetchone()["c"] == 0
    finally:
        conn.close()


# --- the retry rule the statuses depend on ----------------------------------


def test_a_failed_file_is_retried_and_re_reported_on_the_next_sync(folder, run_sync):
    """`document.status` has no column for a reason (db/schema.sql is
    signed), so re-attempting is the only way the report keeps telling the
    truth about a broken file. Reported Failed once and then silently
    Unchanged forever would break F-02 criterion 3 after run one."""
    _locked_pdf(folder / "locked.pdf")

    first = run_sync()
    second = run_sync()

    assert _results(first) == {"locked.pdf": SyncResult.FAILED}
    assert _results(second) == {"locked.pdf": SyncResult.FAILED}
    assert _reason(second, "locked.pdf")


def test_a_fixed_file_is_ingested_on_the_next_sync(folder, run_sync):
    """The other half: the retry is not busywork, it is what lets a file
    the user has repaired come back without a manual re-index."""
    _locked_pdf(folder / "doc.pdf")
    assert _results(run_sync()) == {"doc.pdf": SyncResult.FAILED}

    (folder / "doc.pdf").unlink()
    _write(folder, "doc.pdf", "")
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Article 12 Periode d'essai", fontsize=20)
    doc.save(folder / "doc.pdf")
    doc.close()

    assert _results(run_sync()) == {"doc.pdf": SyncResult.ADDED}


def test_a_skipped_file_is_retried_too(folder, run_sync):
    _write(folder, "empty.md", "   ")

    assert _results(run_sync()) == {"empty.md": SyncResult.SKIPPED}
    assert _results(run_sync()) == {"empty.md": SyncResult.SKIPPED}


def test_a_failed_file_deleted_from_disk_is_reported_removed(folder, run_sync):
    """The other side of splitting the two status sets. A `failed` row
    whose file the user deleted must clear, not sit in the registry for
    ever describing a document that is not there."""
    _locked_pdf(folder / "locked.pdf")
    run_sync()

    (folder / "locked.pdf").unlink()
    report = run_sync()

    assert _results(report) == {"locked.pdf": SyncResult.REMOVED}


# --- workspace deletion (the ST-16 follow-up ST-17 owns) --------------------


def test_deleting_a_workspace_takes_both_derived_stores_and_the_registry(
    folder, run_sync, store, workspace, db_path, parents_path
):
    _write(folder, "code.md", HR_TEXT)
    run_sync()
    assert list((parents_path / workspace.id).glob("*.json"))

    sync.delete_workspace(
        workspace_id=workspace.id,
        db_path=db_path,
        client=store,
        parent_base_path=parents_path,
    )

    assert not (parents_path / workspace.id).exists()
    assert not store.collection_exists(vector_store.collection_name(workspace.id))
    assert workspace.id not in {w.id for w in ws.list_workspaces(db_path=db_path)}


def test_deleting_a_workspace_leaves_the_source_files_untouched(
    folder, run_sync, store, workspace, db_path, parents_path
):
    """F-01's third criterion, and the one users refuse to believe."""
    path = _write(folder, "code.md", HR_TEXT)
    run_sync()

    sync.delete_workspace(
        workspace_id=workspace.id,
        db_path=db_path,
        client=store,
        parent_base_path=parents_path,
    )

    assert path.read_text(encoding="utf-8") == HR_TEXT


# --- drift check ------------------------------------------------------------


def _check_values(table: str, column: str) -> set[str]:
    """The allowed values of one CHECK (... IN (...)) constraint, read out
    of db/schema.sql itself."""
    import re
    from pathlib import Path as _Path

    ddl = (_Path(__file__).resolve().parents[2] / "db" / "schema.sql").read_text(
        encoding="utf-8"
    )
    body = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n\);", ddl, re.S)
    assert body, f"{table} not found in schema.sql"
    clause = re.search(rf"{column}.*?CHECK\s*\(.*?IN \((.*?)\)", body.group(1), re.S)
    assert clause, f"no CHECK on {table}.{column}"
    return set(re.findall(r"'([a-z_]+)'", clause.group(1)))


def test_sync_result_enum_matches_the_schema_check_constraint():
    """A mechanical drift check, not discipline. It reads the SQL rather
    than a recorded hash, so it compares against the artifact that is
    actually applied -- the trap the journal records from S1-A3, where a
    test named "byte-identical to the delivery" compared against a
    constant and passed on the wrong copy for weeks."""
    assert {r.value for r in SyncResult} == _check_values("sync_item", "result")


def test_document_status_enum_matches_the_schema_check_constraint():
    assert {s.value for s in DocumentStatus} == _check_values("document", "status")


def test_change_detection_agrees_with_sync_about_document_statuses():
    """The third copy of this vocabulary. `change_detection` reads the
    column that `sync` writes, and a value in one and not the other is a
    branch that can never fire."""
    known = {s.value for s in DocumentStatus}
    assert change_detection._STATUS_WITHOUT_DERIVED_DATA <= known
    assert change_detection._STATUS_ALREADY_REPORTED_REMOVED <= known
