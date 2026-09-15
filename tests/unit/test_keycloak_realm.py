"""Guards on the dev realm that `compose.keycloak.yaml` imports.

Signing in used to be five things to click in Keycloak's admin console,
redone from scratch every time the container stopped. `keycloak/realm-sanad.json`
replaced that with one command, which only helps if the file keeps agreeing
with the code that reads it: the role names come from `config.auth_role_prefix`
plus `ui.auth.ROLES`, and the callback URL comes from
`config.keycloak_redirect_url`. A rename on either side silently produces a
realm where everyone signs in with no role, so both are pinned here.

Two bugs found on 2026-09-15 by running it, each pinned below so it cannot
return: a volume mounted on `/opt/keycloak/data/h2` is created owned by root
and Keycloak dies on boot, and a seeded person with no email address is
stopped by Keycloak's "Update Account Information" page instead of reaching
Sanad.
"""

import json
import re
from pathlib import Path

import yaml

import ui.auth as auth
from config import Settings

ROOT = Path(__file__).resolve().parents[2]
REALM = json.loads((ROOT / "keycloak" / "realm-sanad.json").read_text(encoding="utf-8"))
COMPOSE = yaml.safe_load((ROOT / "compose.keycloak.yaml").read_text(encoding="utf-8"))
KEYCLOAK = COMPOSE["services"]["keycloak"]


def _client() -> dict:
    return next(c for c in REALM["clients"] if c["clientId"] == "sanad")


def test_realm_defines_exactly_the_three_roles_the_code_reads():
    defaults = Settings()
    expected = {f"{defaults.auth_role_prefix}{role}" for role in auth.ROLES}

    assert {r["name"] for r in REALM["roles"]["realm"]} == expected
    assert all(r.get("description") for r in REALM["roles"]["realm"])


def test_client_is_confidential_and_matches_the_configured_callback():
    defaults = Settings()
    client = _client()

    assert client["clientId"] == defaults.keycloak_client_id
    assert client["publicClient"] is False
    assert client["clientAuthenticatorType"] == "client-secret"
    assert client["standardFlowEnabled"] is True
    assert defaults.keycloak_redirect_url in client["redirectUris"]
    # Without a post-logout URL Keycloak answers 400 on sign-out
    # (docs/known-issues.md). The default callback's origin must be listed.
    logout = client["attributes"]["post.logout.redirect.uris"].split("##")
    assert defaults.keycloak_redirect_url.replace("/auth/callback", "/auth/login") in logout


def test_no_secret_and_no_password_is_committed_in_the_realm():
    """The core law forbids a secret in a committed file, and this file is
    an export-shaped thing, which is exactly where one hides. Every secret
    must be a `${...}` placeholder Keycloak fills from the environment."""
    placeholder = re.compile(r"^\$\{[A-Z_]+(:.*)?\}$")

    assert placeholder.match(_client()["secret"])
    for user in REALM["users"]:
        for credential in user["credentials"]:
            assert placeholder.match(credential["value"]), user["username"]


def test_every_seeded_person_can_actually_reach_sanad():
    """2026-09-15: the four demo people were seeded without an email, and
    Keycloak 26 stopped each one at "Update Account Information" before the
    browser ever came back to Sanad. An email and an empty required-action
    list are what make the seeded password enough to sign in."""
    assert len(REALM["users"]) == 4

    for user in REALM["users"]:
        assert user["enabled"] is True
        assert user["email"], user["username"]
        # RFC 2606 reserves .invalid: a demo account can never mail a person.
        assert user["email"].endswith("@sanad.invalid")
        assert user["emailVerified"] is True
        assert user["requiredActions"] == [], user["username"]

    by_roles = {tuple(u["realmRoles"]): u["username"] for u in REALM["users"]}
    defaults = Settings()
    for role in auth.ROLES:
        assert (f"{defaults.auth_role_prefix}{role}",) in by_roles
    # One person with no role at all: the "ask an administrator" screen is a
    # real state of the product (UX spec) and needs someone to demonstrate it.
    assert () in by_roles


def test_compose_imports_the_realm_and_can_write_its_database():
    """2026-09-15: mounting the named volume on `/opt/keycloak/data/h2`
    made Keycloak die on boot with AccessDeniedException on
    keycloakdb.mv.db. The image ships `/opt/keycloak/data` owned by uid
    1000, so a volume there inherits a writable owner; `h2` does not exist
    in the image, so a volume there is created owned by root."""
    assert "--import-realm" in KEYCLOAK["command"]

    mounts = {m.split(":")[1]: m for m in KEYCLOAK["volumes"]}
    assert "/opt/keycloak/data" in mounts
    assert "/opt/keycloak/data/h2" not in mounts
    assert mounts["/opt/keycloak/data"].startswith("sanad-keycloak-data:")
    assert mounts["/opt/keycloak/data/import"].endswith(":ro")
    assert COMPOSE["volumes"] == {"sanad-keycloak-data": None}


def test_compose_demands_every_secret_instead_of_defaulting_one():
    """A demo realm whose admin password or client secret came from a
    committed default is someone else's open door. Each of these four uses
    compose's `:?` form, which refuses to start when the variable is unset."""
    environment = KEYCLOAK["environment"]

    for name in (
        "KC_BOOTSTRAP_ADMIN_USERNAME",
        "KC_BOOTSTRAP_ADMIN_PASSWORD",
        "KEYCLOAK_CLIENT_SECRET",
        "KEYCLOAK_SEED_PASSWORD",
    ):
        assert ":?" in environment[name], name

    # The one that MAY default: it is a URL, not a secret, and local is
    # where it nearly always points.
    assert environment["KEYCLOAK_PUBLIC_APP_URL"].startswith("${KEYCLOAK_PUBLIC_APP_URL:-")


def test_keycloak_is_still_only_reachable_from_this_machine():
    """LD-07: like Sanad itself, the dev realm binds loopback only."""
    assert KEYCLOAK["ports"] == ["127.0.0.1:8080:8080"]


def test_the_deployed_keycloak_starts_and_imports_the_same_realm():
    """2026-09-15: the published image has an ENTRYPOINT and no CMD, so
    Railway started it with no arguments, got the help text and an exited
    container. The deploy Dockerfile supplies the command -- and copies the
    SAME realm file the dev compose imports, so the demo and a developer's
    machine cannot drift apart."""
    dockerfile = (ROOT / "deploy" / "keycloak" / "Dockerfile").read_text(encoding="utf-8")
    instructions = [
        line.strip()
        for line in dockerfile.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert any(i.startswith("FROM ") and KEYCLOAK["image"] in i for i in instructions), (
        "the deployed Keycloak must be the version the dev realm is tested against"
    )
    copied = [i for i in instructions if i.startswith("COPY ")]
    assert any("keycloak/realm-sanad.json" in i for i in copied)
    assert any("/opt/keycloak/data/import/" in i for i in copied)

    command = next(i for i in instructions if i.startswith("CMD "))
    assert "start" in command and "--import-realm" in command
    # `start`, never `start-dev`: production mode on a public address.
    assert "start-dev" not in command
