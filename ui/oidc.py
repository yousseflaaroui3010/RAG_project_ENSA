"""The one seam between Sanad and Keycloak (S6, docs/design/S6-auth-rbac.md).

Three calls, and nothing else about the provider reaches the rest of the
app:

    authorization_url(state, nonce, redirect_uri, ui_locales) -> str
    exchange_code(code, redirect_uri)             -> dict   (tokens)
    introspect(access_token)                      -> dict   (claims)

NO NEW DEPENDENCY, and no JWT parsing anywhere. The authorization-code
flow is back-channel: the code is exchanged server-to-server over TLS,
and the roles come from Keycloak's own introspection endpoint as plain
JSON. Nothing arriving through the browser is ever trusted, so there is
no signature for this process to verify -- which is exactly the case
OIDC Core 3.1.3.7 describes, and it is why `authlib`/`pyjwt` are not
here.

A PROTOCOL, then one implementation. Tests script the protocol (the chat
model is faked the same way, for the same reason: docs/phase2/ENGINEERING-RULES.md
forbids secrets in tests, and CI has no Keycloak).
"""

from __future__ import annotations

import dataclasses
import functools
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

from config import get_settings

# Read from the issuer once per process. A realm's endpoints do not move
# while a server is running, and re-fetching them on every sign-in would
# put a network call in front of a redirect.
_DISCOVERY_PATH = "/.well-known/openid-configuration"
_TIMEOUT_SECONDS = 10


class ProviderUnavailableError(Exception):
    """Keycloak could not be reached, or answered something unusable.

    Named, like `ChatUnavailableError`, so a sign-in failure reads as "the
    login service is down" on screen rather than as a stack trace -- and
    never as "wrong password", which would be a lie about the person."""


class Provider(Protocol):
    def authorization_url(
        self, *, state: str, nonce: str, redirect_uri: str, ui_locales: str = ""
    ) -> str: ...

    def exchange_code(self, *, code: str, redirect_uri: str) -> dict[str, Any]: ...

    def introspect(self, access_token: str) -> dict[str, Any]: ...


@dataclass
class KeycloakProvider:
    """The real provider, over `urllib`."""

    issuer: str
    client_id: str
    # repr=False: this instance is now kept for the life of the process, so
    # a stray `logger.exception(provider)` or a debugger would otherwise
    # print the client secret (review, 2026-09-16).
    client_secret: str = dataclasses.field(repr=False)
    _endpoints: dict[str, str] | None = None

    def _discover(self) -> dict[str, str]:
        if self._endpoints is None:
            data = _get_json(self.issuer.rstrip("/") + _DISCOVERY_PATH)
            try:
                self._endpoints = {
                    "authorization": data["authorization_endpoint"],
                    "token": data["token_endpoint"],
                    "introspection": data["introspection_endpoint"],
                    "end_session": data.get("end_session_endpoint", ""),
                }
            except KeyError as exc:
                raise ProviderUnavailableError(
                    f"the realm at {self.issuer!r} did not publish {exc.args[0]!r} "
                    f"in its OpenID configuration."
                ) from exc
        return self._endpoints

    def authorization_url(
        self, *, state: str, nonce: str, redirect_uri: str, ui_locales: str = ""
    ) -> str:
        params = {
            "client_id": self.client_id,
            "response_type": "code",
            "scope": "openid profile email",
            "redirect_uri": redirect_uri,
            "state": state,
            "nonce": nonce,
        }
        # OIDC Core 3.1.2.1 `ui_locales`: the sign-in and sign-up pages open
        # in the language Sanad is showing, not the browser's. Seen
        # 2026-09-15: French Sanad, English Keycloak pages.
        if ui_locales:
            params["ui_locales"] = ui_locales
        query = urllib.parse.urlencode(params)
        return f"{self._discover()['authorization']}?{query}"

    def exchange_code(self, *, code: str, redirect_uri: str) -> dict[str, Any]:
        return _post_form(
            self._discover()["token"],
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )

    def introspect(self, access_token: str) -> dict[str, Any]:
        return _post_form(
            self._discover()["introspection"],
            {
                "token": access_token,
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )

    def end_session_url(self, *, redirect_uri: str, ui_locales: str = "") -> str:
        """Where to send the browser so Keycloak forgets it too. Empty when
        the realm publishes no such endpoint -- the local session is still
        deleted, and the caller simply lands back on Sanad."""
        endpoint = self._discover().get("end_session", "")
        if not endpoint:
            return ""
        params = {"client_id": self.client_id, "post_logout_redirect_uri": redirect_uri}
        # The confirmation page in Sanad's language too (RP-Initiated Logout
        # 1.0 `ui_locales`); without it, it followed the browser's.
        if ui_locales:
            params["ui_locales"] = ui_locales
        query = urllib.parse.urlencode(params)
        return f"{endpoint}?{query}"


def _get_json(url: str) -> dict[str, Any]:
    return _read(urllib.request.Request(url, method="GET"), url)


def _post_form(url: str, fields: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(fields).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    return _read(request, url)


def _read(request: urllib.request.Request, url: str) -> dict[str, Any]:
    """One call, with every failure named rather than leaked.

    The URL is included because it names the realm an operator misspelled;
    the request body never is -- it carries the client secret and the
    authorization code (docs/phase2/ENGINEERING-RULES.md: never log a full body)."""
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ProviderUnavailableError(
            f"the login service answered {exc.code} for {url!r}."
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ProviderUnavailableError(
            f"the login service at {url!r} could not be reached."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ProviderUnavailableError(
            f"the login service at {url!r} did not answer with JSON."
        ) from exc
    if not isinstance(payload, dict):
        raise ProviderUnavailableError(
            f"the login service at {url!r} answered a {type(payload).__name__}."
        )
    return payload


@functools.lru_cache(maxsize=4)
def _provider(issuer: str, client_id: str, client_secret: str) -> KeycloakProvider:
    """One provider per configuration, kept for the life of the process.

    KEPT, not rebuilt: a provider caches the realm's endpoints on itself,
    so returning a new one per call made the module's own promise ("read
    from the issuer once per process") false -- every hit on `/auth/login`,
    a route open to anyone signed in or not, blocked on a fresh discovery
    call with a 10-second timeout. Keyed on the settings it was built from,
    so changing them (a test, a re-read .env) yields a different provider
    rather than a stale one. Found by review, 2026-09-16."""
    return KeycloakProvider(
        issuer=issuer, client_id=client_id, client_secret=client_secret
    )


def build_provider() -> KeycloakProvider:
    """The configured provider.

    Raises before any redirect happens when a setting is missing: a
    half-configured login that silently lets everyone in is the one
    outcome this whole module exists to prevent."""
    settings = get_settings()
    missing = [
        name
        for name, value in (
            ("KEYCLOAK_ISSUER", settings.keycloak_issuer),
            ("KEYCLOAK_CLIENT_ID", settings.keycloak_client_id),
            ("KEYCLOAK_CLIENT_SECRET", settings.keycloak_client_secret),
        )
        if not value
    ]
    if missing:
        raise ProviderUnavailableError(
            f"AUTH_MODE is 'keycloak' but {', '.join(missing)} is empty. Set it "
            f"in .env, or choose AUTH_MODE=password (shared password) or "
            f"AUTH_MODE=none (local, no login)."
        )
    return _provider(
        settings.keycloak_issuer,
        settings.keycloak_client_id,
        settings.keycloak_client_secret,
    )
