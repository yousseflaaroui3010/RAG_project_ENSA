"""The password gate, tested for what it REFUSES as much as what it lets in.

A gate is the one kind of code where the passing test proves the less
interesting half. `test_no_password_configured_lets_everything_through` is
the regression guard for ADR-13 (the local-first default must not change);
everything else here exists to watch the gate say no.

`_credentials_match` is exercised directly rather than only through HTTP,
because the header-parsing failure modes -- not base64, base64 of
non-UTF-8, no colon, wrong scheme -- are easy to get wrong in a way that
turns a rejection into a 500, and a crash is not a refusal.
"""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ui.access_gate import AccessGate, _credentials_match

PASSWORD = "correct horse battery staple"


def _client(password: str) -> TestClient:
    app = FastAPI()
    app.add_middleware(AccessGate, password=password)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"ok": "yes"}

    @app.get("/static/sanad.css")
    def css() -> dict[str, str]:
        return {"ok": "css"}

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "1.0.1"}

    @app.post("/api/v1/health")
    def health_post() -> dict[str, str]:
        # Only GET is exempted -- this route exists purely to prove that a
        # different method on the exact same path still gets gated.
        return {"status": "ok", "version": "1.0.1"}

    return TestClient(app)


def _basic(user: str, password: str) -> dict[str, str]:
    raw = f"{user}:{password}".encode()
    return {"Authorization": "Basic " + base64.b64encode(raw).decode()}


# --- the default: no gate at all (ADR-13) --------------------------------


def test_no_password_configured_lets_everything_through():
    """THE REGRESSION GUARD FOR THE LOCAL-FIRST DEFAULT. With no password
    set, this middleware must be invisible -- a developer running the app
    on a laptop, and every other test in this suite, gets the behaviour
    that existed before the gate was written."""
    assert _client("").get("/").status_code == 200


# --- the gate refusing -----------------------------------------------------


def test_no_authorization_header_is_refused():
    response = _client(PASSWORD).get("/")
    assert response.status_code == 401


def test_a_refusal_asks_for_credentials():
    """Without this header a browser never shows a login prompt, so the
    gate would look like a broken site rather than a locked one."""
    response = _client(PASSWORD).get("/")
    assert response.headers["www-authenticate"].startswith("Basic ")


def test_the_wrong_password_is_refused():
    response = _client(PASSWORD).get("/", headers=_basic("sanad", "not the password"))
    assert response.status_code == 401


def test_a_password_that_is_a_prefix_of_the_real_one_is_refused():
    """The length check runs before the comparison; a prefix must not be
    treated as a match by any path through it."""
    response = _client(PASSWORD).get("/", headers=_basic("sanad", PASSWORD[:-1]))
    assert response.status_code == 401


def test_an_empty_supplied_password_is_refused():
    response = _client(PASSWORD).get("/", headers=_basic("sanad", ""))
    assert response.status_code == 401


@pytest.mark.parametrize(
    "header",
    [
        "",
        "Basic",
        "Basic ",
        "Bearer " + base64.b64encode(b"sanad:x").decode(),
        "Basic not-base64!!",
        "Basic " + base64.b64encode(b"no-colon-here").decode(),
        "Basic " + base64.b64encode(b"\xff\xfe invalid utf-8").decode(),
    ],
)
def test_a_malformed_header_is_refused_and_never_raises(header: str):
    """Each of these is a caller error. The gate must answer 401, not 500:
    a traceback is not a refusal, and it leaks more than it withholds."""
    assert _credentials_match(header, PASSWORD) is False


def test_a_missing_header_is_refused():
    assert _credentials_match(None, PASSWORD) is False


# --- the gate allowing -----------------------------------------------------


def test_the_right_password_is_let_in():
    response = _client(PASSWORD).get("/", headers=_basic("sanad", PASSWORD))
    assert response.status_code == 200
    assert response.json() == {"ok": "yes"}


def test_the_user_id_is_ignored():
    """One shared secret, no accounts. Any user-id with the right password
    is in -- stated as a test so nobody later reads the gate as
    per-user authentication, which it is not."""
    response = _client(PASSWORD).get("/", headers=_basic("anybody at all", PASSWORD))
    assert response.status_code == 200


def test_a_password_containing_a_colon_works():
    """RFC 7617: everything after the FIRST colon is the password. Getting
    this wrong silently truncates any password with a colon in it, which
    a generated secret can easily contain."""
    tricky = "a:b:c:d"
    response = _client(tricky).get("/", headers=_basic("sanad", tricky))
    assert response.status_code == 200


def test_static_assets_load_before_the_password_is_given():
    """UX spec 4: the stylesheet must load or the browser's own login
    prompt renders against an unstyled page. These assets carry no
    workspace data."""
    assert _client(PASSWORD).get("/static/sanad.css").status_code == 200


# --- the ST-05 Railway liveness exemption ----------------------------------


def test_health_check_is_open_with_no_password():
    """Railway (and any platform health check) cannot carry a password, and
    a gated health check reads to the platform as 'never came up' rather
    than 'locked'. This route answers only status and version -- nothing
    an operator would mind a stranger reading."""
    response = _client(PASSWORD).get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "1.0.1"}


def test_every_other_route_still_needs_the_password():
    """The exemption is narrow: one exact (method, path) pair, not a
    prefix. A POST to the same path, and every other route, stays gated."""
    client = _client(PASSWORD)
    assert client.get("/").status_code == 401
    assert client.post("/api/v1/health").status_code == 401
