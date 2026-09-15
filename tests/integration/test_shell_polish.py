"""Three things the page shell got wrong, each seen on 2026-09-15.

1. In the login-free mode the header named a "local" person, offered a Sign
   out that signs nobody out, and linked an admin page whose activity log is
   only written with accounts on. `AuthGate` attaches the unrestricted LOCAL
   principal to every request there, so `_signed_in_as` was never None.
   With `AUTH_MODE=keycloak` the account IS shown -- pinned in
   test_s6_auth.py (`action="/auth/logout"` for a signed-in person).
2. Every page asked for /favicon.ico and got a 404 (seen in a real
   browser's console).
3. Below 768px the stylesheet hides <main> and shows a notice, which left a
   phone screen reader no main landmark (Lighthouse landmark-one-main).

The password mode takes the same `AuthGate` branch as the none mode (one
`!= MODE_KEYCLOAK` test), so the none mode stands for both here.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app import Runtime, create_app
from db import repo


def _page(tmp_path) -> str:
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    client = TestClient(create_app(Runtime(ports_factory=lambda: None, db_path=db_path)))
    response = client.get("/workspaces")
    assert response.status_code == 200
    return response.text


def test_the_login_free_header_names_nobody_and_offers_no_sign_out(tmp_path):
    """Kill test: return `request.state.principal` unfiltered from
    `_signed_in_as` (the old code) and all three assertions go red."""
    page = _page(tmp_path)

    assert 'action="/auth/logout"' not in page, "a Sign out that signs nobody out"
    assert 'class="shell__who"' not in page, "the header names a person who does not exist"
    assert 'href="/admin"' not in page, "a link to an admin page that is always empty here"


def test_every_page_carries_its_own_tab_icon_so_the_browser_never_asks_for_one(tmp_path):
    """Kill test: delete the icon link and both assertions go red. The
    browser only falls back to requesting /favicon.ico when a page names no
    icon; a data: URI is never fetched from this server."""
    page = _page(tmp_path)

    icon = re.search(r'<link rel="icon"[^>]*href="([^"]+)"', page)
    assert icon, "no tab icon declared, so the browser requests /favicon.ico"
    assert icon.group(1).startswith("data:image/svg+xml,")


def test_the_phone_notice_is_the_main_landmark_and_there_is_still_one_main_element(tmp_path):
    """Kill test: drop `role="main"` from the notice and the first assertion
    goes red. The count keeps the fix from becoming a SECOND <main> element,
    which HTML forbids while both are in the document."""
    page = _page(tmp_path)

    assert re.search(r'<div class="desktop-only" role="main">', page)
    assert len(re.findall(r"<main\b", page)) == 1
