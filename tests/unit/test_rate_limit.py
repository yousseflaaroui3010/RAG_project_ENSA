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
    assert refused == 51, "the oldest hit ages out 60 s after it, 50 s from now, rounded up"


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
def test_the_client_address_is_the_hop_the_proxy_appended(forwarded, expected):
    assert client_address(_request(forwarded)) == expected
