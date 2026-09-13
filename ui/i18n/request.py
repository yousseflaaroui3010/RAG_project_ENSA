"""Per-request interface language (S6), and the middleware that sets it.

Resolution order: an explicit `?lang=` link (which also sets the
`sanad_lang` cookie for later visits), then that cookie, then the
`default_ui_language` setting (French unless configured otherwise). An
unsupported value at any step is skipped, never echoed back.

A plain ASGI middleware rather than Starlette's BaseHTTPMiddleware: the
latter buffers streaming responses through an extra task, and answers are
about to stream (wave 2). This one only reads the query/cookie on the way
in and adds one `Set-Cookie` header on the way out.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
from urllib.parse import parse_qs, urlencode

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ui.i18n import DEFAULT, SUPPORTED

COOKIE_NAME = "sanad_lang"
_COOKIE_MAX_AGE_SECONDS = 365 * 24 * 60 * 60


def _default_language() -> str:
    # Imported at call time: config imports nothing from here, but keeping
    # this lazy means ui.i18n stays importable by scripts with no settings.
    from config import get_settings

    configured = get_settings().default_ui_language
    return configured if configured in SUPPORTED else DEFAULT


def _query_language(query_string: bytes) -> str | None:
    values = parse_qs(query_string.decode("latin-1")).get("lang")
    return values[-1] if values and values[-1] in SUPPORTED else None


def _cookie_language(headers: list[tuple[bytes, bytes]]) -> str | None:
    for name, value in headers:
        if name.lower() == b"cookie":
            jar = SimpleCookie()
            try:
                jar.load(value.decode("latin-1"))
            except Exception:  # noqa: BLE001 -- a malformed cookie header is just ignored
                return None
            morsel = jar.get(COOKIE_NAME)
            if morsel is not None and morsel.value in SUPPORTED:
                return morsel.value
    return None


def resolve_language(request: Request) -> str:
    """The language for one request, from the request alone."""
    query = request.query_params.get("lang")
    if query in SUPPORTED:
        return query
    cookie = request.cookies.get(COOKIE_NAME)
    if cookie in SUPPORTED:
        return cookie
    return _default_language()


class LanguageMiddleware:
    """Stamps `scope["state"]["lang_ui"]` (read as `request.state.lang_ui`)
    for every HTTP request, and sets the cookie when a valid `?lang=` was
    sent -- only then, so an invalid value never overwrites a good cookie."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        chosen = _query_language(scope.get("query_string", b""))
        language = chosen or _cookie_language(scope.get("headers", [])) or _default_language()
        scope.setdefault("state", {})["lang_ui"] = language

        async def send_with_cookie(message: Message) -> None:
            if chosen and message["type"] == "http.response.start":
                cookie = (
                    f"{COOKIE_NAME}={chosen}; Max-Age={_COOKIE_MAX_AGE_SECONDS}; "
                    "Path=/; SameSite=Lax"
                )
                message["headers"] = [*message.get("headers", []), (b"set-cookie", cookie.encode())]
            await send(message)

        await self.app(scope, receive, send_with_cookie)


def context_language(request: Request) -> str:
    """The language a template renders in: what the middleware decided, or a
    fresh resolution for a request that never went through it."""
    language = getattr(request.state, "lang_ui", None)
    return language if language in SUPPORTED else resolve_language(request)


def language_links(request: Request) -> list[dict[str, object]]:
    """One entry per supported language for the switcher: the same page with
    `?lang=` set (other query parameters kept), and whether it is current."""
    from ui.i18n import DISPLAY_NAMES, SHORT_NAMES

    current = context_language(request)
    links = []
    for code in SUPPORTED:
        params = [(k, v) for k, v in request.query_params.multi_items() if k != "lang"]
        params.append(("lang", code))
        query = urlencode(params)
        links.append(
            {
                "code": code,
                "name": DISPLAY_NAMES[code],
                "short": SHORT_NAMES[code],
                "href": f"{request.url.path}?{query}",
                "current": code == current,
            }
        )
    return links


__all__ = [
    "COOKIE_NAME",
    "LanguageMiddleware",
    "context_language",
    "language_links",
    "resolve_language",
]
