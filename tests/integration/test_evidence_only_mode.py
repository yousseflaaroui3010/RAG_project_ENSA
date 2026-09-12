"""`config.evidence_only`: a published instance that says no honestly.

WHAT THIS MODE IS FOR, because a flag that turns features off looks like a
bug until you know the number behind it. Sanad's embedding model is
`intfloat/multilingual-e5-base`: 278M parameters, 1,112 MB at float32. A
small trial-plan container cannot hold that. Both Sync AND Chat load that
model -- Chat too, through `vector_store`'s `embed_query` -- so on that box
neither can ever work.

THE FAILURE THIS REPLACES was the worst kind. A platform can kill the
process partway through loading the model and restart it; the browser is
left polling a Sync that no longer exists, showing "Scanning the workspace
folder..." indefinitely, and nothing anywhere says why. Ported from MB's
`feat/S1-ST-05-docker-deploy` branch, which observed exactly this in
production, onto main's structure: `Runtime.ports()` and
`Runtime.start_sync()` (app.py) are the two seams both the screens and the
`/api/v1` API call, so one check in each covers every caller.

WHAT IS DELIBERATELY NOT TESTED HERE: that answering works when the flag is
off. That is every other integration test in this directory. Most tests
below check only that the flag is what stops Sync or Chat -- with it off,
the run starts -- because a refusal test that passes for the wrong reason
(no workspace, bad folder, missing schema) would be indistinguishable from
a correct one.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

import app as app_module
import vector_store
from app import EVIDENCE_ONLY_MESSAGE, Runtime, create_app
from config import get_settings
from db import repo
from tests.fake_encoders import install as install_fake_encoders

WAIT = 10


def _wait_until(predicate, *, timeout: float = WAIT) -> None:
    """Second copy of `test_s2_workspaces_screen._wait_until`, on purpose.

    The project's duplication rule allows two copies and asks for a
    decision on the third. Importing a private helper out of a sibling
    test module couples two test files' internals for four lines; if a
    third file needs this, it moves to a shared fixture then."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError(f"condition never became true within {timeout}s")


ARTICLE = (
    "Article {n}. Le present article decrit une regle du travail avec assez "
    "de texte pour produire plusieurs morceaux une fois decoupe, afin que la "
    "synchronisation ait vraiment quelque chose a convertir et a indexer. "
) * 6


def _corpus(tmp_path):
    folder = tmp_path / "corpus"
    folder.mkdir()
    (folder / "a.txt").write_text(ARTICLE.format(n=1), encoding="utf-8")
    return folder


def _set_evidence_only(monkeypatch, value: bool) -> None:
    """Override the setting where `app.py` reads it.

    `app.py` does `from config import get_settings`, so the name to patch is
    `app.get_settings` -- patching `config.get_settings` would leave app.py
    holding the original reference and the test would pass while the flag
    did nothing."""
    settings = get_settings().model_copy(update={"evidence_only": value})
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)


def _app(tmp_path, monkeypatch, *, client):
    install_fake_encoders(monkeypatch)
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    runtime = Runtime(db_path=db_path, client=client)
    return TestClient(create_app(runtime)), runtime, db_path


def _make_workspace(app_client, folder) -> str:
    created = app_client.post(
        "/workspaces",
        data={"name": "HR", "folder_path": str(folder)},
        follow_redirects=False,
    )
    assert created.status_code == 303
    return created.headers["location"].split("ws=")[1]


def test_sync_is_declined_with_a_sentence_and_no_run_is_ever_started(
    tmp_path, monkeypatch
):
    """The operator sees the reason, and the database proves nothing ran.

    Asserting on the page alone would pass even if a Sync had started and
    crashed behind it -- which is exactly the production failure this mode
    exists to prevent. The `sync_run` count is what makes "never started"
    a fact rather than a hope."""
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, db_path = _app(tmp_path, monkeypatch, client=client)
        workspace_id = _make_workspace(app_client, _corpus(tmp_path))

        _set_evidence_only(monkeypatch, True)
        page = app_client.post(
            f"/workspaces/{workspace_id}/sync", follow_redirects=True
        )

        assert page.status_code == 200
        assert "read-only" in page.text
        assert "cannot answer questions or run a Sync" in page.text

        with repo.session(db_path) as conn:
            rows = list(conn.execute("SELECT COUNT(*) FROM sync_run"))
        assert rows[0][0] == 0, "evidence-only mode must not start a sync run"


def test_chat_is_declined_with_the_same_sentence(tmp_path, monkeypatch):
    """Chat refuses too, and says the SAME thing Sync said.

    Chat is included because it is the half people assume is safe: it only
    embeds one short query, so it looks lightweight. It loads the identical
    model, so it hits the identical wall."""
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, _db_path = _app(tmp_path, monkeypatch, client=client)
        _make_workspace(app_client, _corpus(tmp_path))

        _set_evidence_only(monkeypatch, True)
        page = app_client.post(
            "/chat/ask",
            data={"question": "Quelle est la duree de la periode d'essai ?"},
            follow_redirects=True,
        )

        assert page.status_code == 200
        assert "read-only" in page.text
        assert "Run Sanad locally" in page.text


def test_the_read_only_screens_still_serve(tmp_path, monkeypatch):
    """The whole point of the mode: reports and workspaces keep working.

    A mode that turned the site off would be a worse outage than the crash
    it replaces."""
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, _db_path = _app(tmp_path, monkeypatch, client=client)
        _make_workspace(app_client, _corpus(tmp_path))

        _set_evidence_only(monkeypatch, True)

        assert app_client.get("/reports").status_code == 200
        assert app_client.get("/workspaces").status_code == 200


def test_with_the_flag_off_the_sync_actually_starts(tmp_path, monkeypatch):
    """The control probe: prove the FLAG is what stops the Sync.

    Without this, all three tests above would pass just as happily if the
    refusal came from a missing folder, an unwritable database, or a route
    that 500s -- and the mode would look correct while doing nothing. Here
    the flag is explicitly OFF and the same POST reaches the real code
    path, so a `sync_run` row appears."""
    with vector_store.open_store(tmp_path / "qdrant") as client:
        app_client, _runtime, db_path = _app(tmp_path, monkeypatch, client=client)
        workspace_id = _make_workspace(app_client, _corpus(tmp_path))

        _set_evidence_only(monkeypatch, False)
        started = app_client.post(
            f"/workspaces/{workspace_id}/sync", follow_redirects=True
        )

        assert started.status_code == 200
        assert EVIDENCE_ONLY_MESSAGE not in started.text

        with repo.session(db_path) as conn:
            rows = list(conn.execute("SELECT COUNT(*) FROM sync_run"))
        assert rows[0][0] == 1, "with the flag off, a real sync run must be claimed"

        # WAIT FOR THE RUN TO FINISH BEFORE LEAVING THIS BLOCK, and the
        # reason is not tidiness. This test is the only one in the file that
        # lets a REAL sync start, and that sync runs on a background thread
        # holding the Qdrant client. Without this wait the `with` block
        # closed the client underneath the running thread and the whole
        # pytest process died with "Windows fatal exception: access
        # violation" -- exit 139, no failing test named, every other file's
        # results lost. Seen once; the individual file passed on its own,
        # so only the full-suite run caught it.
        def _finished() -> bool:
            with repo.session(db_path) as conn:
                return repo.get_running_sync_run(conn, workspace_id) is None

        _wait_until(_finished)


# --- ST-05: warm-up must not run in evidence-only mode ---------------------
#
# A memory-capped container that both warms up the full embedding model AND
# refuses to ever use it is spending the one resource it does not have on
# work nobody can benefit from -- `Runtime.ports()` above already declines
# every question in this mode. `app.main()` is the one place that turns
# warm-up on at all (`Runtime.warm_up` defaults False so no test or other
# importer downloads a model by accident), so this is tested at that seam
# by faking `uvicorn.run` and reading the `Runtime` it was handed.


def test_main_skips_warm_up_in_evidence_only_mode(monkeypatch):
    captured: dict[str, bool] = {}

    def fake_run(built_app, **_kwargs) -> None:
        captured["warm_up"] = built_app.state.runtime.warm_up

    _set_evidence_only(monkeypatch, True)
    monkeypatch.setattr(app_module.uvicorn, "run", fake_run)

    app_module.main()

    assert captured["warm_up"] is False


def test_main_keeps_warm_up_when_not_evidence_only(monkeypatch):
    """The control probe: prove EVIDENCE_ONLY is what turns warm-up off, not
    some unrelated change to `main` that would make the test above pass for
    the wrong reason."""
    captured: dict[str, bool] = {}

    def fake_run(built_app, **_kwargs) -> None:
        captured["warm_up"] = built_app.state.runtime.warm_up

    _set_evidence_only(monkeypatch, False)
    monkeypatch.setattr(app_module.uvicorn, "run", fake_run)

    app_module.main()

    assert captured["warm_up"] is True
