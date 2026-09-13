"""F-14: which screen direction and document language a workspace's own
content earns (architecture: F-14 "adds an RTL rendering path in `ui`").

THE TRIGGER, decided here rather than guessed at in a template: a screen
mirrors (`<html dir="rtl" lang="ar">`) when the ACTIVE WORKSPACE's own
stored text reads as majority Arabic script. Two other shapes were
considered and rejected:

* a global config flag / env var -- wrong per-workspace: one Sanad
  install holds an Arabic labour-code workspace AND a French one (this is
  the whole premise of F-01's isolation), and a single process-wide
  setting could not show both correctly in the same session;
* a stored per-workspace column (computed once at Sync and cached in
  `workspace`) -- more correct long-term (no per-render disk read) but a
  DDL change to a signed reference table (architecture §7.3) days after
  the Phase 2 pack was signed, for a V2-scoped feature. `docs/phase2/` is
  write-locked (rule 1); this stays a read-only, additive module instead.

So this reads what is ALREADY on disk -- the parent JSON files
`parent_store.py` writes at Sync time -- cheaply and on demand, never at
Sync time and never by loading the embedding model (evidence-only mode,
ST-05, must never trip this: nothing below imports `embeddings.py`).

WHY A SAMPLE, NOT THE WHOLE WORKSPACE: this runs on every render of every
screen (`app.py`'s `_context`, `_ws_context`, `_reports_context`), not
once per Sync. A 2,000-parent legal corpus read whole on every chat
message would turn a page load into a disk scan. `_MAX_PARENTS_SAMPLED`
files, `_SAMPLE_CHARS` characters of each `text` field, is enough signal
for a same-workspace corpus that is either genuinely Arabic or genuinely
not -- Sanad has no mixed-script-workspace requirement to be precise
about (PRD F-01: one workspace, one folder).

An explicit `?dir=rtl`/`?dir=ltr` query override (the ST-38 RTL preview,
`app.py::_direction`) still wins over this when present -- that mechanism
predates F-14 and stays a QA tool for looking at the mirrored CSS with no
Arabic copy at all; auto-detection only fills in when nobody asked for a
specific preview. See the 2026-09-13 DECISIONS row.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from config import get_settings

# Arabic, Arabic Supplement, Arabic Extended-A, and the Presentation Forms
# blocks (the ligated/positional glyphs some producers emit). Together
# these cover the Moroccan legal Arabic this feature targets, including
# Eastern Arabic-Indic digits (U+0660-0669), which live inside the base
# Arabic block.
_ARABIC_SCRIPT = re.compile(
    r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]"
)
# The denominator: any letter or digit, any script. A page of pure
# punctuation/whitespace (an empty or near-empty parent) must not count as
# "0 Arabic out of 0 letters is 100% Arabic" -- see the ZeroDivisionError
# guard below, which is the same shape of bug that would produce.
_LETTER_OR_DIGIT = re.compile(r"\w", re.UNICODE)

# One parent file gives up to this many characters of its `text` field to
# the sample. Small on purpose: a script is visible in the first
# paragraph, and the SAMPLE is a signal, not a proof.
_SAMPLE_CHARS = 500
# At most this many parent files are read per workspace, per render. Caps
# the disk cost for a workspace holding thousands of parents.
_MAX_PARENTS_SAMPLED = 20
# The sample must be MAJORITY Arabic-script letters, not "any Arabic
# found" (which would flip a French workspace quoting one Arabic legal
# term) and not "no non-Arabic found" (which would keep a genuinely
# Arabic corpus in LTR over one Latin file header or footer).
_ARABIC_MAJORITY = 0.5

# Same allow-list `parent_store.py` checks workspace and parent ids
# against before they touch a path -- duplicated rather than imported
# because that one is prefixed private (`_SAFE_IDENTIFIER`) and this
# module's only use of it is a single membership check, not a second
# storage layer.
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")


def workspace_is_arabic(workspace_id: str, *, base_path: str | Path | None = None) -> bool:
    """True when this workspace's own stored parent text reads as
    majority Arabic script, sampled cheaply and never via the embedding
    model.

    False for a workspace with no parents yet (never synced), an id that
    fails the path-segment check, or a sample with no letters at all --
    every one of those is the honest "nothing says this is Arabic" case,
    and LTR is what an empty, French or English workspace should show."""
    if not workspace_id or not _SAFE_IDENTIFIER.match(workspace_id):
        return False

    directory = (
        Path(base_path) if base_path is not None else Path(get_settings().parent_store_path)
    ) / workspace_id
    if not directory.is_dir():
        return False

    # Every render calls this twice (`_direction` and `_lang`), including
    # the chat poll while an answer is running, so the sample is read once
    # per state of the folder, not once per call. The folder's own mtime
    # moves whenever a parent file is added or removed, which is what a
    # Sync that changes the workspace's content does. A parent rewritten in
    # place under the same name keeps the old verdict until the next add or
    # removal; a workspace changing script that way is not a real case.
    try:
        key = (str(directory), directory.stat().st_mtime_ns)
    except OSError:
        return False
    cached = _VERDICTS.get(key)
    if cached is not None:
        return cached
    verdict = _sample_is_arabic(directory)
    if len(_VERDICTS) >= _MAX_CACHED_VERDICTS:
        _VERDICTS.clear()
    _VERDICTS[key] = verdict
    return verdict


# (folder path, folder mtime_ns) -> verdict. Bounded so a long-running
# server that saw many workspaces and many Syncs never grows it forever.
_VERDICTS: dict[tuple[str, int], bool] = {}
_MAX_CACHED_VERDICTS = 256


def _sample_is_arabic(directory: Path) -> bool:
    arabic_chars = 0
    letter_chars = 0
    for path in sorted(directory.glob("*.json"))[:_MAX_PARENTS_SAMPLED]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            sample = payload["text"][:_SAMPLE_CHARS]
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            # A corrupt or unreadable parent is `parent_store.py`'s problem
            # to raise about when an answer actually needs it; this is a
            # best-effort display signal and skips it rather than failing
            # a page render over one bad file.
            continue
        arabic_chars += len(_ARABIC_SCRIPT.findall(sample))
        letter_chars += len(_LETTER_OR_DIGIT.findall(sample))

    if letter_chars == 0:
        return False
    return (arabic_chars / letter_chars) >= _ARABIC_MAJORITY


def text_is_arabic(text: str | None) -> bool:
    """True when one short piece of USER- or MODEL-WRITTEN text -- a
    question, an answer, a reworded search string, a workspace name --
    reads as majority Arabic script.

    The per-element counterpart to `workspace_is_arabic`: that function
    decides whether the whole SCREEN mirrors, from stored document text;
    this one decides whether ONE element also gets `lang="ar"` next to
    its `dir="auto"` (task brief: "lang=ar on Arabic content blocks where
    known helps screen readers"). Templates call it directly (registered
    as a Jinja global in `app.py`) rather than through a stored flag,
    because there is no per-message language field anywhere in the
    pipeline (agent/state.py's `Answer` does not carry one) -- this reads
    the same text the template is about to render, at render time, the
    only place that text and this decision are both already in hand.

    Same threshold, same scripts, as `workspace_is_arabic`, but no
    sampling cap: a question or an answer is already short enough (openapi
    bounds a question at `question_max_length`) that reading it whole
    costs nothing, unlike a multi-thousand-character parent section."""
    if not text:
        return False
    sample = text[:_SAMPLE_CHARS]
    letters = len(_LETTER_OR_DIGIT.findall(sample))
    if letters == 0:
        return False
    return (len(_ARABIC_SCRIPT.findall(sample)) / letters) >= _ARABIC_MAJORITY
