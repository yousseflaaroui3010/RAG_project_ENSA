"""F-14: `ui.rtl`'s content-language detection, the real trigger behind
`app.py`'s auto-mirroring (`_direction`/`_lang`/`_workspace_is_arabic`).

Two functions, two shapes of test:

* `workspace_is_arabic` reads stored parent JSON files off disk (the same
  files `parent_store.py` writes at Sync time) -- these tests write real
  JSON files to `tmp_path`, matching `parent_store.save_parents`'s own
  on-disk shape, and never touch the embedding model or a real Sync.
* `text_is_arabic` is a pure function over one string -- the per-element
  signal `app.py` registers as the Jinja global `is_arabic`.
"""

from __future__ import annotations

import json

from ui import rtl

ARABIC_SENTENCE = (
    "المادة 13: مدة "
    "التجربة ثلاثة "
    "أشهر للأطر."
)
FRENCH_SENTENCE = (
    "La periode d'essai est de trois mois pour les cadres et assimiles, "
    "renouvelable une seule fois."
)


def _write_parent(directory, parent_id: str, text: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "id": parent_id,
        "text": text,
        "source_file": "code-du-travail.pdf",
        "section_label": None,
    }
    (directory / f"{parent_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


# --- workspace_is_arabic ----------------------------------------------


def test_a_workspace_of_arabic_parents_is_detected_as_arabic(tmp_path):
    directory = tmp_path / "ws-1"
    _write_parent(directory, "p1", ARABIC_SENTENCE * 5)
    _write_parent(directory, "p2", ARABIC_SENTENCE * 5)

    assert rtl.workspace_is_arabic("ws-1", base_path=tmp_path) is True


def test_a_workspace_of_french_parents_is_not_detected_as_arabic(tmp_path):
    directory = tmp_path / "ws-1"
    _write_parent(directory, "p1", FRENCH_SENTENCE * 5)
    _write_parent(directory, "p2", FRENCH_SENTENCE * 5)

    assert rtl.workspace_is_arabic("ws-1", base_path=tmp_path) is False


def test_a_workspace_with_no_parents_yet_is_not_arabic(tmp_path):
    """Never synced == honest 'not Arabic', not an error and not a guess."""
    assert rtl.workspace_is_arabic("never-synced", base_path=tmp_path) is False


def test_an_empty_parent_directory_is_not_arabic(tmp_path):
    """The directory exists (a workspace that WAS synced) but every parent
    is empty text -- the zero-letters case must not divide by zero and
    must not read as "100% Arabic of nothing"."""
    directory = tmp_path / "ws-1"
    _write_parent(directory, "p1", "")
    _write_parent(directory, "p2", "   \n\n   ")

    assert rtl.workspace_is_arabic("ws-1", base_path=tmp_path) is False


def test_a_corrupt_parent_file_is_skipped_not_fatal(tmp_path):
    """A best-effort display signal must not crash a page render over one
    bad file -- `parent_store.get_parent` is where a corrupt parent is
    supposed to raise, at answer time; this is not that seam."""
    directory = tmp_path / "ws-1"
    directory.mkdir(parents=True)
    (directory / "broken.json").write_text("not json at all {{{", encoding="utf-8")
    _write_parent(directory, "p2", ARABIC_SENTENCE * 5)

    assert rtl.workspace_is_arabic("ws-1", base_path=tmp_path) is True


def test_a_hostile_workspace_id_is_rejected_not_traversed(tmp_path):
    """The same allow-list `parent_store.py` checks path segments
    against, applied here too: a `../` id must never escape `base_path`."""
    assert rtl.workspace_is_arabic("../../etc", base_path=tmp_path) is False


def test_workspace_is_arabic_never_reaches_a_majority_from_a_minority(tmp_path):
    """A single Arabic legal term quoted inside an otherwise-French
    workspace must not flip the whole workspace to RTL -- the majority
    threshold (DECISIONS.md, 2026-09-13) is the whole point of sampling
    a ratio rather than checking "any Arabic found"."""
    directory = tmp_path / "ws-1"
    _write_parent(directory, "p1", FRENCH_SENTENCE + " (terme: مادة)")

    assert rtl.workspace_is_arabic("ws-1", base_path=tmp_path) is False


# --- text_is_arabic -----------------------------------------------------


def test_text_is_arabic_true_for_arabic_prose():
    assert rtl.text_is_arabic(ARABIC_SENTENCE) is True


def test_text_is_arabic_false_for_french_prose():
    assert rtl.text_is_arabic(FRENCH_SENTENCE) is False


def test_text_is_arabic_false_for_none_and_empty():
    assert rtl.text_is_arabic(None) is False
    assert rtl.text_is_arabic("") is False


def test_text_is_arabic_false_for_a_file_name_even_if_others_are_arabic():
    """A search string that is just a bare Latin file name (no letters at
    all otherwise) must not be mislabelled Arabic by an empty denominator
    quirk -- it has Latin letters, so the ratio is a clean 0."""
    assert rtl.text_is_arabic("code-du-travail.pdf") is False
