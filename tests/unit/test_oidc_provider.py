"""The real Keycloak provider's sign-in URL, without a network.

`_endpoints` is pre-filled, so `_discover()` never fetches anything.
"""

from urllib.parse import parse_qs, urlparse

from ui.oidc import KeycloakProvider


def _provider() -> KeycloakProvider:
    return KeycloakProvider(
        issuer="https://keycloak.test/realms/sanad",
        client_id="sanad",
        client_secret="unused-here",
        _endpoints={
            "authorization": "https://keycloak.test/realms/sanad/protocol/openid-connect/auth",
            "token": "",
            "introspection": "",
            "end_session": "",
        },
    )


def test_sign_in_asks_keycloak_for_the_visitors_language():
    """2026-09-15: Keycloak's sign-in and sign-up pages came up in English
    for a visitor reading Sanad in French, because Keycloak follows the
    browser, not Sanad. OIDC's `ui_locales` carries Sanad's choice."""
    url = _provider().authorization_url(
        state="s", nonce="n", redirect_uri="https://sanad.test/auth/callback", ui_locales="ar"
    )

    assert parse_qs(urlparse(url).query)["ui_locales"] == ["ar"]


def test_sign_out_confirmation_opens_in_the_visitors_language_too():
    """Same browser run, 2026-09-15: after the sign-in page was fixed, the
    "are you sure you want to log out?" page still came up in English.
    RP-Initiated Logout accepts `ui_locales` as well."""
    provider = _provider()
    provider._endpoints["end_session"] = (
        "https://keycloak.test/realms/sanad/protocol/openid-connect/logout"
    )

    url = provider.end_session_url(
        redirect_uri="https://sanad.test/auth/login", ui_locales="fr"
    )

    query = parse_qs(urlparse(url).query)
    assert query["ui_locales"] == ["fr"]
    assert query["post_logout_redirect_uri"] == ["https://sanad.test/auth/login"]


def test_no_language_means_no_ui_locales_parameter():
    url = _provider().authorization_url(
        state="s", nonce="n", redirect_uri="https://sanad.test/auth/callback"
    )

    assert "ui_locales" not in parse_qs(urlparse(url).query)


def test_the_realm_is_read_once_per_process_not_once_per_request(monkeypatch):
    """The module says "Read from the issuer once per process", and until
    2026-09-16 it was not true: `build_provider()` returned a NEW provider
    every call, each with an empty endpoint cache, so every hit on
    `/auth/login` -- a route open to anyone, signed in or not -- made a
    blocking 10-second-timeout call to Keycloak before redirecting. A
    handful of concurrent requests could tie up the server's workers and
    point them all at the realm."""
    import ui.oidc as oidc
    from config import get_settings

    settings = get_settings().model_copy(
        update={
            "keycloak_issuer": "https://keycloak.test/realms/sanad",
            "keycloak_client_id": "sanad",
            "keycloak_client_secret": "test-secret",
        }
    )
    monkeypatch.setattr(oidc, "get_settings", lambda: settings)
    oidc._provider.cache_clear()
    # Cleared AFTER as well: the cache is module level, so a provider
    # pointing at keycloak.test would otherwise outlive this test and be
    # handed to whatever runs next (review, 2026-09-16).
    fetched: list[str] = []

    def fake_get_json(url: str) -> dict:
        fetched.append(url)
        return {
            "authorization_endpoint": "https://keycloak.test/auth",
            "token_endpoint": "https://keycloak.test/token",
            "introspection_endpoint": "https://keycloak.test/introspect",
            "end_session_endpoint": "https://keycloak.test/logout",
        }

    monkeypatch.setattr(oidc, "_get_json", fake_get_json)

    for _ in range(5):
        oidc.build_provider().authorization_url(
            state="s", nonce="n", redirect_uri="https://sanad.test/auth/callback"
        )

    assert len(fetched) == 1, f"one discovery call expected, made {len(fetched)}"
    oidc._provider.cache_clear()
