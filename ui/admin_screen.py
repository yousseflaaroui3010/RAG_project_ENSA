"""What the S6 admin screen shows (docs/design/S6-auth-rbac.md).

Same split as every other screen in this package: the rules live here
where a test can call them, and the template only loops. Roles are NOT
edited here -- they are Keycloak's, and a second place to change them
would be a second truth.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from db import repo
from ui import auth


@dataclass(frozen=True)
class Person:
    id: str
    username: str
    display_name: str
    email: str | None
    roles: tuple[str, ...]
    last_login_at: str
    granted: frozenset[str]

    @property
    def is_admin(self) -> bool:
        return auth.ADMIN in self.roles


@dataclass(frozen=True)
class ActivityRow:
    created_at: str
    username: str
    action: str
    detail: str | None
    workspace_name: str | None
    # The STORED id of the person this event was about, for the three
    # person events only; None for every other action. Shown beside the
    # username, never replaced by it -- see `activity`.
    person_id: str | None = None


def people(*, db_path: str | Path | None = None) -> list[Person]:
    """Everyone who has ever signed in, with what they hold."""
    with repo.session(db_path) as conn:
        rows = repo.list_users(conn)
        return [
            Person(
                id=row["id"],
                username=row["username"],
                display_name=row["display_name"] or row["username"],
                email=row["email"],
                roles=tuple(r for r in (row["roles"] or "").split() if r in auth.ROLES),
                last_login_at=row["last_login_at"],
                granted=frozenset(repo.granted_workspace_ids(conn, row["id"])),
            )
            for row in rows
        ]


def _workspace_names(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["id"]: row["name"] for row in conn.execute("SELECT id, name FROM workspace")}


# The three actions whose `detail` is the id of the PERSON acted on. app.py
# writes them through these names, so the list the log resolves and the list
# the routes write are one list, not two that must be kept in step by hand.
# Nothing else is resolved: a refused action's detail is a URL path. The
# values are the English phrases `ui/i18n` translates -- change one there too.
GRANTED_ACCESS = "granted access"
REVOKED_ACCESS = "revoked access"
SIGNED_OUT_EVERYWHERE = "signed a person out everywhere"
PERSON_ACTIONS = frozenset({GRANTED_ACCESS, REVOKED_ACCESS, SIGNED_OUT_EVERYWHERE})


def activity(*, limit: int = 200, db_path: str | Path | None = None) -> list[ActivityRow]:
    """The log, newest first, with workspace ids resolved to names.

    A workspace that has since been deleted leaves its id unresolved and
    the row shows no name rather than a dangling identifier: the event
    still happened, and hiding it would be the worse lie.

    The person a grant, revoke or forced sign-out was ABOUT is shown by
    username AND id. An administrator reading "access granted
    6fb523a6-decc-..." alone cannot tell who that was (seen in a real
    browser, 2026-09-15) -- but the username alone is worse for an audit
    trail: `app_user.username` is overwritten at every sign-in and is not
    unique, so a person who renamed themselves in Keycloak would rewrite who
    every past event appears to be about, and two accounts can share a name.
    So the log keeps STORING the id, and the screen shows the name with the
    id beside it (review of this change). An id that no longer resolves is
    shown as stored, for the same reason as a deleted workspace."""
    with repo.session(db_path) as conn:
        names = _workspace_names(conn)
        usernames = {row["id"]: row["username"] for row in repo.list_users(conn)}
        rows = []
        for row in repo.list_activity(conn, limit):
            about_person = row["action"] in PERSON_ACTIONS
            rows.append(
                ActivityRow(
                    created_at=row["created_at"],
                    username=row["username"],
                    action=row["action"],
                    detail=(
                        usernames.get(row["detail"], row["detail"])
                        if about_person
                        else row["detail"]
                    ),
                    workspace_name=names.get(row["workspace_id"]),
                    person_id=row["detail"] if about_person else None,
                )
            )
        return rows


def set_grants(
    *, user_id: str, workspace_ids: set[str], db_path: str | Path | None = None
) -> tuple[set[str], set[str]]:
    """Make this person's grants exactly `workspace_ids`. (added, removed).

    The form posts the WHOLE new state (an unticked box sends nothing), so
    this diffs rather than adds: without the removal half, unticking a box
    would silently do nothing and the screen would lie on the next load."""
    with repo.session(db_path) as conn:
        known = set(_workspace_names(conn))
        wanted = workspace_ids & known
        current = repo.granted_workspace_ids(conn, user_id)
        added, removed = wanted - current, current - wanted
        for workspace_id in added:
            repo.grant_workspace(conn, workspace_id=workspace_id, user_id=user_id)
        for workspace_id in removed:
            repo.revoke_workspace(conn, workspace_id=workspace_id, user_id=user_id)
    return added, removed
