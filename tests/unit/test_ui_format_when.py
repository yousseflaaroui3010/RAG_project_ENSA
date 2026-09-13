"""ui.screen.format_when: stored timestamps shown the way a person reads them."""

from __future__ import annotations

from ui.screen import format_when


def test_an_offset_timestamp_is_shown_in_utc_and_says_so():
    assert format_when("2026-09-12T14:12:46.567306+00:00") == "12 Sep 2026, 14:12 UTC"


def test_a_non_utc_offset_is_converted_rather_than_mislabelled():
    """A +01:00 time labelled UTC without converting would be an hour wrong."""
    assert format_when("2026-09-12T15:12:00+01:00") == "12 Sep 2026, 14:12 UTC"


def test_a_naive_timestamp_is_not_claimed_to_be_utc():
    assert format_when("2026-09-05T08:03:00") == "5 Sep 2026, 08:03"


def test_nothing_becomes_a_dash_and_garbage_passes_through():
    assert format_when(None) == "—"
    assert format_when("") == "—"
    assert format_when("not a date") == "not a date"
