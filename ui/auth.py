"""Who is asking, and what they are allowed to do (S6, ST-54).

Three modes (`AUTH_MODE`): `none` is the local-first app with no login at
all, `password` is the shared-secret gate, and `keycloak` is named people.

THE PERMISSION RULES LIVE HERE, IN ONE PLACE. A route asks
`principal.may_manage_workspace(owner)`; it never decides ownership
itself. Two routes deciding "may this person change this workspace" in
two places is how one of them ends up wrong.

ST-54 (YL's ruling, 2026-09-18): THERE ARE NO ROLES. Every signed-in
person is equal. Keycloak only says who they are. A person owns the
workspaces they create and may do everything to those; a workspace with
no owner (every one made before ST-54, like the live demo's) is SHARED:
everyone may read it and ask it, nobody may change it. Someone else's
workspace is invisible -- not merely refused -- so its name never leaks
through a selector. The login-free modes are one unrestricted person who
owns and sees everything, exactly as before S6.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from config import get_settings

MODE_NONE = "none"
MODE_PASSWORD = "password"
MODE_KEYCLOAK = "keycloak"

# The cookie that carries the session token. `sanad_lang` next to it is
# the only other cookie this app sets.
SESSION_COOKIE = "sanad_session"
# The short-lived cookie holding the `state`/`nonce` of a sign-in that has
# started but not finished.
FLOW_COOKIE = "sanad_login"
FLOW_MAX_AGE_SECONDS = 600


@dataclass(frozen=True)
class Principal:
    """Whoever is making this request."""

    id: str
    username: str
    display_name: str
    # True for the local, login-free modes: nothing is checked and
    # everything is allowed, exactly as before S6.
    unrestricted: bool = False

    def may_see_workspace(self, owner_user_id: str | None) -> bool:
        """Their own, or a shared one (no owner). Anything else is not
        offered anywhere -- not in the selector, not in routing, not in
        Reports -- and refused if a stale or forged request names it."""
        return self.unrestricted or owner_user_id is None or owner_user_id == self.id

    def may_manage_workspace(self, owner_user_id: str | None) -> bool:
        """Rename, re-flag, delete, upload, remove, Sync: their own only.
        A shared workspace is read-and-ask for everyone who signs in."""
        return self.unrestricted or (owner_user_id is not None and owner_user_id == self.id)


LOCAL = Principal(
    id="local",
    username="local",
    display_name="local",
    unrestricted=True,
)


def current_mode() -> str:
    return get_settings().auth_mode


def principal_from_session(row: sqlite3.Row) -> Principal:
    return Principal(
        id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"] or row["username"],
    )


def new_session_token() -> tuple[str, str]:
    """A fresh (cookie value, database key) pair.

    The database stores the HASH. A copy of the registry is then a list of
    sessions nobody can use, which is the same reasoning that keeps the
    API key out of `ui/conversation.py`'s error panel."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_expiry() -> str:
    hours = get_settings().session_ttl_hours
    return (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
