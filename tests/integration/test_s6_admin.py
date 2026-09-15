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
from ui.conversation import Message, MessageKind


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


def test_signing_a_person_out_everywhere_also_deletes_their_stored_history(keycloak):  # noqa: F811
    """ST-51, law 09-08: admin "sign out everywhere" is the answer to
    "take this person's data out of the running process" -- their stored
    transcripts must go too, in every workspace, and nobody else's row
    may be touched."""
    client, runtime, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    reader_conversation = runtime.conversation(ws.id, "kc-reader")
    reader_conversation.messages.append(Message(kind=MessageKind.ANSWER, text="reader's answer"))
    runtime.save_conversation("kc-reader", reader_conversation)
    sign_in(CURATOR_CLAIMS)
    curator_conversation = runtime.conversation(ws.id, "kc-curator")
    curator_conversation.messages.append(Message(kind=MessageKind.ANSWER, text="curator's answer"))
    runtime.save_conversation("kc-curator", curator_conversation)
    sign_in(ADMIN_CLAIMS)

    client.post("/admin/people/kc-reader/sign-out", follow_redirects=False)

    with repo.session(db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM chat_history WHERE user_id = 'kc-reader'"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM chat_history WHERE user_id = 'kc-curator'"
            ).fetchone()[0]
            == 1
        ), "another person's stored history must survive"


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


CREATE_HINT = 'title="Create a workspace before asking questions"'
ASK_ADMIN_HINT = 'title="No workspace is shared with you: ask an administrator for access"'


def test_the_disabled_chat_link_gives_each_person_a_reason_they_can_act_on(keycloak):  # noqa: F811
    """Seen in a real browser, 2026-09-15: Omar, a reader with nothing
    granted, hovered the greyed-out Chat link and was told to "create a
    workspace" -- which no control on his page lets him do.

    Kill test: put back the single title and the reader assertion goes red.
    Kill test: flip the condition and BOTH go red. The admin half is what
    stops a blanket "ask an administrator" from passing: an admin with no
    workspace is the one person who CAN create one. The CURATOR half is what
    stops the check drifting to `is_curator` (review of this change: that
    edit passed a reader-and-admin-only version of this test) -- a curator
    manages documents but cannot create a workspace. The login-free mode is
    pinned separately in test_s1_chat_screen.py and test_s2_workspaces_screen.py."""
    client, _, _, _, sign_in = keycloak

    sign_in(READER_CLAIMS)
    reader_page = client.get("/workspaces").text
    assert ASK_ADMIN_HINT in reader_page
    assert CREATE_HINT not in reader_page

    sign_in(CURATOR_CLAIMS)
    curator_page = client.get("/workspaces").text
    assert ASK_ADMIN_HINT in curator_page
    assert CREATE_HINT not in curator_page

    sign_in(ADMIN_CLAIMS)
    admin_page = client.get("/workspaces").text
    assert CREATE_HINT in admin_page
    assert ASK_ADMIN_HINT not in admin_page


def _detail_for(rows, action: str) -> str | None:
    matches = [row.detail for row in rows if row.action == action]
    assert matches, f"no {action!r} event was logged, so this proves nothing"
    return matches[0]


def test_the_log_names_the_person_acted_on_beside_their_stored_id(keycloak):  # noqa: F811
    """Seen in a real browser, 2026-09-15: "access granted 6fb523a6-decc-..."
    -- an administrator cannot tell who that was. Shown by username now,
    WITH the id beside it: `app_user.username` is overwritten at each
    sign-in and is not unique, so a name alone would let a renamed account
    rewrite who past events appear to be about (review of this change).

    Kill test: drop the username lookup and the name assertions go red.
    Kill test: drop the id from the template and the page assertion goes
    red. Kill test: store the username at WRITE time and the storage
    assertion goes red -- the audit trail keeps the stable id."""
    client, _, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(READER_CLAIMS)
    sign_in(ADMIN_CLAIMS)

    client.post("/admin/grants", data={"user_id": "kc-reader", "workspace_id": [ws.id]})
    client.post("/admin/grants", data={"user_id": "kc-reader"})
    client.post("/admin/people/kc-reader/sign-out")

    rows = admin_screen.activity(db_path=db_path)
    for action in admin_screen.PERSON_ACTIONS:
        assert _detail_for(rows, action) == "omar"
        assert [r.person_id for r in rows if r.action == action][0] == "kc-reader"

    # On the page, in the LOG section only: the people table above it
    # carries "kc-reader" in a hidden form field whatever the log shows.
    page = client.get("/admin").text
    log = page[page.index('id="admin-activity"'):]
    assert "omar" in log
    assert '<span class="muted mono">kc-reader</span>' in log

    with repo.session(db_path) as conn:
        stored = [
            row["detail"]
            for row in repo.list_activity(conn)
            if row["action"] == admin_screen.GRANTED_ACCESS
        ]
    assert stored == ["kc-reader"]


def test_the_admin_page_header_lists_the_workspaces_that_exist(keycloak):  # noqa: F811
    """Seen in a real browser, 2026-09-15: on /admin, with a workspace
    existing, the header said "no workspace yet", disabled the selector and
    disabled the Chat link. The page borrowed the sign-in page's context,
    whose workspace list is empty on purpose (nobody is signed in there).

    Kill test: remove the `workspaces` override in `admin_route` and all
    three assertions go red."""
    client, _, db_path, _, sign_in = keycloak
    ws = workspaces.create_workspace(name="HR", folder_path=str(db_path.parent), db_path=db_path)
    sign_in(ADMIN_CLAIMS)

    page = client.get("/admin").text

    # `<option value=` and the disabled span's class, not `value="{id}"` or
    # `href="/"`: a grant checkbox can carry the same value, and the Sanad
    # logo is `href="/"` on every page, so either would pass whatever the
    # header showed.
    assert f'<option value="{ws.id}"' in page, "the header selector does not offer the workspace"
    assert 'class="shell__link is-disabled"' not in page, "the Chat link is still disabled"
    assert CREATE_HINT not in page


def test_only_person_events_are_resolved_and_an_unknown_id_is_shown_as_stored(keycloak):  # noqa: F811
    """A refused action's detail is a URL path: it must never be looked up
    as a person. And an id with no account behind it is shown as stored,
    for the same reason a deleted workspace's events stay readable.

    Kill test: resolve `detail` for EVERY action and the refused row reads
    "pathname" instead of "/admin". That is FORCED here: an account whose id
    is literally "/admin" exists, so the lookup has something to wrongly
    find -- without it, resolving everything would still leave "/admin" and
    this could not fail. Kill test: drop the fallback in `.get(id, id)` and
    the unknown id shows as None."""
    client, _, db_path, _, sign_in = keycloak
    sign_in(
        {
            "sub": "/admin",
            "preferred_username": "pathname",
            "name": "Path Name",
            "realm_access": {"roles": ["sanad-reader"]},
        }
    )
    sign_in(ADMIN_CLAIMS)
    with repo.session(db_path) as conn:
        repo.record_activity(
            conn, user_id="kc-admin", username="amina", action="refused", detail="/admin"
        )
        repo.record_activity(
            conn, user_id="kc-admin", username="amina", action="granted access", detail="kc-gone"
        )

    rows = admin_screen.activity(db_path=db_path)

    assert _detail_for(rows, "refused") == "/admin"
    assert _detail_for(rows, "granted access") == "kc-gone"
