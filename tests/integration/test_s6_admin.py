"""S6 admin view: granting workspaces, ending sessions, reading the log.

Reuses the scripted-provider fixture from `test_s6_auth.py`: the rules
being checked here are about roles and grants, not about Keycloak.
"""

from __future__ import annotations

import workspaces
from db import repo
from tests.integration.test_s6_auth import (  # noqa: F401 -- the fixture
    ADMIN_CLAIMS,
    CURATOR_CLAIMS,
    READER_CLAIMS,
    keycloak,
)
from ui import admin_screen, auth


def _actions(db_path) -> list[str]:
    with repo.session(db_path) as conn:
        return [row["action"] for row in repo.list_activity(conn)]


def test_only_an_admin_can_open_the_admin_view(keycloak):  # noqa: F811
    client, _, _, _, sign_in = keycloak

    sign_in(READER_CLAIMS)
    assert client.get("/admin", follow_redirects=False).status_code == 303
    assert "shell__link" in client.get("/workspaces").text
    assert 'href="/admin"' not in client.get("/workspaces").text

    sign_in(ADMIN_CLAIMS)
    page = client.get("/admin")
    assert page.status_code == 200
    assert 'href="/admin"' in page.text


def test_the_admin_view_lists_people_with_their_roles(keycloak):  # noqa: F811
    client, _, _, _, sign_in = keycloak
    sign_in(READER_CLAIMS)
    sign_in(CURATOR_CLAIMS)
    sign_in(ADMIN_CLAIMS)

    page = client.get("/admin").text

    assert "Omar Reader" in page and "Sara Curator" in page and "Amina Admin" in page
    assert "reader" in page and "curator" in page
    assert "Every workspace (admin role)" in page, "an admin needs no grants"


def test_ticking_a_box_gives_that_person_the_workspace(keycloak):  # noqa: F811
    client, _, db_path, _, sign_in = keycloak
    hr = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    workspaces.create_workspace(name="Legal", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    assert f'href="/workspaces?ws={hr.id}"' not in client.get("/workspaces").text
    sign_in(ADMIN_CLAIMS)

    client.post(
        "/admin/grants",
        data={"user_id": "kc-reader", "workspace_id": [hr.id]},
        follow_redirects=False,
    )

    sign_in(READER_CLAIMS)
    page = client.get("/workspaces").text
    assert f'href="/workspaces?ws={hr.id}"' in page
    assert "Legal" not in page
    assert "granted access" in _actions(db_path)


def test_unticking_every_box_takes_the_workspaces_away(keycloak):  # noqa: F811
    client, _, db_path, _, sign_in = keycloak
    hr = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    sign_in(ADMIN_CLAIMS)
    client.post(
        "/admin/grants", data={"user_id": "kc-reader", "workspace_id": [hr.id]},
        follow_redirects=False,
    )

    # A form of checkboxes posts NOTHING for an unticked box, so an empty
    # submission means "none" and must revoke rather than do nothing.
    client.post("/admin/grants", data={"user_id": "kc-reader"}, follow_redirects=False)

    sign_in(READER_CLAIMS)
    page = client.get("/workspaces").text
    assert f'href="/workspaces?ws={hr.id}"' not in page
    assert "No workspace has been given to you yet" in page, (
        "a reader with nothing granted must not be told to create one"
    )
    assert "revoked access" in _actions(db_path)


def test_two_ticked_boxes_both_land(keycloak):  # noqa: F811
    """The form decoder used to keep only the last value of a repeated
    field, which would have granted one workspace out of two, silently."""
    client, _, db_path, _, sign_in = keycloak
    hr = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    legal = workspaces.create_workspace(
        name="Legal", folder_path=str(db_path.parent), db_path=db_path
    )
    sign_in(READER_CLAIMS)
    sign_in(ADMIN_CLAIMS)

    client.post(
        "/admin/grants",
        data={"user_id": "kc-reader", "workspace_id": [hr.id, legal.id]},
        follow_redirects=False,
    )

    with repo.session(db_path) as conn:
        assert repo.granted_workspace_ids(conn, "kc-reader") == {hr.id, legal.id}


def test_a_reader_cannot_grant_themselves_anything(keycloak):  # noqa: F811
    client, _, db_path, _, sign_in = keycloak
    hr = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)

    response = client.post(
        "/admin/grants",
        data={"user_id": "kc-reader", "workspace_id": [hr.id]},
        follow_redirects=False,
    )

    assert response.status_code == 303
    with repo.session(db_path) as conn:
        assert repo.granted_workspace_ids(conn, "kc-reader") == set()


def test_signing_a_person_out_everywhere_ends_their_session(keycloak):  # noqa: F811
    client, runtime, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    runtime.conversation(ws.id, "kc-reader")
    reader_cookie = client.cookies[auth.SESSION_COOKIE]
    sign_in(ADMIN_CLAIMS)

    client.post("/admin/people/kc-reader/sign-out", follow_redirects=False)

    with repo.session(db_path) as conn:
        assert repo.get_session(conn, auth.hash_token(reader_cookie)) is None
    assert not any(key.startswith("kc-reader|") for key in runtime.conversations)
    assert "signed a person out everywhere" in _actions(db_path)


def test_the_activity_log_shows_what_was_done_and_never_a_question(keycloak):  # noqa: F811
    client, _, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(ADMIN_CLAIMS)
    client.post(f"/workspaces/{ws.id}/sync", follow_redirects=False)

    page = client.get("/admin").text

    assert "signed in" in page
    assert "started a sync" in page
    assert "HR" in page
    with repo.session(db_path) as conn:
        assert all(
            row["detail"] is None or len(row["detail"]) < 120
            for row in repo.list_activity(conn)
        ), "a detail long enough to be a question has no business in the log"


def test_a_deleted_workspace_leaves_its_events_readable(keycloak):  # noqa: F811
    """The event still happened; hiding it would be the worse lie."""
    client, _, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="Gone", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(ADMIN_CLAIMS)
    client.post(f"/workspaces/{ws.id}/sync", follow_redirects=False)
    with repo.session(db_path) as conn:
        conn.execute("DELETE FROM workspace WHERE id = ?", (ws.id,))

    rows = admin_screen.activity(db_path=db_path)

    assert any(row.action == "started a sync" for row in rows)
    assert all(row.workspace_name != "Gone" for row in rows)
    assert client.get("/admin").status_code == 200


def test_a_workspace_id_that_does_not_exist_grants_nothing_and_breaks_nothing(keycloak):  # noqa: F811
    """`workspace_grant.workspace_id` has a foreign key, so an id nobody
    created would raise inside the request and answer 500. Filtered to the
    workspaces that exist, a hand-edited form is simply ignored."""
    client, _, db_path, _, sign_in = keycloak
    real = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    sign_in(ADMIN_CLAIMS)

    response = client.post(
        "/admin/grants",
        data={"user_id": "kc-reader", "workspace_id": [real.id, "not-a-workspace"]},
        follow_redirects=False,
    )

    assert response.status_code == 303
    with repo.session(db_path) as conn:
        assert repo.granted_workspace_ids(conn, "kc-reader") == {real.id}
