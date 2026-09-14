"""Who is asking, and what they are allowed to do (S6).

docs/design/S6-auth-rbac.md is the design; this module is the part every
route asks. Three modes (`AUTH_MODE`): `none` is today's local-first app
with no login at all, `password` is the existing shared-secret gate, and
`keycloak` is named people with roles.

THE PERMISSION RULES LIVE HERE, IN ONE PLACE. A route asks
`principal.may_manage_documents(workspace_id, granted)`; it never reads a
role name itself. Two routes deciding "is this person an admin" in two
places is how one of them ends up wrong, and it is the failure nobody
notices until the wrong person deletes a workspace.

NOBODY IS ANYTHING BY DEFAULT. A person Keycloak knows but who carries no
Sanad role gets `roles=()`, which permits nothing -- they see one page
saying an administrator must grant access. The alternative (defaulting to
reader) turns a misconfigured realm into quiet, invisible access.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from config import get_settings

MODE_NONE = "none"
MODE_PASSWORD = "password"
MODE_KEYCLOAK = "keycloak"

ADMIN = "admin"
CURATOR = "curator"
READER = "reader"
ROLES = (ADMIN, CURATOR, READER)

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
    roles: tuple[str, ...]
    # True for the local, login-free modes: nothing is checked and
    # everything is allowed, exactly as before S6.
    unrestricted: bool = False

    @property
    def is_admin(self) -> bool:
        return self.unrestricted or ADMIN in self.roles

    @property
    def is_curator(self) -> bool:
        return self.is_admin or CURATOR in self.roles

    @property
    def has_any_role(self) -> bool:
        return self.unrestricted or bool(self.roles)

    def may_see_workspace(self, workspace_id: str, granted: Iterable[str]) -> bool:
        """An admin sees every workspace; everyone else sees only what they
        were granted. A workspace that is not visible is not offered
        anywhere -- not in the selector, not in routing, not in Reports."""
        return self.is_admin or workspace_id in set(granted)

    def may_ask(self, workspace_id: str, granted: Iterable[str]) -> bool:
        return self.has_any_role and self.may_see_workspace(workspace_id, granted)

    def may_manage_documents(self, workspace_id: str, granted: Iterable[str]) -> bool:
        """Upload, remove, Sync. Curators, in the workspaces they hold."""
        return self.is_curator and self.may_see_workspace(workspace_id, granted)

    def may_manage_workspaces(self) -> bool:
        """Create, rename, re-flag, delete a workspace: admins only."""
        return self.is_admin

    def may_read_activity(self) -> bool:
        return self.is_admin


LOCAL = Principal(
    id="local",
    username="local",
    display_name="local",
    roles=ROLES,
    unrestricted=True,
)


def current_mode() -> str:
    return get_settings().auth_mode


def roles_from_claims(claims: dict, *, prefix: str | None = None) -> tuple[str, ...]:
    """The Sanad roles inside Keycloak's introspection answer.

    Realm roles and this client's roles are both read, because a realm can
    be organised either way and an operator who put `sanad-admin` in the
    client's role list has not made a mistake. Anything without the
    configured prefix belongs to another application and is ignored."""
    marker = get_settings().auth_role_prefix if prefix is None else prefix
    found: set[str] = set()
    realm = claims.get("realm_access") or {}
    sources = [realm.get("roles") or []]
    for entry in (claims.get("resource_access") or {}).values():
        if isinstance(entry, dict):
            sources.append(entry.get("roles") or [])
    for source in sources:
        for raw in source:
            if not isinstance(raw, str) or not raw.startswith(marker):
                continue
            name = raw[len(marker) :].lower()
            if name in ROLES:
                found.add(name)
    return tuple(role for role in ROLES if role in found)


def principal_from_session(row: sqlite3.Row) -> Principal:
    roles = tuple(r for r in (row["roles"] or "").split() if r in ROLES)
    return Principal(
        id=row["user_id"],
        username=row["username"],
        display_name=row["display_name"] or row["username"],
        roles=roles,
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
