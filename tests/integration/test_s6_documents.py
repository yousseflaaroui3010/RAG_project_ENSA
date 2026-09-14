"""S6 documents through the real app: upload, download, remove.

Real routes, templates, SQLite, embedded Qdrant and `sync.py`; the two
encoders are faked for the same reason every screen test gives. What this
cannot prove is the browser half -- the drop zone and its script -- which
is checked by hand in a real browser and recorded in the build journal.
"""

from __future__ import annotations

import time
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient

import app as app_module
import ui.documents
import vector_store
import workspaces
from app import Runtime, create_app
from config import get_settings
from db import repo
from tests.fake_encoders import install as install_fake_encoders

WAIT = 15
ARTICLE = (
    "Article 1 : Ceci est un texte de demonstration assez long pour etre "
    "decoupe et indexe par la synchronisation, avec plusieurs phrases. " * 8
)


def _wait_for_sync_to_finish(db_path, workspace_id):
    deadline = time.monotonic() + WAIT
    while time.monotonic() < deadline:
        with repo.session(db_path) as conn:
            if repo.get_running_sync_run(conn, workspace_id) is None:
                return
        time.sleep(0.05)
    raise AssertionError("the Sync never finished")


@pytest.fixture
def docs_app(tmp_path, monkeypatch):
    install_fake_encoders(monkeypatch)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "a.txt").write_text(ARTICLE, encoding="utf-8")
    (folder / ".env").write_text("CLOUD_API_KEY=not-a-document", encoding="utf-8")
    with vector_store.open_store(tmp_path / "qdrant") as client:
        runtime = Runtime(db_path=db_path, client=client)
        workspace = workspaces.create_workspace(
            name="HR", folder_path=str(folder), db_path=db_path
        )
        yield TestClient(create_app(runtime)), runtime, workspace, folder, db_path
        _wait_for_sync_to_finish(db_path, workspace.id)


def _upload(client, workspace_id, name, body, **headers):
    return client.post(
        f"/workspaces/{workspace_id}/documents",
        content=body,
        headers={"X-File-Name": quote(name), "Content-Type": "application/octet-stream", **headers},
    )


def test_an_uploaded_file_lands_in_the_workspace_folder(docs_app):
    client, _, workspace, folder, _ = docs_app

    response = _upload(client, workspace.id, "مدونة الشغل.txt", ARTICLE.encode("utf-8"))

    assert response.status_code == 201
    body = response.json()
    assert body["file_name"] == "مدونة الشغل.txt"
    assert body["replaced"] is False
    assert (folder / "مدونة الشغل.txt").read_text(encoding="utf-8") == ARTICLE


def test_the_same_name_again_is_reported_as_replaced(docs_app):
    client, _, workspace, folder, _ = docs_app

    response = _upload(client, workspace.id, "a.txt", b"new content")

    assert response.status_code == 201
    assert response.json()["replaced"] is True
    assert (folder / "a.txt").read_bytes() == b"new content"


@pytest.mark.parametrize(
    ("name", "status"),
    [("../outside.txt", 400), ("..\\outside.txt", 400), ("run.exe", 415), ("", 400)],
)
def test_a_bad_name_is_refused_and_nothing_is_written_anywhere(docs_app, tmp_path, name, status):
    client, _, workspace, folder, _ = docs_app
    before = sorted(p.name for p in tmp_path.rglob("*"))

    response = _upload(client, workspace.id, name, b"payload")

    assert response.status_code == status
    assert response.json()["error"]
    assert sorted(p.name for p in tmp_path.rglob("*")) == before


def test_an_oversize_upload_is_refused_with_413_and_leaves_nothing(docs_app, monkeypatch):
    client, _, workspace, folder, _ = docs_app
    small = get_settings().model_copy(update={"upload_max_bytes": 16})
    monkeypatch.setattr(ui.documents, "get_settings", lambda: small)
    before = sorted(p.name for p in folder.iterdir())

    response = _upload(client, workspace.id, "big.txt", b"x" * 64)

    assert response.status_code == 413
    assert sorted(p.name for p in folder.iterdir()) == before


def test_evidence_only_refuses_uploads_and_hides_the_drop_zone(docs_app, monkeypatch):
    client, _, workspace, folder, _ = docs_app
    locked = get_settings().model_copy(update={"evidence_only": True})
    monkeypatch.setattr(app_module, "get_settings", lambda: locked)

    response = _upload(client, workspace.id, "new.txt", b"payload")
    page = client.get(f"/workspaces?ws={workspace.id}").text

    assert response.status_code == 409
    assert not (folder / "new.txt").exists()
    assert "data-dropzone" not in page


def test_the_workspace_page_offers_a_drop_zone_hidden_until_the_script_runs(docs_app):
    client, _, workspace, _, _ = docs_app

    page = client.get(f"/workspaces?ws={workspace.id}").text

    zone = page.split("data-dropzone")[0].rsplit("<section", 1)[1]
    assert "hidden" in zone, "without the script the drop zone would be a dead control"
    assert f'data-upload-url="/workspaces/{workspace.id}/documents"' in page


def test_download_returns_the_original_bytes_as_an_attachment(docs_app):
    client, _, workspace, folder, _ = docs_app

    response = client.get(f"/workspaces/{workspace.id}/documents/a.txt")

    assert response.status_code == 200
    assert response.content == (folder / "a.txt").read_bytes()
    assert response.headers["content-disposition"].startswith("attachment")
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("name", [".env", "..%5C..%5Csanad.db", "missing.txt"])
def test_download_never_serves_anything_but_a_document_in_the_folder(docs_app, name):
    client, _, workspace, _, _ = docs_app

    response = client.get(f"/workspaces/{workspace.id}/documents/{name}")

    assert response.status_code in {400, 404, 415}
    assert b"CLOUD_API_KEY" not in response.content


def test_after_a_sync_each_present_document_has_download_and_remove_links(docs_app):
    client, runtime, workspace, _, db_path = docs_app
    client.post(f"/workspaces/{workspace.id}/sync")
    _wait_for_sync_to_finish(db_path, workspace.id)

    page = client.get(f"/workspaces?ws={workspace.id}").text

    assert f'href="/workspaces/{workspace.id}/documents/a.txt"' in page
    assert f'href="/workspaces/{workspace.id}/documents/a.txt/remove"' in page
    assert "/documents/.env" not in page, "an unsupported file must not be offered"


def test_removing_asks_first_then_deletes_the_file_and_starts_a_sync(docs_app):
    client, _, workspace, folder, db_path = docs_app

    confirm = client.get(f"/workspaces/{workspace.id}/documents/a.txt/remove")
    assert confirm.status_code == 200
    assert (folder / "a.txt").exists(), "the confirmation page must not delete anything"

    done = client.post(
        f"/workspaces/{workspace.id}/documents/a.txt/remove", follow_redirects=False
    )

    assert done.status_code == 303
    assert "removed=a.txt" in done.headers["location"]
    assert not (folder / "a.txt").exists()
    assert (folder / ".env").exists()
    with repo.session(db_path) as conn:
        assert repo.list_sync_runs(conn, workspace.id), "no Sync was started after removal"


def test_upload_is_behind_the_password_gate(docs_app, monkeypatch):
    _, runtime, workspace, folder, _ = docs_app
    gated = get_settings().model_copy(update={"access_password": "secret"})
    monkeypatch.setattr(app_module, "get_settings", lambda: gated)
    client = TestClient(create_app(runtime))

    response = _upload(client, workspace.id, "sneaky.txt", b"payload")

    assert response.status_code == 401
    assert not (folder / "sneaky.txt").exists()
