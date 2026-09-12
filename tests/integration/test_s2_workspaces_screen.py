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

import contextlib
import threading
import time

import pytest
from fastapi.testclient import TestClient

import chunking
import sync
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
    # The injected client keeps these Sync tests on one embedded store.
    # None of them hits Chat, so no ports factory is needed.
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


def test_a_double_click_is_blocked_even_while_the_first_sync_waits_for_the_index(
    tmp_path, monkeypatch
):
    """Rule-5 review of 57187cf: the run row used to be claimed inside the
    background thread, so while the first Sync waited for the index a
    second click found no running row and started a second Sync. The claim
    now happens in the request. The index is made slow to open here so the
    first Sync is still waiting when the second click lands."""
    with vector_store.open_store(tmp_path / "qdrant") as real:
        install_fake_encoders(monkeypatch)
        db_path = tmp_path / "sanad.db"
        repo.ensure_schema(db_path)
        gate = threading.Event()

        @contextlib.contextmanager
        def slow_open(*_args, **_kwargs):
            gate.wait(WAIT)
            yield real

        monkeypatch.setattr(vector_store, "open_store", slow_open)
        app_client = TestClient(create_app(Runtime(db_path=db_path)))
        workspace = workspaces.create_workspace(
            name="HR", folder_path=str(_corpus(tmp_path)), db_path=db_path
        )

        app_client.post(f"/workspaces/{workspace.id}/sync", follow_redirects=False)
        second = app_client.post(
            f"/workspaces/{workspace.id}/sync", follow_redirects=False
        )

        try:
            assert "sync_blocked=1" in second.headers["location"]
            with repo.session(db_path) as conn:
                assert len(repo.list_sync_runs(conn, workspace.id)) == 1
        finally:
            gate.set()

        def _finished() -> bool:
            with repo.session(db_path) as conn:
                return repo.get_running_sync_run(conn, workspace.id) is None

        _wait_until(_finished)


def test_a_sync_that_cannot_open_the_index_does_not_block_the_next_one(
    tmp_path, monkeypatch
):
    """A claimed run is a promise to finish the row. When the index cannot
    be opened (the command-line evaluator holds it) the Sync never starts,
    and an unfinished row would refuse every later Sync of this workspace."""
    install_fake_encoders(monkeypatch)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)

    def busy_open(*_args, **_kwargs):
        raise vector_store.StoreAlreadyOpenError("the evaluator holds the index")

    monkeypatch.setattr(vector_store, "open_store", busy_open)
    runtime = Runtime(db_path=db_path)
    app_client = TestClient(create_app(runtime))
    workspace = workspaces.create_workspace(
        name="HR", folder_path=str(_corpus(tmp_path)), db_path=db_path
    )

    app_client.post(f"/workspaces/{workspace.id}/sync", follow_redirects=False)
    _wait_until(lambda: workspace.id in runtime.sync_errors)
    _wait_until(lambda: workspace.id not in runtime.sync_cancel_events)

    with repo.session(db_path) as conn:
        assert repo.get_running_sync_run(conn, workspace.id) is None
        (run,) = repo.list_sync_runs(conn, workspace.id)
        assert run["finished_at"] is not None
    page = app_client.get(f"/workspaces?ws={workspace.id}")
    assert "evaluator holds the index" in page.text


def test_chat_shares_the_open_index_instead_of_waiting_for_a_sync(
    tmp_path, monkeypatch
):
    """Rule-5 review of 57187cf: one lock held for a whole Sync made a
    Chat question wait silently behind it. A second operation in the same
    process now shares the open client, and the index closes only after
    the last one ends."""
    settings = vector_store.get_settings().model_copy(
        update={"qdrant_storage_path": str(tmp_path / "qdrant")}
    )
    monkeypatch.setattr(vector_store, "get_settings", lambda: settings)
    runtime = Runtime(db_path=tmp_path / "sanad.db")
    holding, release = threading.Event(), threading.Event()
    seen: dict[str, object] = {}

    def long_sync() -> None:
        with runtime.store() as client:
            seen["sync"] = client
            holding.set()
            release.wait(WAIT)

    def chat() -> None:
        with runtime.store() as client:
            seen["chat"] = client

    sync_thread = threading.Thread(target=long_sync)
    sync_thread.start()
    try:
        assert holding.wait(WAIT)
        chat_thread = threading.Thread(target=chat)
        chat_thread.start()
        chat_thread.join(2)
        assert "chat" in seen, "Chat waited behind the running Sync"
        assert seen["chat"] is seen["sync"]
    finally:
        release.set()
        sync_thread.join(WAIT)

    # Closed after the last user: this process can open the store again.
    with vector_store.open_store():
        pass


def test_delete_is_refused_while_a_sync_of_that_workspace_runs(tmp_path, monkeypatch):
    """Review of d790e05: with the index shared, a delete no longer waits
    behind a running Sync, and the Sync's next file would re-create the
    dropped collection with no registry row to name it."""
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, db_path = _app(tmp_path, monkeypatch, client=client)
        workspace = workspaces.create_workspace(
            name="Busy", folder_path=str(_corpus(tmp_path)), db_path=db_path
        )
        with repo.session(db_path) as conn:
            repo.insert_sync_run(
                conn, workspace_id=workspace.id, started_at=repo.utc_now()
            )

        response = app_client.post(f"/workspaces/{workspace.id}/delete")

        assert response.status_code == 409
        assert "while a Sync of it is running" in response.text
        assert workspaces.get_workspace(workspace_id=workspace.id, db_path=db_path)


def test_a_failure_to_close_an_unstarted_run_is_logged_not_raised(
    tmp_path, caplog
):
    runtime = Runtime(db_path=tmp_path / "sanad.db")

    def broken(_claim):
        raise RuntimeError("database is locked")

    runtime._finish_unstarted = broken
    claim = sync.SyncClaim(sync_run_id="run-1", workspace_id="ws-1", started_at="t")

    runtime._finish_unstarted_logged(claim)

    assert "could not finish unstarted sync run run-1" in caplog.text


def test_running_sync_offers_cancel_and_the_route_sets_its_event(tmp_path, monkeypatch):
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, runtime, db_path = _app(tmp_path, monkeypatch, client=client)
        workspace = workspaces.create_workspace(
            name="Cancelable", folder_path=str(tmp_path), db_path=db_path
        )
        with repo.session(db_path) as conn:
            repo.insert_sync_run(
                conn, workspace_id=workspace.id, started_at=repo.utc_now()
            )
        event = threading.Event()
        runtime.sync_cancel_events[workspace.id] = event

        page = app_client.get(f"/workspaces?ws={workspace.id}")
        assert "Cancel after current file" in page.text

        response = app_client.post(
            f"/workspaces/{workspace.id}/sync/cancel", follow_redirects=False
        )
        assert response.status_code == 303
        assert event.is_set()


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


def test_workspace_over_file_soft_cap_shows_measured_size_and_split_hint(
    tmp_path, monkeypatch
):
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, db_path = _app(tmp_path, monkeypatch, client=client)
        folder = tmp_path / "large-workspace"
        folder.mkdir()
        for number in range(51):
            (folder / f"file-{number:02}.txt").write_text("x", encoding="utf-8")
        workspace = workspaces.create_workspace(
            name="Large", folder_path=str(folder), db_path=db_path
        )

        page = app_client.get(f"/workspaces?ws={workspace.id}")

        assert "51 files and 0 measured PDF pages" in page.text
        assert "recommended limit of 50 files or 1500 pages" in page.text
        assert "Split it into smaller workspace folders" in page.text


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
        assert "<dialog" in confirm.text
        assert "data-confirm-dialog" in confirm.text
        assert "focus=delete" in confirm.text

        workspaces_page = app_client.get(f"/workspaces?ws={workspace.id}")
        assert "data-delete-trigger" in workspaces_page.text

        deleted = app_client.post(
            f"/workspaces/{workspace.id}/delete", follow_redirects=True
        )
        assert "HR" not in deleted.text or "Create your first workspace" in deleted.text
        assert workspaces.list_workspaces(db_path=db_path) == []


def test_delete_reports_a_busy_index_instead_of_crashing(tmp_path, monkeypatch):
    settings = vector_store.get_settings().model_copy(
        update={"qdrant_storage_path": str(tmp_path / "qdrant")}
    )
    monkeypatch.setattr(vector_store, "get_settings", lambda: settings)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    runtime = Runtime(db_path=db_path, ports_factory=lambda: None)
    app_client = TestClient(create_app(runtime), raise_server_exceptions=False)
    workspace = workspaces.create_workspace(
        name="Busy", folder_path=str(tmp_path), db_path=db_path
    )

    with vector_store.open_store():
        response = app_client.post(f"/workspaces/{workspace.id}/delete")

    assert response.status_code == 409
    assert "cannot be deleted while its document index is in use" in response.text
    assert workspaces.get_workspace(workspace_id=workspace.id, db_path=db_path)


# --- F-13: the read-only "watching" line ------------------------------


@pytest.mark.parametrize(
    ("watch_folders", "evidence_only", "expected"),
    [(True, False, "on"), (False, False, "off"), (True, True, "off")],
)
def test_the_watching_line_tells_the_truth_about_the_running_watcher(
    tmp_path, monkeypatch, watch_folders, evidence_only, expected
):
    """watcher.start_if_enabled never starts in evidence-only mode, so the
    S2 line must say "off" there even when watch_folders is set -- the
    third case is the one that fails if the line reads watch_folders alone."""
    import app as app_module

    settings = app_module.get_settings().model_copy(
        update={"watch_folders": watch_folders, "evidence_only": evidence_only}
    )
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, _db_path = _app(tmp_path, monkeypatch, client=client)
        page = app_client.post(
            "/workspaces",
            data={"name": "HR", "folder_path": str(_corpus(tmp_path))},
            follow_redirects=True,
        ).text

    assert f"Watching for new files: {expected}" in page
