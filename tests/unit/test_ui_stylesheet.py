"""Stylesheet rules that carry behaviour, not only looks.

The contrast, direction and spacing guards live in test_ui_contrast.py; this
file holds rules whose absence breaks a control rather than a colour.
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[2] / "ui" / "static" / "sanad.css"


def test_the_hidden_attribute_beats_every_display_rule():
    """Found in the v2.1 refresh by screenshot: `.btn { display: inline-flex }`
    outranks the browser's own `[hidden] { display: none }`, so the no-script
    "Switch" button stayed visible after sanad.js hid it, and the theme toggle
    would show as a dead control with scripting off. The global rule must be
    there and must be !important to beat class selectors."""
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"\[hidden\]\s*\{\s*display:\s*none\s*!important;\s*\}", css)


def test_the_composer_focus_ring_uses_the_floored_focus_role():
    """The input hides its own outline and the row draws the ring instead, so
    the row's ring must be --focus (3:1 floor), not a decorative tint."""
    css = CSS.read_text(encoding="utf-8")
    rule = re.search(r"\.composer__row:focus-within\s*\{([^}]*)\}", css)
    assert rule, "the composer row has no focus-within ring"
    assert "var(--focus)" in rule.group(1)
