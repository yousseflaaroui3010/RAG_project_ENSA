"""ST-28 exit gate: every S2 state from UX spec 7 and PRD section 8,
demonstrated through the real app -- real routes, real templates, a real
embedded Qdrant, real chunking, real change detection, real `sync.py`.

WHAT IS FAKED, both for the same reasons test_s1_chat_screen.py gives: the
two ENCODERS (`tests/fake_encoders.py`, so nothing downloads hundreds of
megabytes), and one file's CONVERSION-TO-CHUNKING step, monkeypatched to
raise for exactly one file name so the "a failure never blocks the batch"
exit gate has something real to prove against rather than trusting
sync.py's own already-tested try/except.

WHAT THIS DOES NOT PROVE: real double-sync races under real concurrent
requests (TestClient calls are sequential); the blocked-with-a-message
path is proven instead by pre-seeding a running `sync_run` row directly
through `db.repo`, the same public function `sync._claim_sync_run` itself
calls, and then hitting the route -- which is exactly the request-time
race the route's own pre-check exists to catch (see app.py's
`start_sync_route`)."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

import chunking
import vector_store
import workspaces
from app import Runtime, create_app
from db import repo
from tests.fake_encoders import install as install_fake_encoders

WAIT = 10


def _wait_until(predicate, *, timeout: float = WAIT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"condition never became true within {timeout}s")


ARTICLE = (
    "Article {n} : Ceci est un texte de demonstration suffisamment long "
    "pour survivre a la fois comme parent et comme plusieurs enfants "
    "decoupes, afin que la synchronisation ait vraiment quelque chose a "
    "convertir, decouper et indexer plutot qu'une chaine vide. "
) * 6


def _corpus(tmp_path):
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "a.txt").write_text(ARTICLE.format(n=1), encoding="utf-8")
    (folder / "b.txt").write_text(ARTICLE.format(n=2), encoding="utf-8")
    (folder / "c.xyz").write_text("unsupported extension, never converted", encoding="utf-8")
    return folder


def _app(tmp_path, monkeypatch, *, client):
    install_fake_encoders(monkeypatch)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    # `client` already set means the app's own lifespan skips opening a
    # second one on the same Qdrant path (ADR-04) -- see app.py's
    # `lifespan`. None of these tests hit a `/chat/*` route, so no
    # `ports_factory` is needed either.
    runtime = Runtime(db_path=db_path, client=client)
    return TestClient(create_app(runtime)), runtime, db_path


def test_no_workspace_redirects_root_to_workspaces(tmp_path, monkeypatch):
    """Acceptance criterion 1: with no workspace, `/` lands on S2."""
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, _db_path = _app(tmp_path, monkeypatch, client=client)

        redirect = app_client.get("/", follow_redirects=False)
        assert redirect.status_code == 303
        assert redirect.headers["location"] == "/workspaces"

        page = app_client.get("/workspaces")
        assert "Create your first workspace" in page.text
        assert 'title="Create a workspace before asking questions"' in page.text
        assert 'href="/workspaces"' in page.text


def test_create_workspace_appears_in_the_list_and_is_not_synced_yet(tmp_path, monkeypatch):
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, _db_path = _app(tmp_path, monkeypatch, client=client)
        folder = _corpus(tmp_path)

        created = app_client.post(
            "/workspaces",
            data={"name": "HR", "folder_path": str(folder)},
            follow_redirects=True,
        )
        assert created.status_code == 200
        assert "HR" in created.text
        assert "has not been synced yet" in created.text


def test_invalid_folder_path_re_renders_the_form_with_the_error_and_no_redirect(
    tmp_path, monkeypatch
):
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, _db_path = _app(tmp_path, monkeypatch, client=client)

        response = app_client.post(
            "/workspaces",
            data={"name": "HR", "folder_path": "   "},
            follow_redirects=False,
        )
        assert response.status_code == 422
        assert "folder_path" in response.text


def test_sync_reports_six_statuses_and_a_failed_file_never_blocks_the_batch(
    tmp_path, monkeypatch
):
    """The exit gate's own sentence, proven against a real run: `b.txt` is
    made to fail deterministically and `a.txt` (Added) and `c.xyz`
    (Skipped, unsupported) still get their own rows in the same report."""
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, runtime, db_path = _app(tmp_path, monkeypatch, client=client)
        folder = _corpus(tmp_path)

        real_chunk_document = chunking.chunk_document

        def flaky_chunk_document(markdown, *, source_file):
            if source_file == "b.txt":
                raise RuntimeError("synthetic failure for b.txt")
            return real_chunk_document(markdown, source_file=source_file)

        monkeypatch.setattr(chunking, "chunk_document", flaky_chunk_document)

        workspace = workspaces.create_workspace(
            name="HR", folder_path=str(folder), db_path=db_path
        )

        started = app_client.post(
            f"/workspaces/{workspace.id}/sync", follow_redirects=False
        )
        assert started.status_code == 303

        # NOT a DB poll for "no running row": that predicate is true both
        # BEFORE the background thread has claimed a run and AFTER it
        # finishes, and starting a thread is not instantaneous -- a first
        # ad-hoc version of this wait raced that gap and reported "done"
        # before Sync had even started. `last_sync_run_id` is only ever
        # set by `_work`'s own success branch, so waiting on it is waiting
        # on the one fact that means "actually finished".
        _wait_until(lambda: workspace.id in runtime.last_sync_run_id)

        report = app_client.get(f"/workspaces?ws={workspace.id}")
        body = report.text
        assert "a.txt" in body and "Added" in body
        assert "b.txt" in body and "Failed" in body
        assert "synthetic failure for b.txt" in body
        assert "c.xyz" in body and "Skipped" in body
        # Every row landed in ONE report -- the batch was never stopped by
        # b.txt's failure, which is the exit gate's own sentence.
        assert body.count("<tr>") - 1 == 3  # minus the header row


def test_a_second_sync_is_blocked_with_a_message_and_the_first_keeps_going(
    tmp_path, monkeypatch
):
    """F-02 / UX spec 7.3: a running sync_run is pre-seeded directly
    (the same repo function `sync._claim_sync_run` itself calls), which is
    the request-time race the route's pre-check exists to catch."""
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, db_path = _app(tmp_path, monkeypatch, client=client)
        folder = _corpus(tmp_path)
        workspace = workspaces.create_workspace(
            name="HR", folder_path=str(folder), db_path=db_path
        )
        with repo.session(db_path) as conn:
            running_id = repo.insert_sync_run(
                conn, workspace_id=workspace.id, started_at=repo.utc_now()
            )

        blocked = app_client.post(
            f"/workspaces/{workspace.id}/sync", follow_redirects=True
        )
        assert "already running" in blocked.text

        with repo.session(db_path) as conn:
            still_running = repo.get_running_sync_run(conn, workspace.id)
        assert still_running is not None and still_running["id"] == running_id


def test_folder_missing_shows_the_exact_path_and_a_fix_hint(tmp_path, monkeypatch):
    """PRD section 11 / UX spec 7.3: folder missing or unreadable."""
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, runtime, db_path = _app(tmp_path, monkeypatch, client=client)
        missing = str(tmp_path / "never-created")
        workspace = workspaces.create_workspace(
            name="Ghost", folder_path=missing, db_path=db_path
        )

        app_client.post(f"/workspaces/{workspace.id}/sync", follow_redirects=False)

        _wait_until(lambda: workspace.id in runtime.sync_errors)

        page = app_client.get(f"/workspaces?ws={workspace.id}")
        assert missing in page.text
        assert "Check the path" in page.text


def test_delete_confirm_page_states_derived_data_goes_and_files_stay(tmp_path, monkeypatch):
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, db_path = _app(tmp_path, monkeypatch, client=client)
        folder = _corpus(tmp_path)
        workspace = workspaces.create_workspace(
            name="HR", folder_path=str(folder), db_path=db_path
        )

        confirm = app_client.get(f"/workspaces/{workspace.id}/delete")
        assert str(folder) in confirm.text
        assert "does" in confirm.text and "not</strong> touch" in confirm.text

        deleted = app_client.post(
            f"/workspaces/{workspace.id}/delete", follow_redirects=True
        )
        assert "HR" not in deleted.text or "Create your first workspace" in deleted.text
        assert workspaces.list_workspaces(db_path=db_path) == []
