"""Guards on the dev realm that `compose.keycloak.yaml` imports.

Signing in used to be five things to click in Keycloak's admin console,
redone from scratch every time the container stopped. `keycloak/realm-sanad.json`
replaced that with one command, which only helps if the file keeps agreeing
with the code that reads it: the callback URL comes from
`config.keycloak_redirect_url`, so it is pinned here. Since ST-54 Sanad
reads no role from the realm (every signed-in person is equal), so the
realm carries no Sanad role at all (removed 2026-09-19), and a test below
keeps it that way.

Two bugs found on 2026-09-15 by running it, each pinned below so it cannot
return: a volume mounted on `/opt/keycloak/data/h2` is created owned by root
and Keycloak dies on boot, and a seeded person with no email address is
stopped by Keycloak's "Update Account Information" page instead of reaching
Sanad.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from config import Settings

ROOT = Path(__file__).resolve().parents[2]
REALM = json.loads((ROOT / "keycloak" / "realm-sanad.json").read_text(encoding="utf-8"))
COMPOSE = yaml.safe_load((ROOT / "compose.keycloak.yaml").read_text(encoding="utf-8"))
KEYCLOAK = COMPOSE["services"]["keycloak"]


def _client() -> dict:
    return next(c for c in REALM["clients"] if c["clientId"] == "sanad")


def test_anyone_can_sign_up():
    """YL asked for sign-up, not only sign-in (2026-09-15). Since ST-54 a
    new person owns nothing and sees only the shared workspaces until they
    create their own."""
    assert REALM["registrationAllowed"] is True


def test_the_default_role_is_defined_where_keycloak_actually_reads_it():
    """2026-09-15, found only by signing up in a browser: composites written
    INSIDE `defaultRole` are silently ignored on import. The realm imported
    without error, the file said "reader", and the new person arrived with
    no role at all. They take effect only on the role's own entry in
    `roles.realm`, which is the shape Keycloak's own export uses."""
    assert REALM["defaultRole"] == {"name": "default-roles-sanad"}


def test_sign_up_needs_no_mail_server_and_refuses_weak_passwords():
    """No outgoing mail: sending email is a stop-and-ask action on this
    project and there is no mail server, so email verification would lock
    every new person out. The password rule is the guard that remains."""
    assert REALM["verifyEmail"] is False
    policy = REALM["passwordPolicy"]
    length = int(re.search(r"length\((\d+)\)", policy).group(1))
    assert length >= 10
    assert "notUsername" in policy
    assert "notEmail" in policy
    assert REALM["bruteForceProtected"] is True


def test_keycloak_pages_offer_exactly_the_languages_sanad_speaks():
    from ui.i18n import SUPPORTED

    assert REALM["internationalizationEnabled"] is True
    assert set(REALM["supportedLocales"]) == set(SUPPORTED)
    # The DECLARED default, not Settings(): the test environment switches the
    # interface to English on purpose, and the realm follows the product.
    assert REALM["defaultLocale"] == Settings.model_fields["default_ui_language"].default


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
    must be a `${...}` placeholder Keycloak fills from the environment --
    and a BARE one: `${KEYCLOAK_SEED_PASSWORD:hunter2}` is a placeholder
    with a committed password as its default, and must fail here too."""
    placeholder = re.compile(r"^\$\{[A-Z_]+\}$")

    assert placeholder.match(_client()["secret"])
    for user in REALM["users"]:
        for credential in user["credentials"]:
            assert placeholder.match(credential["value"]), user["username"]


def test_the_admin_demo_person_has_a_password_of_their_own():
    """Review, 2026-09-15: all four demo people shared one password, so
    whoever was handed the reader login for a demo also held the admin one
    on a public site."""
    passwords = {
        u["username"]: u["credentials"][0]["value"] for u in REALM["users"]
    }
    admin = passwords.pop("sanad-admin-demo")

    assert admin == "${KEYCLOAK_ADMIN_SEED_PASSWORD}"
    assert admin not in passwords.values()


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
    committed default is someone else's open door. Each of these uses
    compose's `:?` form, which refuses to start when the variable is unset."""
    environment = KEYCLOAK["environment"]

    for name in (
        "KC_BOOTSTRAP_ADMIN_USERNAME",
        "KC_BOOTSTRAP_ADMIN_PASSWORD",
        "KEYCLOAK_CLIENT_SECRET",
        "KEYCLOAK_SEED_PASSWORD",
        "KEYCLOAK_ADMIN_SEED_PASSWORD",
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


def test_the_deployed_keycloak_refuses_to_start_without_a_placeholder_value():
    """Review, 2026-09-15: the dev compose refuses to start with a secret
    unset, but the deployed image had no such check. Recreated with an empty
    database and one variable missing, the one-time import could make a
    public account's password the literal placeholder text readable in this
    repository. The start guard must name every placeholder the realm uses,
    and the image must actually go through it. (The guard itself was run in
    a container on 2026-09-15: missing value, trailing slash and complete
    settings each behaved as written.)"""
    dockerfile = (ROOT / "deploy" / "keycloak" / "Dockerfile").read_text(encoding="utf-8")
    guard = (ROOT / "deploy" / "keycloak" / "start.sh").read_text(encoding="utf-8")
    required = set(
        re.search(r"required=\((.*?)\)", guard, re.DOTALL).group(1).split()
    )
    realm_text = (ROOT / "keycloak" / "realm-sanad.json").read_text(encoding="utf-8")
    placeholders = set(re.findall(r"\$\{([A-Z_]+)", realm_text))

    assert placeholders, "the realm is expected to carry placeholders"
    assert placeholders <= required, placeholders - required
    assert 'ENTRYPOINT ["/opt/keycloak/bin/sanad-start.sh"]' in dockerfile
    assert "deploy/keycloak/start.sh /opt/keycloak/bin/sanad-start.sh" in dockerfile
    assert 'exec /opt/keycloak/bin/kc.sh "$@"' in guard
    # Railway's builder runs this on Linux: a CRLF shebang would read as
    # "/bin/bash\r" and the container would not start at all.
    assert b"\r" not in (ROOT / "deploy" / "keycloak" / "start.sh").read_bytes()


def _run_guard(environment: dict[str, str]) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available to run deploy/keycloak/start.sh")
    guard = (ROOT / "deploy" / "keycloak" / "start.sh").as_posix()
    # A bare environment on purpose: nothing inherited from this machine
    # may satisfy a check. PATH only, so bash can find its own tools.
    return subprocess.run(
        [bash, guard, "start"],
        env={"PATH": os.environ.get("PATH", ""), **environment},
        capture_output=True,
        text=True,
        timeout=30,
    )


_COMPLETE = {
    "KEYCLOAK_CLIENT_SECRET": "x",
    "KEYCLOAK_SEED_PASSWORD": "x",
    "KEYCLOAK_ADMIN_SEED_PASSWORD": "x",
    "KEYCLOAK_PUBLIC_APP_URL": "https://sanad.example",
    "KC_HOSTNAME": "https://keycloak.example",
    "KC_DB_URL": "jdbc:postgresql://db:5432/keycloak",
    "KC_DB_USERNAME": "u",
    "KC_DB_PASSWORD": "p",
}


def test_the_start_guard_really_refuses_each_missing_setting():
    """The test above reads the files; this one RUNS the guard, so deleting
    its `-z` check or its `exit 1` turns the suite red (review, 2026-09-15).
    Each setting is removed on its own, and the refusal must name it."""
    for name in _COMPLETE:
        environment = {k: v for k, v in _COMPLETE.items() if k != name}

        result = _run_guard(environment)

        assert result.returncode == 1, (name, result.stderr)
        assert name in result.stderr, (name, result.stderr)
        assert "refuses to start" in result.stderr


def test_the_start_guard_refuses_a_trailing_slash_and_passes_complete_settings():
    slash = _run_guard({**_COMPLETE, "KEYCLOAK_PUBLIC_APP_URL": "https://sanad.example/"})
    complete = _run_guard(_COMPLETE)

    assert slash.returncode == 1 and "must not end with /" in slash.stderr
    # Complete settings get PAST the guard to `exec kc.sh`, which does not
    # exist outside the image: whatever happens next, it is not a refusal.
    assert "refuses to start" not in complete.stderr


def test_the_realm_defines_no_sanad_role_and_gives_none():
    """Sanad reads no role since ST-54; a role left in the realm would only
    mislead whoever reads it into thinking it still means something."""
    names = {r["name"] for r in REALM["roles"]["realm"]}
    assert not {n for n in names if n.startswith("sanad-")}
    default = next(r for r in REALM["roles"]["realm"] if r["name"] == "default-roles-sanad")
    assert not [n for n in default["composites"]["realm"] if n.startswith("sanad-")]
    assert all(not u.get("realmRoles") for u in REALM["users"])
