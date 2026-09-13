"""Sanad's translation catalogs (S6): French by default, Arabic and
English as switchable UI languages.

2026-09-13 human ruling recorded in DECISIONS.md: "the whole platform
should be in French, with possibility to switch to Arabic" -- a change to
docs/phase2's assumption 3 ("V1 UI copy is English"), which is why this
lives outside docs/phase2/ entirely (that pack is write-locked, rule 1)
rather than as an edit to the signed UX spec.

DESIGN, kept deliberately small so a later wave (streaming, a document
library, a reports redesign, Keycloak login) can add keys without
touching this module:

* One dict per language (`fr.py`, `ar.py`, `en.py`), flat, dotted keys
  ("screen.component.thing"), no nesting -- a dict is trivial to diff and
  trivial to test for "same key set" (see tests/unit/test_i18n.py).
* `translate(lang, key, **params)` is the only way to read one. It never
  raises: a missing key is a loud, visible marker in the page
  (`⟦missing:key⟧`) plus a logged warning, never a 500 and never silent
  English leaking through -- "parked and visible beats fixed-wrong" is
  the same rule the task brief states for copy that has no home yet.
* Fallback is requested language -> fr -> en -> the marker. fr is the
  product default (the human ruling above), so a key present only in en
  (a gap while translating) still shows SOMETHING sooner than nothing,
  and fr suggests itself first because it is what most operators will
  actually be running.
* Parameters go through `str.format(**params)`. The result is a plain
  `str`; Jinja autoescapes it like any other expression, so a parameter
  drawn from user or document text (a workspace name, a question) cannot
  inject markup. NEVER mark a `t(...)` call `| safe` unless the key ends
  in `_html` AND every one of its catalog values is fixed prose with no
  `{param}` -- see `_HTML_SAFE_SUFFIX` below. No key in this project uses
  that suffix yet; it exists so a future one can, without a second
  mechanism being invented for it.
* Plurals: `count=` selects a category per the CURRENT language's own
  CLDR rule (`plural_category`), tried as `key.<category>`, falling back
  to `key.other` within that same language before falling back to the
  next language in the chain. fr/en use the simple English-shaped rule
  the task brief asks for (one for exactly 1, other otherwise) -- real
  CLDR French one is "i = 0 or 1", but the brief is explicit ("fr/en
  one/other") and a French speaker reads "0 fichier" as slightly odd
  but never wrong, whereas diverging from the brief without saying so
  would be the worse failure. Arabic gets the real six-category CLDR
  rule (zero/one/two/few/many/other) because Arabic morphology makes the
  simplification actually wrong ("2 ملفات" is not "5 ملفات" is not
  "11 ملفا").
"""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from functools import lru_cache

from markupsafe import Markup, escape

from ui.i18n import ar, en, fr

logger = logging.getLogger(__name__)

# Supported UI languages, fr first because it is DEFAULT (see module
# docstring). Order here is also the order the language switcher renders
# in (app.py reads this, not a second hardcoded tuple).
SUPPORTED: tuple[str, ...] = ("fr", "ar", "en")
DEFAULT = "fr"

# Human-readable display names for the language switcher. Each language
# names ITSELF, in itself -- "Français", "العربية", "English" -- which is
# the one thing every UI-language switcher on earth agrees on: naming a
# language is not something the current locale gets a vote on, so this is
# not run through `translate` at all.
DISPLAY_NAMES: Mapping[str, str] = {
    "fr": "Français",
    "ar": "العربية",
    "en": "English",
}

# What the compact header switcher shows; the full name above stays the
# accessible name. Arabic shows its own first letter, not a Latin code.
SHORT_NAMES: Mapping[str, str] = {"fr": "FR", "ar": "ع", "en": "EN"}

_CATALOGS: Mapping[str, Mapping[str, str]] = {
    "fr": fr.MESSAGES,
    "ar": ar.MESSAGES,
    "en": en.MESSAGES,
}

# A key ending in this suffix is allowed to be marked `| safe` in a
# template -- see the module docstring's rule. Nothing in this project
# uses it yet (grep the catalogs: no key ends in `_html`); it is declared
# here, not enforced by code, because the enforcement that matters is the
# human rule at the call site ("never mark it safe unless..."), and a
# runtime check here could not tell a safe literal from an unsafe one.
_HTML_SAFE_SUFFIX = "_html"


def _fallback_chain(lang: str) -> list[str]:
    """Requested language, then fr, then en -- each listed once even if
    the caller asked for fr or en directly."""
    chain = [lang, "fr", "en"]
    seen: list[str] = []
    for candidate in chain:
        if candidate in _CATALOGS and candidate not in seen:
            seen.append(candidate)
    return seen


def plural_category(lang: str, count: int) -> str:
    """Which CLDR plural bucket `count` falls into, for `lang`.

    fr/en: the simple two-way rule the task brief asks for (see module
    docstring for why this is a deliberate simplification for fr).
    ar: CLDR's own six-category Arabic rule, needed because Arabic really
    does inflect differently for 0, 1, 2, 3-10, 11-99, and 100+/other."""
    n = abs(int(count))
    if lang == "ar":
        if n == 0:
            return "zero"
        if n == 1:
            return "one"
        if n == 2:
            return "two"
        rem100 = n % 100
        if 3 <= rem100 <= 10:
            return "few"
        if 11 <= rem100 <= 99:
            return "many"
        return "other"
    # fr, en, and anything else this project ever adds without its own
    # plural rule yet: one for exactly 1, other otherwise.
    return "one" if n == 1 else "other"


def translate(lang: str, key: str, **params: object) -> str:
    """One catalog entry, resolved and formatted.

    Never raises. `count` in `params`, if present, selects a plural
    category PER LANGUAGE IN THE FALLBACK CHAIN -- not fixed once from
    the requested language -- so a key missing only its Arabic `.few`
    form still degrades to French's plural rule for that same count
    rather than showing the wrong Arabic form."""
    count = params.get("count")
    for candidate_lang in _fallback_chain(lang):
        catalog = _CATALOGS[candidate_lang]
        lookup_key = key
        if count is not None:
            category = plural_category(candidate_lang, count)  # type: ignore[arg-type]
            categorized = f"{key}.{category}"
            if categorized in catalog:
                lookup_key = categorized
            elif f"{key}.other" in catalog:
                lookup_key = f"{key}.other"
            # Otherwise the key has no plural forms at all (e.g. "Sources
            # ({count})"): `count` is just a parameter, use the plain key.
        template = catalog.get(lookup_key)
        if template is None:
            continue
        try:
            return template.format(**params)
        except (KeyError, IndexError) as exc:
            logger.warning(
                "ui.i18n: catalog entry %r for lang=%r is missing a "
                "parameter the caller passed (%s); falling through",
                lookup_key,
                candidate_lang,
                exc,
            )
            continue
    logger.warning("ui.i18n: no catalog entry for key=%r (lang=%r)", key, lang)
    return f"⟦missing:{key}⟧"


def translate_markup(lang: str, key: str, **params: object) -> Markup:
    """A catalog entry whose TEXT is trusted markup (keys ending in `_html`).

    Every parameter is escaped before it is inserted (`Markup.format`
    escapes its arguments), so a workspace name or a question can never add
    a tag: only the fixed catalog wording can. Used for sentences that wrap
    a name in `<bdi>` or stress a word with `<strong>`."""
    if not key.endswith(_HTML_SAFE_SUFFIX):
        raise ValueError(f"translate_markup only reads *_html keys, got {key!r}")
    for candidate_lang in _fallback_chain(lang):
        template = _CATALOGS[candidate_lang].get(key)
        if template is not None:
            return Markup(template).format(**params)
    logger.warning("ui.i18n: no catalog entry for key=%r (lang=%r)", key, lang)
    return Markup(escape(f"\u27e6missing:{key}\u27e7"))


@lru_cache(maxsize=1)
def _phrase_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Every English sentence Python code builds (`phr.*` keys in en.py), as
    a matcher. Literal sentences are tried before ones with `{params}`, and
    longer templates before shorter, so the most specific wording wins."""
    compiled = []
    for key, template in en.MESSAGES.items():
        if not key.startswith("phr."):
            continue
        parts = re.split(r"\{(\w+)\}", template)
        pattern = "".join(
            re.escape(part) if index % 2 == 0 else f"(?P<{part}>.+?)"
            for index, part in enumerate(parts)
        )
        compiled.append((len(parts) > 1, -len(template), key, re.compile(f"^{pattern}$", re.S)))
    compiled.sort(key=lambda item: (item[0], item[1]))
    return tuple((key, rx) for _params, _length, key, rx in compiled)


def translate_text(lang: str, text: object) -> object:
    """Translate a sentence that Python code produced in English.

    Status labels, stage names, error sentences and file reasons are built
    in English by modules the tests pin (ui/*.py, sync.py, conversion.py).
    Rather than thread a language through all of them, a template passes
    the finished English text here: it is matched against the `phr.*`
    entries and re-rendered in `lang` with the same parameters. Text that
    matches nothing (a model's exception message, a document's words) comes
    back unchanged, so this can never hide information. English is returned
    as is."""
    if lang == "en" or not isinstance(text, str) or not text:
        return text
    for key, pattern in _phrase_patterns():
        match = pattern.match(text)
        if match:
            return translate(lang, key, **match.groupdict())
    return text


def js_strings(lang: str) -> dict[str, str]:
    """The small subset of catalog entries `sanad.js` reads at runtime.

    Rendered into `data-i18n` on `<body>` (`tojson`-escaped) rather than
    handing the script the whole catalog: the script has exactly one
    visible string it cannot get from the DOM already (the S3 poll's
    "evaluation finished" fallback, `reports_screen.py`/`reports.html`
    build every OTHER label server-side and the script only ever copies
    text across, never invents it) -- see DECISIONS.md, 2026-09-13."""
    return {
        "reports.status.finished_sentence": translate(
            lang, "reports.status.finished_sentence"
        ),
    }


__all__ = [
    "DEFAULT",
    "DISPLAY_NAMES",
    "SHORT_NAMES",
    "SUPPORTED",
    "js_strings",
    "plural_category",
    "translate",
    "translate_markup",
    "translate_text",
]
