"""S6: every screen renders in French and in Arabic, through the real app.

The English-leak check is the strong one: for a page rendered in French or
Arabic, no English catalog sentence may appear in it (unless that language
genuinely uses the same words). A template string that was never wrapped in
t() shows up here as English inside a French page.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import vector_store
from agent import nodes
from app import Runtime, create_app
from db import repo
from tests.conversations import live_conversation
from tests.integration.test_s1_chat_screen import (  # noqa: F401 -- fixture reuse
    _ask,
    _settled,
    sanad,
)
from tests.integration.test_s3_reports_screen import _seed_feedback, _seed_report
from ui.conversation import Message, MessageKind
from ui.i18n import ar, en, fr

CATALOGS = {"fr": fr.MESSAGES, "ar": ar.MESSAGES}
TEMPLATES = Path(__file__).resolve().parents[2] / "ui" / "templates"


def _visible_text(page: str) -> str:
    """The page as a reader sees it: tags and scripts out, entities decoded."""
    page = re.sub(r"<script.*?</script>", " ", page, flags=re.S)
    page = re.sub(r"<[^>]+>", " ", page)
    return " ".join(html.unescape(page).split())


def _english_leaks(page: str, lang: str) -> list[str]:
    text = _visible_text(page)
    leaks = []
    for key, english in en.MESSAGES.items():
        if "{" in english or len(english) < 10 or key.endswith("_html"):
            continue
        if CATALOGS[lang].get(key) == english:
            continue
        if english in text:
            leaks.append(f"{key}: {english}")
    return leaks


def _assert_localised(page: str, lang: str) -> None:
    assert f'<html lang="{lang}"' in page
    assert "⟦missing:" not in page
    assert _english_leaks(page, lang) == []


def _empty_app(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    runtime = Runtime(ports_factory=lambda: None, db_path=db_path)
    return TestClient(create_app(runtime)), db_path


@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_chat_with_an_answer_sources_trace_and_feedback_is_localised(sanad, lang):  # noqa: F811
    build, workspace, _ = sanad
    client, runtime = build(legal_flag=True)
    client.get(f"/?lang={lang}")
    _ask(client)
    page = _settled(client, runtime, workspace.id)

    assert "bubble--answer" in page, "the fixture must reach a real answer"
    _assert_localised(page, lang)
    if lang == "ar":
        assert '<html lang="ar" dir="rtl">' in page


@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_an_honest_refusal_is_localised_too(sanad, lang):  # noqa: F811
    """Seen on the live demo, 2026-09-16: the refusal -- the product's whole
    claim -- came up in English inside a French page. Its wording is built
    in `agent/nodes.py`, so it reaches the screen as a finished English
    sentence and needs `tx()` like every other sentence Python produces."""
    build, workspace, _ = sanad
    client, runtime = build()
    client.get(f"/?lang={lang}")
    conversation = live_conversation(runtime, workspace.id)
    conversation.messages.append(
        Message(
            kind=MessageKind.REFUSAL,
            text=nodes.REFUSAL_TEXT,
            searched=("duree periode essai cadre",),
            retries=2,
        )
    )

    page = client.get("/").text

    assert "bubble--refusal" in page, "the test must render a real refusal"
    _assert_localised(page, lang)
    assert nodes.REFUSAL_TEXT not in _visible_text(page)
    if lang == "ar":
        # Reverting only the is_arabic() half of the line would leave an
        # Arabic paragraph unmarked, and a screen reader would read it
        # aloud in a French voice.
        assert re.search(r'class="refusal__lead"[^>]*lang="ar"', page)


@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_workspaces_and_delete_confirmation_are_localised(tmp_path, monkeypatch, lang):
    from tests.integration.test_s2_workspaces_screen import _app, _corpus

    with vector_store.open_store(tmp_path / "qdrant") as store:
        client, _runtime, _db = _app(tmp_path, monkeypatch, client=store)
        empty = client.get(f"/workspaces?lang={lang}").text
        _assert_localised(empty, lang)
        created = client.post(
            "/workspaces", data={"name": "RH", "folder_path": str(_corpus(tmp_path))},
            follow_redirects=True,
        ).text
        _assert_localised(created, lang)
        workspace_id = re.search(r"/workspaces/([0-9a-f-]+)/delete", created).group(1)
        confirm = client.get(f"/workspaces/{workspace_id}/delete").text
        _assert_localised(confirm, lang)


@pytest.mark.parametrize("lang", ["fr", "ar"])
def test_reports_list_detail_and_feedback_are_localised(tmp_path, lang):
    client, db_path = _empty_app(tmp_path)
    empty = client.get(f"/reports?lang={lang}").text
    _assert_localised(empty, lang)

    run_id, _report_path = _seed_report(tmp_path, db_path)
    _seed_feedback(db_path)
    listing = client.get("/reports").text
    assert f"/reports/{run_id}" in listing, "the seeded run must be listed"
    _assert_localised(listing, lang)
    response = client.get(f"/reports/{run_id}")
    # A real report, not the "no such report" page: that page is localised
    # too, and an earlier version of this test passed on it by mistake.
    assert response.status_code == 200
    assert "data-report-scores" in response.text
    _assert_localised(response.text, lang)


def test_choosing_arabic_is_remembered_and_mirrors_the_screen(tmp_path):
    client, _db = _empty_app(tmp_path)

    chosen = client.get("/reports?lang=ar")
    assert "sanad_lang=ar" in chosen.headers.get("set-cookie", "")
    assert '<html lang="ar" dir="rtl">' in chosen.text

    later = client.get("/reports")
    assert '<html lang="ar" dir="rtl">' in later.text


def test_an_unsupported_language_is_ignored_and_not_remembered(tmp_path):
    client, _db = _empty_app(tmp_path)

    response = client.get("/reports?lang=xx")

    assert "set-cookie" not in response.headers
    assert '<html lang="en"' in response.text, "falls back to the configured default"


def test_without_a_choice_the_configured_default_applies(tmp_path, monkeypatch):
    import ui.i18n.request as request_module
    from config import get_settings

    french = get_settings().model_copy(update={"default_ui_language": "fr"})
    monkeypatch.setattr("config.get_settings", lambda: french)
    client, _db = _empty_app(tmp_path)

    page = client.get("/reports").text

    assert request_module.COOKIE_NAME == "sanad_lang"
    assert '<html lang="fr" dir="ltr">' in page


def test_the_switcher_offers_each_language_named_in_itself(tmp_path):
    client, _db = _empty_app(tmp_path)

    page = client.get("/reports?lang=fr").text
    switcher = page.split('class="lang-switch"')[1].split("</nav>")[0]

    assert 'hreflang="fr" lang="fr"' in switcher and "Français" in switcher
    assert 'hreflang="ar" lang="ar"' in switcher and "العربية" in switcher
    assert 'hreflang="en" lang="en"' in switcher and "English" in switcher
    current = re.findall(r'lang-switch__link is-current"[^>]*hreflang="(\w+)"', switcher)
    assert current == ["fr"]


ALLOWED_LITERAL_TEXT = {
    # A shell command, shown verbatim so it can be copied.
    "uv run python scripts/run_evaluation.py --workspace-id &lt;id&gt;",
}


def test_no_template_contains_hard_coded_english_copy():
    """Text between tags that is not a t()/th()/tx() call, a Jinja value, or a
    comment must not be English words -- that is copy that escaped
    translation."""
    offenders = []
    for template in sorted(TEMPLATES.glob("*.html")):
        source = template.read_text(encoding="utf-8")
        source = re.sub(r"\{#.*?#\}", " ", source, flags=re.S)
        source = re.sub(r"<script.*?</script>", " ", source, flags=re.S)
        source = re.sub(r"<svg.*?</svg>", " ", source, flags=re.S)
        source = re.sub(r"\{\{.*?\}\}|\{%.*?%\}", " ", source, flags=re.S)
        for chunk in re.split(r"<[^>]+>", source):
            text = " ".join(chunk.split())
            if text in ALLOWED_LITERAL_TEXT:
                continue
            if re.search(r"[A-Za-z]{2,}\s+[A-Za-z]{2,}", text):
                offenders.append(f"{template.name}: {text}")
        for attribute in re.findall(r'(?:title|aria-label|placeholder)="([^"{]+)"', source):
            if re.search(r"[A-Za-z]{2,}", attribute):
                offenders.append(f"{template.name}: attribute {attribute}")
    assert offenders == []
