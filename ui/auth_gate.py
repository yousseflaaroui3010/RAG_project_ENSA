"""Who is signed in, attached to every request (S6).

Installed beside `AccessGate`, and INERT unless `AUTH_MODE` is
`keycloak` -- the local-first default (ADR-13) and the published demo's
shared password both keep behaving exactly as they did, which is the same
rule `AccessGate` itself follows.

With `keycloak` on, this does two things and no more:

* attaches `request.state.principal` (who, and with which roles) so no
  route has to look a session up itself;
* refuses anything that is not signed in, by sending a browser to the
  sign-in page and answering an API caller with 401.

IT DOES NOT DECIDE PERMISSIONS. Whether a signed-in person may delete a
workspace is `ui/auth.py`'s question, asked by the route that does the
deleting. A middleware that also enforced permissions would have to know
every route's meaning, and would be the only place to look when one of
them is wrong.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp

from config import get_settings
from db import repo
from ui import auth

# Reachable without a session: the stylesheet and script (a sign-in page
# must not render unstyled), the platform's liveness probe, and the
# sign-in routes themselves -- a login that required a login could never
# be completed.
_OPEN_PREFIXES = ("/static/", "/auth/")
_HEALTH = ("GET", "/api/v1/health")

# `last_seen_at` is a nicety, not a lock. The chat screen polls several
# times a second while an answer is being written, and writing a row on
# every poll would be a database write per 300ms for nothing.
_TOUCH_AFTER_SECONDS = 300


class AuthGate(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, db_path: str | Path | None = None) -> None:
        super().__init__(app)
        self._db_path = db_path

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if get_settings().auth_mode != auth.MODE_KEYCLOAK:
            # Local and password modes: one unrestricted principal, exactly
            # the behaviour every release before S6 had.
            request.state.principal = auth.LOCAL
            return await call_next(request)

        # WHO FIRST, THEN WHETHER. An open path still gets the principal
        # attached when there is a session behind it: `/auth/logout` is
        # open (a sign-out cannot require a sign-in), and it has to know
        # whose session it is deleting. Skipping the lookup there left
        # sign-out recording nothing and clearing nobody's transcript.
        request.state.principal = None
        token = request.cookies.get(auth.SESSION_COOKIE)
        if token:
            with repo.session(self._db_path) as conn:
                row = repo.get_session(conn, auth.hash_token(token))
                if row is not None:
                    request.state.principal = auth.principal_from_session(row)
                    if _is_stale(row["last_seen_at"]):
                        repo.touch_session(conn, row["token_hash"])

        path = request.url.path
        if path.startswith(_OPEN_PREFIXES) or (request.method, path) == _HEALTH:
            return await call_next(request)
        if request.state.principal is None:
            return _refuse(request)
        return await call_next(request)


def _is_stale(last_seen_at: str) -> bool:
    try:
        seen = datetime.fromisoformat(last_seen_at)
    except ValueError:
        return True
    return datetime.now(UTC) - seen > timedelta(seconds=_TOUCH_AFTER_SECONDS)


def _refuse(request: Request) -> Response:
    """A browser is sent to sign in; a machine is told plainly.

    The split is on the ROUTE, plus the one header a script sets on
    itself. `/api/v1` is a contract (openapi, ADR-13) and a 303 to an HTML
    page would be a surprising answer there; the chat and sync polls
    (`X-Requested-With: fetch`) would silently swallow a redirect and show
    a stale screen for ever. Everything else is a browser looking at a
    page, whatever its Accept header happens to say -- keying this on
    Accept alone sent a plain `GET /` to a 401 instead of the sign-in
    page."""
    polling = request.headers.get("x-requested-with", "").lower() == "fetch"
    if request.url.path.startswith("/api/") or polling:
        return JSONResponse(
            status_code=401,
            content={"code": "NOT_AUTHENTICATED", "message": "Sign in to use Sanad."},
        )
    return RedirectResponse("/auth/login", status_code=303)
