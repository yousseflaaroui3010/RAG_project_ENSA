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


def test_a_signed_in_person_is_recorded_once(keycloak):
    client, _, db_path, _, sign_in = keycloak

    sign_in(ADMIN_CLAIMS)
    sign_in(ADMIN_CLAIMS)

    with repo.session(db_path) as conn:
        users = repo.list_users(conn)
    assert len(users) == 1
    assert users[0]["username"] == "amina"
    assert len(_sessions(db_path)) == 2, "each sign-in is its own browser session"


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


def _seed_report(
    db_path, tmp_path, *, answer: str, owner: str | None = "kc-someone-else"
) -> tuple[str, str]:
    """A workspace with one evaluation answer in it -- by default someone
    ELSE's private one (ST-54); `owner=None` makes it shared."""
    report_path = tmp_path / "run.json"
    report_path.write_text("{}", encoding="utf-8")
    with repo.session(db_path) as conn:
        workspace_id = repo.create_workspace(
            conn, name="Salaires direction", folder_path=str(tmp_path), owner_user_id=owner
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


def test_a_report_of_someone_elses_private_workspace_is_not_readable(
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


def test_the_owner_reads_their_own_report(keycloak, tmp_path):
    """The other side: the check must not lock out the person who may look."""
    client, _, db_path, _, sign_in = keycloak
    answer = "le salaire du directeur est de 42 000 dirhams"
    run_id, _ = _seed_report(db_path, tmp_path, answer=answer, owner=READER_CLAIMS["sub"])
    sign_in(READER_CLAIMS)

    page = client.get(f"/reports/{run_id}")

    assert page.status_code == 200
    assert "Salaires direction" in page.text


def test_anyone_reads_the_report_of_a_shared_workspace(keycloak, tmp_path):
    """The shared demo is readable by everyone, reports included."""
    client, _, db_path, _, sign_in = keycloak
    answer = "le salaire du directeur est de 42 000 dirhams"
    run_id, _ = _seed_report(db_path, tmp_path, answer=answer, owner=None)
    sign_in(READER_CLAIMS)

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

    assert runtime.active_for(READER_CLAIMS["sub"]) is None


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

    assert runtime.active_for(READER_CLAIMS["sub"]) != workspace_id


def test_the_panel_never_shows_someone_elses_workspace(keycloak, tmp_path):
    """Security review, 2026-09-16: the panel the Workspaces page polls
    once handed out a workspace's name, folder path and file table without
    the checks the page itself made. It must hide someone else's private
    workspace even when asked for it by id."""
    client, _, db_path, _, sign_in = keycloak
    _, workspace_id = _seed_report(db_path, tmp_path, answer="x")
    sign_in(READER_CLAIMS)

    panel = client.get(f"/workspaces/panel?ws={workspace_id}")

    assert "Salaires direction" not in panel.text


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


def test_a_person_with_no_role_uses_sanad_like_anyone(keycloak):
    """ST-54: roles are gone. An account the realm gives no Sanad role at
    all -- the old "ask an administrator" dead end -- reads the shared
    workspace like everyone else."""
    client, _, db_path, _, sign_in = keycloak
    workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(NO_ROLE_CLAIMS)

    for path in ("/", "/workspaces", "/reports"):
        page = client.get(path)
        assert page.status_code == 200, path
    assert "HR" in client.get("/").text


def test_anyone_signed_in_creates_a_workspace_and_owns_it(keycloak):
    client, _, db_path, _, sign_in = keycloak
    sign_in(READER_CLAIMS)

    response = client.post(
        "/workspaces",
        data={"name": "Mine", "folder_path": str(db_path.parent)},
        follow_redirects=False,
    )

    assert response.status_code == 303
    [created] = workspaces.list_workspaces(db_path=db_path)
    with repo.session(db_path) as conn:
        assert repo.workspace_owners(conn) == {created.id: READER_CLAIMS["sub"]}
    sign_in(CURATOR_CLAIMS)
    assert "Mine" not in client.get("/workspaces").text, "private to its owner"


def test_only_the_owner_deletes_a_workspace(keycloak):
    """Nobody deletes a shared workspace or someone else's; the owner
    deletes their own. Both halves, so a rule that always refuses fails."""
    client, _, db_path, _, sign_in = keycloak
    shared = workspaces.create_workspace(
        name="Shared", folder_path=str(db_path.parent), db_path=db_path
    )
    theirs = workspaces.create_workspace(
        name="Theirs", folder_path=str(db_path.parent), db_path=db_path,
        owner_user_id=CURATOR_CLAIMS["sub"],
    )
    sign_in(READER_CLAIMS)

    for ws in (shared, theirs):
        client.post(f"/workspaces/{ws.id}/delete", follow_redirects=False)
    assert {w.id for w in workspaces.list_workspaces(db_path=db_path)} == {shared.id, theirs.id}

    sign_in(CURATOR_CLAIMS)
    client.post(f"/workspaces/{theirs.id}/delete", follow_redirects=False)
    assert [w.id for w in workspaces.list_workspaces(db_path=db_path)] == [shared.id]


def test_someone_elses_workspace_is_not_even_listed(keycloak):
    client, _, db_path, _, sign_in = keycloak
    workspaces.create_workspace(
        name="Shared HR", folder_path=str(db_path.parent), db_path=db_path
    )
    workspaces.create_workspace(
        name="Hidden Legal", folder_path=str(db_path.parent), db_path=db_path,
        owner_user_id=CURATOR_CLAIMS["sub"],
    )
    sign_in(READER_CLAIMS)

    for path in ("/workspaces", "/"):
        page = client.get(path).text
        assert "Shared HR" in page, path
        assert "Hidden Legal" not in page, path


def test_only_the_owner_starts_a_sync(keycloak):
    client, runtime, db_path, _, sign_in = keycloak
    mine = workspaces.create_workspace(
        name="Mine", folder_path=str(db_path.parent), db_path=db_path,
        owner_user_id=CURATOR_CLAIMS["sub"],
    )
    shared = workspaces.create_workspace(
        name="Shared", folder_path=str(db_path.parent), db_path=db_path
    )
    started: list[str] = []
    runtime.start_sync = started.append  # this instance only
    sign_in(CURATOR_CLAIMS)

    refused = client.post(f"/workspaces/{shared.id}/sync", follow_redirects=False)
    client.post(f"/workspaces/{mine.id}/sync", follow_redirects=False)

    assert refused.status_code == 303
    assert started == [mine.id]


# --- one transcript per person ----------------------------------------------


def test_two_people_never_share_a_conversation(keycloak):
    client, runtime, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)

    # A grant points at an app_user row, so the person has to have signed
    # in at least once before they can be granted anything.
    sign_in(READER_CLAIMS)
    sign_in(CURATOR_CLAIMS)
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
    """The reader, signed in, owning one workspace (ST-54)."""
    client, runtime, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(
        name=name, folder_path=str(db_path.parent), db_path=db_path,
        owner_user_id=READER_CLAIMS["sub"],
    )
    sign_in(READER_CLAIMS)
    return client, runtime, db_path, sign_in, ws


def _shared_between_two(keycloak):
    """One SHARED workspace both the reader and the curator can see, with
    the reader signed in -- for tests where two people meet in it and only
    conversation ownership may keep them apart."""
    client, runtime, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    return client, runtime, db_path, sign_in, ws


def _stored(runtime, user_id, ws_id, question, answer):
    conversation = runtime.new_conversation(user_id, ws_id)
    conversation.messages.append(Message(kind=MessageKind.USER, text=question))
    conversation.messages.append(Message(kind=MessageKind.ANSWER, text=answer))
    runtime.save_conversation(conversation)
    return conversation


def _with_a_source(runtime, user_id, ws_id, passage_text):
    """A stored conversation whose answer has one real source card, so the
    passage viewer WOULD show `passage_text` if it served this card."""
    from ui.conversation import Passage, SourceCard, segments_for

    card = SourceCard(
        index=0,
        file_name="contrat.pdf",
        section_label="Article 1",
        passages=(Passage(
            file_name="contrat.pdf", section_label="Article 1",
            segments=segments_for(passage_text, []), highlighted=False,
        ),),
    )
    conversation = runtime.new_conversation(user_id, ws_id)
    conversation.messages.append(Message(kind=MessageKind.USER, text="a question"))
    conversation.messages.append(
        Message(kind=MessageKind.ANSWER, text="an answer", sources=(card,))
    )
    runtime.save_conversation(conversation)
    return conversation


def test_the_passage_viewer_serves_only_the_owners_card(keycloak):
    """Positive control first -- the owner DOES see the card's text -- so
    the refusal below is proven to be the owner check, not an empty card."""
    client, runtime, db_path, sign_in, ws = _shared_between_two(keycloak)
    sign_in(CURATOR_CLAIMS)
    theirs = _with_a_source(runtime, "kc-curator", ws.id, "CURATOR-PASSAGE-TEXT")
    assert "CURATOR-PASSAGE-TEXT" in client.get(f"/chat/passage/{theirs.id}/1/0").text

    sign_in(READER_CLAIMS)

    assert "CURATOR-PASSAGE-TEXT" not in client.get(f"/chat/passage/{theirs.id}/1/0").text


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
    client, runtime, db_path, sign_in, ws = _shared_between_two(keycloak)
    sign_in(CURATOR_CLAIMS)
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
    assert f'name="conversation_id" value="{kept.id}"' not in empty, (
        "the empty chat must not continue the kept one"
    )
    assert f'href="/?c={kept.id}"' in empty, "the kept one is one click away"


def test_someone_elses_conversation_is_not_found_on_every_route(keycloak):
    """Not yours and does not exist are the same 404 -- on the page that
    only renders too, not just on the actions -- and nothing changes."""
    client, runtime, db_path, sign_in, ws = _shared_between_two(keycloak)
    sign_in(CURATOR_CLAIMS)
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


def test_a_conversation_in_someone_elses_private_workspace_is_not_found(keycloak):
    """A stored conversation in a workspace the person cannot see must not
    be reachable -- by id, through any route."""
    client, runtime, db_path, _, _ = _reader_with_a_workspace(keycloak)
    locked = workspaces.create_workspace(
        name="Locked", folder_path=str(db_path.parent), db_path=db_path,
        owner_user_id="kc-someone-else",
    )
    stranded = _with_a_source(runtime, "kc-reader", locked.id, "LOCKED-PASSAGE-TEXT")

    assert client.get(f"/chat/conversations/{stranded.id}").status_code == 404
    assert client.post(
        f"/chat/conversations/{stranded.id}/delete", follow_redirects=False
    ).status_code == 404
    passage = client.get(f"/chat/passage/{stranded.id}/1/0").text
    assert "LOCKED-PASSAGE-TEXT" not in passage
    assert stranded.id in runtime.conversations, "still stored and live: only the route refused"


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


def test_a_shared_workspace_offers_no_control_to_change_it(keycloak):
    """A button that cannot work is a dead control -- the rule the theme
    toggle, the sample questions and the drop zone already follow. On a
    shared workspace a non-owner may read, ask and create their own."""
    client, _, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)

    page = client.get(f"/workspaces?ws={ws.id}").text

    assert "HR" in page
    assert f'action="/workspaces/{ws.id}/sync"' not in page
    assert f'href="/workspaces/{ws.id}/delete"' not in page
    assert f'action="/workspaces/{ws.id}/rename"' not in page
    assert "data-dropzone" not in page
    assert 'role="note"' in page, "the page says why: it is shared"
    assert 'action="/workspaces"' in page, "anyone may still create their own"


def test_the_owner_sees_every_control_on_their_own_workspace(keycloak):
    client, _, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(
        name="Mine", folder_path=str(db_path.parent), db_path=db_path,
        owner_user_id=CURATOR_CLAIMS["sub"],
    )
    sign_in(CURATOR_CLAIMS)

    page = client.get(f"/workspaces?ws={ws.id}").text

    assert f'action="/workspaces/{ws.id}/sync"' in page
    assert f'href="/workspaces/{ws.id}/delete"' in page
    assert f'action="/workspaces/{ws.id}/rename"' in page
    assert "data-dropzone" in page
    assert 'role="note"' not in page


# --- what the machine API and Reports may show -----------------------------


def test_the_machine_api_is_closed_to_everyone_signed_in(keycloak):
    """The signed contract lists every workspace with no notion of who is
    asking, and creates one from any server folder. With private
    workspaces and open sign-up (ST-54) it is closed with accounts on --
    for everyone, the person the realm still calls admin included."""
    client, _, db_path, _, sign_in = keycloak
    workspaces.create_workspace(
        name="Hidden Legal", folder_path=str(db_path.parent), db_path=db_path,
        owner_user_id=CURATOR_CLAIMS["sub"],
    )

    for claims in (READER_CLAIMS, ADMIN_CLAIMS):
        sign_in(claims)
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
    assert client.get("/api/v1/health").status_code == 200


def test_reports_never_name_a_workspace_this_person_may_not_open(keycloak):
    """A run row carries the workspace NAME, and a feedback row carries the
    QUESTION someone asked. Someone else's private workspace shows neither.
    A SHARED one shows its runs but not its feedback: that would put one
    person's questions in front of everyone (ST-54). Your own shows both."""
    client, _, db_path, _, sign_in = keycloak
    mine = workspaces.create_workspace(
        name="My HR", folder_path=str(db_path.parent), db_path=db_path,
        owner_user_id=READER_CLAIMS["sub"],
    )
    shared = workspaces.create_workspace(
        name="Shared Demo", folder_path=str(db_path.parent), db_path=db_path
    )
    hidden = workspaces.create_workspace(
        name="Hidden Legal", folder_path=str(db_path.parent), db_path=db_path,
        owner_user_id=CURATOR_CLAIMS["sub"],
    )
    with repo.session(db_path) as conn:
        for ws in (mine, shared, hidden):
            repo.insert_eval_run(conn, workspace_id=ws.id, question_total=1)
            repo.upsert_answer_feedback(
                conn,
                workspace_id=ws.id,
                answer_key=f"key-{ws.id}",
                question=f"QUESTION-IN-{ws.name.upper().replace(' ', '-')}",
                answer_text="answer",
                verdict="up",
            )
    sign_in(READER_CLAIMS)

    page = client.get("/reports").text

    assert "My HR" in page and "QUESTION-IN-MY-HR" in page
    assert "Shared Demo" in page
    assert "QUESTION-IN-SHARED-DEMO" not in page
    assert "Hidden Legal" not in page and "QUESTION-IN-HIDDEN-LEGAL" not in page


# --- documents follow the same roles ----------------------------------------


def _upload(client, workspace_id, name, body):
    from urllib.parse import quote

    return client.post(
        f"/workspaces/{workspace_id}/documents",
        content=body,
        headers={"X-File-Name": quote(name), "Content-Type": "application/octet-stream"},
    )


def test_a_shared_workspace_can_be_read_but_not_changed(keycloak):
    """Upload and remove are the owner's; reading a source document is what
    everyone may do on a shared workspace. Both halves, because a rule that
    only ever refuses would pass a test that allowed nobody anything."""
    client, _, db_path, _, sign_in = keycloak
    folder = db_path.parent / "corpus-shared"
    folder.mkdir(exist_ok=True)
    (folder / "note.txt").write_text("Article 1. Texte.", encoding="utf-8")
    ws = workspaces.create_workspace(name="HR", folder_path=str(folder), db_path=db_path)
    sign_in(READER_CLAIMS)

    added = _upload(client, ws.id, "new.txt", b"payload")
    removed = client.post(
        f"/workspaces/{ws.id}/documents/note.txt/remove", follow_redirects=False
    )
    downloaded = client.get(f"/workspaces/{ws.id}/documents/note.txt")

    assert added.status_code == 403
    assert not (folder / "new.txt").exists()
    assert removed.status_code == 303
    assert (folder / "note.txt").exists(), "a non-owner removed a document"
    assert downloaded.status_code == 200
    assert downloaded.content == b"Article 1. Texte."


def test_the_owner_adds_documents_to_their_own_workspace_only(keycloak):
    client, _, db_path, _, sign_in = keycloak
    mine = db_path.parent / "corpus-mine"
    shared = db_path.parent / "corpus-shared"
    for folder in (mine, shared):
        folder.mkdir(exist_ok=True)
    own = workspaces.create_workspace(
        name="Mine", folder_path=str(mine), db_path=db_path,
        owner_user_id=CURATOR_CLAIMS["sub"],
    )
    other = workspaces.create_workspace(name="Shared", folder_path=str(shared), db_path=db_path)
    sign_in(CURATOR_CLAIMS)

    ok = _upload(client, own.id, "ok.txt", b"payload")
    refused = _upload(client, other.id, "sneaky.txt", b"payload")

    assert ok.status_code == 201
    assert (mine / "ok.txt").exists()
    assert refused.status_code == 403
    assert not (shared / "sneaky.txt").exists()


def test_a_document_in_someone_elses_workspace_cannot_be_downloaded(keycloak):
    client, _, db_path, _, sign_in = keycloak
    folder = db_path.parent / "corpus-hidden"
    folder.mkdir(exist_ok=True)
    (folder / "secret.txt").write_text("CONFIDENTIEL", encoding="utf-8")
    hidden = workspaces.create_workspace(
        name="Hidden", folder_path=str(folder), db_path=db_path,
        owner_user_id=CURATOR_CLAIMS["sub"],
    )
    sign_in(READER_CLAIMS)

    response = client.get(f"/workspaces/{hidden.id}/documents/secret.txt")

    assert response.status_code == 403
    assert b"CONFIDENTIEL" not in response.content


def test_a_non_owner_can_neither_rename_nor_reflag_a_workspace(keycloak):
    """The hidden buttons are not the protection; the routes are. Posted by
    hand, a rename or legal-flag change on a shared workspace or on someone
    else's changes nothing -- and the owner's own does change."""
    client, _, db_path, _, sign_in = keycloak
    shared = workspaces.create_workspace(
        name="Shared", folder_path=str(db_path.parent), db_path=db_path
    )
    theirs = workspaces.create_workspace(
        name="Theirs", folder_path=str(db_path.parent), db_path=db_path,
        owner_user_id=CURATOR_CLAIMS["sub"],
    )
    sign_in(READER_CLAIMS)

    for ws in (shared, theirs):
        client.post(f"/workspaces/{ws.id}/rename", data={"name": "Taken over"})
        client.post(f"/workspaces/{ws.id}/legal-flag", data={"legal_flag": "on"})

    after = {w.id: w for w in workspaces.list_workspaces(db_path=db_path)}
    assert after[shared.id].name == "Shared" and not after[shared.id].legal_flag
    assert after[theirs.id].name == "Theirs" and not after[theirs.id].legal_flag

    sign_in(CURATOR_CLAIMS)
    client.post(f"/workspaces/{theirs.id}/rename", data={"name": "Renamed by owner"})
    client.post(f"/workspaces/{theirs.id}/legal-flag", data={"legal_flag": "on"})
    owned = workspaces.get_workspace(workspace_id=theirs.id, db_path=db_path)
    assert owned.name == "Renamed by owner" and owned.legal_flag


def test_an_id_that_names_no_workspace_is_never_treated_as_shared(keycloak):
    """A missing workspace has no owner either -- and "no owner" is what
    SHARED means. The check must ask whether it exists first, or any
    made-up id would pass as a shared workspace."""
    import types

    from app import may_manage, may_see

    _, runtime, db_path, _, _ = keycloak
    shared = workspaces.create_workspace(
        name="Shared", folder_path=str(db_path.parent), db_path=db_path
    )
    reader = auth.Principal(id="kc-reader", username="omar", display_name="Omar")
    request = types.SimpleNamespace(state=types.SimpleNamespace(principal=reader))

    assert may_see(runtime, request, shared.id) is True
    assert may_manage(runtime, request, shared.id) is False
    assert may_see(runtime, request, "no-such-workspace") is False
    assert may_manage(runtime, request, "no-such-workspace") is False

def test_the_admin_pages_are_gone(keycloak):
    """YL's ruling, 2026-09-18: no admin page, no grants, no roles."""
    client, _, _, _, sign_in = keycloak
    sign_in(ADMIN_CLAIMS)

    assert client.get("/admin").status_code == 404
    assert client.post("/admin/grants", data={"user_id": "x"}).status_code == 404
    assert client.post("/admin/people/kc-reader/sign-out").status_code == 404
    assert 'href="/admin"' not in client.get("/workspaces").text


def test_each_person_keeps_their_own_selected_workspace(keycloak):
    """The selected workspace used to be one value for the whole server, so
    one person switching moved everyone (cold review of #147)."""
    client, runtime, db_path, _, sign_in = keycloak
    first = workspaces.create_workspace(name="A", folder_path=str(db_path.parent), db_path=db_path)
    second = workspaces.create_workspace(
        name="B", folder_path=str(db_path.parent), db_path=db_path
    )
    sign_in(READER_CLAIMS)
    client.post("/workspace", data={"workspace_id": second.id}, follow_redirects=False)
    sign_in(CURATOR_CLAIMS)
    client.post("/workspace", data={"workspace_id": first.id}, follow_redirects=False)

    assert runtime.active_for(READER_CLAIMS["sub"]) == second.id
    assert runtime.active_for(CURATOR_CLAIMS["sub"]) == first.id


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
