"""Sanad content hashing and change detection (ST-12).

Implements the `H{Per file: content hash vs registry}` decision in the
Sync flow (docs/phase2/Sanad_Architecture_v1.0.md section 5.1) and the
change-detection half of PRD F-02: one pass over a workspace folder
classifies every file as new, changed, unchanged or removed so Sync
never reprocesses a file whose bytes did not move.

This module DECIDES, it never ACTS. `detect_changes` is a pure read: it
opens no write transaction, deletes no chunks, converts nothing and
updates no registry row. Conversion is ST-13, chunk deletion and the
registry write are ST-17. Keeping the decision separate from the action
is what makes the four transitions unit-testable without a converter, an
embedder or a vector store existing yet.

Sits above db/repo.py and beside workspaces.py: domain rules here, thin
SQL there, no inline SQL in this file (.claude/rules/backend.md).
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import workspaces
from config import get_settings
from db import repo

# Digest algorithm recorded inside every serialized fingerprint. Stored
# rather than assumed so that changing it later is detectable per row:
# an old row parses, reports a different algorithm, and is re-ingested
# instead of being silently compared across two incompatible digests.
_FINGERPRINT_ALGORITHM = "sha256"

# Field separator for the serialized fingerprint. ':' is safe: it appears
# in neither a hex digest nor a decimal byte count.
_FINGERPRINT_SEPARATOR = ":"
_FINGERPRINT_FIELD_COUNT = 3

# document.status values, per db/schema.sql's CHECK constraint.
#
# These two sets answer two DIFFERENT questions and were one constant until
# ST-17, which is the story that first writes any of these statuses. Sharing
# one set made the two answers agree by accident, and one of them was wrong.
#
# 1. "Is there derived data behind this row?" -- asked of a file that is on
#    disk right now, to decide whether identical bytes still need
#    re-ingesting (`_classify_present_file`). `failed` and `skipped` belong
#    here for exactly the reason `removed` does, and the sentence above is
#    the test: a corrupted PDF and a scanned one both have no chunks and no
#    vectors. Left out, they classified as UNCHANGED forever -- so a broken
#    file silently dropped out of the per-file report after its first sync,
#    was never retried once the user fixed it, and PRD F-02's promise that
#    a corrupted file "is reported as Failed with a plain-language reason"
#    held for one run only. db/schema.sql has no column to store that
#    reason on the document row, so re-attempting is the only way the
#    report can keep telling the truth about it.
_STATUS_REMOVED = "removed"
_STATUS_FAILED = "failed"
_STATUS_SKIPPED = "skipped"
_STATUS_WITHOUT_DERIVED_DATA = frozenset(
    {_STATUS_REMOVED, _STATUS_FAILED, _STATUS_SKIPPED}
)

# 2. "Has this row already been reported Removed?" -- asked of a row whose
#    file is GONE from disk, to decide whether to report it again. Only
#    `removed` qualifies, and widening it would be a real defect in the
#    other direction: a `failed` row whose file the user then deleted would
#    never be reported Removed and would sit in the registry forever,
#    describing a document that is not on disk and cannot be cleared.
_STATUS_ALREADY_REPORTED_REMOVED = frozenset({_STATUS_REMOVED})

# Public: the conversion ladder (ST-13) reports the same reason for the same
# condition, and one shared constant is the only way that stays true. Two
# copies of this string would drift the moment either side is reworded, and
# the user would see two different explanations for one situation.
UNSUPPORTED_TYPE_REASON = "unsupported file type"

# Plain language, and it names the consequence rather than the syscall,
# per PRD section 11's message principle. The user does not need to know
# what `stat` is; they need to know the file was left alone.
UNREADABLE_STAT_REASON = (
    "the file could not be inspected ({error}), so it was left untouched "
    "and its existing passages still answer questions"
)


class ChangeDetectionError(Exception):
    """Base class for change-detection domain errors, so callers catch
    this instead of OSError or sqlite3 exceptions leaking from below."""


class FolderNotFoundError(ChangeDetectionError):
    """Raised when a workspace's `folder_path` does not exist or is not a
    directory. PRD section 8 (S2 error state) requires the exact path in
    the message plus a fix hint, and requires this to be distinguishable
    from "the folder is there and empty" -- an empty folder is a legal
    state that reports every registered document as Removed, whereas an
    unplugged drive must never be allowed to look like that."""

    def __init__(self, folder_path: str | Path):
        self.folder_path = str(folder_path)
        # Plain interpolation, deliberately not `!r`: repr() escapes every
        # backslash, so a Windows path reaches the user as
        # 'C:\\\\Users\\\\...' -- not the "exact path" PRD section 8 asks
        # for, and not something anyone can paste back into a file dialog.
        super().__init__(
            f"workspace folder does not exist or is not a directory: "
            f"{self.folder_path}. Check the path, or reconnect the drive "
            f"if it is on removable or network storage."
        )


class UnreadableFileError(ChangeDetectionError):
    """Raised when a file is listed by the folder scan but its bytes
    cannot be read (permissions, a broken link, a file deleted between
    listing and hashing). Carries the file name so the caller (ST-17) can
    report that one file as Failed with a plain-language reason and keep
    going -- PRD F-02: one failing file never blocks the rest."""

    def __init__(self, file_name: str, reason: str):
        self.file_name = file_name
        self.reason = reason
        super().__init__(f"could not read {file_name!r}: {reason}")


class ChangeStatus(StrEnum):
    """The four transitions ST-12 owns. These are the change-detection
    verdicts, deliberately NOT the six sync_item.result values in
    db/schema.sql: `added`, `failed` and `skipped` are outcomes of
    conversion (ST-13), which has not run yet at this point in the flow.
    ST-17 maps NEW to `added` only once conversion succeeds."""

    NEW = "new"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    REMOVED = "removed"


@dataclass(frozen=True)
class Fingerprint:
    """A file's identity for change detection: digest AND byte size.

    Size is part of the identity, not decoration. It is the collision
    guard the story's exit criterion asks for: two files are treated as
    the same only when both the digest and the byte count match, so a
    digest collision alone cannot make a different file read as
    Unchanged and silently keep stale passages in answers.
    """

    algorithm: str
    hex_digest: str
    size_bytes: int

    def serialize(self) -> str:
        """Render as the single string persisted in `document.content_hash`.

        Both fields live in one column on purpose. The signed reference
        DDL (architecture section 7.3) defines `document` without a size
        column, and docs/phase2/ is write-locked, so widening the table
        would be a deviation from a signed artifact. Packing the guard
        into the existing column keeps the schema exactly as signed and
        loses nothing: the format is documented, parseable and
        round-trips through `parse` (see docs/journal/DECISIONS.md)."""
        return _FINGERPRINT_SEPARATOR.join(
            (self.algorithm, self.hex_digest, str(self.size_bytes))
        )

    @classmethod
    def parse(cls, raw: str | None) -> Fingerprint | None:
        """Inverse of `serialize`, or None when `raw` is not a fingerprint
        this module wrote (NULL, empty, wrong field count, non-numeric
        size, or an unknown algorithm).

        None is not an error, it is "unknown identity", and the caller
        resolves it toward CHANGED -- re-ingesting a file costs one
        conversion, whereas guessing UNCHANGED on an unreadable
        fingerprint would strand stale passages in answers forever. That
        is what makes a future algorithm change safe."""
        if not raw:
            return None
        parts = raw.split(_FINGERPRINT_SEPARATOR)
        if len(parts) != _FINGERPRINT_FIELD_COUNT:
            return None
        algorithm, hex_digest, raw_size = parts
        if algorithm != _FINGERPRINT_ALGORITHM or not hex_digest:
            return None
        try:
            size_bytes = int(raw_size)
        except ValueError:
            return None
        if size_bytes < 0:
            return None
        return cls(algorithm=algorithm, hex_digest=hex_digest, size_bytes=size_bytes)


@dataclass(frozen=True)
class UnsupportedFile:
    """A file present in the folder whose extension is outside PRD F-02's
    V1 set. Carried out of the scan rather than dropped: PRD section 11
    requires an unsupported file to be reported as Skipped with a reason,
    so silently ignoring it would lose a row the user is promised."""

    file_name: str
    reason: str


@dataclass(frozen=True)
class UnreadableFile:
    """A file whose bytes could not be read during the scan (permissions, a
    broken link, a file deleted between listing and hashing).

    Collected rather than raised, because PRD F-02 criterion 3 is explicit:
    a file that cannot be processed is reported as Failed with a
    plain-language reason AND every other file completes. Letting the
    exception escape `scan_folder` would abort the whole sync over one bad
    file -- exactly the behaviour that criterion forbids."""

    file_name: str
    reason: str


@dataclass(frozen=True)
class ScanResult:
    """What one folder scan found: fingerprints for the files Sync can
    process, plus the two kinds it cannot -- unsupported types (reported
    Skipped) and unreadable bytes (reported Failed). They stay in separate
    lists because they map to different sync_item.result values."""

    fingerprints: dict[str, Fingerprint]
    unsupported: list[UnsupportedFile]
    unreadable: list[UnreadableFile]


@dataclass(frozen=True)
class FileChange:
    """One file's verdict. `fingerprint` is the freshly computed identity
    for a file on disk, and None for a REMOVED file (there is nothing
    left to hash).

    `document_id` is the registry row this file already has, or None when
    it has none. Note it is NOT simply "None whenever the status is NEW":
    a file returning after removal is NEW (its chunks were deleted, so it
    must be re-ingested) yet still owns its old row. ST-17 must UPDATE
    that row rather than INSERT, or it violates
    UNIQUE (workspace_id, file_name) in db/schema.sql. Treat "NEW with a
    document_id" as "re-ingest into the existing row"."""

    file_name: str
    status: ChangeStatus
    fingerprint: Fingerprint | None = None
    document_id: str | None = None
    file_type: str | None = None


@dataclass(frozen=True)
class ChangeReport:
    """Everything one detection pass concluded about a workspace folder."""

    workspace_id: str
    folder_path: str
    changes: list[FileChange]
    unsupported: list[UnsupportedFile]
    unreadable: list[UnreadableFile]

    def by_status(self, status: ChangeStatus) -> list[FileChange]:
        return [change for change in self.changes if change.status is status]


def file_type(path: Path) -> str:
    """Extension without the dot, lower-cased, matching the values
    db/schema.sql stores in `document.file_type`.

    Public because the conversion ladder (ST-13) dispatches on exactly
    this value: if the two modules derived a file's type by different
    rules, a file could be scanned as one type and converted as another."""
    return path.suffix.lstrip(".").lower()


def is_supported(path: Path) -> bool:
    """Whether Sync processes this file type in V1 (PRD F-02). The list
    lives in config.py; never hardcode it a second time."""
    return file_type(path) in get_settings().supported_document_extensions


def compute_fingerprint(path: Path) -> Fingerprint:
    """Hash one file's bytes and pair the digest with its byte size.

    Reads incrementally in `hash_read_chunk_bytes` blocks so a large PDF
    never lands in memory whole. Size is counted from the bytes actually
    read, not from `stat()`, so the two halves of the fingerprint can
    never disagree about the same file: a `stat()` taken before the read
    could describe a different version of a file being written
    concurrently.

    Raises UnreadableFileError (never a bare OSError) carrying the file
    name, so `scan_folder` can turn it into one reportable per-file
    failure. Note that raising is only half the contract: `scan_folder`
    must actually catch it, or PRD F-02 criterion 3 ("every other file
    completes") is broken by a single unreadable file."""
    digest = hashlib.new(_FINGERPRINT_ALGORITHM)
    size_bytes = 0
    chunk_size = get_settings().hash_read_chunk_bytes
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
                size_bytes += len(chunk)
    except OSError as exc:
        raise UnreadableFileError(path.name, exc.strerror or str(exc)) from exc
    return Fingerprint(
        algorithm=_FINGERPRINT_ALGORITHM,
        hex_digest=digest.hexdigest(),
        size_bytes=size_bytes,
    )


def scan_folder(folder: str | Path) -> ScanResult:
    """Fingerprint every supported file directly inside `folder`.

    Not recursive: a workspace is one folder of documents (PRD F-01), and
    silently walking into subfolders would ingest content the user never
    pointed at. Subdirectories are skipped entirely rather than reported
    as unsupported -- a folder is not a document the user expected to
    see in a file report.

    Files are keyed by name, which is exactly the uniqueness rule the
    registry enforces (db/schema.sql: UNIQUE (workspace_id, file_name)).

    One unreadable file is collected into `unreadable`, never raised: PRD
    F-02 criterion 3 requires the other files to complete. A whole missing
    FOLDER is the opposite case and does raise FolderNotFoundError, so a
    disconnected drive can never be mistaken for a folder emptied by the
    user -- that mistake would report every document as Removed and
    delete every chunk in the workspace."""
    resolved = Path(folder)
    if not resolved.is_dir():
        raise FolderNotFoundError(resolved)

    fingerprints: dict[str, Fingerprint] = {}
    unsupported: list[UnsupportedFile] = []
    unreadable: list[UnreadableFile] = []
    for entry in sorted(resolved.iterdir()):
        # `Path.is_file()` SWALLOWS ONLY SOME ERRORS, and the difference is
        # the whole point. Read its source before changing this: it catches
        # OSError, then RE-RAISES unless the errno is in
        # `pathlib._IGNORED_ERRNOS` = (ENOENT, ENOTDIR, EBADF, ELOOP).
        # EACCES is not in that tuple.
        #
        # So a permission-denied file does NOT quietly return False. It
        # raises PermissionError straight out of `scan_folder`, and every
        # other file in the workspace goes unindexed -- the exact outcome
        # PRD F-02 criterion 3 forbids, "one broken file costs one row and
        # the batch finishes". One locked file killed the whole sync.
        #
        # The errors it DOES swallow are the right ones to swallow: ENOENT
        # means the file really was deleted between `iterdir` and here, and
        # letting that fall through to the REMOVED sweep is correct, because
        # it genuinely is removed.
        #
        # Found by the ST-12 review pass hunting for the shape PR #40 fixed
        # elsewhere. "Removed" has one meaning in this module -- gone from
        # disk -- and "we were not allowed to look" is never that.
        try:
            is_file = entry.is_file()
        except OSError as exc:
            unreadable.append(
                UnreadableFile(
                    file_name=entry.name,
                    reason=UNREADABLE_STAT_REASON.format(error=exc.strerror or exc),
                )
            )
            continue
        if not is_file:
            continue
        if not is_supported(entry):
            unsupported.append(
                UnsupportedFile(file_name=entry.name, reason=UNSUPPORTED_TYPE_REASON)
            )
            continue
        try:
            fingerprints[entry.name] = compute_fingerprint(entry)
        except UnreadableFileError as exc:
            unreadable.append(UnreadableFile(file_name=exc.file_name, reason=exc.reason))
    return ScanResult(
        fingerprints=fingerprints, unsupported=unsupported, unreadable=unreadable
    )


def _classify_present_file(row: sqlite3.Row | None, fingerprint: Fingerprint) -> ChangeStatus:
    """Verdict for a file that exists on disk right now.

    Three ways to be NEW rather than UNCHANGED, and the last two are the
    ones a naive hash comparison gets wrong:
      - no registry row at all;
      - a row whose status leaves no derived data behind it (`removed`,
        `failed` or `skipped` -- see `_STATUS_WITHOUT_DERIVED_DATA`), so
        identical bytes still need re-ingesting or the file would stay
        unanswerable forever AND drop out of the per-file report;
      - a row whose stored fingerprint cannot be parsed, which is
        resolved toward reprocessing (see `Fingerprint.parse`).

    Otherwise the comparison is on the whole fingerprint -- digest AND
    size -- so a digest collision alone cannot produce UNCHANGED."""
    if row is None:
        return ChangeStatus.NEW
    if row["status"] in _STATUS_WITHOUT_DERIVED_DATA:
        return ChangeStatus.NEW
    stored = Fingerprint.parse(row["content_hash"])
    if stored is None:
        return ChangeStatus.CHANGED
    return ChangeStatus.UNCHANGED if stored == fingerprint else ChangeStatus.CHANGED


def detect_changes(
    *, workspace_id: str, db_path: str | Path | None = None
) -> ChangeReport:
    """Classify every file in a workspace's folder against its registry.

    The folder comes from the workspace row, never from a caller
    argument: `workspace.folder_path` is the single source of truth for
    where a workspace's documents live, and letting a caller pass a
    different folder would let one workspace's registry be diffed against
    another's files. Raises WorkspaceNotFoundError for an unknown id and
    FolderNotFoundError for a missing folder.

    Read-only, and deliberately so: it opens no write transaction, so it
    can never leave the registry half-updated, and ST-17 stays the single
    place that mutates state during a sync.

    A registry row already marked `removed` and still absent from disk
    produces no FileChange at all. It was reported Removed once, its
    chunks are already gone, and re-reporting it on every subsequent sync
    would put a permanent phantom row in the user's file report."""
    workspace = workspaces.get_workspace(workspace_id=workspace_id, db_path=db_path)
    scan = scan_folder(workspace.folder_path)

    conn = repo.get_connection(db_path)
    try:
        rows = {row["file_name"]: row for row in repo.list_documents(conn, workspace_id)}
    finally:
        conn.close()

    changes: list[FileChange] = []
    for file_name, fingerprint in scan.fingerprints.items():
        row = rows.get(file_name)
        changes.append(
            FileChange(
                file_name=file_name,
                status=_classify_present_file(row, fingerprint),
                fingerprint=fingerprint,
                document_id=row["id"] if row is not None else None,
                file_type=file_type(Path(file_name)),
            )
        )

    # Names that are on disk but produced no fingerprint. They must be
    # excluded from the REMOVED sweep below: a file we merely failed to READ
    # is still present, and calling it Removed would make ST-17 delete the
    # chunks of a document that never went anywhere. Removed means gone from
    # disk, not "we had trouble with it".
    #
    # BOTH problem lists belong here, and only `unreadable` was covered
    # until the ST-17 review pass. An UNSUPPORTED file is present on disk
    # for exactly the same reason -- it produced no fingerprint, but it is
    # right there -- so a file already carrying a document row that later
    # falls outside `supported_document_extensions` was reported Skipped
    # AND Removed in the SAME run: two report rows for one file, breaking
    # sync.py's "one row per file" rule, with the Removed branch deleting
    # the passages of a file the user never touched while the Skipped row
    # said nothing had happened to it.
    present_but_unhashed = {
        problem.file_name
        for problem in (*scan.unreadable, *scan.unsupported)
    }

    for file_name, row in rows.items():
        if file_name in scan.fingerprints or file_name in present_but_unhashed:
            continue
        if row["status"] in _STATUS_ALREADY_REPORTED_REMOVED:
            continue
        changes.append(
            FileChange(
                file_name=file_name,
                status=ChangeStatus.REMOVED,
                document_id=row["id"],
                file_type=row["file_type"],
            )
        )

    changes.sort(key=lambda change: change.file_name)
    return ChangeReport(
        workspace_id=workspace_id,
        folder_path=workspace.folder_path,
        changes=changes,
        unsupported=scan.unsupported,
        unreadable=scan.unreadable,
    )
