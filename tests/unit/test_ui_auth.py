"""S6, ST-54: who may see and change a workspace.

ST-54 (YL's ruling, 2026-09-18) dropped the roles: every signed-in person
is equal, owns what they create, may read and ask a shared (ownerless)
workspace, and cannot see anyone else's. Each rule is asserted in both
directions -- a stranger changing your workspace is one failure, an owner
locked out of their own is the other.
"""

from __future__ import annotations

import pytest

from ui import auth
from ui.auth import Principal

AMINA = Principal(id="u-amina", username="amina", display_name="Amina")


# --- ownership ----------------------------------------------------------------


def test_an_owner_sees_and_manages_their_own_workspace():
    assert AMINA.may_see_workspace("u-amina")
    assert AMINA.may_manage_workspace("u-amina")


def test_a_shared_workspace_is_readable_by_everyone_and_changeable_by_nobody():
    assert AMINA.may_see_workspace(None)
    assert not AMINA.may_manage_workspace(None)


def test_someone_elses_workspace_is_neither_visible_nor_changeable():
    assert not AMINA.may_see_workspace("u-omar")
    assert not AMINA.may_manage_workspace("u-omar")


def test_the_local_principal_of_the_login_free_modes_may_do_everything():
    assert auth.LOCAL.unrestricted
    for owner in (None, "local", "u-omar"):
        assert auth.LOCAL.may_see_workspace(owner)
        assert auth.LOCAL.may_manage_workspace(owner)


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
