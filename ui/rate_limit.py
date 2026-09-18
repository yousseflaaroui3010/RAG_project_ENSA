"""ST-55: a cap on how often one person, or one address, may do the
costly or abusable things (known issue "Nothing is rate limited").

WHAT IS CAPPED, AND WHY EACH:

* starting sign-in (`/auth/login`), per client address -- sign-up is open to
  anyone. Only the FIRST step is counted: counting the return from Keycloak
  too made one sign-in cost two, and could refuse someone AFTER they had
  typed a correct password (review of #150). Set far above a class sharing
  one school address; Keycloak's own brute-force protection guards the
  passwords themselves;
* asking (`POST /chat/ask`), per person -- every question is a PAID model call;
* starting a Sync, per person -- the heaviest work the server does;
* creating a workspace and uploading a document, per person -- since ST-54
  anyone signed in may do both, and each costs disk on the shared volume;
* every other change a person can post (new conversation, feedback, history
  deletion, renames, flags, deletions, document removal), per person --
  cheap one by one, but a script could churn the database.

ONLY WITH ACCOUNTS ON (`AUTH_MODE=keycloak`). The login-free modes are one
person on their own machine (ADR-13); capping them would only get in their
way.

IN PROCESS, NO NEW DEPENDENCY. A sliding window per (rule, key): the times of
the last requests, oldest dropped as they age out. The demo runs ONE process
(Railway, one replica), so one process's memory is the whole picture; a
second replica would need a shared store, and DECISIONS says so. The number
of keys is bounded (`_MAX_KEYS`): when full, the least recently used key
goes. Keys are kept in order of last use, and a use either records a hit or
is refused while the window is full, so the least recently used keys are
exactly the ones whose windows have passed -- they go before any live one.
(A separate "clear expired keys first" pass was written after review of
#150 and removed: it could never change which key went.)

THE LIMITS ARE CONSTANTS HERE, not settings, for one recorded reason: every
setting must be documented in `.env.example`, which the coding agent is not
allowed to open (DECISIONS 2026-09-18, ST-55). Moving them into config.py is
a two-line change once someone documents them there.

THE CLIENT ADDRESS. Behind a proxy (the configured callback is https -- the
same signal `_cookies_are_secure` uses), it is the LAST entry of
`X-Forwarded-For`, the one the proxy itself appended; earlier entries are
whatever the client chose to send. Without a proxy (a laptop, a local
Docker), the header is anyone's to invent, so it is ignored and the
socket's own address is used (review of #150).
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass
from html import escape
from urllib.parse import urlsplit

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from ui import auth, i18n
from ui.i18n.request import context_language

_MAX_KEYS = 10_000


@dataclass(frozen=True)
class Rule:
    name: str
    method: str
    path: re.Pattern[str]
    limit: int
    window_seconds: int
    # "person" keys by the signed-in person, "address" by the client address.
    per: str


RULES: tuple[Rule, ...] = (
    Rule("sign-in", "GET", re.compile(r"^/auth/login$"), 60, 300, "address"),
    Rule("ask", "POST", re.compile(r"^/chat/ask$"), 20, 600, "person"),
    Rule("sync", "POST", re.compile(r"^/workspaces/[^/]+/sync$"), 20, 3600, "person"),
    Rule("create-workspace", "POST", re.compile(r"^/workspaces$"), 10, 3600, "person"),
    Rule("upload", "POST", re.compile(r"^/workspaces/[^/]+/documents$"), 500, 3600, "person"),
    Rule(
        "change",
        "POST",
        re.compile(
            r"^/chat/(new|feedback|history/delete|conversations/[^/]+/(rename|delete))$"
            r"|^/workspaces/[^/]+/(rename|legal-flag|delete|documents/[^/]+/remove)$"
        ),
        120,
        600,
        "person",
    ),
)


def _behind_a_proxy() -> bool:
    return urlsplit(auth.get_settings().keycloak_redirect_url).scheme == "https"


def client_address(request: Request, *, behind_proxy: bool | None = None) -> str:
    """The address to key sign-in attempts by (see the module docstring)."""
    proxied = _behind_a_proxy() if behind_proxy is None else behind_proxy
    if proxied:
        forwarded = request.headers.get("x-forwarded-for", "")
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1]
    return request.client.host if request.client else "unknown"


class Limiter:
    """Sliding windows, one per (rule, key). Thread-safe: Starlette runs
    plain `def` routes on a thread pool, and every request passes here."""

    def __init__(self, clock=time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._hits: OrderedDict[tuple[str, str], deque[float]] = OrderedDict()

    def take(self, rule: Rule, key: str) -> int:
        """Record one request. 0 if allowed, else the whole seconds to wait
        before the oldest request in the window ages out."""
        slot = (rule.name, key)
        with self._lock:
            now = self._clock()
            hits = self._hits.get(slot)
            if hits is None:
                # Room is made BEFORE the new key goes in.
                while len(self._hits) >= _MAX_KEYS:
                    self._hits.popitem(last=False)
                hits = deque()
                self._hits[slot] = hits
            else:
                self._hits.move_to_end(slot)
            while hits and hits[0] <= now - rule.window_seconds:
                hits.popleft()
            if len(hits) >= rule.limit:
                return max(1, math.ceil(hits[0] + rule.window_seconds - now))
            hits.append(now)
            return 0

class RateLimit(BaseHTTPMiddleware):
    """Refuses, with 429 and `Retry-After`, a request over its rule's cap.
    Installed inside `AuthGate`, so the signed-in person is known."""

    def __init__(self, app, limiter: Limiter | None = None) -> None:
        super().__init__(app)
        self.limiter = limiter or Limiter()

    async def dispatch(self, request: Request, call_next) -> Response:
        if auth.current_mode() != auth.MODE_KEYCLOAK:
            return await call_next(request)
        path = request.url.path
        for rule in RULES:
            if request.method != rule.method or not rule.path.match(path):
                continue
            if rule.per == "person":
                principal = getattr(request.state, "principal", None)
                if principal is None:
                    break  # not signed in: AuthGate has already refused it
                key = principal.id
            else:
                key = client_address(request)
            wait = self.limiter.take(rule, key)
            if wait:
                return _refused(request, wait)
            break
        return await call_next(request)


def _refused(request: Request, wait: int) -> Response:
    """JSON for the page's own scripts; for a plain form post, a small real
    page in the person's language and direction, with a way back -- not a
    bare line of text (review of #150)."""
    lang = context_language(request)
    sentence = i18n.translate(lang, "rate.limited", seconds=wait)
    headers = {"Retry-After": str(wait)}
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse(status_code=429, content={"error": sentence}, headers=headers)
    back = i18n.translate(lang, "rate.back")
    direction = "rtl" if lang == "ar" else "ltr"
    page = (
        f'<!doctype html><html lang="{escape(lang)}" dir="{direction}"><head>'
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        f"<title>Sanad</title></head><body><main><p>{escape(sentence)}</p>"
        f'<p><a href="/">{escape(back)}</a></p></main></body></html>'
    )
    return HTMLResponse(page, status_code=429, headers=headers)
