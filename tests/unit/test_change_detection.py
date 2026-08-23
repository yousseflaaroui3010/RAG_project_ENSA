"""ST-12 exit gate: the new / changed / unchanged / removed transitions,
including the size+hash collision guard.

Reference: docs/phase2/Sanad_Architecture_v1.0.md section 5.1 (the
`H{Per file: content hash vs registry}` decision in the Sync flow) and
docs/phase2/Sanad_PRD_v1.0.md F-02.

Every test writes real bytes to a real folder under `tmp_path`, and the
filesystem is mocked in exactly one place, for a reason given at
`_fail_reads_of`. Everything else is acted out for real: the ST-11 review
found a test that passed while proving nothing, and a mocked read would
hide precisely the bugs this module can have (chunk-boundary errors, a
size that disagrees with its digest, a scan that walks into subfolders).
"""

from __future__ import annotations

import pytest

import change_detection as cd
import workspaces as ws
from db import repo


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "sanad.db"
    repo.ensure_schema(path)
    return path


@pytest.fixture
def folder(tmp_path):
    path = tmp_path / "docs"
    path.mkdir()
    return path


@pytest.fixture
def workspace(db_path, folder):
    return ws.create_workspace(name="HR", folder_path=str(folder), db_path=db_path)


def _write(folder, name: str, text: str):
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def _register(db_path, workspace_id: str, name: str, content_hash: str, status="active") -> str:
    """Put a document row in the registry as a previous sync would have.

    Takes `content_hash` as a raw string rather than a Fingerprint so a
    test can deliberately store a malformed or hand-built value -- that
    is the whole point of the collision-guard and legacy-value tests."""
    with repo.session(db_path) as conn:
        return repo.insert_document(
            conn,
            workspace_id=workspace_id,
            file_name=name,
            file_type=name.rsplit(".", 1)[-1],
            content_hash=content_hash,
            status=status,
        )


def _status_of(report, file_name: str):
    return next(c.status for c in report.changes if c.file_name == file_name)


# --- fingerprinting ---------------------------------------------------------


def test_same_bytes_produce_the_same_fingerprint(folder):
    a = _write(folder, "a.txt", "hello")
    b = _write(folder, "b.txt", "hello")
    assert cd.compute_fingerprint(a) == cd.compute_fingerprint(b)


def test_one_changed_byte_changes_the_digest(folder):
    path = _write(folder, "a.txt", "hello")
    before = cd.compute_fingerprint(path)
    path.write_text("hellp", encoding="utf-8")
    after = cd.compute_fingerprint(path)

    assert after.hex_digest != before.hex_digest
    # Same length, so the digest is the only thing that caught it. If this
    # ever passes on size alone the collision guard below proves nothing.
    assert after.size_bytes == before.size_bytes


def test_fingerprint_size_is_counted_from_the_bytes_actually_read(folder):
    path = _write(folder, "a.txt", "0123456789")
    assert cd.compute_fingerprint(path).size_bytes == path.stat().st_size


def test_hashing_is_independent_of_the_read_chunk_size(folder, monkeypatch):
    """A file larger than one read block must hash identically to the same
    bytes read whole. This is the test that fails if the incremental read
    loop drops or double-counts a chunk at a boundary."""
    from config import get_settings

    payload = "x" * 5000
    path = _write(folder, "big.txt", payload)

    whole = cd.compute_fingerprint(path)

    settings = get_settings()
    monkeypatch.setattr(settings, "hash_read_chunk_bytes", 7, raising=True)
    chunked = cd.compute_fingerprint(path)

    assert chunked == whole
    assert chunked.size_bytes == len(payload)


def test_fingerprint_round_trips_through_serialize_and_parse(folder):
    original = cd.compute_fingerprint(_write(folder, "a.txt", "hello"))
    assert cd.Fingerprint.parse(original.serialize()) == original


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "legacy-plain-digest",
        "sha256:abc",
        "sha256:abc:notanumber",
        "sha256::12",
        "md5:abc:12",
        "sha256:abc:-1",
    ],
)
def test_unparseable_stored_fingerprints_are_rejected(raw):
    assert cd.Fingerprint.parse(raw) is None


def test_unreadable_file_raises_a_domain_error(folder):
    with pytest.raises(cd.UnreadableFileError):
        cd.compute_fingerprint(folder / "does-not-exist.txt")


# --- folder scan ------------------------------------------------------------


def test_scan_fingerprints_supported_files_only_and_reports_the_rest(folder):
    _write(folder, "policy.pdf", "pdf bytes")
    _write(folder, "notes.md", "# notes")
    _write(folder, "installer.exe", "binary")

    scan = cd.scan_folder(folder)

    assert set(scan.fingerprints) == {"policy.pdf", "notes.md"}
    # Not silently dropped: PRD section 11 promises the user a Skipped row
    # with a reason for an unsupported file type.
    assert [u.file_name for u in scan.unsupported] == ["installer.exe"]
    assert scan.unsupported[0].reason


def test_scan_does_not_descend_into_subfolders(folder):
    _write(folder, "top.txt", "top")
    nested = folder / "archive"
    nested.mkdir()
    _write(nested, "buried.txt", "buried")

    scan = cd.scan_folder(folder)

    assert set(scan.fingerprints) == {"top.txt"}
    # A subfolder is not a document; it must not appear as a Skipped file.
    assert scan.unsupported == []


def test_scan_of_a_missing_folder_raises_with_the_path_in_the_message(tmp_path):
    missing = tmp_path / "unplugged-drive"
    with pytest.raises(cd.FolderNotFoundError) as exc:
        cd.scan_folder(missing)
    assert str(missing) in str(exc.value)


# --- the four transitions ---------------------------------------------------


def test_file_not_in_the_registry_is_new(db_path, folder, workspace):
    _write(folder, "policy.pdf", "v1")

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "policy.pdf") is cd.ChangeStatus.NEW
    assert report.by_status(cd.ChangeStatus.NEW)[0].document_id is None


def test_untouched_file_is_unchanged(db_path, folder, workspace):
    path = _write(folder, "policy.pdf", "v1")
    _register(db_path, workspace.id, "policy.pdf", cd.compute_fingerprint(path).serialize())

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "policy.pdf") is cd.ChangeStatus.UNCHANGED


def test_edited_file_is_changed(db_path, folder, workspace):
    path = _write(folder, "policy.pdf", "v1")
    _register(db_path, workspace.id, "policy.pdf", cd.compute_fingerprint(path).serialize())

    path.write_text("v2 with different content", encoding="utf-8")
    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "policy.pdf") is cd.ChangeStatus.CHANGED
    # ST-17 needs the id to delete the old chunks; it must not have to look it up.
    assert report.by_status(cd.ChangeStatus.CHANGED)[0].document_id is not None


def test_file_gone_from_disk_is_removed(db_path, folder, workspace):
    path = _write(folder, "policy.pdf", "v1")
    _register(db_path, workspace.id, "policy.pdf", cd.compute_fingerprint(path).serialize())
    path.unlink()

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "policy.pdf") is cd.ChangeStatus.REMOVED
    # Nothing left to hash, and ST-17 needs the id to delete its chunks.
    removed = report.by_status(cd.ChangeStatus.REMOVED)[0]
    assert removed.fingerprint is None
    assert removed.document_id is not None


def test_all_four_transitions_in_one_pass(db_path, folder, workspace):
    """The four verdicts must be independent. A classifier that falls
    through to one bucket still passes each single-transition test above;
    it fails here."""
    kept = _write(folder, "kept.txt", "same")
    edited = _write(folder, "edited.txt", "before")
    vanished = _write(folder, "vanished.txt", "gone soon")
    _write(folder, "fresh.txt", "brand new")

    _register(db_path, workspace.id, "kept.txt", cd.compute_fingerprint(kept).serialize())
    _register(db_path, workspace.id, "edited.txt", cd.compute_fingerprint(edited).serialize())
    _register(db_path, workspace.id, "vanished.txt", cd.compute_fingerprint(vanished).serialize())

    edited.write_text("after", encoding="utf-8")
    vanished.unlink()

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert {c.file_name: c.status for c in report.changes} == {
        "kept.txt": cd.ChangeStatus.UNCHANGED,
        "edited.txt": cd.ChangeStatus.CHANGED,
        "vanished.txt": cd.ChangeStatus.REMOVED,
        "fresh.txt": cd.ChangeStatus.NEW,
    }


# --- the collision guard (ST-12 exit criterion: size + hash) ----------------


def test_same_digest_but_different_size_is_changed_not_unchanged(db_path, folder, workspace):
    """The stated collision guard. A real SHA-256 collision cannot be
    produced in a unit test, so the collision is injected: the registry
    holds this file's exact digest paired with a different byte count.
    Compare on the digest alone and this returns UNCHANGED, leaving stale
    passages in answers forever."""
    path = _write(folder, "policy.pdf", "v1 content")
    actual = cd.compute_fingerprint(path)
    forged = cd.Fingerprint(
        algorithm=actual.algorithm,
        hex_digest=actual.hex_digest,
        size_bytes=actual.size_bytes + 1,
    )
    _register(db_path, workspace.id, "policy.pdf", forged.serialize())

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "policy.pdf") is cd.ChangeStatus.CHANGED


def test_same_size_but_different_digest_is_changed_not_unchanged(db_path, folder, workspace):
    """The other half of the guard: size must not be able to stand in for
    the digest. Both files are 10 bytes."""
    path = _write(folder, "policy.pdf", "0123456789")
    other = cd.compute_fingerprint(_write(folder, "decoy.txt", "9876543210"))
    assert other.size_bytes == cd.compute_fingerprint(path).size_bytes
    _register(db_path, workspace.id, "policy.pdf", other.serialize())

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "policy.pdf") is cd.ChangeStatus.CHANGED


def test_unparseable_stored_hash_is_reprocessed_not_skipped(db_path, folder, workspace):
    """A row whose content_hash this module cannot read resolves toward
    CHANGED. Re-ingesting costs one conversion; guessing UNCHANGED on an
    unknown identity strands stale passages permanently."""
    _write(folder, "policy.pdf", "v1")
    _register(db_path, workspace.id, "policy.pdf", "some-legacy-plain-digest")

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "policy.pdf") is cd.ChangeStatus.CHANGED


# --- registry statuses ------------------------------------------------------


def test_file_returning_after_removal_is_new_even_with_identical_bytes(
    db_path, folder, workspace
):
    """A `removed` row has no chunks behind it any more. Identical bytes
    must still be re-ingested, or the restored file stays unanswerable
    while the report cheerfully calls it Unchanged."""
    path = _write(folder, "policy.pdf", "v1")
    _register(
        db_path,
        workspace.id,
        "policy.pdf",
        cd.compute_fingerprint(path).serialize(),
        status="removed",
    )

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "policy.pdf") is cd.ChangeStatus.NEW


@pytest.mark.parametrize("status", ["failed", "skipped"])
def test_a_file_with_no_derived_data_is_new_even_with_identical_bytes(
    db_path, folder, workspace, status
):
    """Same rule as the `removed` case above, and it was missing until
    ST-17 became the first story to write these statuses.

    A `failed` or `skipped` row has no chunks and no vectors behind it,
    exactly like a `removed` one. Classified UNCHANGED, a corrupted file
    was reported Failed on its first sync and then quietly vanished from
    every later report while still being unanswerable -- so PRD F-02
    criterion 3 held for one run only, and a file the user repaired was
    never picked up. db/schema.sql is signed and has no column to store
    the failure reason on the document row, so re-attempting is the only
    way the per-file report can keep telling the truth about it."""
    path = _write(folder, "broken.pdf", "v1")
    _register(
        db_path,
        workspace.id,
        "broken.pdf",
        cd.compute_fingerprint(path).serialize(),
        status=status,
    )

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "broken.pdf") is cd.ChangeStatus.NEW


def test_an_active_row_with_identical_bytes_is_still_unchanged(
    db_path, folder, workspace
):
    """The other side of the rule above, pinned so that widening
    `_STATUS_WITHOUT_DERIVED_DATA` any further -- to `active`, say --
    cannot pass. Without this, "re-ingest everything, every sync" would
    satisfy the retry tests perfectly."""
    path = _write(folder, "policy.pdf", "v1")
    _register(
        db_path,
        workspace.id,
        "policy.pdf",
        cd.compute_fingerprint(path).serialize(),
        status="active",
    )

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "policy.pdf") is cd.ChangeStatus.UNCHANGED


def test_a_file_whose_type_stopped_being_supported_is_not_reported_removed(
    db_path, folder, workspace, monkeypatch
):
    """The other half of the rule the REMOVED sweep already states.

    "Removed means gone from disk, not 'we had trouble with it'" was
    applied to unreadable files only, and an UNSUPPORTED file is present
    on disk for exactly the same reason: it produced no fingerprint, but
    it is right there. Reported Removed, it got a second report row in
    the same run (Skipped AND Removed) and ST-17 deleted the passages of
    a file the user never touched.

    Reachable by narrowing `supported_document_extensions`, which is a
    supported operator setting -- config.py notes PPTX moving the other
    way for ST-48, so the list is not frozen."""
    _write(folder, "deck.pptx", "slides")
    _register(db_path, workspace.id, "deck.pptx", "sha256:deadbeef:6")
    settings = cd.get_settings()
    narrowed = settings.model_copy(update={"supported_document_extensions": ("pdf",)})
    monkeypatch.setattr(cd, "get_settings", lambda: narrowed)

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert [problem.file_name for problem in report.unsupported] == ["deck.pptx"]
    assert [change.file_name for change in report.changes] == []


def test_already_removed_row_still_absent_is_not_reported_again(db_path, folder, workspace):
    _register(db_path, workspace.id, "gone.pdf", "sha256:deadbeef:5", status="removed")

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert report.changes == []


@pytest.mark.parametrize("status", ["failed", "skipped"])
def test_failed_and_skipped_rows_are_still_removed_when_the_file_disappears(
    db_path, folder, workspace, status
):
    """`failed` and `skipped` rows have no chunks either, but unlike
    `removed` they were never reported as gone. When the file disappears
    the user must still see one Removed row."""
    _register(db_path, workspace.id, "broken.pdf", "sha256:deadbeef:5", status=status)

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert _status_of(report, "broken.pdf") is cd.ChangeStatus.REMOVED


# --- scoping and error handling ---------------------------------------------


def test_detection_never_sees_another_workspaces_documents(db_path, tmp_path):
    hr_folder = tmp_path / "hr"
    hr_folder.mkdir()
    manuals_folder = tmp_path / "manuals"
    manuals_folder.mkdir()

    hr = ws.create_workspace(name="HR", folder_path=str(hr_folder), db_path=db_path)
    manuals = ws.create_workspace(
        name="Manuals", folder_path=str(manuals_folder), db_path=db_path
    )

    _write(hr_folder, "shared-name.pdf", "hr copy")
    _register(db_path, manuals.id, "shared-name.pdf", "sha256:deadbeef:5")

    report = cd.detect_changes(workspace_id=hr.id, db_path=db_path)

    # Scoped correctly, HR has never seen this file: NEW. Leak the Manuals
    # row in and it reads as CHANGED against a fingerprint from another
    # workspace's file (PRD F-01 #1).
    assert _status_of(report, "shared-name.pdf") is cd.ChangeStatus.NEW
    assert report.folder_path == str(hr_folder)


def test_empty_folder_reports_every_registered_document_as_removed(
    db_path, folder, workspace
):
    _register(db_path, workspace.id, "a.pdf", "sha256:aaa:3")
    _register(db_path, workspace.id, "b.pdf", "sha256:bbb:3")

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert {c.file_name for c in report.by_status(cd.ChangeStatus.REMOVED)} == {
        "a.pdf",
        "b.pdf",
    }


def test_missing_folder_raises_instead_of_reporting_everything_removed(
    db_path, folder, workspace
):
    """The dangerous near-miss: an unplugged drive must not be
    indistinguishable from a folder the user emptied. One means "report
    nothing yet"; the other means "delete every chunk in this
    workspace"."""
    path = _write(folder, "policy.pdf", "v1")
    _register(db_path, workspace.id, "policy.pdf", cd.compute_fingerprint(path).serialize())
    path.unlink()
    folder.rmdir()

    with pytest.raises(cd.FolderNotFoundError):
        cd.detect_changes(workspace_id=workspace.id, db_path=db_path)


def test_unknown_workspace_raises_workspace_not_found(db_path):
    with pytest.raises(ws.WorkspaceNotFoundError):
        cd.detect_changes(workspace_id="does-not-exist", db_path=db_path)


def test_detection_writes_nothing_to_the_registry(db_path, folder, workspace):
    """detect_changes decides, it never acts. If it ever starts writing
    the registry itself, ST-17 loses the single place that mutates state
    during a sync and a failed conversion could leave a file marked
    ingested."""
    path = _write(folder, "policy.pdf", "v1")
    _register(db_path, workspace.id, "policy.pdf", cd.compute_fingerprint(path).serialize())
    _write(folder, "fresh.pdf", "new")

    conn = repo.get_connection(db_path)
    try:
        before = [dict(r) for r in repo.list_documents(conn, workspace.id)]
    finally:
        conn.close()

    cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    conn = repo.get_connection(db_path)
    try:
        after = [dict(r) for r in repo.list_documents(conn, workspace.id)]
    finally:
        conn.close()

    assert after == before


# --- unreadable files: PRD F-02 #3, one bad file never blocks the rest ------


def _fail_reads_of(monkeypatch, *file_names: str):
    """Make named files raise UnreadableFileError while staying real files
    on disk.

    This is the one seam in the suite that is patched rather than acted out,
    and the reason is that neither real alternative works portably: chmod
    does not remove an owner's read access on Windows, and replacing the file
    with a directory changes `is_file()`, so `scan_folder` skips it before it
    ever tries to read -- a trap the first version of these tests fell into,
    passing for entirely the wrong reason.

    The chain stays fully covered, because the half this does not exercise is
    exercised elsewhere: `test_unreadable_file_raises_a_domain_error` proves a
    genuine OSError becomes UnreadableFileError against a real filesystem, and
    these tests prove scan_folder collects that error instead of propagating
    it. Patched here is the boundary between the two, not the behaviour."""
    real = cd.compute_fingerprint

    def fake(path):
        if path.name in file_names:
            raise cd.UnreadableFileError(path.name, "permission denied")
        return real(path)

    monkeypatch.setattr(cd, "compute_fingerprint", fake)


def test_one_unreadable_file_does_not_abort_the_scan(folder, monkeypatch):
    """PRD F-02 criterion 3: a file that cannot be processed is reported,
    and every other file completes. Letting UnreadableFileError escape
    scan_folder loses the whole sync over one bad file."""
    _write(folder, "good-a.txt", "fine")
    _write(folder, "bad.txt", "doomed")
    _write(folder, "good-b.txt", "also fine")
    _fail_reads_of(monkeypatch, "bad.txt")

    scan = cd.scan_folder(folder)

    assert set(scan.fingerprints) == {"good-a.txt", "good-b.txt"}
    assert [u.file_name for u in scan.unreadable] == ["bad.txt"]
    assert scan.unreadable[0].reason


def test_unreadable_file_is_reported_separately_from_unsupported(folder, monkeypatch):
    """They map to different sync_item.result values -- Failed vs Skipped --
    so collapsing them into one list would mislabel one of them."""
    _write(folder, "bad.txt", "doomed")
    _write(folder, "installer.exe", "binary")
    _fail_reads_of(monkeypatch, "bad.txt")

    scan = cd.scan_folder(folder)

    assert [u.file_name for u in scan.unreadable] == ["bad.txt"]
    assert [u.file_name for u in scan.unsupported] == ["installer.exe"]


def test_unreadable_registered_file_is_not_reported_as_removed(
    db_path, folder, workspace, monkeypatch
):
    """The dangerous one. An unreadable file is still ON DISK. Reporting it
    Removed makes ST-17 delete the chunks of a document that never went
    anywhere, and the user loses answers from a file they can still see."""
    path = _write(folder, "policy.pdf", "v1")
    _register(db_path, workspace.id, "policy.pdf", cd.compute_fingerprint(path).serialize())
    _fail_reads_of(monkeypatch, "policy.pdf")

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert report.by_status(cd.ChangeStatus.REMOVED) == []
    assert [u.file_name for u in report.unreadable] == ["policy.pdf"]


def test_a_genuinely_deleted_file_is_still_removed_alongside_an_unreadable_one(
    db_path, folder, workspace, monkeypatch
):
    """The other side of the previous test: suppressing REMOVED for
    unreadable files must not suppress it for actually-deleted ones."""
    _write(folder, "unreadable.pdf", "v1")
    deleted = _write(folder, "deleted.pdf", "v1")
    _register(
        db_path,
        workspace.id,
        "unreadable.pdf",
        cd.compute_fingerprint(folder / "unreadable.pdf").serialize(),
    )
    _register(
        db_path, workspace.id, "deleted.pdf", cd.compute_fingerprint(deleted).serialize()
    )
    _fail_reads_of(monkeypatch, "unreadable.pdf")
    deleted.unlink()

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert [c.file_name for c in report.by_status(cd.ChangeStatus.REMOVED)] == ["deleted.pdf"]


# --- the NEW-with-an-existing-row case --------------------------------------


def test_file_returning_after_removal_is_new_but_keeps_its_document_id(
    db_path, folder, workspace
):
    """`document_id` is not simply "None whenever NEW". A file returning
    after removal is NEW yet owns its old registry row, and ST-17 must
    UPDATE that row rather than INSERT -- an INSERT would violate
    UNIQUE (workspace_id, file_name) and fail the sync."""
    path = _write(folder, "policy.pdf", "v1")
    doc_id = _register(
        db_path,
        workspace.id,
        "policy.pdf",
        cd.compute_fingerprint(path).serialize(),
        status="removed",
    )

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)
    returning = report.by_status(cd.ChangeStatus.NEW)[0]

    assert returning.status is cd.ChangeStatus.NEW
    assert returning.document_id == doc_id


def test_a_genuinely_new_file_has_no_document_id(db_path, folder, workspace):
    """The discriminating half: a file with no registry row must still
    report document_id None, or the previous test would pass against an
    implementation that invented an id for everything."""
    _write(folder, "fresh.pdf", "brand new")

    report = cd.detect_changes(workspace_id=workspace.id, db_path=db_path)

    assert report.by_status(cd.ChangeStatus.NEW)[0].document_id is None
