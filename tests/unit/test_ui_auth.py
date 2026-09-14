"""S6: roles as Keycloak states them, and what each role may do.

Every row of the permission table in docs/design/S6-auth-rbac.md is a
rule someone could get wrong in one direction (a reader deleting a
workspace) or the other (an admin locked out of their own instance), so
each is asserted in both directions.
"""

from __future__ import annotations

import pytest

from ui import auth
from ui.auth import ADMIN, CURATOR, READER, Principal


def person(*roles: str) -> Principal:
    return Principal(id="u-1", username="amina", display_name="Amina", roles=roles)


# --- roles as the provider states them -------------------------------------


def test_only_prefixed_sanad_roles_are_read_from_the_realm():
    claims = {
        "realm_access": {"roles": ["offline_access", "sanad-admin", "default-roles"]},
    }

    assert auth.roles_from_claims(claims, prefix="sanad-") == (ADMIN,)


def test_roles_on_this_client_count_too_and_duplicates_collapse():
    claims = {
        "realm_access": {"roles": ["sanad-reader"]},
        "resource_access": {
            "sanad": {"roles": ["sanad-curator", "sanad-reader"]},
            "other-app": {"roles": ["sanad-admin"]},
        },
    }

    assert auth.roles_from_claims(claims, prefix="sanad-") == (ADMIN, CURATOR, READER)


@pytest.mark.parametrize(
    "claims",
    [
        {},
        {"realm_access": {}},
        {"realm_access": {"roles": ["admin", "curator", "reader"]}},
        {"realm_access": {"roles": ["sanad-superuser", "sanad-"]}},
        {"realm_access": {"roles": [None, 7]}},
    ],
)
def test_anything_else_grants_nothing(claims):
    assert auth.roles_from_claims(claims, prefix="sanad-") == ()


# --- what each role may do --------------------------------------------------


def test_a_person_with_no_role_may_do_nothing_at_all():
    nobody = person()

    assert not nobody.has_any_role
    assert not nobody.may_ask("ws", {"ws"})
    assert not nobody.may_manage_documents("ws", {"ws"})
    assert not nobody.may_manage_workspaces()
    assert not nobody.may_read_activity()


def test_a_reader_asks_in_granted_workspaces_only_and_changes_nothing():
    reader = person(READER)

    assert reader.may_ask("granted", {"granted"})
    assert not reader.may_ask("other", {"granted"})
    assert not reader.may_manage_documents("granted", {"granted"})
    assert not reader.may_manage_workspaces()


def test_a_curator_manages_documents_where_granted_but_owns_no_workspace():
    curator = person(CURATOR)

    assert curator.may_manage_documents("granted", {"granted"})
    assert not curator.may_manage_documents("other", {"granted"})
    assert not curator.may_manage_workspaces()
    assert not curator.may_read_activity()


def test_an_admin_sees_every_workspace_without_a_grant():
    admin = person(ADMIN)

    assert admin.may_see_workspace("never-granted", set())
    assert admin.may_manage_documents("never-granted", set())
    assert admin.may_manage_workspaces()
    assert admin.may_read_activity()


def test_the_local_principal_of_the_login_free_modes_may_do_everything():
    assert auth.LOCAL.unrestricted
    assert auth.LOCAL.may_manage_workspaces()
    assert auth.LOCAL.may_ask("any", set())
    assert auth.LOCAL.may_manage_documents("any", set())


# --- sessions ---------------------------------------------------------------


def test_the_cookie_value_is_never_what_the_database_stores():
    token, stored = auth.new_session_token()

    assert token and stored != token
    assert auth.hash_token(token) == stored
    assert len(stored) == 64, "a SHA-256 hex digest"


def test_two_sessions_never_get_the_same_token():
    assert auth.new_session_token()[0] != auth.new_session_token()[0]


def test_a_new_session_expires_in_the_future():
    from datetime import UTC, datetime

    assert datetime.fromisoformat(auth.session_expiry()) > datetime.now(UTC)


# --- the setting and the code agree ----------------------------------------


def test_the_three_modes_config_accepts_are_the_three_the_code_knows():
    """config.py spells the modes as literals (it must never import ui/),
    so this is the check that keeps the two lists from drifting."""
    from config import Settings

    for mode in (auth.MODE_NONE, auth.MODE_PASSWORD, auth.MODE_KEYCLOAK):
        assert Settings(auth_mode=mode).auth_mode == mode
    with pytest.raises(ValueError):
        Settings(auth_mode="kecloak")


def test_a_session_lifetime_must_be_positive():
    from config import Settings

    with pytest.raises(ValueError):
        Settings(session_ttl_hours=0)
