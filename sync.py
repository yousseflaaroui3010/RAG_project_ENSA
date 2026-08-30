"""Sanad sync engine (ST-17): architecture section 5.1, end to end.

This is the first module that makes the other five do something. ST-12
decides what changed, ST-13 converts it, ST-14 splits it, ST-15 embeds it,
ST-16 stores it -- and until now nothing called any of them. Everything
here is wiring plus the four rules that only exist once the stages are
joined up:

1. **One report row per file, always.** PRD F-02 and section 5.1's flow
   both end every branch in the report. A file that produces no row is a
   file the user cannot see, so `_run` walks three lists (changes,
   unsupported, unreadable) and each element leaves exactly one row.
2. **One failing file costs one row.** F-02 criterion 3. `convert_file`
   already cannot raise for a bad document, but embedding, chunking and
   the vector write can, so each file's ingest is contained.
3. **Delete before re-indexing, never after.** Section 5.1 puts `DEL` on
   the changed branch for a reason given in `_ingest`.
4. **The run row outlives its own failure.** It is written before the
   folder is scanned and finished in a `finally`, so a sync that dies
   cannot leave a workspace permanently blocked by its own guard.

Ordering, which is the part that is not obvious: the derived stores are
written PARENTS FIRST, THEN VECTORS, the exact mirror of the
vectors-then-parents order `vector_store.delete_document` uses. Both
orders can be interrupted; these two fail the same safe way. A crash
mid-write leaves parent files nothing points at (invisible to search,
overwritten by the next sync) rather than vectors citing a parent file
that does not exist, which is a broken citation served to a user -- the
one failure a sourced-answer product cannot absorb.
"""

from __future__ import annotations

import logging
import threading
from contextlib import ExitStack
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

import change_detection
import chunking
import conversion
import embeddings
import parent_store
import vector_store
import workspaces
from change_detection import ChangeStatus, FileChange
from conversion import ConversionOutcome
from db import repo

logger = logging.getLogger(__name__)


class SyncResult(StrEnum):
    """The six `sync_item.result` values from db/schema.sql.

    Deliberately not the same enum as `change_detection.ChangeStatus`,
    which has four values and stops at "what happened to the bytes".
    These six are what the USER is shown (UX spec section 7.2's file
    table), and three of them -- added, failed, skipped -- are only known
    after conversion has run. Mapping one onto the other is this module's
    job and is the reason both enums exist."""

    ADDED = "added"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    FAILED = "failed"
    REMOVED = "removed"
    SKIPPED = "skipped"


class DocumentStatus(StrEnum):
    """The four `document.status` values from db/schema.sql.

    Sync is the only writer of this column, so the vocabulary lives here.
    `change_detection` READS it and keeps its own private constants;
    `test_sync.py` asserts both against the CHECK constraint in
    db/schema.sql so the three cannot drift apart silently."""

    ACTIVE = "active"
    FAILED = "failed"
    SKIPPED = "skipped"
    REMOVED = "removed"


# Plain language, names what happened and what it means for answers (PRD
# section 11's message principle). UX spec section 7.2 is explicit that
# the reason column carries text for Failed, Skipped AND Removed, so a
# removed file is not allowed the empty reason the other clean outcomes
# get.
REMOVED_REASON = (
    "the file is no longer in the workspace folder, so its passages were "
    "removed from answers"
)

# Appended to a removal that did not fully complete. Never fake success
# (PRD section 11): a deletion that left files behind is reported as such,
# with the next step named. Re-running Sync retries them, which is exactly
# what `vector_store.delete_document` is built to make safe.
UNREADABLE_PARENTS_NOTE = (
    "; {count} stored section file(s) could not be read and were left in "
    "place -- run Sync again to retry them"
)

# Used when a stage after conversion raises. The exception type and message
# are included because the alternative is a user staring at "something went
# wrong" with nothing to paste into a bug report; the full traceback goes
# to the log, never to this string.
UNEXPECTED_FAILURE_REASON = "the file could not be indexed: {detail}"

# Guards the check-and-insert in `_claim_sync_run` only, never a whole
# sync. Two threads reaching the guard together would otherwise both read
# "no run in progress" and both insert one, which is precisely the case
# PRD section 11 says must be blocked. ST-51 runs Sync as a background
# task off a FastAPI request, so this is the very next story's race, not a
# hypothetical one. Held for microseconds: it serialises the claim, it
# does not serialise syncing.
_claim_guard = threading.Lock()


class SyncError(Exception):
    """Base for sync failures, so callers catch this rather than the union
    of what five modules can raise."""


class SyncInProgressError(SyncError):
    """A second Sync was asked for while one is running on this workspace.

    PRD section 11: "Blocked with a message; first run keeps going". The
    running run's id and start time travel with the error because the S2
    screen (UX spec 7.3) has to say which run is still going, and a
    message that just says "busy" leaves the user with nothing to look
    at."""

    def __init__(self, workspace_id: str, sync_run_id: str, started_at: str):
        self.workspace_id = workspace_id
        self.sync_run_id = sync_run_id
        self.started_at = started_at
        super().__init__(
            f"a sync started at {started_at} is still running for workspace "
            f"{workspace_id!r}; it keeps going and this request was not started"
        )


@dataclass(frozen=True)
class SyncItemReport:
    """One row of the per-file report, mirroring `sync_item` in
    db/schema.sql and `SyncItem` in openapi.yaml."""

    file_name: str
    result: SyncResult
    reason: str | None = None
    document_id: str | None = None


@dataclass(frozen=True)
class SyncReport:
    """What one Sync did, mirroring openapi.yaml's `SyncRunDetail`.

    Returned as well as persisted. The rows are already in the registry by
    the time this is built -- each file commits its own -- so this object
    is a convenience for the caller, never the only copy."""

    sync_run_id: str
    workspace_id: str
    started_at: str
    finished_at: str
    items: list[SyncItemReport]

    def count(self, result: SyncResult) -> int:
        return sum(1 for item in self.items if item.result is result)

    @property
    def counts(self) -> dict[SyncResult, int]:
        """All six, including the zeros. openapi.yaml marks every count
        required, so a missing key would be a contract violation, and a
        report that silently omits "failed: 0" reads as if nobody
        looked."""
        return {result: self.count(result) for result in SyncResult}


@dataclass(frozen=True)
class _DocumentWrite:
    """The document-row state one file's outcome implies.

    A value rather than a call so that `_record` can write the document
    row and its sync_item row inside ONE transaction. They have to be
    atomic: a document marked `active` whose report row never landed, or a
    report row pointing at a document that was never updated, are both
    states no later sync can detect or repair."""

    file_type: str
    content_hash: str
    status: DocumentStatus
    page_count: int | None
    last_synced_at: str


def sync_workspace(
    *,
    workspace_id: str,
    db_path: str | Path | None = None,
    client: Any | None = None,
    qdrant_path: str | Path | None = None,
    parent_base_path: str | Path | None = None,
) -> SyncReport:
    """Run one Sync over a workspace and return its per-file report.

    `client` is the open Qdrant client, and passing one is how a caller
    that already holds it obeys ADR-04's single-client rule -- opening a
    second one on the same storage path raises
    `vector_store.StoreAlreadyOpenError`. When it is None this function
    owns the client for the duration, which is what a CLI or a test wants.

    Raises `SyncInProgressError` if this workspace already has an
    unfinished run, `workspaces.WorkspaceNotFoundError` for an unknown id,
    and `change_detection.FolderNotFoundError` when the folder is gone.
    That last one propagates deliberately: PRD section 11 wants the exact
    path and a fix hint shown with nothing partially ingested, and a
    folder-level failure has no file to hang a report row on. The run row
    is still finished before it leaves, so the failure costs a visible
    empty run and never a stuck workspace.
    """
    # Checked before the run row is claimed so an unknown workspace cannot
    # leave a sync_run behind -- and because insert would fail on the
    # foreign key anyway, with sqlite's message instead of ours.
    workspace = workspaces.get_workspace(workspace_id=workspace_id, db_path=db_path)

    started_at = repo.utc_now()
    sync_run_id = _claim_sync_run(
        workspace_id=workspace_id, db_path=db_path, started_at=started_at
    )

    # Collected by reference rather than returned, so that a run which
    # dies part way through still finishes with the counts of the files it
    # did manage. A partial report is evidence; a report of zeros is a
    # lie about work that happened.
    items: list[SyncItemReport] = []
    try:
        with ExitStack() as stack:
            active_client = (
                client
                if client is not None
                else stack.enter_context(vector_store.open_store(qdrant_path))
            )
            _run(
                active_client,
                workspace_id=workspace_id,
                folder=workspace.folder_path,
                sync_run_id=sync_run_id,
                db_path=db_path,
                parent_base_path=parent_base_path,
                items=items,
            )
    finally:
        finished_at = repo.utc_now()
        counts = SyncReport(
            sync_run_id=sync_run_id,
            workspace_id=workspace_id,
            started_at=started_at,
            finished_at=finished_at,
            items=items,
        ).counts
        with repo.session(db_path) as conn:
            repo.finish_sync_run(
                conn,
                sync_run_id=sync_run_id,
                finished_at=finished_at,
                added=counts[SyncResult.ADDED],
                changed=counts[SyncResult.CHANGED],
                unchanged=counts[SyncResult.UNCHANGED],
                failed=counts[SyncResult.FAILED],
                removed=counts[SyncResult.REMOVED],
                skipped=counts[SyncResult.SKIPPED],
            )

    items.sort(key=lambda item: item.file_name)
    return SyncReport(
        sync_run_id=sync_run_id,
        workspace_id=workspace_id,
        started_at=started_at,
        finished_at=finished_at,
        items=items,
    )


def delete_workspace(
    *,
    workspace_id: str,
    db_path: str | Path | None = None,
    client: Any | None = None,
    qdrant_path: str | Path | None = None,
    parent_base_path: str | Path | None = None,
) -> vector_store.StoreDeletion:
    """Delete a workspace and everything derived from it (PRD F-01).

    Lives here rather than in `workspaces.py` for the reason ST-16
    recorded when it left this wiring undone: dropping the derived stores
    needs the Qdrant client, and opening one inside `workspaces.py` would
    put a second client on the storage path and break ADR-04. Sync is the
    module that owns the client, so Sync owns this.

    DERIVED STORES FIRST, registry second, and the order is the safety
    property again. This way round, an interrupted delete leaves a
    registry row whose derived data is already gone -- which looks exactly
    like a workspace that has never been synced, and one Sync repairs it.
    The other way round leaves Qdrant collections and parent directories
    with no registry row naming them, so nothing in the system knows they
    exist and no later run can ever clean them up.

    The user's source folder is not touched; nothing here goes near it."""
    with ExitStack() as stack:
        active_client = (
            client
            if client is not None
            else stack.enter_context(vector_store.open_store(qdrant_path))
        )
        deletion = vector_store.delete_workspace(
            active_client,
            workspace_id=workspace_id,
            parent_base_path=parent_base_path,
        )
    workspaces.delete_workspace(workspace_id=workspace_id, db_path=db_path)
    return deletion


def _claim_sync_run(
    *, workspace_id: str, db_path: str | Path | None, started_at: str
) -> str:
    """Refuse a second concurrent Sync, or claim the run row.

    The row is written BEFORE the folder scan, so the in-progress window
    covers the whole run. Doing it the other way round would leave the
    scan -- the slowest part on a 200-page corpus -- unguarded, which is
    the exact window a user double-clicking Sync lands in.

    Known limit, recorded rather than papered over: the guard is the
    unfinished row, so a process KILLED mid-sync (not merely raising --
    `sync_workspace`'s `finally` covers that) leaves a row that blocks
    this workspace until someone finishes it. Clearing it needs an
    operator action that no screen offers yet; it belongs with the S2 sync
    controls in ST-28. A timeout was deliberately not invented here,
    because "how long is too long" is a product decision that story owns
    and a wrong guess silently starts a second sync over live data."""
    with _claim_guard:
        with repo.session(db_path) as conn:
            running = repo.get_running_sync_run(conn, workspace_id)
            if running is not None:
                raise SyncInProgressError(
                    workspace_id=workspace_id,
                    sync_run_id=running["id"],
                    started_at=running["started_at"],
                )
            return repo.insert_sync_run(
                conn, workspace_id=workspace_id, started_at=started_at
            )


def _run(
    client: Any,
    *,
    workspace_id: str,
    folder: str,
    sync_run_id: str,
    db_path: str | Path | None,
    parent_base_path: str | Path | None,
    items: list[SyncItemReport],
) -> None:
    """Walk everything the scan found and leave one report row per file."""
    report = change_detection.detect_changes(
        workspace_id=workspace_id, db_path=db_path
    )

    # Claim the collection for this workspace now, before any file is
    # processed and only once the folder has been scanned successfully.
    #
    # Not redundant with the `ensure_collection` inside `upsert_children`,
    # which is never reached when a run indexes nothing: that function
    # returns early for an empty child list. Without this line, a
    # workspace whose files were ALL skipped or failed ends the sync with
    # no collection, and `vector_store.search` then raises
    # CollectionNotFoundError -- whose whole job is to mean "this
    # workspace has never been synced" as distinct from "the sync ran and
    # found nothing". Those are different things to tell a user, and one
    # of them sends them to fix the wrong problem.
    #
    # It runs after `detect_changes`, so a missing folder still creates
    # nothing (PRD section 11: nothing partially ingested).
    vector_store.ensure_collection(client, workspace_id=workspace_id)

    rows_by_name = _document_rows(workspace_id=workspace_id, db_path=db_path)

    # PRD section 11: "Skipped, listed in the sync report with the reason".
    #
    # THE COMMENT THAT USED TO BE HERE SAID "an unsupported file never gets
    # a document row (it has no fingerprint and nothing was ingested)", and
    # PR #40's own scenario disproves it: a file that was ingested as a
    # supported type and LATER fell outside `supported_document_extensions`
    # -- because an operator narrowed the list -- has a document row, live
    # vectors and parent files. PR #40 stopped that file being reported
    # Removed as well as Skipped. It did not stop the file still answering.
    #
    # So the report said Skipped while the product kept citing it. That is
    # the report lying about the product, which is worse than either state
    # on its own, and F-02's whole contract is that the per-file report is
    # what actually happened.
    #
    # `skipped` is the right document status AND it obliges the deletion,
    # rather than merely permitting it: ST-17 put `skipped` inside
    # `change_detection._STATUS_WITHOUT_DERIVED_DATA`, so a `skipped` row
    # asserts there is no derived data. Marking the row without deleting
    # would make that assertion false and leave orphan vectors no later
    # sync could find. The two go together or neither is correct.
    for unsupported in report.unsupported:
        row = rows_by_name.get(unsupported.file_name)
        items.append(
            _skip_unsupported(
                client,
                workspace_id=workspace_id,
                file_name=unsupported.file_name,
                reason=unsupported.reason,
                row=row,
                sync_run_id=sync_run_id,
                db_path=db_path,
                parent_base_path=parent_base_path,
            )
        )

    # A file present but unreadable. Its document row is deliberately left
    # ALONE: the bytes we could not read this run are not evidence that
    # last run's chunks are wrong, so its existing passages keep answering
    # questions. Marking it `failed` would delete nothing but would tell
    # `change_detection` there is no derived data, which is false.
    #
    # The contrast with the unsupported branch above is the point, and it
    # is not an inconsistency. "We could not read it this run" is a fact
    # about US and says nothing about the file; "this type is no longer
    # processed" is a decision about the FILE that the operator made.
    for unreadable in report.unreadable:
        row = rows_by_name.get(unreadable.file_name)
        items.append(
            _record(
                db_path,
                sync_run_id=sync_run_id,
                workspace_id=workspace_id,
                file_name=unreadable.file_name,
                result=SyncResult.FAILED,
                reason=unreadable.reason,
                document_id=row["id"] if row is not None else None,
            )
        )

    for change in report.changes:
        if change.status is ChangeStatus.UNCHANGED:
            # Not reprocessed and not touched: F-02 criterion 2. The row
            # is the whole outcome.
            items.append(
                _record(
                    db_path,
                    sync_run_id=sync_run_id,
                    workspace_id=workspace_id,
                    file_name=change.file_name,
                    result=SyncResult.UNCHANGED,
                    document_id=change.document_id,
                )
            )
            continue

        if change.status is ChangeStatus.REMOVED:
            items.append(
                _remove(
                    client,
                    workspace_id=workspace_id,
                    change=change,
                    row=rows_by_name.get(change.file_name),
                    sync_run_id=sync_run_id,
                    db_path=db_path,
                    parent_base_path=parent_base_path,
                )
            )
            continue

        try:
            items.append(
                _ingest(
                    client,
                    workspace_id=workspace_id,
                    change=change,
                    folder=folder,
                    sync_run_id=sync_run_id,
                    db_path=db_path,
                    parent_base_path=parent_base_path,
                )
            )
        except Exception as exc:  # noqa: BLE001 - deliberate, see below
            # F-02 criterion 3 outranks a tidy exception list, exactly as
            # it does in `conversion.convert_file`. `convert_file` cannot
            # raise for a bad document, but chunking, embedding and the
            # Qdrant write all can, and one surprise must cost one file
            # rather than the remaining 199. Logged with a full traceback,
            # so containing it is not hiding it.
            #
            # Honest limit: this cannot tell "this document broke the
            # embedder" from "the embedder is down". An infrastructure
            # failure therefore produces one Failed row per file rather
            # than one run-level error. Every row still carries the real
            # reason, so the report is not misleading, only repetitive.
            logger.exception("sync failed on %s", change.file_name)
            items.append(
                _record(
                    db_path,
                    sync_run_id=sync_run_id,
                    workspace_id=workspace_id,
                    file_name=change.file_name,
                    result=SyncResult.FAILED,
                    reason=UNEXPECTED_FAILURE_REASON.format(
                        detail=f"{type(exc).__name__}: {exc}"
                    ),
                    document_id=change.document_id,
                    document=_failure_write(change, DocumentStatus.FAILED),
                )
            )


def _document_rows(
    *, workspace_id: str, db_path: str | Path | None
) -> dict[str, Any]:
    """This workspace's document rows keyed by file name.

    A second read of what `detect_changes` also loaded, because the two
    lists it hands back for problem files carry a name and a reason but no
    document id -- and a report row that cannot point at the document it
    is about is a row the S2 file table cannot link."""
    conn = repo.get_connection(db_path)
    try:
        return {row["file_name"]: row for row in repo.list_documents(conn, workspace_id)}
    finally:
        conn.close()


def _remove(
    client: Any,
    *,
    workspace_id: str,
    change: FileChange,
    row: Any | None,
    sync_run_id: str,
    db_path: str | Path | None,
    parent_base_path: str | Path | None,
) -> SyncItemReport:
    """Delete a gone file's derived data and mark its row removed.

    F-02 criterion 4: "reported as Removed and its passages stop appearing
    in answers". Both stores go in one call, in the order
    `vector_store.delete_document` fixes.

    The row is kept, not deleted. `change_detection` uses `removed` to
    know the file must be re-ingested if it comes back even with identical
    bytes, and deleting the row would also NULL the document_id on every
    past report row that mentioned it (db/schema.sql: ON DELETE SET NULL),
    quietly rewriting history the user may still be reading."""
    deletion = vector_store.delete_document(
        client,
        workspace_id=workspace_id,
        source_file=change.file_name,
        parent_base_path=parent_base_path,
    )
    reason = REMOVED_REASON
    if deletion.unreadable_parent_files:
        reason += UNREADABLE_PARENTS_NOTE.format(
            count=len(deletion.unreadable_parent_files)
        )

    document = None
    if row is not None:
        # The stored fingerprint is carried over unchanged. It describes
        # the file as it last was, which is true and is the only honest
        # value available -- there is nothing on disk left to hash.
        document = _DocumentWrite(
            file_type=row["file_type"],
            content_hash=row["content_hash"],
            status=DocumentStatus.REMOVED,
            page_count=row["page_count"],
            last_synced_at=repo.utc_now(),
        )
    return _record(
        db_path,
        sync_run_id=sync_run_id,
        workspace_id=workspace_id,
        file_name=change.file_name,
        result=SyncResult.REMOVED,
        reason=reason,
        document_id=change.document_id,
        document=document,
    )


def _skip_unsupported(
    client: Any,
    *,
    workspace_id: str,
    file_name: str,
    reason: str,
    row: Any | None,
    sync_run_id: str,
    db_path: str | Path | None,
    parent_base_path: str | Path | None,
) -> SyncItemReport:
    """Report one unsupported file, and stop it answering if it ever did.

    The common case is a file that was never ingested: no row, nothing
    derived, one Skipped report line and nothing else to do. `row` is None
    and this is a single `_record` call.

    The case that had a bug in it is a file that WAS ingested and later
    fell outside `supported_document_extensions`, because an operator
    narrowed the list. That file has a document row, live vectors and
    parent files, so before this function existed the report said Skipped
    while answers kept citing it.

    Deletion happens first and the row is written second, mirroring
    `_remove` and for the same reason: both orders can fail halfway, and
    only this one fails safely. Vectors gone with the row still `active`
    is a file that answers nothing and will be re-examined next sync;
    the row `skipped` with vectors still live is the exact lie this
    function exists to end, made permanent -- no later sync would look at
    a `skipped` row again.
    """
    if row is None:
        return _record(
            db_path,
            sync_run_id=sync_run_id,
            workspace_id=workspace_id,
            file_name=file_name,
            result=SyncResult.SKIPPED,
            reason=reason,
        )

    deletion = vector_store.delete_document(
        client,
        workspace_id=workspace_id,
        source_file=file_name,
        parent_base_path=parent_base_path,
    )
    full_reason = reason
    if deletion.unreadable_parent_files:
        full_reason += UNREADABLE_PARENTS_NOTE.format(
            count=len(deletion.unreadable_parent_files)
        )
    return _record(
        db_path,
        sync_run_id=sync_run_id,
        workspace_id=workspace_id,
        file_name=file_name,
        result=SyncResult.SKIPPED,
        reason=full_reason,
        document_id=row["id"],
        document=_DocumentWrite(
            # Fingerprint carried over unchanged, as `_remove` does: it
            # describes the file as it last was, which is still true.
            file_type=row["file_type"],
            content_hash=row["content_hash"],
            status=DocumentStatus.SKIPPED,
            page_count=row["page_count"],
            last_synced_at=repo.utc_now(),
        ),
    )


def _ingest(
    client: Any,
    *,
    workspace_id: str,
    change: FileChange,
    folder: str,
    sync_run_id: str,
    db_path: str | Path | None,
    parent_base_path: str | Path | None,
) -> SyncItemReport:
    """Convert, chunk, embed and store one new or changed file."""
    # Delete first, unconditionally, and note that this runs BEFORE
    # conversion -- section 5.1's `DEL -> CV` edge, not the other way.
    #
    # Three reasons, and only the first is the obvious one:
    #  - a shrinking document leaves stranded parents. ST-14 predicted it
    #    and ST-16 proved that delete-then-index is what clears them.
    #  - the bytes on disk CHANGED, so the old chunks describe text that
    #    is no longer in the file. Keeping them until the new ones are
    #    ready would mean citing content the user cannot find, which is
    #    worse than briefly having nothing to cite. That is also why a
    #    conversion failure below is allowed to leave the file with no
    #    passages at all.
    #  - it runs for a NEW file too, where there is usually nothing to
    #    delete and the call is cheap. "Usually" is the point: a run that
    #    died after writing vectors but before committing the registry
    #    leaves a file that looks NEW and has stale vectors. This is the
    #    only thing that ever cleans those up.
    vector_store.delete_document(
        client,
        workspace_id=workspace_id,
        source_file=change.file_name,
        parent_base_path=parent_base_path,
    )

    result = conversion.convert_file(Path(folder) / change.file_name)

    if result.outcome is not ConversionOutcome.CONVERTED:
        # FAILED and SKIPPED differ for the user (broken vs nothing to
        # index) and both leave the document with no derived data, which
        # is what the status records.
        status = (
            DocumentStatus.FAILED
            if result.outcome is ConversionOutcome.FAILED
            else DocumentStatus.SKIPPED
        )
        sync_result = (
            SyncResult.FAILED
            if result.outcome is ConversionOutcome.FAILED
            else SyncResult.SKIPPED
        )
        return _record(
            db_path,
            sync_run_id=sync_run_id,
            workspace_id=workspace_id,
            file_name=change.file_name,
            result=sync_result,
            reason=result.reason,
            document_id=change.document_id,
            document=_failure_write(change, status, page_count=result.page_count),
        )

    chunked = chunking.chunk_document(result.markdown, source_file=change.file_name)
    dense_vectors = embeddings.embed_children(chunked.children)

    # Parents before vectors: the mirror of the delete order, for the
    # reason in this module's docstring.
    parent_store.save_parents(
        workspace_id=workspace_id,
        parents=chunked.parents,
        base_path=parent_base_path,
    )
    vector_store.upsert_children(
        client,
        workspace_id=workspace_id,
        children=chunked.children,
        dense_vectors=dense_vectors,
    )

    # NEW means "needs ingesting", not "has no row" -- a file returning
    # after removal is NEW and still owns its row. `_record` decides
    # insert vs update on the document_id, never on the status, because
    # doing it on the status is how UNIQUE (workspace_id, file_name) gets
    # violated (change_detection.FileChange says so in as many words).
    sync_result = (
        SyncResult.ADDED if change.status is ChangeStatus.NEW else SyncResult.CHANGED
    )
    return _record(
        db_path,
        sync_run_id=sync_run_id,
        workspace_id=workspace_id,
        file_name=change.file_name,
        result=sync_result,
        # No reason: UX spec 7.2 keeps the column empty for Added,
        # Changed and Unchanged.
        document_id=change.document_id,
        document=_DocumentWrite(
            file_type=change.file_type or "",
            content_hash=change.fingerprint.serialize(),
            status=DocumentStatus.ACTIVE,
            page_count=result.page_count,
            last_synced_at=repo.utc_now(),
        ),
    )


def _failure_write(
    change: FileChange, status: DocumentStatus, page_count: int | None = None
) -> _DocumentWrite:
    """The document row for a file that reached no derived data.

    The fingerprint is still recorded. That is what lets the NEXT sync see
    the file as UNCHANGED-by-bytes while `_STATUS_WITHOUT_DERIVED_DATA`
    independently forces a retry -- so a file the user has not fixed is
    re-attempted and re-reported, and one they HAVE fixed is caught by the
    hash as well."""
    return _DocumentWrite(
        file_type=change.file_type or "",
        content_hash=change.fingerprint.serialize() if change.fingerprint else "",
        status=status,
        page_count=page_count,
        last_synced_at=repo.utc_now(),
    )


def _record(
    db_path: str | Path | None,
    *,
    sync_run_id: str,
    workspace_id: str,
    file_name: str,
    result: SyncResult,
    reason: str | None = None,
    document_id: str | None = None,
    document: _DocumentWrite | None = None,
) -> SyncItemReport:
    """Write one file's document row and its report row in one
    transaction, and return the report row.

    Committing per file rather than per run is what makes F-02 criterion 3
    true at the registry level as well as in the report: a failure on file
    47 must not roll back the 46 files that already succeeded."""
    with repo.session(db_path) as conn:
        resolved_id = document_id
        if document is not None:
            if resolved_id is None:
                resolved_id = repo.insert_document(
                    conn,
                    workspace_id=workspace_id,
                    file_name=file_name,
                    file_type=document.file_type,
                    content_hash=document.content_hash,
                    page_count=document.page_count,
                    status=document.status,
                    last_synced_at=document.last_synced_at,
                )
            else:
                repo.update_document(
                    conn,
                    document_id=resolved_id,
                    file_type=document.file_type,
                    content_hash=document.content_hash,
                    page_count=document.page_count,
                    status=document.status,
                    last_synced_at=document.last_synced_at,
                )
        repo.insert_sync_item(
            conn,
            sync_run_id=sync_run_id,
            file_name=file_name,
            result=result,
            document_id=resolved_id,
            reason=reason,
        )
    return SyncItemReport(
        file_name=file_name,
        result=result,
        reason=reason,
        document_id=resolved_id,
    )
