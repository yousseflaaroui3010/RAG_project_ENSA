from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Response

import sync
import vector_store
import workspaces
from agent.chat import ChatUnavailableError
from api.models import AskRequest, WorkspaceCreate, WorkspaceUpdate
from api.service import ApiService, EmptyWorkspaceError, ResourceNotFoundError, SessionBusyError
from ui.conversation import redact_secrets

logger = logging.getLogger(__name__)


def error(status: int, code: str, message: str, next_step: str) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"code": code, "message": message, "next_step": next_step},
    )


def build_router(service: ApiService, *, version: str) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.get("/health", tags=["system"], operation_id="healthCheck")
    def health_check():
        return {"status": "ok", "version": version}

    @router.get("/workspaces", tags=["workspaces"], operation_id="listWorkspaces")
    def list_workspaces():
        return service.list_workspaces()

    @router.post(
        "/workspaces", status_code=201, tags=["workspaces"], operation_id="createWorkspace"
    )
    def create_workspace(body: WorkspaceCreate):
        try:
            return service.create_workspace(**body.model_dump())
        except workspaces.DuplicateWorkspaceNameError as exc:
            raise error(409, "NAME_TAKEN", str(exc), "Choose a different workspace name.") from None

    @router.get("/workspaces/{workspace_id}", tags=["workspaces"], operation_id="getWorkspace")
    def get_workspace(workspace_id: str):
        try:
            return service.workspace_detail(workspace_id)
        except workspaces.WorkspaceNotFoundError as exc:
            raise error(
                404, "WORKSPACE_NOT_FOUND", str(exc), "List workspaces and use an existing id."
            ) from None

    @router.patch("/workspaces/{workspace_id}", tags=["workspaces"], operation_id="updateWorkspace")
    def update_workspace(workspace_id: str, body: WorkspaceUpdate):
        try:
            return service.update_workspace(workspace_id, **body.model_dump())
        except workspaces.WorkspaceNotFoundError as exc:
            raise error(
                404, "WORKSPACE_NOT_FOUND", str(exc), "List workspaces and use an existing id."
            ) from None
        except workspaces.DuplicateWorkspaceNameError as exc:
            raise error(409, "NAME_TAKEN", str(exc), "Choose a different workspace name.") from None

    @router.delete(
        "/workspaces/{workspace_id}",
        status_code=204,
        tags=["workspaces"],
        operation_id="deleteWorkspace",
    )
    def delete_workspace(workspace_id: str):
        try:
            service.delete_workspace(workspace_id)
        except workspaces.WorkspaceNotFoundError as exc:
            raise error(
                404, "WORKSPACE_NOT_FOUND", str(exc), "List workspaces and use an existing id."
            ) from None
        except (sync.SyncInProgressError, vector_store.StoreAlreadyOpenError) as exc:
            raise error(
                409, "SYNC_IN_PROGRESS", str(exc), "Wait for the active operation, then retry."
            ) from None
        return Response(status_code=204)

    @router.post(
        "/workspaces/{workspace_id}/sync", status_code=202, tags=["sync"], operation_id="startSync"
    )
    def start_sync(workspace_id: str):
        try:
            return {"sync_run_id": service.start_sync(workspace_id)}
        except workspaces.WorkspaceNotFoundError as exc:
            raise error(
                404, "WORKSPACE_NOT_FOUND", str(exc), "List workspaces and use an existing id."
            ) from None
        except sync.SyncInProgressError as exc:
            raise error(
                409, "SYNC_IN_PROGRESS", str(exc), "Poll the existing sync run until it finishes."
            ) from None
        except sync.EvidenceOnlyError as exc:
            # ESCALATION (docs/journal/DECISIONS.md, ST-05): the contract
            # documents 409 on this operation only for "a sync is already
            # running", not for this reason. 409 is reused rather than
            # inventing an undocumented status, because every other
            # "cannot run this right now" condition on this contract is
            # already a 409 (SYNC_IN_PROGRESS here, INDEX_BUSY on ask); the
            # `code` field is what actually distinguishes the two for a
            # caller, and `Error.code` is documented as free-form.
            raise error(
                409,
                "EVIDENCE_ONLY",
                str(exc),
                "Run Sanad locally to sync documents.",
            ) from None

    @router.get("/workspaces/{workspace_id}/sync-runs", tags=["sync"], operation_id="listSyncRuns")
    def list_sync_runs(workspace_id: str):
        try:
            return service.list_sync_runs(workspace_id)
        except workspaces.WorkspaceNotFoundError as exc:
            raise error(
                404, "WORKSPACE_NOT_FOUND", str(exc), "List workspaces and use an existing id."
            ) from None

    @router.get("/sync-runs/{sync_run_id}", tags=["sync"], operation_id="getSyncRun")
    def get_sync_run(sync_run_id: str):
        try:
            return service.sync_run_detail(sync_run_id)
        except ResourceNotFoundError as exc:
            raise error(
                404, "SYNC_RUN_NOT_FOUND", str(exc), "Use an id returned by the Sync endpoints."
            ) from None

    @router.post("/workspaces/{workspace_id}/ask", tags=["ask"], operation_id="askQuestion")
    def ask_question(workspace_id: str, body: AskRequest):
        try:
            return service.ask(workspace_id, **body.model_dump())
        except workspaces.WorkspaceNotFoundError as exc:
            raise error(
                404, "WORKSPACE_NOT_FOUND", str(exc), "List workspaces and use an existing id."
            ) from None
        except EmptyWorkspaceError:
            raise error(
                409,
                "EMPTY_WORKSPACE",
                "The workspace has no synced content.",
                "Run Sync, then ask again.",
            ) from None
        except SessionBusyError as exc:
            raise error(
                409, "SESSION_BUSY", str(exc), "Wait for the current question to finish."
            ) from None
        except vector_store.StoreAlreadyOpenError:
            # ESCALATION (no documented status fits): another process (the
            # command-line evaluator, or a running Sync) holds the embedded
            # index open. This is a concurrency conflict, not a model
            # failure, so it must not be reported as MODEL_UNREACHABLE --
            # that would send an operator to check API keys for a problem
            # that has nothing to do with the model. 409 is chosen over 503
            # because every other "something else is using this resource
            # right now" condition in this contract (SYNC_IN_PROGRESS on
            # start-sync and on delete) is already a 409; flag for the
            # contract owners if a dedicated status is wanted instead.
            raise error(
                409,
                "INDEX_BUSY",
                "Another Sanad process is using the search index right now.",
                "Wait for the other operation to finish, then retry.",
            ) from None
        except ChatUnavailableError:
            raise error(
                503,
                "MODEL_UNREACHABLE",
                "Sanad could not reach the configured answering model.",
                "Check model settings and retry.",
            ) from None
        except Exception as exc:
            # An unexpected bug (a KeyError, an AttributeError, anything not
            # already named above) must never be reported as a false
            # "model unreachable" -- that hides real defects behind a
            # message that tells the operator to check the wrong thing.
            # Logged (redacted, no traceback -- a provider exception's own
            # text can carry the configured API key) and surfaced as a
            # genuine 500.
            logger.error(
                "unexpected failure answering workspace %s: %s",
                workspace_id,
                redact_secrets(f"{type(exc).__name__}: {exc}"),
            )
            raise error(
                500,
                "INTERNAL_ERROR",
                "Sanad hit an unexpected problem answering this question.",
                "Try again; if it keeps happening, check the server log.",
            ) from None

    @router.get(
        "/workspaces/{workspace_id}/eval-runs", tags=["evaluation"], operation_id="listEvalRuns"
    )
    def list_eval_runs(workspace_id: str):
        try:
            return service.list_eval_runs(workspace_id)
        except workspaces.WorkspaceNotFoundError as exc:
            raise error(
                404, "WORKSPACE_NOT_FOUND", str(exc), "List workspaces and use an existing id."
            ) from None

    @router.get("/eval-runs/{eval_run_id}", tags=["evaluation"], operation_id="getEvalRun")
    def get_eval_run(eval_run_id: str):
        try:
            return service.eval_run_detail(eval_run_id)
        except ResourceNotFoundError as exc:
            raise error(
                404,
                "EVAL_RUN_NOT_FOUND",
                str(exc),
                "Use an id returned by the evaluation endpoints.",
            ) from None

    return router
