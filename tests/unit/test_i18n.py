"""S6 interface language: catalogs, lookup rules, and the English sentences
Python code builds (which must stay translatable)."""

from __future__ import annotations

import pytest
from markupsafe import Markup

import agent.nodes as nodes
import app as app_module
import change_detection
import conversion
import sync
import ui.conversation as conversation
import ui.runs as runs
import ui.screen as screen
import ui.workspaces_screen as workspaces_screen
from config import Settings
from ui import i18n
from ui.i18n import ar, en, fr

PLURAL_SUFFIXES = {"zero", "one", "two", "few", "many", "other"}


def _base_keys(messages: dict[str, str]) -> set[str]:
    keys = set()
    for key in messages:
        head, _, tail = key.rpartition(".")
        keys.add(head if tail in PLURAL_SUFFIXES and head else key)
    return keys


@pytest.mark.parametrize("catalog", [fr, ar], ids=["fr", "ar"])
def test_every_catalog_carries_exactly_the_english_keys(catalog):
    """A key only in English would show English copy inside a French page;
    a key only in French would never be tested in English at all."""
    assert _base_keys(catalog.MESSAGES) == _base_keys(en.MESSAGES)


@pytest.mark.parametrize("catalog", [fr, ar, en], ids=["fr", "ar", "en"])
def test_every_plural_key_has_an_other_form(catalog):
    """`other` is the fallback every plural lookup lands on."""
    for key in catalog.MESSAGES:
        head, _, tail = key.rpartition(".")
        if tail in PLURAL_SUFFIXES:
            assert f"{head}.other" in catalog.MESSAGES, f"{key} has no {head}.other"


def test_the_setting_accepts_exactly_the_supported_languages():
    """config.py keeps a literal copy of the list so it never imports ui/."""
    for code in i18n.SUPPORTED:
        assert Settings(_env_file=None, default_ui_language=code).default_ui_language == code
    with pytest.raises(ValueError):
        Settings(_env_file=None, default_ui_language="de")


def test_french_is_the_real_default(monkeypatch):
    monkeypatch.delenv("DEFAULT_UI_LANGUAGE", raising=False)
    assert Settings(_env_file=None).default_ui_language == "fr"
    assert i18n.DEFAULT == "fr"


@pytest.mark.parametrize(
    ("count", "category"),
    [(0, "zero"), (1, "one"), (2, "two"), (3, "few"), (10, "few"), (11, "many"),
     (99, "many"), (100, "other"), (102, "other"), (103, "few"), (111, "many")],
)
def test_arabic_plural_categories_follow_cldr(count, category):
    assert i18n.plural_category("ar", count) == category


def test_french_and_english_plurals_are_one_or_other():
    assert i18n.plural_category("fr", 1) == "one"
    assert i18n.plural_category("fr", 2) == "other"
    assert i18n.plural_category("en", 0) == "other"


def test_plural_lookup_uses_the_language_own_forms():
    assert i18n.translate("ar", "ws.sync.processed", count=2) == "تمت معالجة ملفين حتى الآن"
    assert i18n.translate("ar", "ws.sync.processed", count=5) == "تمت معالجة 5 ملفات حتى الآن"
    assert i18n.translate("ar", "ws.sync.processed", count=11) == "تمت معالجة 11 ملفًا حتى الآن"
    assert i18n.translate("fr", "ws.sync.processed", count=1) == "1 fichier traité jusqu’ici"


def test_count_on_a_key_without_plural_forms_is_just_a_parameter():
    """Found by the screen test: "Sources ({count})" has no .one/.other, and
    passing count= used to fall through to the missing marker in every
    language, English included."""
    assert i18n.translate("en", "sources.title", count=2) == "Sources (2)"
    assert i18n.translate("ar", "sources.title", count=2) == "المصادر (2)"


def test_a_missing_key_is_loud_not_silent():
    assert i18n.translate("fr", "no.such.key") == "⟦missing:no.such.key⟧"


def test_markup_keys_escape_their_parameters():
    """The catalog's own <bdi> survives; a workspace name's tags do not."""
    rendered = i18n.translate_markup("fr", "conv.route.yes_html", name="<script>x</script>")
    assert isinstance(rendered, Markup)
    assert "<bdi>&lt;script&gt;x&lt;/script&gt;</bdi>" in rendered
    with pytest.raises(ValueError):
        i18n.translate_markup("fr", "chat.send")


def test_unknown_text_passes_through_untranslated():
    """A model's exception message or a document's words are never hidden."""
    assert i18n.translate_text("fr", "ValueError: boom") == "ValueError: boom"
    assert i18n.translate_text("en", "Added") == "Added"


def test_parameters_survive_phrase_translation():
    assert i18n.translate_text("fr", "Running 3/60") == "En cours 3/60"
    assert i18n.translate_text("fr", "the file could not be read: disk gone") == (
        "le fichier n’a pas pu être lu : disk gone"
    )


def _english_sentences_built_in_python() -> list[str]:
    """The actual strings the code produces today, read from the code itself,
    so a reworded sentence that no longer matches its catalog entry fails
    here instead of silently staying English on a French page."""
    proposal = conversation.route_proposal_message("q", [
        type("Candidate", (), {"name": "Manuels", "workspace_id": "w", "score": 0.9})()
    ])
    error = conversation.error_message(RuntimeError("x"), "Quelle durée ?")
    return [
        screen.SOURCES_PROMISE,
        screen.NO_DOCUMENTS_REASON,
        screen.BUSY_REASON,
        *screen.sample_questions(["code.pdf"]),
        *runs.STAGE_LABELS.values(),
        conversation.NO_MATCH_TEXT,
        conversation.INTERRUPTED_TEXT,
        # Both refusals, not just the one seen failing on the demo: the
        # unreadable-sections variant is rendered by the same template
        # line and would go back to English unnoticed (review, 2026-09-16).
        nodes.REFUSAL_TEXT,
        nodes.REFUSAL_TEXT_UNREADABLE,
        proposal.text,
        error.error.sentence,
        error.error.attempted,
        error.error.hint,
        *(label for _role, _shape, label in workspaces_screen._STATUS_META.values()),
        app_module.EVIDENCE_ONLY_MESSAGE,
        change_detection.UNSUPPORTED_TYPE_REASON,
        change_detection.UNREADABLE_STAT_REASON.format(error="denied"),
        conversion._REASON_PDF_DAMAGED,
        conversion._REASON_PDF_LOCKED,
        conversion._REASON_PDF_NO_TEXT_LAYER,
        conversion._REASON_PDF_OCR_NO_TEXT,
        conversion._REASON_PDF_OCR_TOO_LONG.format(pages=300, limit=200),
        conversion._REASON_DOCX_DAMAGED,
        conversion._REASON_PPTX_DAMAGED,
        conversion._REASON_EMPTY,
        conversion._REASON_UNDECODABLE,
        conversion._REASON_UNREADABLE.format(detail="denied"),
        sync.REMOVED_REASON,
        sync.UNEXPECTED_FAILURE_REASON.format(detail="boom"),
        sync.CANCELLED_REASON,
    ]


@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_every_sentence_python_builds_has_a_translation(lang):
    untranslated = [
        text for text in _english_sentences_built_in_python()
        if i18n.translate_text(lang, text) == text
    ]
    assert untranslated == []


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("en", "12 Sep 2026, 14:12 UTC"),
        ("fr", "12 sept. 2026, 14:12 UTC"),
        ("ar", "12 شتنبر 2026، 14:12 UTC"),
    ],
)
def test_dates_read_naturally_in_each_language(lang, expected):
    assert screen.format_when("2026-09-12T14:12:46+00:00", lang) == expected
