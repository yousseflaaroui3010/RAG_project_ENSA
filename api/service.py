from __future__ import annotations

import dataclasses
import threading
from typing import Any

import recovery
import sync
import workspaces
from db import repo
from ui.conversation import Conversation
from ui.runs import Run


class ResourceNotFoundError(Exception):
    pass


class EmptyWorkspaceError(Exception):
    pass


class SessionBusyError(Exception):
    pass


class ApiService:
    """Product operations shared by the JSON routes without route-body rules."""

    def __init__(self, runtime: Any):
        self.runtime = runtime
        self.sessions: dict[tuple[str, str], Conversation] = {}
        self._session_lock = threading.Lock()

    def list_workspaces(self) -> list[dict[str, Any]]:
        return [
            dataclasses.asdict(item)
            for item in workspaces.list_workspaces(db_path=self.runtime.db_path)
        ]

    def create_workspace(self, *, name: str, folder_path: str, legal_flag: bool) -> dict[str, Any]:
        return dataclasses.asdict(
            workspaces.create_workspace(
                name=name,
                folder_path=folder_path,
                legal_flag=legal_flag,
                db_path=self.runtime.db_path,
            )
        )

    def workspace_detail(self, workspace_id: str) -> dict[str, Any]:
        workspace = workspaces.get_workspace(
            workspace_id=workspace_id, db_path=self.runtime.db_path
        )
        with repo.session(self.runtime.db_path) as conn:
            documents = [dict(row) for row in repo.list_documents(conn, workspace_id)]
        fields = ("id", "file_name", "file_type", "page_count", "status", "last_synced_at")
        return {
            **dataclasses.asdict(workspace),
            "documents": [{field: row[field] for field in fields} for row in documents],
        }

    def update_workspace(
        self, workspace_id: str, *, name: str | None, legal_flag: bool | None
    ) -> dict[str, Any]:
        workspace = workspaces.get_workspace(
            workspace_id=workspace_id, db_path=self.runtime.db_path
        )
        if name is not None:
            workspace = workspaces.rename_workspace(
                workspace_id=workspace_id,
                new_name=name,
                db_path=self.runtime.db_path,
            )
        if legal_flag is not None:
            workspace = workspaces.set_legal_flag(
                workspace_id=workspace_id,
                legal_flag=legal_flag,
                db_path=self.runtime.db_path,
            )
        return dataclasses.asdict(workspace)

    def delete_workspace(self, workspace_id: str) -> None:
        with repo.session(self.runtime.db_path) as conn:
            if repo.get_running_sync_run(conn, workspace_id) is not None:
                raise sync.SyncInProgressError(workspace_id, "running", "unknown")
        with self.runtime.store() as client:
            sync.delete_workspace(
                workspace_id=workspace_id,
                db_path=self.runtime.db_path,
                client=client,
            )

    def start_sync(self, workspace_id: str) -> str:
        claim = sync.claim_sync(workspace_id=workspace_id, db_path=self.runtime.db_path)
        cancel_event = threading.Event()
        self.runtime.sync_cancel_events[workspace_id] = cancel_event

        def work() -> None:
            try:
                with self.runtime.store() as client:
                    report = sync.sync_workspace(
                        workspace_id=workspace_id,
                        db_path=self.runtime.db_path,
                        client=client,
                        cancel_requested=cancel_event.is_set,
                        claim=claim,
                    )
                self.runtime.last_sync_run_id[workspace_id] = report.sync_run_id
            except Exception as exc:
                self.runtime.sync_errors[workspace_id] = str(exc)
                with repo.session(self.runtime.db_path) as conn:
                    recovery.finish_abandoned_sync_run(
                        conn, claim.sync_run_id, finished_at=repo.utc_now()
                    )
            finally:
                if self.runtime.sync_cancel_events.get(workspace_id) is cancel_event:
                    self.runtime.sync_cancel_events.pop(workspace_id, None)

        threading.Thread(target=work, daemon=True, name="sanad-api-sync").start()
        return claim.sync_run_id

    @staticmethod
    def sync_summary(row: Any) -> dict[str, Any]:
        return {
            **dict(row),
            "state": "running" if row["finished_at"] is None else "finished",
        }

    def list_sync_runs(self, workspace_id: str) -> list[dict[str, Any]]:
        workspaces.get_workspace(workspace_id=workspace_id, db_path=self.runtime.db_path)
        with repo.session(self.runtime.db_path) as conn:
            return [self.sync_summary(row) for row in repo.list_sync_runs(conn, workspace_id)]

    def sync_run_detail(self, sync_run_id: str) -> dict[str, Any]:
        with repo.session(self.runtime.db_path) as conn:
            row = repo.get_sync_run(conn, sync_run_id)
            if row is None:
                raise ResourceNotFoundError(sync_run_id)
            items = repo.list_sync_items(conn, sync_run_id)
        return {
            **self.sync_summary(row),
            "items": [
                {"file_name": item["file_name"], "result": item["result"], "reason": item["reason"]}
                for item in items
            ],
        }

    def ask(self, workspace_id: str, *, question: str, session_id: str | None) -> dict[str, Any]:
        workspace = workspaces.get_workspace(
            workspace_id=workspace_id, db_path=self.runtime.db_path
        )
        with repo.session(self.runtime.db_path) as conn:
            if not any(
                row["status"] == "active" for row in repo.list_documents(conn, workspace_id)
            ):
                raise EmptyWorkspaceError(workspace_id)
        with self._session_lock:
            conversation = (
                self.sessions.get((workspace_id, session_id)) if session_id is not None else None
            ) or Conversation(workspace_id=workspace_id, session_id=session_id)
            run = Run(question=question, workspace_id=workspace_id, session_id=session_id)
            if not conversation.begin(run, question):
                raise SessionBusyError(session_id or "new session")
        try:
            with self.runtime.ports() as ports:
                run.execute(ports)
        except Exception as exc:
            run.fail(exc)
        conversation.settle(legal_workspace=workspace.legal_flag)
        answer = run.answer
        if run.error is not None:
            raise run.error
        if answer is None:
            raise RuntimeError("the answering run finished without an answer")
        with self._session_lock:
            self.sessions[(workspace_id, answer.session_id)] = conversation
        return {
            "kind": answer.kind.value,
            "text": answer.text,
            "sources": [dataclasses.asdict(source) for source in answer.sources],
            "searched": list(answer.searched),
            "disclaimer": workspace.legal_flag and answer.kind.value == "answer",
            "refusal": answer.refusal,
            "session_id": answer.session_id,
            "trace_id": answer.trace_id,
        }

    @staticmethod
    def eval_summary(row: Any) -> dict[str, Any]:
        fields = (
            "id",
            "workspace_id",
            "run_at",
            "groundedness",
            "relevancy",
            "refusal_pass",
            "refusal_total",
            "passed",
        )
        result = {field: row[field] for field in fields}
        result["passed"] = bool(result["passed"])
        return result

    def list_eval_runs(self, workspace_id: str) -> list[dict[str, Any]]:
        workspaces.get_workspace(workspace_id=workspace_id, db_path=self.runtime.db_path)
        with repo.session(self.runtime.db_path) as conn:
            return [
                self.eval_summary(row)
                for row in repo.list_eval_runs(conn)
                if row["workspace_id"] == workspace_id
            ]

    def eval_run_detail(self, eval_run_id: str) -> dict[str, Any]:
        with repo.session(self.runtime.db_path) as conn:
            row = repo.get_eval_run(conn, eval_run_id)
            if row is None:
                raise ResourceNotFoundError(eval_run_id)
            results = repo.list_eval_results(conn, eval_run_id)
        fields = ("question_id", "kind", "groundedness", "relevancy", "passed")
        return {
            **self.eval_summary(row),
            "results": [
                {
                    **{field: result[field] for field in fields[:-1]},
                    "passed": bool(result["passed"]),
                }
                for result in results
            ],
        }
