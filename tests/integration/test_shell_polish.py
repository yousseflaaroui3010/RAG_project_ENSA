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
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urldefrag

from fastapi.testclient import TestClient

from app import Runtime, create_app
from db import repo

SVG_NS = "{http://www.w3.org/2000/svg}"
SEEN_LETTER = "س"


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
    """Kill test: delete the icon link and the first assertion goes red. The
    browser only falls back to requesting /favicon.ico when a page names no
    icon; a data: URI is never fetched from this server.

    The icon is DECODED AND PARSED, not just found (review of this change):
    a link that merely starts with `data:image/svg+xml,` stays green with an
    unencoded `#`, a truncated `</svg>` or the wrong letter bytes, and the
    tab would show a blank square. Kill test: break any of those and the
    parse or the letter assertion goes red."""
    page = _page(tmp_path)

    icon = re.search(r'<link[^>]*\brel="icon"[^>]*\bhref="([^"]+)"', page)
    assert icon, "no tab icon declared, so the browser requests /favicon.ico"
    prefix = "data:image/svg+xml,"
    assert icon.group(1).startswith(prefix)
    # Cut at the first raw `#` exactly as a browser does: in a URL it starts
    # the fragment, so everything after it never reaches the SVG parser. A
    # colour written as a bare `#1D4E78` instead of `%231D4E78` truncates the
    # icon there -- and a plain `unquote` would have parsed it happily.
    document, _fragment = urldefrag(icon.group(1))
    svg = ET.fromstring(unquote(document[len(prefix):]))
    text = svg.find(f"{SVG_NS}text")
    assert text is not None and text.text == SEEN_LETTER, "the icon must show the seen letter"


def test_the_phone_notice_is_the_main_landmark_and_there_is_still_one_main_element(tmp_path):
    """Kill test: drop `role="main"` from the notice and the first assertion
    goes red. The count keeps the fix from becoming a SECOND <main> element,
    which HTML forbids while both are in the document. Attributes are matched
    in any order, so a harmless reorder does not turn this red."""
    page = _page(tmp_path)

    notice = re.search(r'<div\b[^>]*\bclass="desktop-only"[^>]*>', page)
    assert notice and 'role="main"' in notice.group(0)
    assert len(re.findall(r"<main\b", page)) == 1


def test_the_stylesheet_shows_exactly_one_main_area_at_each_width():
    """WHICH of the two is visible is decided by the stylesheet, not the
    markup, so the markup test above cannot see it (review of this change).
    Two edits would leave that test green while a phone showed the wrong
    thing: dropping `.main` from the phone rule (both visible) or changing
    the notice's `display: block` (no notice at all).

    Kill test: make either edit and this goes red."""
    css_path = Path(__file__).resolve().parents[2] / "ui" / "static" / "sanad.css"
    css = css_path.read_text(encoding="utf-8")

    assert re.search(r"^\.desktop-only\s*\{\s*display:\s*none;\s*\}", css, re.M), (
        "outside the phone rule the notice must be hidden"
    )
    phone = re.search(r"@media \(max-width: 767px\) \{(.*?)\n\}", css, re.S)
    assert phone, "the phone rule is gone"
    rule = phone.group(1)
    hidden = re.search(r"([^{}]*)\{\s*display:\s*none;\s*\}", rule)
    assert hidden, "the phone rule no longer hides anything"
    assert ".main" in [selector.strip() for selector in hidden.group(1).split(",")]
    assert re.search(r"\.desktop-only\s*\{[^}]*display:\s*block;", rule), (
        "on a phone the notice must be shown"
    )
