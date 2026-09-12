"""A password in front of every route, for the deployed case only.

WHY THIS EXISTS AND WHY IT IS OFF BY DEFAULT.

`app.py::main` binds 127.0.0.1 and says why in its own comment: ADR-13 and
LD-07, "single user, no authentication, and nothing about this server is
safe to expose on a network." That is a correct decision for the product
the architecture describes -- local-first, documents never leaving the
machine -- and NOTHING HERE CHANGES IT. With `access_password` unset, which
is the default and what every developer and every test gets, this module
adds no behaviour whatsoever.

What it covers is the one case the signed architecture did not anticipate:
a container published on a public URL for a demo (ST-05, Railway hosting).
There, "no authentication" stops being a reasonable default and becomes a
way to hand a workspace of legal documents to anyone who guesses the
address. The honest options were to add a gate or to not deploy; this is
the gate.

WHAT THIS IS NOT. This is a shared bearer secret, not user accounts. There
is one password for the whole instance, no identities, no roles, no
sessions, no lockout and no rate limit. It raises the cost of casual access
from zero to "know the password"; it does not make the instance safe to
put real client data behind. Anyone reading this file before relying on it
should read that sentence twice -- it is the whole security model.

CONSTANT-TIME COMPARISON IS NOT DECORATION HERE. `secrets.compare_digest`
is used because `==` on a secret returns as soon as two bytes differ, and
the time it took to say no is itself information. The project's own law
names this. Length is compared first, on the encoded bytes, because
`compare_digest` is only constant-time for inputs of equal length.
"""

from __future__ import annotations

import base64
import binascii
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# UX spec 4: the stylesheet and the vendored script must load before the
# operator has typed anything, or the login prompt renders unstyled. These
# are static assets that carry no workspace data.
_OPEN_PREFIXES = ("/static/",)

# The one exact route exempted by path AND method, not by prefix: a
# platform's liveness probe (Railway's own health check, and anything else
# polling this before a human ever opens the site) has no way to carry a
# password, and a gated health check reads to the platform as "the
# container never came up" rather than "the container is locked". Exempted
# because of what this ONE route returns, not because health checks in
# general are safe: `api/routes.py::health_check` answers only
# `{"status": "ok", "version": ...}`, no workspace data, no document
# content, nothing an operator would mind a stranger reading.
_HEALTH_METHOD = "GET"
_HEALTH_PATH = "/api/v1/health"

_UNAUTHORIZED = Response(
    content="Authentication required.",
    status_code=401,
    headers={"WWW-Authenticate": 'Basic realm="Sanad", charset="UTF-8"'},
)


def _credentials_match(header: str | None, expected_password: str) -> bool:
    """True only for a well-formed Basic header whose password matches.

    Every failure path returns False rather than raising: a malformed
    header is a caller error, not a server fault, and an exception here
    would turn a bad password into a 500 with a traceback.
    """
    if not header:
        return False

    scheme, _, encoded = header.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False

    try:
        decoded = base64.b64decode(encoded, validate=True).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return False

    # RFC 7617: everything after the FIRST colon is the password, because a
    # password is allowed to contain colons and a user-id is not.
    _, separator, supplied = decoded.partition(":")
    if not separator:
        return False

    supplied_bytes = supplied.encode("utf-8")
    expected_bytes = expected_password.encode("utf-8")

    # Length first. `compare_digest` is only constant-time when both
    # operands are the same length, so comparing straight away would leak
    # the password's length through timing.
    if len(supplied_bytes) != len(expected_bytes):
        return False
    return secrets.compare_digest(supplied_bytes, expected_bytes)


class AccessGate(BaseHTTPMiddleware):
    """Refuses every request that does not carry the shared password.

    Installed unconditionally by `app.create_app`; INERT unless a password
    is configured. That ordering is deliberate -- a gate that has to be
    remembered at each deploy is a gate that will be forgotten once.
    """

    def __init__(self, app: ASGIApp, *, password: str) -> None:
        super().__init__(app)
        self._password = password

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        if not self._password:
            # The local-first default (ADR-13). No password configured
            # means no gate, and the app behaves exactly as it did before
            # this module existed.
            return await call_next(request)

        if request.url.path.startswith(_OPEN_PREFIXES):
            return await call_next(request)

        if request.method == _HEALTH_METHOD and request.url.path == _HEALTH_PATH:
            return await call_next(request)

        if not _credentials_match(request.headers.get("authorization"), self._password):
            # Deliberately identical for "no header", "malformed header"
            # and "wrong password": telling a caller WHICH of those it was
            # tells an attacker whether they have the right shape.
            return _UNAUTHORIZED

        return await call_next(request)
