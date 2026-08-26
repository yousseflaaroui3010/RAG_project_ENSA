"""ST-23: the prompt registry loader.

Reference: architecture section 11 (`agent/prompts.py`), `prompts/README.md`
("one folder per prompt id, one PROMPT.md per folder ... inline prompt
strings in app code fail review") and `.claude/rules/prompts-registry.md`.

Half the file tests the REAL registry entries rather than fixtures, on
purpose: a loader that parses hand-written test files perfectly and chokes
on the two prompts the product actually ships would pass a fixture-only
suite. The other half needs malformed files, which the registry rightly
does not contain, so those get a `tmp_path` registry.
"""

from __future__ import annotations

import pytest

from agent.prompts import (
    MalformedPromptError,
    PromptNotFoundError,
    PromptVariableError,
    load_prompt,
)

GOOD = """---
id: probe
version: 2.1.0
owner: YL
model: "{{CHAT_MODEL}}"
changelog: 2.1.0 a probe
---
<system>
You do one thing.
</system>
<user>
Question: {{QUESTION}}
Context: {{PASSAGES}}
</user>
"""


def _registry(tmp_path, prompt_id: str, text: str):
    folder = tmp_path / prompt_id
    folder.mkdir()
    (folder / "PROMPT.md").write_text(text, encoding="utf-8")
    return tmp_path


# --- the prompts the product actually ships ---------------------------


@pytest.mark.parametrize("prompt_id", ["relevance-grader", "query-reword"])
def test_every_shipped_prompt_loads_with_both_halves_and_a_version(prompt_id):
    """The registry entries themselves, not a fixture shaped like one."""
    prompt = load_prompt(prompt_id)

    assert prompt.id == prompt_id
    assert prompt.version, "a prompt with no version cannot be reproduced later"
    assert prompt.system.strip()
    assert prompt.user_template.strip()


def test_the_grader_prompt_asks_for_the_two_words_the_parser_reads():
    """Two files that must agree: the prompt tells the model to answer
    RELEVANT or OFF_TOPIC, and `agent/grading.py` parses exactly those.
    Change one without the other and every question fails at the parse.

    This is the cheap half of a drift check -- it cannot prove the model
    obeys, only that the two halves of OUR side still name the same
    words."""
    system = load_prompt("relevance-grader").system

    assert "RELEVANT" in system
    assert "OFF_TOPIC" in system


# --- rendering --------------------------------------------------------


def test_rendering_fills_every_variable(tmp_path):
    base = _registry(tmp_path, "probe", GOOD)

    rendered = load_prompt("probe", base).render(
        question="Combien de mois ?", passages="Article 13. Trois mois."
    )

    assert "Combien de mois ?" in rendered
    assert "Article 13. Trois mois." in rendered
    assert "{{" not in rendered


def test_a_variable_nobody_filled_is_an_error_not_a_hole(tmp_path):
    """The silent failure this guard exists for: miss one and the model
    receives the literal text `{{PASSAGES}}` and answers something
    plausible about nothing. No exception, no log, and an answer that
    looks like every other answer."""
    base = _registry(tmp_path, "probe", GOOD)

    with pytest.raises(PromptVariableError, match="PASSAGES"):
        load_prompt("probe", base).render(question="q")


def test_a_value_the_template_does_not_use_is_an_error_too(tmp_path):
    """The other direction, and it needs its own test because checking one
    way catches one bug. Rename `{{PASSAGES}}` in the file and every call
    site still passes `passages=`: the value is dropped, the placeholder
    stays, and the grader judges a question with nothing under it."""
    base = _registry(tmp_path, "probe", GOOD)

    with pytest.raises(PromptVariableError, match="PASSAGE_TEXT"):
        load_prompt("probe", base).render(
            question="q", passages="p", passage_text="stale name"
        )


# --- malformed entries ------------------------------------------------


def test_an_unknown_id_names_the_registry_it_looked_in(tmp_path):
    with pytest.raises(PromptNotFoundError) as caught:
        load_prompt("no-such-prompt", tmp_path)

    message = str(caught.value)
    assert "no-such-prompt" in message
    assert str(tmp_path) in message, "the error must name where it looked"


def test_a_file_without_frontmatter_is_refused(tmp_path):
    base = _registry(tmp_path, "bare", "<system>x</system>\n<user>y</user>\n")

    with pytest.raises(MalformedPromptError, match="frontmatter"):
        load_prompt("bare", base)


def test_a_file_missing_a_section_is_refused(tmp_path):
    text = GOOD.replace("<user>\nQuestion: {{QUESTION}}\nContext: {{PASSAGES}}\n</user>\n", "")
    base = _registry(tmp_path, "half", text)

    with pytest.raises(MalformedPromptError, match="<user> section"):
        load_prompt("half", base)


def test_a_folder_whose_file_declares_a_different_id_is_refused(tmp_path):
    """The folder name is how a prompt is asked for. A mismatch means one
    of the two is a copy of something else -- which is how a grader ends
    up being sent an answer-writing prompt with nobody noticing, because
    both load fine."""
    base = _registry(tmp_path, "grader-v2", GOOD.replace("id: probe", "id: probe-old"))

    with pytest.raises(MalformedPromptError, match="declares id"):
        load_prompt("grader-v2", base)
