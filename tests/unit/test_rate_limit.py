"""ST-55: the rate limiter's own rules, with a scripted clock.

Route-level proof (sign-in, asking, the login-free modes untouched) lives in
tests/integration/test_s6_auth.py and test_s1_chat_screen.py.
"""

from __future__ import annotations

import re
import types

import pytest

from ui import rate_limit
from ui.rate_limit import Limiter, Rule, client_address

RULE = Rule("test", "POST", re.compile(r"^/x$"), limit=3, window_seconds=60, per="person")


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_request_over_the_limit_is_refused_with_the_seconds_to_wait():
    clock = Clock()
    limiter = Limiter(clock=clock)

    allowed = [limiter.take(RULE, "amina") for _ in range(3)]
    clock.now += 10
    refused = limiter.take(RULE, "amina")

    assert allowed == [0, 0, 0]
    assert refused == 50, "the oldest hit ages out 60 s after it: exactly 50 s from now"


def test_the_window_slides_so_waiting_is_enough():
    clock = Clock()
    limiter = Limiter(clock=clock)
    for _ in range(3):
        limiter.take(RULE, "amina")

    clock.now += 60

    assert limiter.take(RULE, "amina") == 0


def test_a_refused_request_does_not_count_against_the_person():
    """Otherwise someone retrying while refused would never get back in."""
    clock = Clock()
    limiter = Limiter(clock=clock)
    for _ in range(3):
        limiter.take(RULE, "amina")
    clock.now += 30
    for _ in range(10):
        assert limiter.take(RULE, "amina") > 0

    # The three allowed requests have aged out; the ten refused ones, 30 s
    # younger, would still fill the window if they had been counted.
    clock.now += 31

    assert limiter.take(RULE, "amina") == 0


def test_people_and_rules_are_counted_separately():
    limiter = Limiter(clock=Clock())
    other_rule = Rule("other", "POST", re.compile(r"^/y$"), 3, 60, "person")
    for _ in range(3):
        limiter.take(RULE, "amina")

    assert limiter.take(RULE, "omar") == 0
    assert limiter.take(other_rule, "amina") == 0
    assert limiter.take(RULE, "amina") > 0


def test_a_flood_of_new_keys_cannot_grow_memory_without_limit(monkeypatch):
    monkeypatch.setattr(rate_limit, "_MAX_KEYS", 3)
    limiter = Limiter(clock=Clock())

    for n in range(10):
        limiter.take(RULE, f"address-{n}")

    assert len(limiter._hits) == 3
    assert ("test", "address-9") in limiter._hits, "the newest stays"
    assert ("test", "address-0") not in limiter._hits, "the stalest goes first"


def test_a_full_table_drops_expired_keys_before_a_live_one(monkeypatch):
    """Second review of #150, its counterexample: someone creates
    workspaces (a one-hour window) at t=0, an address hits sign-in (five
    minutes) at t=100. At t=1000 a newcomer arrives in a full table. The
    sign-in key has expired; the workspace key has not, and must survive --
    least-recently-used alone would drop it and reset that person's count."""
    monkeypatch.setattr(rate_limit, "_MAX_KEYS", 2)
    clock = Clock()
    clock.now = 0.0
    limiter = Limiter(clock=clock)
    hourly = Rule("create", "POST", re.compile(r"^/w$"), 1, 3600, "person")
    short = Rule("sign-in", "GET", re.compile(r"^/l$"), 5, 300, "address")

    limiter.take(hourly, "amina")
    clock.now = 100.0
    limiter.take(short, "203.0.113.9")
    clock.now = 1000.0
    limiter.take(short, "198.51.100.7")

    assert limiter.take(hourly, "amina") > 0, "her hourly count was reset"
    assert ("sign-in", "203.0.113.9") not in limiter._hits


def _request(forwarded: str | None, host: str = "10.0.0.1"):
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return types.SimpleNamespace(headers=headers, client=types.SimpleNamespace(host=host))


@pytest.mark.parametrize(
    ("forwarded", "expected"),
    [
        ("203.0.113.9", "203.0.113.9"),
        # The client may send its own header; the proxy APPENDS the real
        # address, so only the last entry can be trusted.
        ("1.2.3.4, 203.0.113.9", "203.0.113.9"),
        ("  , 203.0.113.9 ", "203.0.113.9"),
        (None, "10.0.0.1"),
        ("", "10.0.0.1"),
    ],
)
def test_behind_a_proxy_the_address_is_the_hop_the_proxy_appended(forwarded, expected):
    assert client_address(_request(forwarded), behind_proxy=True) == expected


def test_without_a_proxy_a_forwarded_header_is_ignored():
    """Review of #150: with nothing in front to append a real address, the
    header is whatever the client invents -- a fresh bucket per request."""
    assert client_address(_request("9.9.9.9"), behind_proxy=False) == "10.0.0.1"


@pytest.mark.parametrize(
    ("method", "path", "rule"),
    [
        ("GET", "/auth/login", "sign-in"),
        ("GET", "/auth/callback", None),
        ("POST", "/chat/ask", "ask"),
        ("POST", "/workspaces/abc/sync", "sync"),
        ("POST", "/workspaces", "create-workspace"),
        ("POST", "/workspaces/abc/documents", "upload"),
        ("POST", "/chat/new", "change"),
        ("POST", "/chat/feedback", "change"),
        ("POST", "/chat/history/delete", "change"),
        ("POST", "/chat/conversations/abc/rename", "change"),
        ("POST", "/chat/conversations/abc/delete", "change"),
        ("POST", "/workspaces/abc/rename", "change"),
        ("POST", "/workspaces/abc/legal-flag", "change"),
        ("POST", "/workspaces/abc/delete", "change"),
        ("POST", "/workspaces/abc/documents/contrat.pdf/remove", "change"),
        ("GET", "/workspaces", None),
        ("GET", "/chat/messages", None),
        ("POST", "/workspaces/abc/sync/cancel", None),
    ],
)
def test_each_rule_covers_exactly_its_real_routes(method, path, rule):
    """A typo in a path pattern would silently cap nothing (review of #150).
    One sign-in is ONE count: the return from Keycloak is not counted."""
    matched = [r.name for r in rate_limit.RULES if r.method == method and r.path.match(path)]
    assert matched == ([rule] if rule else [])


def test_every_post_route_is_capped_or_deliberately_exempt():
    """Second review of #150: the rule table was checked against paths
    written by hand, so a renamed route or a new costly POST would have
    passed silently uncapped. This walks the real app instead."""
    from app import Runtime, create_app

    exempt = {
        "/auth/logout",
        "/chat/cancel",
        "/workspace",
        "/workspaces/{workspace_id}/sync/cancel",
    }
    uncovered = []
    for route in create_app(Runtime()).routes:
        methods = getattr(route, "methods", None) or set()
        if "POST" not in methods or route.path.startswith("/api/") or route.path in exempt:
            continue
        concrete = re.sub(r"\{[^}]+\}", "abc", route.path)
        if not any(r.method == "POST" and r.path.match(concrete) for r in rate_limit.RULES):
            uncovered.append(route.path)

    assert uncovered == []
