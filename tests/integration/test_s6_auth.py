"""S6 login, through the real app, with a scripted provider.

WHAT IS REAL: the routes, the middleware, the templates, SQLite, the
session cookie, the role checks. WHAT IS FAKED: Keycloak itself --
docs/phase2/ENGINEERING-RULES.md forbids secrets in tests and CI has no Docker, so
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
from ui.conversation import Message, MessageKind

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
        self.ui_locales: str | None = None

    def authorization_url(
        self, *, state: str, nonce: str, redirect_uri: str, ui_locales: str = ""
    ) -> str:
        self.ui_locales = ui_locales
        return f"https://keycloak.test/realms/sanad/auth?state={state}&nonce={nonce}"

    def exchange_code(self, *, code: str, redirect_uri: str) -> dict:
        self.codes.append(code)
        return {"access_token": f"access-for-{code}"}

    def introspect(self, access_token: str) -> dict:
        return {**self.claims, "active": self.active}

    def end_session_url(self, *, redirect_uri: str, ui_locales: str = "") -> str:
        self.logout_ui_locales = ui_locales
        return f"https://keycloak.test/realms/sanad/logout?redirect={redirect_uri}"


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


def test_sign_in_and_sign_up_pages_open_in_the_language_sanad_is_showing(keycloak):
    """2026-09-15: a visitor reading Sanad in French got Keycloak's sign-in
    and sign-up pages in English (Keycloak follows the browser). The
    language chosen in Sanad now travels with the redirect."""
    client, _, _, provider, _ = keycloak

    client.get("/auth/login?lang=ar", follow_redirects=False)
    arabic = provider.ui_locales
    client.cookies.clear()
    client.get("/auth/login?lang=en", follow_redirects=False)
    english = provider.ui_locales

    assert (arabic, english) == ("ar", "en")


def test_sign_out_confirmation_opens_in_the_language_sanad_is_showing(keycloak):
    client, _, _, provider, sign_in = keycloak
    sign_in(ADMIN_CLAIMS)
    client.get("/?lang=ar", follow_redirects=False)

    client.post("/auth/logout", follow_redirects=False)

    assert provider.logout_ui_locales == "ar"


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


def test_signing_out_also_ends_the_session_at_keycloak(keycloak):
    """Found in a real browser against a real realm: deleting our own
    cookie left the realm's SSO session alive, so the next Sign in was
    answered silently with the same person -- on the shared demo machine,
    a sign-out button that signs nobody out."""
    client, _, _, _, sign_in = keycloak
    sign_in(ADMIN_CLAIMS)

    response = client.post("/auth/logout", follow_redirects=False)

    assert response.headers["location"].startswith(
        "https://keycloak.test/realms/sanad/logout"
    )
    assert "/auth/login" in response.headers["location"]


def test_sign_out_returns_to_the_configured_origin_not_the_one_the_proxy_hid(
    keycloak, monkeypatch
):
    """Found on the published demo, 2026-09-15: Railway ends TLS at its own
    proxy, so the app sees every request as plain http. The sign-out return
    address was built from the request and came out `http://...`, which the
    realm had never registered (only `https://...`), and Keycloak answered
    400 -- nobody on the demo could sign out. The configured callback URL
    already carries the right scheme and host, and is the one address the
    realm is known to trust, so the return address is built from it.

    The fixture uses the same origin for the configured URL and the test
    client, which is why the old code passed; this test makes them differ,
    the way a TLS proxy does."""
    client, _, _, _, sign_in = keycloak
    sign_in(ADMIN_CLAIMS)
    # Changed only after signing in: the https callback would make the
    # sign-in cookie secure, which the plain-http test client never sends
    # back. Sign-out reads the setting at the moment it runs.
    behind_proxy = app_module.get_settings().model_copy(
        update={"keycloak_redirect_url": "https://sanad.example/auth/callback"}
    )
    for module in (app_module, ui.auth, ui.auth_gate):
        monkeypatch.setattr(module, "get_settings", lambda: behind_proxy)

    response = client.post("/auth/logout", follow_redirects=False)

    redirect = parse_qs(urlparse(response.headers["location"]).query)["redirect"][0]
    assert redirect == "https://sanad.example/auth/login"


def test_cookies_are_secure_when_the_configured_address_is_https_behind_a_proxy(
    keycloak, monkeypatch
):
    """Seen on the published demo, 2026-09-15: behind Railway's TLS proxy
    every request looks like plain http, so both sign-in cookies were set
    WITHOUT `Secure` and a browser would send the session over http too.
    Same root cause as the sign-out 400. The configured callback's scheme
    is the truth about how people reach the app, so it decides."""
    client, _, _, provider, _ = keycloak
    provider.claims = ADMIN_CLAIMS
    # Start under the fixture's http settings so the flow cookie is stored
    # by this plain-http client, then switch to an https deployment.
    start = client.get("/auth/login", follow_redirects=False)
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    deployed = app_module.get_settings().model_copy(
        update={"keycloak_redirect_url": "https://sanad.example/auth/callback"}
    )
    for module in (app_module, ui.auth, ui.auth_gate):
        monkeypatch.setattr(module, "get_settings", lambda: deployed)

    # Finish the flow first: starting a new one would replace its cookie.
    done = client.get(f"/auth/callback?code=abc&state={state}", follow_redirects=False)
    assert done.status_code == 303, done.text[:200]
    client.cookies.clear()
    login = client.get("/auth/login", follow_redirects=False)

    flow_cookie = next(
        c for c in login.headers.get_list("set-cookie") if c.startswith(auth.FLOW_COOKIE)
    )
    session_cookie = next(
        c for c in done.headers.get_list("set-cookie") if c.startswith(auth.SESSION_COOKIE)
    )
    assert "secure" in flow_cookie.lower()
    assert "secure" in session_cookie.lower()


def test_cookies_are_not_secure_on_a_plain_http_machine(keycloak):
    """The other side, so the test above cannot pass by always setting
    Secure: on 127.0.0.1 over http a Secure cookie is never sent back and
    nobody could finish signing in."""
    client, _, _, provider, _ = keycloak
    provider.claims = ADMIN_CLAIMS

    login = client.get("/auth/login", follow_redirects=False)

    flow_cookie = next(
        c for c in login.headers.get_list("set-cookie") if c.startswith(auth.FLOW_COOKIE)
    )
    assert "secure" not in flow_cookie.lower()


def _seed_report(db_path, tmp_path, *, answer: str) -> tuple[str, str]:
    """A workspace nobody granted, with one evaluation answer in it."""
    report_path = tmp_path / "run.json"
    report_path.write_text("{}", encoding="utf-8")
    with repo.session(db_path) as conn:
        workspace_id = repo.create_workspace(
            conn, name="Salaires direction", folder_path=str(tmp_path)
        )
        run_id = repo.insert_eval_run(
            conn,
            workspace_id=workspace_id,
            status="running",
            question_total=1,
            report_path=str(report_path),
        )
        repo.insert_eval_result(
            conn,
            eval_run_id=run_id,
            question_id="g-in-fake-001",
            kind="in_scope",
            answer_kind="answer",
            answer_text=answer,
            passed=True,
            groundedness=1.0,
            relevancy=0.8,
            sources_present=True,
        )
    return run_id, workspace_id


def test_a_report_of_a_workspace_you_were_not_granted_is_not_readable(
    keycloak, tmp_path
):
    """Review of the sign-up change, 2026-09-15: these two routes checked
    neither role nor grant. Once anyone can sign up, a stranger holding a
    run id could read the evaluation answers of a workspace nobody shared
    with them -- the answers quote the documents."""
    client, _, db_path, _, sign_in = keycloak
    answer = "le salaire du directeur est de 42 000 dirhams"
    run_id, _ = _seed_report(db_path, tmp_path, answer=answer)
    sign_in(READER_CLAIMS)

    page = client.get(f"/reports/{run_id}")
    export = client.get(f"/reports/{run_id}/export")

    assert page.status_code == 404, "an ungranted report must not render"
    assert answer not in page.text
    assert "Salaires direction" not in page.text
    assert export.status_code == 404
    assert answer not in export.text


def test_an_admin_still_reads_any_report(keycloak, tmp_path):
    """The other side: the fix must not lock out the person who may look."""
    client, _, db_path, _, sign_in = keycloak
    answer = "le salaire du directeur est de 42 000 dirhams"
    run_id, _ = _seed_report(db_path, tmp_path, answer=answer)
    sign_in(ADMIN_CLAIMS)

    page = client.get(f"/reports/{run_id}")

    assert page.status_code == 200
    assert "Salaires direction" in page.text


def test_a_reader_reads_the_report_of_a_workspace_they_were_granted(
    keycloak, tmp_path
):
    """The positive control the review asked for: a check written as
    "admins only" would pass every test above and still lock out the reader
    this feature exists for."""
    client, _, db_path, _, sign_in = keycloak
    answer = "le salaire du directeur est de 42 000 dirhams"
    run_id, workspace_id = _seed_report(db_path, tmp_path, answer=answer)
    sign_in(READER_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=workspace_id, user_id=READER_CLAIMS["sub"])

    page = client.get(f"/reports/{run_id}")

    assert page.status_code == 200
    assert "Salaires direction" in page.text


def test_a_stale_page_naming_a_deleted_workspace_just_falls_back(keycloak, tmp_path):
    """Refusing must mean "not yours", not "your page is old". A workspace
    deleted while this screen was open posts an id that exists nowhere; the
    honest answer is the person's own first workspace, with no refusal in
    the activity log for an admin to puzzle over."""
    client, runtime, db_path, _, sign_in = keycloak
    sign_in(READER_CLAIMS)

    client.post(
        "/workspace",
        data={"workspace_id": "11111111-2222-3333-4444-555555555555"},
        follow_redirects=False,
    )

    assert runtime.active_workspace_id is None
    assert "refused" not in _actions(db_path)


def test_the_delete_confirmation_page_does_not_name_a_workspace_you_cannot_touch(
    keycloak, tmp_path
):
    """Same review: the POST that deletes checked the role, the GET that
    shows the confirmation did not, so it printed the workspace's name to
    anyone signed in."""
    client, _, db_path, _, sign_in = keycloak
    _, workspace_id = _seed_report(db_path, tmp_path, answer="x")
    sign_in(READER_CLAIMS)

    page = client.get(f"/workspaces/{workspace_id}/delete", follow_redirects=False)

    assert page.status_code == 303
    assert "Salaires direction" not in page.text


def test_selecting_a_workspace_you_cannot_see_changes_nothing(keycloak, tmp_path):
    """Same review: the posted id was written to the shell's selection
    without a check, so any signed-in person could point the selector at a
    workspace that was never shared with them."""
    client, runtime, db_path, _, sign_in = keycloak
    _, workspace_id = _seed_report(db_path, tmp_path, answer="x")
    sign_in(READER_CLAIMS)

    client.post("/workspace", data={"workspace_id": workspace_id}, follow_redirects=False)

    assert runtime.active_workspace_id != workspace_id
    assert "refused" in _actions(db_path)


def test_a_person_with_no_role_sees_no_workspace_panel(keycloak, tmp_path):
    """Security review, 2026-09-16: `/workspaces` shows the no-role page,
    but the panel it polls for did not check the role at all, so an account
    that signed in with no Sanad role -- which anyone can create, sign-up is
    open -- could still pull the workspace name, its folder path and its
    file table out of the poll target if a grant row existed for it."""
    client, _, db_path, _, sign_in = keycloak
    _, workspace_id = _seed_report(db_path, tmp_path, answer="x")
    sign_in(NO_ROLE_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(
            conn, workspace_id=workspace_id, user_id=NO_ROLE_CLAIMS["sub"]
        )

    panel = client.get("/workspaces/panel")
    confirm = client.get("/chat/history/delete")

    assert panel.status_code == 403
    assert "Salaires direction" not in panel.text
    assert confirm.status_code == 403


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
    runtime.new_conversation("kc-reader", ws.id).messages.append(
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
    runtime.new_conversation("kc-reader", ws.id)

    client.post("/auth/logout", follow_redirects=False)

    assert not [c for c in runtime.conversations.values() if c.user_id == "kc-reader"]


def test_signing_out_keeps_the_stored_transcript_for_next_time(keycloak):
    """S6 saved chat history: ordinary sign-out clears MEMORY (proven above) but must
    leave storage alone -- that is the whole point of a stored transcript,
    it comes back at the next sign-in, unlike admin "sign out everywhere"
    (test_s6_admin.py), which deletes both."""
    client, runtime, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-reader")
    conversation = runtime.new_conversation("kc-reader", ws.id)
    conversation.messages.append(Message(kind=MessageKind.ANSWER, text="reader's answer"))
    runtime.save_conversation(conversation)

    client.post("/auth/logout", follow_redirects=False)

    with repo.session(db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM conversation WHERE user_id = 'kc-reader'"
            ).fetchone()[0]
            == 1
        )

    sign_in(READER_CLAIMS)
    restored = runtime.latest_conversation("kc-reader", ws.id)
    assert restored is not conversation, "sign-out must have dropped the live copy"
    assert [m.text for m in restored.messages] == ["reader's answer"], (
        "the transcript must reload from storage at the next sign-in"
    )


# --- ST-53: many conversations, a list, rename, delete ---------------------


def _reader_with_a_workspace(keycloak, name: str = "HR"):
    client, runtime, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name=name, folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-reader")
    return client, runtime, db_path, sign_in, ws


def _stored(runtime, user_id, ws_id, question, answer):
    conversation = runtime.new_conversation(user_id, ws_id)
    conversation.messages.append(Message(kind=MessageKind.USER, text=question))
    conversation.messages.append(Message(kind=MessageKind.ANSWER, text=answer))
    runtime.save_conversation(conversation)
    return conversation


def test_a_signed_in_person_sees_their_conversations_and_can_open_an_older_one(keycloak):
    client, runtime, _, _, ws = _reader_with_a_workspace(keycloak)
    older = _stored(runtime, "kc-reader", ws.id, "OLDER-QUESTION", "OLDER-ANSWER")
    newer = _stored(runtime, "kc-reader", ws.id, "NEWER-QUESTION", "NEWER-ANSWER")

    page = client.get("/").text

    assert 'class="history"' in page
    assert page.index(f'href="/?c={newer.id}"') < page.index(f'href="/?c={older.id}"'), (
        "the list is newest first"
    )
    assert "NEWER-ANSWER" in page and "OLDER-ANSWER" not in page, "no ?c= opens the latest"

    opened = client.get(f"/?c={older.id}").text
    assert "OLDER-ANSWER" in opened and "NEWER-ANSWER" not in opened
    assert f'name="conversation_id" value="{older.id}"' in opened, (
        "the next question must continue the conversation that was opened"
    )


def test_the_list_never_shows_someone_elses_conversation(keycloak):
    client, runtime, db_path, sign_in, ws = _reader_with_a_workspace(keycloak)
    sign_in(CURATOR_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-curator")
    theirs = _stored(runtime, "kc-curator", ws.id, "CURATOR-QUESTION", "CURATOR-ANSWER")
    sign_in(READER_CLAIMS)

    page = client.get("/").text
    forced = client.get(f"/?c={theirs.id}").text

    assert theirs.id not in page and "CURATOR-QUESTION" not in page
    assert "CURATOR-ANSWER" not in forced, "an id in the address must not open their chat"


def test_new_conversation_when_signed_in_keeps_the_one_on_screen(keycloak):
    """YL's ST-53 ruling: signed in, New conversation opens an empty chat
    and the previous one stays -- stored, listed, still openable."""
    client, runtime, db_path, _, ws = _reader_with_a_workspace(keycloak)
    kept = _stored(runtime, "kc-reader", ws.id, "KEPT-QUESTION", "KEPT-ANSWER")

    response = client.post(
        "/chat/new", data={"conversation_id": kept.id}, follow_redirects=False
    )

    assert response.headers["location"] == "/?c=new"
    with repo.session(db_path) as conn:
        assert [row[0] for row in conn.execute("SELECT id FROM conversation")] == [kept.id]
    empty = client.get("/?c=new").text
    assert "KEPT-ANSWER" not in empty
    assert 'name="conversation_id" value=""' in empty
    assert f'href="/?c={kept.id}"' in empty, "the kept one is one click away"


def test_someone_elses_conversation_is_not_found_on_every_route(keycloak):
    """Not yours and does not exist are the same 404 -- on the page that
    only renders too, not just on the actions -- and nothing changes."""
    client, runtime, db_path, sign_in, ws = _reader_with_a_workspace(keycloak)
    sign_in(CURATOR_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-curator")
    theirs = _stored(runtime, "kc-curator", ws.id, "CURATOR-QUESTION", "CURATOR-ANSWER")
    sign_in(READER_CLAIMS)

    manage = client.get(f"/chat/conversations/{theirs.id}")
    rename = client.post(
        f"/chat/conversations/{theirs.id}/rename", data={"title": "mine now"},
        follow_redirects=False,
    )
    delete = client.post(f"/chat/conversations/{theirs.id}/delete", follow_redirects=False)
    unknown = client.get("/chat/conversations/does-not-exist")

    assert [manage.status_code, rename.status_code, delete.status_code, unknown.status_code] == [
        404, 404, 404, 404,
    ]
    assert manage.text == unknown.text, "the two cases must be indistinguishable"
    with repo.session(db_path) as conn:
        row = conn.execute("SELECT title FROM conversation WHERE id = ?", (theirs.id,)).fetchone()
    assert row is not None and row[0] == "CURATOR-QUESTION"


def test_a_conversation_in_a_workspace_no_longer_granted_is_not_found(keycloak):
    """A stored conversation in a workspace the person can no longer see
    must not be reachable -- by id, through any route."""
    client, runtime, db_path, _, _ = _reader_with_a_workspace(keycloak)
    locked = workspaces.create_workspace(
        name="Locked", folder_path=str(db_path.parent), db_path=db_path
    )
    stranded = _stored(runtime, "kc-reader", locked.id, "LOCKED-QUESTION", "LOCKED-ANSWER")

    assert client.get(f"/chat/conversations/{stranded.id}").status_code == 404
    assert client.post(
        f"/chat/conversations/{stranded.id}/delete", follow_redirects=False
    ).status_code == 404
    passage = client.get(f"/chat/passage/{stranded.id}/1/0").text
    assert "LOCKED-ANSWER" not in passage


def test_renaming_a_conversation_shows_the_new_title_in_the_list(keycloak):
    client, runtime, _, _, ws = _reader_with_a_workspace(keycloak)
    conversation = _stored(runtime, "kc-reader", ws.id, "FIRST-QUESTION", "ANSWER")
    assert client.get(f"/chat/conversations/{conversation.id}").status_code == 200

    response = client.post(
        f"/chat/conversations/{conversation.id}/rename",
        data={"title": "  Notes   préavis  "},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/?c={conversation.id}"
    page = client.get("/").text
    assert "Notes préavis" in page
    assert "FIRST-QUESTION</a>" not in page


def test_an_empty_or_over_long_title_is_refused_with_the_reason_on_the_page(keycloak):
    client, runtime, db_path, _, ws = _reader_with_a_workspace(keycloak)
    conversation = _stored(runtime, "kc-reader", ws.id, "KEPT-TITLE", "ANSWER")

    empty = client.post(
        f"/chat/conversations/{conversation.id}/rename", data={"title": "   "},
        follow_redirects=False,
    )
    too_long = client.post(
        f"/chat/conversations/{conversation.id}/rename", data={"title": "x" * 81},
        follow_redirects=False,
    )

    assert (empty.status_code, too_long.status_code) == (400, 400)
    assert 'aria-invalid="true"' in empty.text and 'aria-invalid="true"' in too_long.text
    assert empty.text != too_long.text, "each refusal names its own reason"
    with repo.session(db_path) as conn:
        assert conn.execute("SELECT title FROM conversation").fetchone()[0] == "KEPT-TITLE"


def test_deleting_one_conversation_keeps_the_others_and_a_get_deletes_nothing(keycloak):
    client, runtime, db_path, _, ws = _reader_with_a_workspace(keycloak)
    gone = _stored(runtime, "kc-reader", ws.id, "GONE-QUESTION", "GONE-ANSWER")
    kept = _stored(runtime, "kc-reader", ws.id, "KEPT-QUESTION", "KEPT-ANSWER")

    client.get(f"/chat/conversations/{gone.id}")
    with repo.session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversation").fetchone()[0] == 2

    response = client.post(f"/chat/conversations/{gone.id}/delete", follow_redirects=False)

    assert response.status_code == 303
    with repo.session(db_path) as conn:
        assert [row[0] for row in conn.execute("SELECT id FROM conversation")] == [kept.id]
    assert "GONE-ANSWER" not in client.get(f"/?c={gone.id}").text


def test_a_reader_is_offered_no_control_they_may_not_use(keycloak):
    """Found in a real browser: the reader's own workspace page still
    showed Sync and "new workspace". The routes refused them, but a button
    that cannot work is a dead control -- the rule the theme toggle, the
    sample questions and the drop zone already follow."""
    client, _, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-reader")

    page = client.get(f"/workspaces?ws={ws.id}").text

    assert "HR" in page, "the granted workspace is still shown"
    assert f'action="/workspaces/{ws.id}/sync"' not in page
    assert 'action="/workspaces"' not in page
    assert f'href="/workspaces/{ws.id}/delete"' not in page
    assert "data-dropzone" not in page, "a reader may not add documents either"


def test_a_curator_keeps_sync_in_a_granted_workspace_but_not_the_settings(keycloak):
    client, _, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(CURATOR_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-curator")

    page = client.get(f"/workspaces?ws={ws.id}").text

    assert f'action="/workspaces/{ws.id}/sync"' in page
    assert "data-dropzone" in page, "a curator adds documents in a granted workspace"
    assert f'href="/workspaces/{ws.id}/delete"' not in page


def test_an_admin_still_sees_every_control(keycloak):
    client, _, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(ADMIN_CLAIMS)

    page = client.get(f"/workspaces?ws={ws.id}").text

    assert f'action="/workspaces/{ws.id}/sync"' in page
    assert 'action="/workspaces"' in page
    assert f'href="/workspaces/{ws.id}/delete"' in page


# --- what the machine API and Reports may show -----------------------------


def test_the_machine_api_belongs_to_administrators_once_there_are_accounts(keycloak):
    """Found by reading the diff: the gate authenticated /api/v1 but
    nothing authorised it, and the signed contract has no notion of who is
    asking -- so a reader with a session could list every workspace's name
    there, and create one, while the screens correctly hid them."""
    client, _, db_path, _, sign_in = keycloak
    workspaces.create_workspace(
        name="Hidden Legal", folder_path=str(db_path.parent), db_path=db_path
    )

    sign_in(READER_CLAIMS)
    listed = client.get("/api/v1/workspaces")
    created = client.post(
        "/api/v1/workspaces",
        json={"name": "Mine", "folder_path": str(db_path.parent), "legal_flag": False},
    )

    assert listed.status_code == 403
    assert listed.json()["code"] == "NOT_ALLOWED"
    assert "Hidden Legal" not in listed.text
    assert created.status_code == 403
    assert [w.name for w in workspaces.list_workspaces(db_path=db_path)] == ["Hidden Legal"]

    sign_in(ADMIN_CLAIMS)
    assert client.get("/api/v1/workspaces").status_code == 200


def test_reports_never_name_a_workspace_this_person_may_not_open(keycloak):
    """A run row carries the workspace NAME, and a feedback row carries the
    QUESTION someone asked in it. Both are hidden everywhere else for an
    ungranted workspace; Reports must not be the way out."""
    client, _, db_path, _, sign_in = keycloak
    granted = workspaces.create_workspace(
        name="Granted HR", folder_path=str(db_path.parent), db_path=db_path
    )
    hidden = workspaces.create_workspace(
        name="Hidden Legal", folder_path=str(db_path.parent), db_path=db_path
    )
    with repo.session(db_path) as conn:
        # A run per workspace, so the RUNS table is exercised too and not
        # only the feedback one -- mutating the runs filter survived while
        # this test created no runs at all.
        for workspace_id in (granted.id, hidden.id):
            repo.insert_eval_run(conn, workspace_id=workspace_id, question_total=1)
        for workspace_id, question in (
            (granted.id, "QUESTION-IN-GRANTED"),
            (hidden.id, "QUESTION-IN-HIDDEN"),
        ):
            repo.upsert_answer_feedback(
                conn,
                workspace_id=workspace_id,
                answer_key=f"key-{workspace_id}",
                question=question,
                answer_text="answer",
                verdict="up",
            )
    sign_in(READER_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=granted.id, user_id="kc-reader")

    page = client.get("/reports").text

    assert "Granted HR" in page and "QUESTION-IN-GRANTED" in page
    assert "Hidden Legal" not in page
    assert "QUESTION-IN-HIDDEN" not in page


def test_an_admin_still_sees_every_workspace_in_reports(keycloak):
    client, _, db_path, _, sign_in = keycloak
    workspaces.create_workspace(name="Alpha", folder_path=str(db_path.parent), db_path=db_path)
    workspaces.create_workspace(name="Beta", folder_path=str(db_path.parent), db_path=db_path)
    ws = workspaces.list_workspaces(db_path=db_path)
    with repo.session(db_path) as conn:
        for workspace in ws:
            repo.upsert_answer_feedback(
                conn, workspace_id=workspace.id, answer_key=f"k-{workspace.id}",
                question=f"Q-{workspace.name}", answer_text="a", verdict="up",
            )
    sign_in(ADMIN_CLAIMS)

    page = client.get("/reports").text

    assert "Alpha" in page and "Beta" in page


# --- documents follow the same roles ----------------------------------------


def _upload(client, workspace_id, name, body):
    from urllib.parse import quote

    return client.post(
        f"/workspaces/{workspace_id}/documents",
        content=body,
        headers={"X-File-Name": quote(name), "Content-Type": "application/octet-stream"},
    )


def test_a_reader_cannot_add_or_remove_a_document_but_can_download_one(keycloak):
    """Upload, remove and Sync are curator work; reading a source document
    is what a reader is for. Both halves, because a rule that only ever
    refuses would pass a test that granted nobody anything."""
    client, _, db_path, _, sign_in = keycloak
    folder = db_path.parent / "corpus-roles"
    folder.mkdir(exist_ok=True)
    (folder / "note.txt").write_text("Article 1. Texte.", encoding="utf-8")
    ws = workspaces.create_workspace(name="HR", folder_path=str(folder), db_path=db_path)
    sign_in(READER_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=ws.id, user_id="kc-reader")

    added = _upload(client, ws.id, "new.txt", b"payload")
    removed = client.post(
        f"/workspaces/{ws.id}/documents/note.txt/remove", follow_redirects=False
    )
    downloaded = client.get(f"/workspaces/{ws.id}/documents/note.txt")

    assert added.status_code == 403
    assert not (folder / "new.txt").exists()
    assert removed.status_code == 303
    assert (folder / "note.txt").exists(), "a reader removed a document"
    assert downloaded.status_code == 200
    assert downloaded.content == b"Article 1. Texte."


def test_a_curator_may_add_and_remove_in_a_granted_workspace_only(keycloak):
    client, _, db_path, _, sign_in = keycloak
    mine = db_path.parent / "corpus-mine"
    theirs = db_path.parent / "corpus-theirs"
    for folder in (mine, theirs):
        folder.mkdir(exist_ok=True)
    granted = workspaces.create_workspace(name="Mine", folder_path=str(mine), db_path=db_path)
    other = workspaces.create_workspace(name="Theirs", folder_path=str(theirs), db_path=db_path)
    sign_in(CURATOR_CLAIMS)
    with repo.session(db_path) as conn:
        repo.grant_workspace(conn, workspace_id=granted.id, user_id="kc-curator")

    ok = _upload(client, granted.id, "ok.txt", b"payload")
    refused = _upload(client, other.id, "sneaky.txt", b"payload")

    assert ok.status_code == 201
    assert (mine / "ok.txt").exists()
    assert refused.status_code == 403
    assert not (theirs / "sneaky.txt").exists()
    with repo.session(db_path) as conn:
        actions = [row["action"] for row in repo.list_activity(conn)]
    assert "uploaded a document" in actions


def test_a_document_in_a_workspace_nobody_granted_cannot_be_downloaded(keycloak):
    client, _, db_path, _, sign_in = keycloak
    folder = db_path.parent / "corpus-hidden"
    folder.mkdir(exist_ok=True)
    (folder / "secret.txt").write_text("CONFIDENTIEL", encoding="utf-8")
    hidden = workspaces.create_workspace(name="Hidden", folder_path=str(folder), db_path=db_path)
    sign_in(READER_CLAIMS)

    response = client.get(f"/workspaces/{hidden.id}/documents/secret.txt")

    assert response.status_code == 403
    assert b"CONFIDENTIEL" not in response.content


def test_every_response_carries_the_security_headers(keycloak, tmp_path):
    """Security review, 2026-09-16: the app set none of these. They must be
    on the pages nobody is signed in for too -- the sign-in redirect and
    the refusal pages are exactly what an attacker would frame."""
    from ui.security_headers import HEADERS

    client, _, db_path, _, sign_in = keycloak
    signed_out = client.get("/", follow_redirects=False)
    sign_in(ADMIN_CLAIMS)
    signed_in = client.get("/workspaces")

    # The four values are written out HERE, not read from the code under
    # test: a test that loops over the same tuple the middleware sends
    # passes on `x-frame-options: ALLOWALL`, and passes on an empty tuple
    # without executing a single assertion (review, 2026-09-16).
    for response in (signed_out, signed_in):
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert response.headers["permissions-policy"] == (
            "camera=(), microphone=(), geolocation=()"
        )
    assert len(HEADERS) == 4, "a header was added or removed without a test"
    # The one interesting branch in the middleware: a route that sets a
    # header itself must keep EXACTLY ONE copy of it. This has to reach the
    # real download route -- an unknown id answers 404 long before the
    # route sets anything, and would prove nothing (review, 2026-09-16).
    workspace = workspaces.create_workspace(
        name="Docs", folder_path=str(tmp_path), db_path=db_path
    )
    (tmp_path / "note.md").write_text("# une note", encoding="utf-8")
    download = client.get(f"/workspaces/{workspace.id}/documents/note.md")

    assert download.status_code == 200, download.text[:200]
    assert download.headers.get_list("x-content-type-options") == ["nosniff"]
