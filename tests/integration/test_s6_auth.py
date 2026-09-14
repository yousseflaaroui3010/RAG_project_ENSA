"""S6 login, through the real app, with a scripted provider.

WHAT IS REAL: the routes, the middleware, the templates, SQLite, the
session cookie, the role checks. WHAT IS FAKED: Keycloak itself --
docs/phase2/CLAUDE.md forbids secrets in tests and CI has no Docker, so
the provider is scripted exactly as the chat model is. A hand-run against
a real Keycloak is recorded in the build journal.

WHAT THIS CANNOT PROVE: that a real realm issues the claims this fake
issues. It proves the rules Sanad applies to them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import app as app_module
import ui.auth
import ui.auth_gate
import workspaces
from app import Runtime, create_app
from config import get_settings
from db import repo
from ui import auth

ADMIN_CLAIMS = {
    "sub": "kc-admin",
    "preferred_username": "amina",
    "name": "Amina Admin",
    "email": "amina@example.ma",
    "realm_access": {"roles": ["sanad-admin"]},
}
READER_CLAIMS = {
    "sub": "kc-reader",
    "preferred_username": "omar",
    "name": "Omar Reader",
    "realm_access": {"roles": ["sanad-reader"]},
}
CURATOR_CLAIMS = {
    "sub": "kc-curator",
    "preferred_username": "sara",
    "name": "Sara Curator",
    "realm_access": {"roles": ["sanad-curator"]},
}
NO_ROLE_CLAIMS = {
    "sub": "kc-new",
    "preferred_username": "nouveau",
    "realm_access": {"roles": ["offline_access"]},
}


class FakeProvider:
    """Keycloak, scripted. Records what it was asked for."""

    def __init__(self) -> None:
        self.claims = ADMIN_CLAIMS
        self.active = True
        self.codes: list[str] = []

    def authorization_url(self, *, state: str, nonce: str, redirect_uri: str) -> str:
        return f"https://keycloak.test/realms/sanad/auth?state={state}&nonce={nonce}"

    def exchange_code(self, *, code: str, redirect_uri: str) -> dict:
        self.codes.append(code)
        return {"access_token": f"access-for-{code}"}

    def introspect(self, access_token: str) -> dict:
        return {**self.claims, "active": self.active}


@pytest.fixture
def keycloak(tmp_path, monkeypatch):
    """A real app in `keycloak` mode, plus a helper to sign someone in."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    settings = get_settings().model_copy(
        update={
            "auth_mode": auth.MODE_KEYCLOAK,
            "keycloak_issuer": "https://keycloak.test/realms/sanad",
            "keycloak_client_id": "sanad",
            "keycloak_client_secret": "test-secret",
            "keycloak_redirect_url": "http://testserver/auth/callback",
            "sqlite_db_path": str(db_path),
        }
    )
    # Each module did `from config import get_settings`, so each holds its
    # own reference: patching only `config` would leave the gate reading
    # the real settings and the test would pass while the mode did nothing.
    for module in (app_module, ui.auth, ui.auth_gate):
        monkeypatch.setattr(module, "get_settings", lambda: settings)

    provider = FakeProvider()
    runtime = Runtime(ports_factory=lambda: None, db_path=db_path, oidc_provider=provider)
    client = TestClient(create_app(runtime), base_url="http://testserver")

    def sign_in(claims: dict) -> None:
        provider.claims = claims
        client.cookies.clear()
        start = client.get("/auth/login", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        done = client.get(
            f"/auth/callback?code=abc&state={state}", follow_redirects=False
        )
        assert done.status_code == 303, done.text[:200]

    return client, runtime, db_path, provider, sign_in


def _sessions(db_path) -> list:
    with repo.session(db_path) as conn:
        return list(conn.execute("SELECT * FROM user_session"))


def _actions(db_path) -> list[str]:
    with repo.session(db_path) as conn:
        return [row["action"] for row in repo.list_activity(conn)]


# --- the flow ---------------------------------------------------------------


def test_a_stranger_is_sent_to_sign_in_and_sees_no_workspace_name(keycloak):
    client, _, db_path, _, _ = keycloak
    workspaces.create_workspace(name="Secret HR", folder_path=str(db_path.parent), db_path=db_path)

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"
    page = client.get("/auth/login", follow_redirects=False)
    assert "Secret HR" not in page.text


def test_sign_in_sends_the_browser_to_keycloak_with_a_state_and_remembers_it(keycloak):
    client, _, _, _, _ = keycloak

    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 303
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert response.headers["location"].startswith("https://keycloak.test/")
    assert query["state"][0] and query["nonce"][0]
    assert auth.FLOW_COOKIE in response.cookies
    assert query["state"][0] in response.cookies[auth.FLOW_COOKIE]


def test_a_callback_with_the_wrong_state_is_refused_and_no_session_is_written(keycloak):
    client, _, db_path, provider, _ = keycloak
    client.get("/auth/login", follow_redirects=False)

    response = client.get("/auth/callback?code=abc&state=not-the-one", follow_redirects=False)

    assert response.status_code == 400
    assert _sessions(db_path) == []
    assert provider.codes == [], "a forged state must not even reach the token exchange"


def test_a_callback_with_no_flow_cookie_at_all_is_refused(keycloak):
    client, _, db_path, _, _ = keycloak

    response = client.get("/auth/callback?code=abc&state=anything", follow_redirects=False)

    assert response.status_code == 400
    assert _sessions(db_path) == []


def test_a_flow_cookie_this_server_did_not_sign_is_refused(keycloak):
    """Login CSRF: an attacker who can set a cookie must not be able to
    plant their own `state` and complete a sign-in the person never
    started. The cookie is signed with the client secret, so a made-up
    one does not verify."""
    client, _, db_path, provider, _ = keycloak
    client.cookies.set(auth.FLOW_COOKIE, "forged-state:forged-nonce:deadbeef", path="/auth")

    response = client.get(
        "/auth/callback?code=abc&state=forged-state", follow_redirects=False
    )

    assert response.status_code == 400
    assert _sessions(db_path) == []
    assert provider.codes == []


def test_a_signed_in_person_is_recorded_once_with_their_roles(keycloak):
    client, _, db_path, _, sign_in = keycloak

    sign_in(ADMIN_CLAIMS)
    sign_in(ADMIN_CLAIMS)

    with repo.session(db_path) as conn:
        users = repo.list_users(conn)
    assert len(users) == 1
    assert users[0]["username"] == "amina"
    assert users[0]["roles"] == "admin"
    assert len(_sessions(db_path)) == 2, "each sign-in is its own browser session"
    assert _actions(db_path).count("signed in") == 2


def test_the_session_cookie_is_http_only_and_never_the_stored_value(keycloak):
    client, _, db_path, _, sign_in = keycloak

    sign_in(ADMIN_CLAIMS)

    cookie = client.cookies[auth.SESSION_COOKIE]
    stored = _sessions(db_path)[0]["token_hash"]
    assert stored != cookie
    assert stored == auth.hash_token(cookie)


def test_after_signing_in_the_header_names_the_person_and_offers_sign_out(keycloak):
    client, _, _, _, sign_in = keycloak

    sign_in(ADMIN_CLAIMS)
    page = client.get("/workspaces")

    assert page.status_code == 200
    assert "Amina Admin" in page.text
    assert 'action="/auth/logout"' in page.text


def test_signing_out_deletes_the_session_and_locks_the_door_again(keycloak):
    client, _, db_path, _, sign_in = keycloak
    sign_in(ADMIN_CLAIMS)

    client.post("/auth/logout", follow_redirects=False)

    assert _sessions(db_path) == []
    after = client.get("/", follow_redirects=False)
    assert after.status_code == 303 and after.headers["location"] == "/auth/login"
    assert "signed out" in _actions(db_path)


def test_an_expired_session_is_not_a_session(keycloak):
    client, _, db_path, _, sign_in = keycloak
    sign_in(ADMIN_CLAIMS)
    past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    with repo.session(db_path) as conn:
        conn.execute("UPDATE user_session SET expires_at = ?", (past,))

    response = client.get("/", follow_redirects=False)

    # WHERE it redirects is the whole test. `/` also answers 303 when it
    # simply has no workspace to show (it sends you to S2), so asserting
    # the status alone passed with the expiry check deleted -- found by
    # mutating that check and watching this test stay green.
    assert response.status_code == 303
    assert response.headers["location"] == "/auth/login"


def test_an_inactive_token_is_refused_even_with_a_valid_state(keycloak):
    client, _, db_path, provider, _ = keycloak
    provider.active = False
    start = client.get("/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]

    response = client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)

    assert response.status_code == 400
    assert _sessions(db_path) == []


def test_the_api_answers_json_not_a_redirect_when_nobody_is_signed_in(keycloak):
    client, _, _, _, _ = keycloak

    response = client.get("/api/v1/workspaces")

    assert response.status_code == 401
    assert response.json()["code"] == "NOT_AUTHENTICATED"


def test_the_health_probe_stays_open(keycloak):
    client, _, _, _, _ = keycloak

    assert client.get("/api/v1/health").status_code == 200


# --- roles ------------------------------------------------------------------


def test_an_account_with_no_sanad_role_sees_one_honest_page_everywhere(keycloak):
    client, _, db_path, _, sign_in = keycloak
    workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(NO_ROLE_CLAIMS)

    for path in ("/", "/workspaces", "/reports"):
        page = client.get(path)
        assert page.status_code == 403, path
        assert "no Sanad role" in page.text or "not granted" in page.text.lower()
        assert "HR" not in page.text.split("<main")[1] if "<main" in page.text else True


def test_a_reader_cannot_create_a_workspace(keycloak):
    client, _, db_path, _, sign_in = keycloak
    sign_in(READER_CLAIMS)

    response = client.post(
        "/workspaces",
        data={"name": "Mine", "folder_path": str(db_path.parent)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert workspaces.list_workspaces(db_path=db_path) == []
    assert "refused" in _actions(db_path)


def test_a_curator_cannot_delete_a_workspace(keycloak):
    client, _, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(CURATOR_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-curator")

    client.post(f"/workspaces/{ws.id}/delete", follow_redirects=False)

    assert [w.id for w in workspaces.list_workspaces(db_path=db_path)] == [ws.id]


def test_a_workspace_nobody_granted_is_not_even_listed(keycloak):
    client, _, db_path, _, sign_in = keycloak
    seen = workspaces.create_workspace(
        name="Granted HR", folder_path=str(db_path.parent), db_path=db_path
    )
    workspaces.create_workspace(
        name="Hidden Legal", folder_path=str(db_path.parent), db_path=db_path
    )
    sign_in(READER_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=seen.id, user_id="kc-reader")

    page = client.get("/workspaces")

    assert "Granted HR" in page.text
    assert "Hidden Legal" not in page.text


def test_a_curator_may_sync_a_granted_workspace_and_not_another(keycloak):
    client, runtime, db_path, _, sign_in = keycloak
    granted = workspaces.create_workspace(
        name="Granted", folder_path=str(db_path.parent), db_path=db_path
    )
    other = workspaces.create_workspace(
        name="Other", folder_path=str(db_path.parent), db_path=db_path
    )
    sign_in(CURATOR_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=granted.id, user_id="kc-curator")

    refused = client.post(f"/workspaces/{other.id}/sync", follow_redirects=False)
    assert refused.status_code == 303
    assert "started a sync" not in _actions(db_path)

    client.post(f"/workspaces/{granted.id}/sync", follow_redirects=False)
    assert "started a sync" in _actions(db_path)


# --- one transcript per person ----------------------------------------------


def test_two_people_never_share_a_conversation(keycloak):
    client, runtime, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    runtime.active_workspace_id = ws.id

    # A grant points at an app_user row, so the person has to have signed
    # in at least once before they can be granted anything.
    sign_in(READER_CLAIMS)
    sign_in(CURATOR_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-reader")
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-curator")
    sign_in(READER_CLAIMS)
    runtime.conversation(ws.id, "kc-reader").messages.append(
        __import__("ui.conversation", fromlist=["Message"]).Message(
            kind=__import__("ui.conversation", fromlist=["MessageKind"]).MessageKind.USER,
            text="QUESTION-DE-OMAR",
        )
    )
    mine = client.get("/chat/messages").text
    assert "QUESTION-DE-OMAR" in mine

    sign_in(CURATOR_CLAIMS)
    theirs = client.get("/chat/messages").text
    assert "QUESTION-DE-OMAR" not in theirs, "one person's transcript reached another"


def test_signing_out_forgets_that_person_transcript(keycloak):
    client, runtime, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-reader")
    runtime.conversation(ws.id, "kc-reader")

    client.post("/auth/logout", follow_redirects=False)

    assert not any(key.startswith("kc-reader|") for key in runtime.conversations)
