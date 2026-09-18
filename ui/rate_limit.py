"""ST-55: a cap on how often one person, or one address, may do the
costly or abusable things (known issue "Nothing is rate limited").

WHAT IS CAPPED, AND WHY EACH:

* signing in (`/auth/login`, `/auth/callback`), per client address -- sign-up
  is open to anyone, and each attempt costs a round trip to Keycloak;
* asking (`POST /chat/ask`), per person -- every question is a PAID model call;
* creating a workspace and uploading a document, per person -- since ST-54
  anyone signed in may do both, and each costs disk on the shared volume;
* renaming or deleting conversations, per person -- cheap one by one, but a
  script could churn the database.

ONLY WITH ACCOUNTS ON (`AUTH_MODE=keycloak`). The login-free modes are one
person on their own machine (ADR-13); capping them would only get in their
way.

IN PROCESS, NO NEW DEPENDENCY. A sliding window per (rule, key): the times of
the last requests, oldest dropped as they age out. The demo runs ONE process
(Railway, one replica), so one process's memory is the whole picture; a
second replica would need a shared store, and DECISIONS says so. The number
of keys is bounded (`_MAX_KEYS`): the stalest key is dropped first, so a
flood of made-up addresses cannot grow memory without limit.

THE LIMITS ARE CONSTANTS HERE, not settings, for one recorded reason: every
setting must be documented in `.env.example`, which the coding agent is not
allowed to open (DECISIONS 2026-09-18, ST-55). Moving them into config.py is
a two-line change once someone documents them there.

THE CLIENT ADDRESS behind Railway's proxy is the LAST entry of
`X-Forwarded-For` -- the one the proxy itself appended. Earlier entries are
whatever the client chose to send, so trusting the first one would let
anyone pick a fresh address per request. Without the header (a laptop, the
tests), it is the socket's own address.
"""

from __future__ import annotations

import re
import threading
import time
from collections import OrderedDict, deque
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response

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
    Rule("sign-in", "GET", re.compile(r"^/auth/(login|callback)$"), 20, 300, "address"),
    Rule("ask", "POST", re.compile(r"^/chat/ask$"), 20, 600, "person"),
    Rule("create-workspace", "POST", re.compile(r"^/workspaces$"), 10, 3600, "person"),
    Rule("upload", "POST", re.compile(r"^/workspaces/[^/]+/documents$"), 200, 3600, "person"),
    Rule(
        "conversation-change",
        "POST",
        re.compile(r"^/chat/conversations/[^/]+/(rename|delete)$"),
        60,
        600,
        "person",
    ),
)


def client_address(request: Request) -> str:
    """The address to key sign-in attempts by (see the module docstring)."""
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
        now = self._clock()
        slot = (rule.name, key)
        with self._lock:
            hits = self._hits.get(slot)
            if hits is None:
                hits = deque()
                self._hits[slot] = hits
                while len(self._hits) > _MAX_KEYS:
                    self._hits.popitem(last=False)
            else:
                self._hits.move_to_end(slot)
            while hits and hits[0] <= now - rule.window_seconds:
                hits.popleft()
            if len(hits) >= rule.limit:
                return max(1, int(hits[0] + rule.window_seconds - now) + 1)
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
    sentence = i18n.translate(context_language(request), "rate.limited", seconds=wait)
    headers = {"Retry-After": str(wait)}
    if request.headers.get("x-requested-with") == "fetch":
        return JSONResponse(status_code=429, content={"error": sentence}, headers=headers)
    return PlainTextResponse(sentence, status_code=429, headers=headers)
