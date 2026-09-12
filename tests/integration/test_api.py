from __future__ import annotations

import contextlib
import threading
import time

import yaml
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

import sync
import vector_store
from agent.ports import AgentPorts
from api.routes import build_router
from api.service import ApiService
from app import APP_VERSION, OPENAPI_CONTRACT, Runtime, create_app
from db import repo
from sync import SyncReport
from vector_store import SearchHit


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


def api(tmp_path, ports_factory=ports):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    store_context = vector_store.open_store(tmp_path / "qdrant")
    client = store_context.__enter__()
    runtime = Runtime(ports_factory=ports_factory, db_path=db_path, client=client)
    return TestClient(create_app(runtime)), db_path, store_context


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
        contract = yaml.safe_load(OPENAPI_CONTRACT.read_text(encoding="utf-8"))
        assert client.get("/openapi.json").json() == contract
    finally:
        store.__exit__(None, None, None)


def test_actual_route_inventory_matches_the_signed_contract(tmp_path):
    client, _db_path, store = api(tmp_path)
    try:
        contract = yaml.safe_load(OPENAPI_CONTRACT.read_text(encoding="utf-8"))
        expected = {
            (path, method.upper(), operation["operationId"], int(success_code))
            for path, path_item in contract["paths"].items()
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
            raise RuntimeError(
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
    client = TestClient(create_app(runtime))
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
