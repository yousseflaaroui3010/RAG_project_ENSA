from __future__ import annotations

import contextlib
import dataclasses
import logging
import threading
import time

import yaml
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import sync
import ui.conversation
import vector_store
from agent.chat import ChatUnavailableError
from agent.ports import AgentPorts
from api.routes import build_router
from api.service import ApiService
from app import APP_VERSION, OPENAPI_CONTRACT, Runtime, create_app
from config import get_settings
from db import repo
from sync import SyncReport
from tests.integration.contract import ContractClient
from vector_store import SearchHit

CONTRACT = yaml.safe_load(OPENAPI_CONTRACT.read_text(encoding="utf-8"))


def ports() -> AgentPorts:
    hit = SearchHit(
        parent_id="p1",
        source_file="guide.txt",
        section_label="Section 1",
        chunk_text="The trial lasts three months.",
        score=1.0,
    )
    return AgentPorts(
        summarize=lambda _history: "",
        clarify=lambda _question, _summary: None,
        rewrite=lambda question, _summary: (question,),
        retrieve=lambda _workspace, _query: (hit,),
        grade=lambda _question, _passages: True,
        reword=lambda _question, previous, _attempt: previous,
        fetch_parents=lambda _workspace, parent_ids: {
            parent_id: "The trial lasts three months." for parent_id in parent_ids
        },
        write_answer=lambda _question, _passages, _parents: "Three months.",
    )


def api(tmp_path, ports_factory=ports, *, contract_checked=True):
    """Build a TestClient wired to a fresh app.

    `contract_checked=True` (the default) returns a `ContractClient`, which
    validates every `/api/v1` response it receives against
    docs/phase2/openapi.yaml as it comes back -- see tests/integration/
    contract.py. That makes every test built on this helper a contract
    test automatically, with no per-call changes. Pass `False` only for a
    test that deliberately exercises an UNDOCUMENTED response (a genuine
    server bug surfacing as a 500 the contract does not list), so that
    proving the bug behaviour is not itself flagged as a contract
    violation."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    store_context = vector_store.open_store(tmp_path / "qdrant")
    client = store_context.__enter__()
    runtime = Runtime(ports_factory=ports_factory, db_path=db_path, client=client)
    app = create_app(runtime)
    test_client = (
        ContractClient(app, contract=CONTRACT) if contract_checked else TestClient(app)
    )
    return test_client, db_path, store_context


def create_workspace(client, tmp_path, name="HR"):
    response = client.post(
        "/api/v1/workspaces",
        json={"name": name, "folder_path": str(tmp_path), "legal_flag": True},
    )
    assert response.status_code == 201
    return response.json()


def test_contract_health_and_docs_are_live(tmp_path):
    client, _db_path, store = api(tmp_path)
    try:
        assert client.get("/api/v1/health").json() == {
            "status": "ok",
            "version": "0.1.0",
        }
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").json() == CONTRACT
    finally:
        store.__exit__(None, None, None)


def test_actual_route_inventory_matches_the_signed_contract(tmp_path):
    client, _db_path, store = api(tmp_path)
    try:
        expected = {
            (path, method.upper(), operation["operationId"], int(success_code))
            for path, path_item in CONTRACT["paths"].items()
            for method, operation in path_item.items()
            if method in {"get", "post", "patch", "delete"}
            for success_code in operation["responses"]
            if success_code.startswith("2")
        }
        router = build_router(ApiService(client.app.state.runtime), version=APP_VERSION)
        actual = {
            (route.path, method, route.operation_id, route.status_code or 200)
            for route in router.routes
            if isinstance(route, APIRoute) and route.path.startswith("/api/v1")
            for method in route.methods
            if method not in {"HEAD", "OPTIONS"}
        }

        assert actual == expected
    finally:
        store.__exit__(None, None, None)


def test_workspace_crud_and_direct_error_shape(tmp_path):
    client, _db_path, store = api(tmp_path)
    try:
        workspace = create_workspace(client, tmp_path)
        assert client.get("/api/v1/workspaces").json()[0]["name"] == "HR"
        detail = client.get(f"/api/v1/workspaces/{workspace['id']}").json()
        assert detail["documents"] == []
        updated = client.patch(
            f"/api/v1/workspaces/{workspace['id']}",
            json={"name": "People", "legal_flag": False},
        )
        assert updated.json()["name"] == "People"
        assert updated.json()["legal_flag"] is False

        duplicate = client.post(
            "/api/v1/workspaces",
            json={"name": "People", "folder_path": str(tmp_path)},
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "NAME_TAKEN"

        assert client.delete(f"/api/v1/workspaces/{workspace['id']}").status_code == 204
        missing = client.get(f"/api/v1/workspaces/{workspace['id']}")
        assert missing.status_code == 404
        assert set(missing.json()) == {"code", "message", "next_step"}
    finally:
        store.__exit__(None, None, None)


def test_request_validation_is_strict_and_does_not_echo_input(tmp_path):
    client, _db_path, store = api(tmp_path)
    try:
        bad_boolean = client.post(
            "/api/v1/workspaces",
            json={
                "name": "HR",
                "folder_path": str(tmp_path),
                "legal_flag": "false",
            },
        )
        assert bad_boolean.status_code == 422

        missing_folder = client.post(
            "/api/v1/workspaces",
            json={"name": "Missing", "folder_path": str(tmp_path / "missing")},
        )
        assert missing_folder.status_code == 422

        # Sev3 fix: "." used to be accepted and silently resolved to the
        # SERVER's own working directory, never the caller's intended
        # folder. The contract's Workspace.folder_path is documented as
        # absolute, so a relative path is now rejected outright.
        relative_folder = client.post(
            "/api/v1/workspaces",
            json={"name": "Relative", "folder_path": "."},
        )
        assert relative_folder.status_code == 422

        workspace = create_workspace(client, tmp_path)
        null_update = client.patch(
            f"/api/v1/workspaces/{workspace['id']}", json={"name": None}
        )
        assert null_update.status_code == 422

        private_input = "private-question-" * 200
        too_long = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask",
            json={"question": private_input},
        )
        assert too_long.status_code == 422
        assert private_input not in too_long.text
        assert all(
            set(item) == {"loc", "msg", "type"}
            for item in too_long.json()["detail"]
        )
    finally:
        store.__exit__(None, None, None)


def test_ask_returns_the_signed_answer_shape_and_empty_workspace_is_409(tmp_path):
    client, db_path, store = api(tmp_path)
    try:
        workspace = create_workspace(client, tmp_path)
        empty = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask", json={"question": "Trial?"}
        )
        assert empty.status_code == 409
        assert empty.json()["code"] == "EMPTY_WORKSPACE"

        with repo.session(db_path) as conn:
            repo.insert_document(
                conn,
                workspace_id=workspace["id"],
                file_name="guide.txt",
                file_type="txt",
                content_hash="sha256:" + "0" * 64 + ":1",
                status="active",
            )
        answer = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask", json={"question": "Trial?"}
        )
        assert answer.status_code == 200
        body = answer.json()
        assert set(body) == {
            "kind",
            "text",
            "sources",
            "searched",
            "disclaimer",
            "refusal",
            "session_id",
            "trace_id",
        }
        assert body["kind"] == "answer"
        assert body["sources"] == [{"file_name": "guide.txt", "section_label": "Section 1"}]
        assert body["disclaimer"] is True
    finally:
        store.__exit__(None, None, None)


def test_model_failure_hides_secrets_and_releases_the_session_for_retry(tmp_path):
    state = {"fail": False}
    secret = "api-secret-that-must-not-leak"

    def changing_ports():
        if state["fail"]:
            # ChatUnavailableError specifically, not a bare RuntimeError:
            # routes.py now maps ONLY this (the real "provider/model
            # unusable" domain error) to 503 MODEL_UNREACHABLE. Anything
            # else is an unexpected bug and becomes a logged 500 instead
            # (see test_ask_unexpected_bug_is_logged_and_returned_as_500).
            raise ChatUnavailableError(
                f"provider request failed at https://example.test?key={secret}"
            )
        return ports()

    client, db_path, store = api(tmp_path, changing_ports)
    try:
        workspace = create_workspace(client, tmp_path)
        with repo.session(db_path) as conn:
            repo.insert_document(
                conn,
                workspace_id=workspace["id"],
                file_name="guide.txt",
                file_type="txt",
                content_hash="sha256:" + "0" * 64 + ":1",
                status="active",
            )
        first = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask",
            json={"question": "Trial?"},
        ).json()

        state["fail"] = True
        failed = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask",
            json={"question": "Again?", "session_id": first["session_id"]},
        )

        assert failed.status_code == 503
        assert failed.json()["code"] == "MODEL_UNREACHABLE"
        assert secret not in failed.text

        state["fail"] = False
        retried = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask",
            json={"question": "Retry?", "session_id": first["session_id"]},
        )
        assert retried.status_code == 200
    finally:
        store.__exit__(None, None, None)


def test_sync_store_failure_finishes_the_claimed_run(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    runtime = Runtime(ports_factory=ports, db_path=db_path)

    @contextlib.contextmanager
    def broken_store():
        raise RuntimeError("store could not open")
        yield

    runtime.store = broken_store
    client = ContractClient(create_app(runtime), contract=CONTRACT)
    workspace = create_workspace(client, tmp_path)

    accepted = client.post(f"/api/v1/workspaces/{workspace['id']}/sync")
    sync_run_id = accepted.json()["sync_run_id"]
    for _ in range(100):
        detail = client.get(f"/api/v1/sync-runs/{sync_run_id}").json()
        if detail["state"] == "finished":
            break
        time.sleep(0.01)

    assert accepted.status_code == 202
    assert detail["state"] == "finished"


def test_ask_unknown_workspace_and_second_sync_use_signed_errors(tmp_path, monkeypatch):
    client, _db_path, store = api(tmp_path)
    started = threading.Event()
    release = threading.Event()

    def blocking_sync(*, workspace_id, db_path, claim, **_kwargs):
        started.set()
        assert release.wait(timeout=5)
        finished_at = repo.utc_now()
        with repo.session(db_path) as conn:
            repo.finish_sync_run(
                conn,
                sync_run_id=claim.sync_run_id,
                finished_at=finished_at,
                added=0,
                changed=0,
                unchanged=0,
                failed=0,
                removed=0,
                skipped=0,
            )
        return SyncReport(
            sync_run_id=claim.sync_run_id,
            workspace_id=workspace_id,
            started_at=claim.started_at,
            finished_at=finished_at,
            items=[],
        )

    try:
        missing = client.post(
            "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/ask",
            json={"question": "Trial?"},
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "WORKSPACE_NOT_FOUND"

        workspace = create_workspace(client, tmp_path)
        monkeypatch.setattr(sync, "sync_workspace", blocking_sync)
        first = client.post(f"/api/v1/workspaces/{workspace['id']}/sync")
        assert first.status_code == 202
        assert started.wait(timeout=2)

        second = client.post(f"/api/v1/workspaces/{workspace['id']}/sync")
        assert second.status_code == 409
        assert second.json()["code"] == "SYNC_IN_PROGRESS"
    finally:
        release.set()
        store.__exit__(None, None, None)


def test_sync_and_evaluation_history_routes(tmp_path, monkeypatch):
    client, db_path, store = api(tmp_path)
    try:
        workspace = create_workspace(client, tmp_path)

        def finish_claimed_sync(*, workspace_id, db_path, claim, **_kwargs):
            finished_at = repo.utc_now()
            with repo.session(db_path) as conn:
                repo.finish_sync_run(
                    conn,
                    sync_run_id=claim.sync_run_id,
                    finished_at=finished_at,
                    added=0,
                    changed=0,
                    unchanged=0,
                    failed=0,
                    removed=0,
                    skipped=0,
                )
            return SyncReport(
                sync_run_id=claim.sync_run_id,
                workspace_id=workspace_id,
                started_at=claim.started_at,
                finished_at=finished_at,
                items=[],
            )

        monkeypatch.setattr(sync, "sync_workspace", finish_claimed_sync)
        accepted = client.post(f"/api/v1/workspaces/{workspace['id']}/sync")
        assert accepted.status_code == 202
        sync_run_id = accepted.json()["sync_run_id"]
        for _ in range(100):
            detail = client.get(f"/api/v1/sync-runs/{sync_run_id}").json()
            if detail["state"] == "finished":
                break
            time.sleep(0.01)
        assert detail["items"] == []
        assert (
            client.get(f"/api/v1/workspaces/{workspace['id']}/sync-runs").json()[0]["id"]
            == sync_run_id
        )

        with repo.session(db_path) as conn:
            eval_id = repo.insert_eval_run(
                conn,
                workspace_id=workspace["id"],
                groundedness=1.0,
                relevancy=1.0,
                refusal_pass=1,
                refusal_total=1,
                passed=True,
            )
            repo.insert_eval_result(
                conn,
                eval_run_id=eval_id,
                question_id="q1",
                kind="in_scope",
                passed=True,
                groundedness=1.0,
                relevancy=1.0,
            )
        assert (
            client.get(f"/api/v1/workspaces/{workspace['id']}/eval-runs").json()[0]["id"] == eval_id
        )
        eval_detail = client.get(f"/api/v1/eval-runs/{eval_id}").json()
        assert eval_detail["results"] == [
            {
                "question_id": "q1",
                "kind": "in_scope",
                "groundedness": 1.0,
                "relevancy": 1.0,
                "passed": True,
            }
        ]
    finally:
        store.__exit__(None, None, None)


def test_workspace_detail_document_entries_carry_every_declared_field(tmp_path):
    """Every existing test that fetches a workspace does so before any
    document exists, so DocumentEntry's own fields (page_count in
    particular, nullable and therefore invisible to a bare `required`
    check) were never validated against a REAL row. This is what makes
    dropping page_count from the response go red."""
    client, db_path, store = api(tmp_path)
    try:
        workspace = create_workspace(client, tmp_path)
        with repo.session(db_path) as conn:
            repo.insert_document(
                conn,
                workspace_id=workspace["id"],
                file_name="guide.txt",
                file_type="txt",
                content_hash="sha256:" + "0" * 64 + ":1",
                status="active",
                page_count=12,
                last_synced_at=repo.utc_now(),
            )
        detail = client.get(f"/api/v1/workspaces/{workspace['id']}").json()
        assert len(detail["documents"]) == 1
        assert detail["documents"][0]["page_count"] == 12
    finally:
        store.__exit__(None, None, None)


def test_sync_run_detail_items_carry_every_declared_field(tmp_path):
    """No other test ever populates a real SyncItem row (every fake sync
    handler in this file returns `items=[]`), so a renamed or dropped
    field on SyncItem was invisible to the suite. This inserts one
    directly, the way a real failed/skipped file would."""
    client, db_path, store = api(tmp_path)
    try:
        workspace = create_workspace(client, tmp_path)
        with repo.session(db_path) as conn:
            sync_run_id = repo.insert_sync_run(
                conn, workspace_id=workspace["id"], started_at=repo.utc_now()
            )
            repo.insert_sync_item(
                conn,
                sync_run_id=sync_run_id,
                file_name="broken.pdf",
                result="failed",
                reason="the file could not be indexed: corrupt PDF",
            )
            repo.finish_sync_run(
                conn,
                sync_run_id=sync_run_id,
                finished_at=repo.utc_now(),
                added=0,
                changed=0,
                unchanged=0,
                failed=1,
                removed=0,
                skipped=0,
            )
        detail = client.get(f"/api/v1/sync-runs/{sync_run_id}").json()
        assert detail["items"] == [
            {
                "file_name": "broken.pdf",
                "result": "failed",
                "reason": "the file could not be indexed: corrupt PDF",
            }
        ]
    finally:
        store.__exit__(None, None, None)


def test_workspace_name_boundary_matches_the_signed_contract(tmp_path):
    """maxLength read from docs/phase2/openapi.yaml itself, not a literal
    copied here -- a mutation raising the config/contract limit (100 -> 500
    or 20) must not be able to fool this test into moving with it."""
    max_length = CONTRACT["components"]["schemas"]["WorkspaceCreate"]["properties"][
        "name"
    ]["maxLength"]
    client, _db_path, store = api(tmp_path)
    try:
        at_limit = client.post(
            "/api/v1/workspaces",
            json={"name": "N" * max_length, "folder_path": str(tmp_path)},
        )
        assert at_limit.status_code == 201

        over_limit = client.post(
            "/api/v1/workspaces",
            json={"name": "N" * (max_length + 1), "folder_path": str(tmp_path)},
        )
        assert over_limit.status_code == 422
    finally:
        store.__exit__(None, None, None)


def test_ask_question_boundary_matches_the_signed_contract(tmp_path):
    max_length = CONTRACT["components"]["schemas"]["AskRequest"]["properties"][
        "question"
    ]["maxLength"]
    client, db_path, store = api(tmp_path)
    try:
        workspace = create_workspace(client, tmp_path)
        with repo.session(db_path) as conn:
            repo.insert_document(
                conn,
                workspace_id=workspace["id"],
                file_name="guide.txt",
                file_type="txt",
                content_hash="sha256:" + "0" * 64 + ":1",
                status="active",
            )

        at_limit = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask",
            json={"question": "a" * max_length},
        )
        assert at_limit.status_code == 200

        over_limit = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask",
            json={"question": "a" * (max_length + 1)},
        )
        assert over_limit.status_code == 422
    finally:
        store.__exit__(None, None, None)


def test_workspace_patch_error_paths_are_signed_errors(tmp_path):
    client, _db_path, store = api(tmp_path)
    try:
        missing = client.patch(
            "/api/v1/workspaces/00000000-0000-0000-0000-000000000000",
            json={"name": "Ghost"},
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "WORKSPACE_NOT_FOUND"

        create_workspace(client, tmp_path, name="Existing")
        second = create_workspace(client, tmp_path, name="Renaming")
        collision = client.patch(
            f"/api/v1/workspaces/{second['id']}",
            json={"name": "Existing"},
        )
        assert collision.status_code == 409
        assert collision.json()["code"] == "NAME_TAKEN"
    finally:
        store.__exit__(None, None, None)


def test_workspace_delete_error_paths_are_signed_errors(tmp_path, monkeypatch):
    client, _db_path, store = api(tmp_path)
    started = threading.Event()
    release = threading.Event()

    def blocking_sync(*, workspace_id, db_path, claim, **_kwargs):
        started.set()
        assert release.wait(timeout=5)
        finished_at = repo.utc_now()
        with repo.session(db_path) as conn:
            repo.finish_sync_run(
                conn,
                sync_run_id=claim.sync_run_id,
                finished_at=finished_at,
                added=0,
                changed=0,
                unchanged=0,
                failed=0,
                removed=0,
                skipped=0,
            )
        return SyncReport(
            sync_run_id=claim.sync_run_id,
            workspace_id=workspace_id,
            started_at=claim.started_at,
            finished_at=finished_at,
            items=[],
        )

    try:
        missing = client.delete("/api/v1/workspaces/00000000-0000-0000-0000-000000000000")
        assert missing.status_code == 404
        assert missing.json()["code"] == "WORKSPACE_NOT_FOUND"

        workspace = create_workspace(client, tmp_path)
        monkeypatch.setattr(sync, "sync_workspace", blocking_sync)
        accepted = client.post(f"/api/v1/workspaces/{workspace['id']}/sync")
        assert accepted.status_code == 202
        assert started.wait(timeout=2)

        blocked = client.delete(f"/api/v1/workspaces/{workspace['id']}")
        assert blocked.status_code == 409
        body = blocked.json()
        assert body["code"] == "SYNC_IN_PROGRESS"
        # Sev3 fix: this used to hardcode "started at unknown" instead of
        # reading the real running sync's own start time.
        assert "unknown" not in body["message"]
        assert workspace["id"] in body["message"]
    finally:
        release.set()
        store.__exit__(None, None, None)


def test_start_sync_unknown_workspace_is_404(tmp_path):
    client, _db_path, store = api(tmp_path)
    try:
        missing = client.post(
            "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/sync"
        )
        assert missing.status_code == 404
        assert missing.json()["code"] == "WORKSPACE_NOT_FOUND"
    finally:
        store.__exit__(None, None, None)


def test_sync_history_and_detail_404_paths(tmp_path):
    client, _db_path, store = api(tmp_path)
    try:
        missing_history = client.get(
            "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/sync-runs"
        )
        assert missing_history.status_code == 404
        assert missing_history.json()["code"] == "WORKSPACE_NOT_FOUND"

        missing_run = client.get(
            "/api/v1/sync-runs/00000000-0000-0000-0000-000000000000"
        )
        assert missing_run.status_code == 404
        assert missing_run.json()["code"] == "SYNC_RUN_NOT_FOUND"
        assert "00000000-0000-0000-0000-000000000000" in missing_run.json()["message"]
    finally:
        store.__exit__(None, None, None)


def test_evaluation_history_and_detail_404_paths(tmp_path):
    client, _db_path, store = api(tmp_path)
    try:
        missing_history = client.get(
            "/api/v1/workspaces/00000000-0000-0000-0000-000000000000/eval-runs"
        )
        assert missing_history.status_code == 404
        assert missing_history.json()["code"] == "WORKSPACE_NOT_FOUND"

        missing_run = client.get(
            "/api/v1/eval-runs/00000000-0000-0000-0000-000000000000"
        )
        assert missing_run.status_code == 404
        assert missing_run.json()["code"] == "EVAL_RUN_NOT_FOUND"
        assert "00000000-0000-0000-0000-000000000000" in missing_run.json()["message"]
    finally:
        store.__exit__(None, None, None)


def test_ask_session_busy_is_409(tmp_path):
    """A second question against the SAME session while the first is still
    running (not two brand-new sessions, which never share a Conversation
    and so never collide) must be refused rather than racing the first run
    to completion -- see ui/conversation.py `Conversation.begin`."""
    entered = threading.Event()
    release = threading.Event()
    release.set()  # the baseline call below must complete, not block

    def blocking_ports():
        base = ports()

        def slow_write_answer(question, passages, parents):
            entered.set()
            assert release.wait(timeout=5)
            return base.write_answer(question, passages, parents)

        return dataclasses.replace(base, write_answer=slow_write_answer)

    client, db_path, store = api(tmp_path, blocking_ports)
    try:
        workspace = create_workspace(client, tmp_path)
        with repo.session(db_path) as conn:
            repo.insert_document(
                conn,
                workspace_id=workspace["id"],
                file_name="guide.txt",
                file_type="txt",
                content_hash="sha256:" + "0" * 64 + ":1",
                status="active",
            )
        first = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask", json={"question": "Trial?"}
        ).json()
        session_id = first["session_id"]

        release.clear()
        entered.clear()
        second_response = {}

        def ask_again():
            second_response["r"] = client.post(
                f"/api/v1/workspaces/{workspace['id']}/ask",
                json={"question": "Second?", "session_id": session_id},
            )

        thread = threading.Thread(target=ask_again)
        thread.start()
        assert entered.wait(timeout=5)

        busy = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask",
            json={"question": "Third?", "session_id": session_id},
        )
        assert busy.status_code == 409
        assert busy.json()["code"] == "SESSION_BUSY"

        release.set()
        thread.join(timeout=5)
        assert second_response["r"].status_code == 200
    finally:
        release.set()
        store.__exit__(None, None, None)


def test_ask_index_busy_is_409_not_a_false_model_unreachable(tmp_path):
    """ESCALATION recorded in the branch report: the contract documents no
    status for 'another process holds the embedded index' on ask, only
    404/409(empty workspace)/422/503(model). 409 with a distinct code is
    used here as the closest fit -- this app's own convention already uses
    409 for every other 'something else is using this resource right now'
    condition (SYNC_IN_PROGRESS on start-sync and on delete). The one
    thing this must NOT do is call it MODEL_UNREACHABLE: that sends an
    operator to check API keys for a problem that has nothing to do with
    the model."""

    def busy_ports():
        raise vector_store.StoreAlreadyOpenError("another process holds this store")

    client, db_path, store = api(tmp_path, busy_ports)
    try:
        workspace = create_workspace(client, tmp_path)
        with repo.session(db_path) as conn:
            repo.insert_document(
                conn,
                workspace_id=workspace["id"],
                file_name="guide.txt",
                file_type="txt",
                content_hash="sha256:" + "0" * 64 + ":1",
                status="active",
            )
        response = client.post(
            f"/api/v1/workspaces/{workspace['id']}/ask", json={"question": "Trial?"}
        )
        assert response.status_code == 409
        assert response.json()["code"] == "INDEX_BUSY"
    finally:
        store.__exit__(None, None, None)


def test_ask_unexpected_bug_is_logged_and_returned_as_500(tmp_path, monkeypatch, caplog):
    """The Sev2 finding this proves: a KeyError-shaped bug used to come
    back as 503 MODEL_UNREACHABLE with nothing logged, which is a real
    defect wearing a false diagnosis. `contract_checked=False` here on
    purpose -- 500 is not a status this operation documents (it is the
    generic "something nobody named broke" fallback), so this test would
    otherwise trip the very check it is proving is not being abused."""
    secret = "sk-should-never-appear-in-a-log-line"
    settings = get_settings().model_copy(update={"cloud_api_key": secret})
    monkeypatch.setattr(ui.conversation, "get_settings", lambda: settings)

    def buggy_ports():
        raise KeyError(f"boom, key={secret}")

    client, db_path, store = api(tmp_path, buggy_ports, contract_checked=False)
    try:
        workspace = create_workspace(client, tmp_path)
        with repo.session(db_path) as conn:
            repo.insert_document(
                conn,
                workspace_id=workspace["id"],
                file_name="guide.txt",
                file_type="txt",
                content_hash="sha256:" + "0" * 64 + ":1",
                status="active",
            )
        with caplog.at_level(logging.ERROR):
            response = client.post(
                f"/api/v1/workspaces/{workspace['id']}/ask", json={"question": "Trial?"}
            )

        assert response.status_code == 500
        assert response.json()["code"] == "INTERNAL_ERROR"
        assert secret not in response.text

        assert caplog.records, "an unexpected bug must be logged, never swallowed silently"
        logged = "\n".join(record.getMessage() for record in caplog.records)
        assert "KeyError" in logged
        assert secret not in logged
    finally:
        store.__exit__(None, None, None)
