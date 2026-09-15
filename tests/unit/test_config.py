"""Smoke test for config.py: the settings object loads with the documented
defaults and every knob referenced in the architecture is present.

ST-02 acceptance: uv sync green, every config var documented; this test is
the executable half of that check (defaults match section 7.5 / 8 / ADR-06).

The drift check at the bottom is new, and the reason it exists is worth
stating once. "Every config var documented in `.env.example`" is ST-02's
own exit criterion, and nothing ever enforced it: `.env.example` is a
plain text file that no code reads. It drifted, and the drift was recorded
as data-layer follow-up 8 in BUILD-STATE on 2026-08-09 and then sat there.

What made it urgent rather than tidy: on 2026-08-29 a `.env` on one
machine still named a Gemini model Google had RETIRED two days earlier,
while `config.py` and `.env.example` both named the current one. The fix
had landed in the tracked files and could not reach the machine. That cost
ST-18 its G4 measurement. This test cannot fix a `.env` -- nothing can,
`.env` is git-ignored and holds a secret -- but it holds the one end that
IS shared, so a setting added to `config.py` can never again be invisible
to the person copying the template.
"""

import re
from pathlib import Path

import pytest

from config import Settings, get_settings

_ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def test_defaults_match_architecture_pins():
    settings = Settings(_env_file=None)

    # F-04 retry ceiling default (architecture §5.2).
    assert settings.retry_ceiling == 2
    # Chunking knobs (architecture §7.5).
    assert settings.chunk_child_size_chars == 500
    assert settings.chunk_child_overlap_chars == 100
    assert settings.parent_merge_below_chars == 2000
    assert settings.parent_split_above_chars == 4000
    # Server binds localhost only (LD-07, ADR-13).
    assert settings.server_host == "127.0.0.1"
    assert settings.server_port == 8000
    # Embedding prefixes (ADR-05 binding rule).
    assert settings.embedding_passage_prefix == "passage: "
    assert settings.embedding_query_prefix == "query: "
    assert settings.embedding_model == "intfloat/multilingual-e5-base"
    # Rolling F-07 memory has a finite input and output envelope.
    assert settings.session_memory_input_max_chars == 16000
    assert settings.session_summary_max_chars == 2000


def test_get_settings_is_cached_singleton():
    assert get_settings() is get_settings()


def test_env_example_has_no_byte_order_mark():
    """The template must not carry a BOM, because it gets COPIED.

    Found by running this file's own drift check: `.env.example` began with
    EF BB BF on main, and had since before this branch. Harmless TODAY only
    by luck -- line 1 is a comment, so the three bytes are swallowed by a
    `#`. Move a real setting to the top, or add one above the header, and
    the first variable becomes `\\ufeffMODEL_MODE`, which pydantic-settings
    does not recognise and does not complain about. It would read as "the
    setting is being ignored for no reason".

    It matters more here than in an ordinary file because the instruction
    on line 1 is "copy to .env": the BOM rides along into the file that
    actually configures the product.

    CLAUDE.md's Windows write trap is exactly this, and it names
    `~/.claude/rules/git-discipline.md` as a file that already carries one.
    Now it is enforced somewhere rather than remembered.
    """
    raw = _ENV_EXAMPLE.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), (
        ".env.example starts with a UTF-8 byte-order mark (EF BB BF). It is "
        "a template meant to be copied to .env, so the mark travels with "
        "it. Write the file with the Write tool, [IO.File]::WriteAllText, "
        "or Set-Content -Encoding utf8NoBOM -- never `>` redirection and "
        "never -Encoding utf8 on PowerShell 5.1."
    )


def _documented_keys() -> set[str]:
    """The variable names `.env.example` actually defines.

    Commented-out lines do NOT count. A `# FOO=bar` line looks like
    documentation to a human skimming the file and gives the reader nothing
    to uncomment-and-fill in a template whose whole job is being copied, so
    treating it as documented would make the check agree with the file
    rather than with the reader.
    """
    keys = set()
    for line in _ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.match(r"^([A-Z][A-Z0-9_]*)=", stripped)
        if match:
            keys.add(match.group(1).lower())
    return keys


def test_ocr_off_by_default_no_validation_runs(tmp_path):
    """The documented contract: empty `ocr_tessdata_dir` is OCR off, and
    off must never fail loud over a directory or language file that was
    never going to be used."""
    settings = Settings(_env_file=None)
    assert settings.ocr_tessdata_dir == ""
    assert settings.ocr_languages == "fra+ara+eng"
    assert settings.ocr_dpi == 300
    assert settings.ocr_max_pages == 200


def test_ocr_tessdata_dir_missing_fails_loud_at_construction(tmp_path):
    """F-16: OCR on with a directory that does not exist is a config
    mistake, and the whole point of failing at startup rather than per
    file is that it never even gets there."""
    missing = tmp_path / "does-not-exist"

    with pytest.raises(ValueError, match="does not exist"):
        Settings(_env_file=None, ocr_tessdata_dir=str(missing))


def test_ocr_missing_language_file_fails_loud_and_names_it(tmp_path):
    """A REAL directory that is missing just one of the requested language
    files must still fail loud, and the message must name the missing
    file -- proven by asserting both what is missing (`ara`) and what is
    NOT (`fra` stays out of the message, so a two-language failure cannot
    be satisfied by naming the wrong one)."""
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "fra.traineddata").write_bytes(b"not a real model, just a marker")

    with pytest.raises(ValueError, match="ara.traineddata") as excinfo:
        Settings(_env_file=None, ocr_tessdata_dir=str(tessdata), ocr_languages="fra+ara")

    assert "fra.traineddata" not in str(excinfo.value)


def test_ocr_dpi_out_of_range_fails_loud_at_both_bounds():
    with pytest.raises(ValueError, match="ocr_dpi"):
        Settings(_env_file=None, ocr_dpi=10)
    with pytest.raises(ValueError, match="ocr_dpi"):
        Settings(_env_file=None, ocr_dpi=1000)


def test_ocr_max_pages_must_be_positive():
    with pytest.raises(ValueError, match="ocr_max_pages"):
        Settings(_env_file=None, ocr_max_pages=0)


def test_chat_history_retention_days_rejects_negative():
    with pytest.raises(ValueError, match="chat_history_retention_days"):
        Settings(_env_file=None, chat_history_retention_days=-1)


def test_chat_history_retention_days_zero_is_allowed():
    """0 is deliberately valid: it is config.py's documented 'keep
    nothing across a restart' switch, not an error."""
    assert Settings(_env_file=None, chat_history_retention_days=0).chat_history_retention_days == 0


def test_chat_history_retention_days_rejects_an_absurdly_large_value():
    """Found by a cold review: 1_000_000 underflows `datetime.min` inside
    the start-up sweep's cutoff arithmetic and raises `OverflowError`
    before the server can serve a single request. Must fail loud here,
    at construction, instead."""
    with pytest.raises(ValueError, match="chat_history_retention_days"):
        Settings(_env_file=None, chat_history_retention_days=1_000_000)


def test_chat_history_retention_days_upper_bound_is_inclusive():
    assert (
        Settings(_env_file=None, chat_history_retention_days=3650).chat_history_retention_days
        == 3650
    )


def test_every_setting_is_documented_in_env_example():
    """ST-02's exit criterion, finally executable.

    Fails LOUDLY with the missing names, because the whole point is that
    the person who adds a setting learns about the template in the same
    minute rather than six weeks later.
    """
    missing = sorted(set(Settings.model_fields) - _documented_keys())
    assert not missing, (
        f"{len(missing)} setting(s) exist in config.py and are NOT in "
        f".env.example: {', '.join(missing)}. Add each one with a comment "
        f"saying what it does, or the next person copying the template gets "
        f"a config they cannot see."
    )


def test_env_example_documents_nothing_that_does_not_exist():
    """The other direction, and it is the one that rots quietly.

    A stale key in the template is worse than a missing one: it is a
    setting someone can fill in, restart, and watch do nothing, with no
    error anywhere -- pydantic-settings ignores unknown environment
    variables. That is a silent failure, which this project has already
    paid for twice in one day.
    """
    unknown = sorted(_documented_keys() - set(Settings.model_fields))
    assert not unknown, (
        f".env.example documents {len(unknown)} variable(s) that config.py "
        f"does not define: {', '.join(unknown)}. Setting one of these does "
        f"NOTHING and reports no error. Remove them, or add the field."
    )
