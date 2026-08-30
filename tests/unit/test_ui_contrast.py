"""UX spec criterion 10, measured rather than eyeballed (ST-27).

"Given any screen in any state, when inspected against WCAG 2.2 AA, then
text contrast is at least 4.5:1, focus is visible at 3:1, and no status is
conveyed by colour alone."

WHY THIS TEST EXISTS AT ALL, and it is not a hypothetical: the React
reference in `designrag-main/` dropped UX spec 3.4's palette for Tailwind
defaults, and the build journal records the measured consequence --
`border-strong` at **1.48:1 in light** (#cbd5e1 on #ffffff) and **1.88:1
in dark** (#334155 on #090d16) against a 3:1 floor. Nothing caught it,
because a contrast failure does not crash, does not fail a linter, and
looks perfectly fine to whoever picked the colour. Section 3.4 names that
exact trap: "getting this backwards is the usual way an interface fails
1.4.11 while looking fine."

IT READS THE STYLESHEET, NOT A FIXTURE. A copy of the palette in this file
would pass forever while `sanad.css` drifted -- the same defect the build
journal calls out in a drift check that compared against a recorded hash
instead of the source. The tokens asserted here are the bytes the browser
loads.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CSS = Path(__file__).resolve().parents[2] / "ui" / "static" / "sanad.css"

# UX spec 3.4's floors, plus the two status roles ST-27 chose under 3.5's
# licence to "swap the hex values, keep the roles and the contrast ratios".
# `border` is deliberately absent: the spec marks it "none, decorative
# only", and forcing 3:1 on every divider "produces a harsh, cluttered
# interface".
FLOORS = {
    "border-strong": 3.0,
    "text": 4.5,
    "text-muted": 4.5,
    "accent": 4.5,
    "focus": 3.0,
    "notice": 4.5,
    "danger": 4.5,
}


def _block(css: str, selector: str) -> str:
    """The declarations inside one rule, by exact selector."""
    start = css.index(selector + " {") + len(selector) + 2
    return css[start : css.index("}", start)]


def _tokens(block: str) -> dict[str, str]:
    return {
        name: value
        for name, value in re.findall(r"--([a-z-]+):\s*(#[0-9A-Fa-f]{6})\s*;", block)
    }


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_colour: str) -> float:
    """WCAG 2.x relative luminance."""
    raw = hex_colour.lstrip("#")
    r, g, b = (int(raw[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def ratio(first: str, second: str) -> float:
    a, b = luminance(first), luminance(second)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.fixture(scope="module")
def palettes() -> dict[str, dict[str, str]]:
    css = CSS.read_text(encoding="utf-8")
    light = _tokens(_block(css, ":root"))
    # The dark tokens are declared twice on purpose -- once under
    # prefers-color-scheme for the operating system and once under
    # [data-theme="dark"] for the explicit toggle (UX spec 3.4 requires
    # both). The explicit block is read here and the two are asserted
    # equal below, so a value fixed in one and forgotten in the other
    # cannot pass.
    dark = _tokens(_block(css, ':root[data-theme="dark"]'))
    return {"light": light, "dark": dark}


def test_the_stylesheet_really_declares_the_roles_this_test_measures(palettes):
    """The control probe.

    Without it, a renamed token or a changed selector makes `_tokens`
    return {} and every ratio assertion below passes vacuously over an
    empty dict -- green, and measuring nothing. This project has shipped
    exactly that shape of vacuous check before."""
    for theme, palette in palettes.items():
        assert "surface" in palette, f"{theme} has no surface to measure against"
        missing = set(FLOORS) - set(palette)
        assert not missing, f"{theme} is missing {sorted(missing)}"


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_role_clears_its_contrast_floor(palettes, theme):
    """The measurement. Ratios are computed here, from the stylesheet, so
    a colour changed in `sanad.css` is re-measured on the next run rather
    than re-trusted."""
    palette = palettes[theme]
    surface = palette["surface"]
    for role, floor in FLOORS.items():
        measured = ratio(palette[role], surface)
        assert measured >= floor, (
            f"{theme} --{role} ({palette[role]}) is {measured:.2f}:1 against "
            f"--surface ({surface}), below its {floor}:1 floor (UX spec 3.4)"
        )


def test_the_two_dark_palettes_cannot_drift_apart(palettes):
    """Dark is declared twice -- for the OS preference and for the toggle.

    Two copies of one palette is exactly the shape where a colour gets
    fixed in one place, and a projector at a defense showing the OS-dark
    variant renders the unfixed one."""
    css = CSS.read_text(encoding="utf-8")
    media = _tokens(_block(css, ':root:not([data-theme="light"])'))
    assert media == palettes["dark"]


def test_the_measurement_agrees_with_the_journal_s_recorded_numbers():
    """Prove the arithmetic on values whose answer is already written down.

    The build journal computed the React reference's failure as 1.48:1
    light and 1.88:1 dark, and UX spec 3.4 publishes 4.59 and 3.94 for the
    value that replaces it. If this function's maths were wrong, every
    assertion above would be wrong in the same direction and still green."""
    assert ratio("#cbd5e1", "#ffffff") == pytest.approx(1.48, abs=0.01)
    assert ratio("#334155", "#090d16") == pytest.approx(1.88, abs=0.01)
    assert ratio("#6E7681", "#FFFFFF") == pytest.approx(4.59, abs=0.01)
    assert ratio("#6E7681", "#14161A") == pytest.approx(3.94, abs=0.01)
