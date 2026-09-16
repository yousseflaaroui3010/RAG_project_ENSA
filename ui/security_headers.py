"""Response headers every page carries, and why each one is here.

Added 2026-09-16 after a security review of the published demo found the
app setting none of them. Each is one line and closes one class of attack
that does not need a bug in Sanad to work.

NO Content-Security-Policy YET, on purpose: the screens carry inline
`<style>` and `<script>` blocks, so a useful policy needs nonces threaded
through every template, and a policy written blind would either break the
product or be so loose it says nothing. It is written down as a gap in
docs/known-issues.md rather than shipped untested.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Belt-and-braces values, none of which depends on how Sanad is deployed.
HEADERS: tuple[tuple[bytes, bytes], ...] = (
    # A page of someone's documents must never be framed by another site:
    # a transparent frame over a "Delete" button is the whole clickjacking
    # trick, and `SameSite=lax` only makes the frame show a signed-out app.
    (b"x-frame-options", b"DENY"),
    # Stop a browser guessing a type for anything served here. Document
    # download already set this one; every other response lacked it.
    (b"x-content-type-options", b"nosniff"),
    # A workspace id in a URL is not secret, but it should not travel to
    # whatever site a source link points at.
    (b"referrer-policy", b"strict-origin-when-cross-origin"),
    # Nothing in Sanad uses a camera, a microphone or a location.
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
)


class SecurityHeaders:
    """Adds `HEADERS` to every HTTP response, without replacing one a route
    set deliberately."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = {name.lower() for name, _value in message.get("headers", [])}
                message["headers"] = [
                    *message.get("headers", []),
                    *((name, value) for name, value in HEADERS if name not in existing),
                ]
            await send(message)

        await self.app(scope, receive, send_with_headers)
