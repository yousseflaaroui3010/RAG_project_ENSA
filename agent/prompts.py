"""Loads product prompts from the registry (ST-23).

Architecture section 11 names this file `agent/prompts.py` and calls it
"all system prompts, versioned in git". `prompts/README.md` says something
slightly different -- "one folder per prompt id, one PROMPT.md per folder"
-- and the two are not in conflict once you notice they describe different
halves: the TEXT lives in the registry, where it is reviewed and versioned
like a product artifact, and this file is the LOADER architecture 11 names.
Nothing here contains a prompt.

That split is what makes the registry's rule enforceable:
docs/phase2/CLAUDE.md and `prompts/README.md` both say inline prompt
strings in app code fail review. A prompt cannot be inlined by accident if
the only way to get one is to ask for it by id.

TWO GUARDS, and both exist because the failure they catch is silent:

1. **An unfilled variable is an error, not a hole.** Miss one and the
   model receives the literal text `{{QUESTION}}` and answers something
   plausible about nothing. Nothing raises, nothing logs, and the answer
   looks like every other answer.
2. **An unknown variable is an error too.** Rename `{{PASSAGES}}` in the
   PROMPT.md and every call site still passes `passages=` -- the value is
   dropped, the placeholder stays, and the grader judges a question with
   no passages under it. Checking only one direction catches only one of
   those two.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

# The registry lives beside the code, not under a configured path: it is
# repository layout (architecture section 11), not an operator tunable.
_REGISTRY = Path(__file__).resolve().parent.parent / "prompts"

_FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
_SECTION = re.compile(r"<(system|user)>\r?\n(.*?)\r?\n</\1>", re.DOTALL)
_VARIABLE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


class PromptError(Exception):
    """Base for every way a prompt can fail to load or render."""


class PromptNotFoundError(PromptError):
    """No PROMPT.md for that id."""


class MalformedPromptError(PromptError):
    """A PROMPT.md missing the frontmatter or one of the two sections."""


class PromptVariableError(PromptError):
    """The variables offered and the variables the template wants differ."""


@dataclass(frozen=True)
class Prompt:
    """One registry entry, parsed.

    `version` is carried rather than ignored because the registry rule is
    that a released version is never edited in place -- so the version is
    what a trace or an evaluation report has to name to be reproducible."""

    id: str
    version: str
    system: str
    user_template: str

    def render(self, **values: str) -> str:
        """The user message, with every variable filled and none left.

        Keyword arguments are lower-case versions of the template's
        `{{UPPER_CASE}}` names, so a call site reads like Python rather
        than like a template."""
        wanted = set(_VARIABLE.findall(self.user_template))
        given = {name.upper() for name in values}
        if missing := sorted(wanted - given):
            raise PromptVariableError(
                f"prompt {self.id!r} needs {missing} and they were not "
                f"given. An unfilled variable is not a blank: the model "
                f"would receive the literal text '{{{{{missing[0]}}}}}' "
                f"and answer around it."
            )
        if extra := sorted(given - wanted):
            raise PromptVariableError(
                f"prompt {self.id!r} was given {extra}, which it does not "
                f"use. Either the template was renamed and this call site "
                f"was not, or the value belongs to a different prompt -- "
                f"both end with the value silently dropped."
            )
        rendered = self.user_template
        for name, value in values.items():
            rendered = rendered.replace("{{" + name.upper() + "}}", value)
        return rendered


def _parse_frontmatter(raw: str, prompt_id: str) -> dict[str, str]:
    """The `key: value` header, read without a YAML parser.

    Deliberately not `pyyaml`, even though it is already a dependency: the
    frontmatter is four flat string fields, and the moment a real parser
    is used somebody will put a nested structure in one, which the
    registry's own format does not have."""
    match = _FRONTMATTER.match(raw)
    if match is None:
        raise MalformedPromptError(
            f"prompt {prompt_id!r} has no --- frontmatter block. Every "
            f"registry entry carries id, version, owner, model and "
            f"changelog (prompts/README.md)."
        )
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip('"')
    return fields


@cache
def load_prompt(prompt_id: str, base_path: str | Path | None = None) -> Prompt:
    """Read one registry entry by id.

    Cached: a prompt is a file that does not change while the process
    runs, and the grader loads one per retry. `base_path` exists for
    tests, mirroring `parent_store`'s parameter of the same name."""
    registry = Path(base_path) if base_path is not None else _REGISTRY
    path = registry / prompt_id / "PROMPT.md"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PromptNotFoundError(
            f"no prompt {prompt_id!r} in the registry at {registry}. One "
            f"folder per id, one PROMPT.md per folder."
        ) from exc

    fields = _parse_frontmatter(raw, prompt_id)
    sections = {name: body for name, body in _SECTION.findall(raw)}
    if missing := sorted({"system", "user"} - set(sections)):
        raise MalformedPromptError(
            f"prompt {prompt_id!r} is missing its <{missing[0]}> section. "
            f"A prompt here is a system message and a user template, "
            f"because that is the shape `agent.chat` sends."
        )
    declared = fields.get("id")
    if declared != prompt_id:
        raise MalformedPromptError(
            f"prompt in folder {prompt_id!r} declares id {declared!r}. The "
            f"folder name is how it is asked for, so a mismatch means one "
            f"of the two is a copy of something else."
        )
    return Prompt(
        id=prompt_id,
        version=fields.get("version", ""),
        system=sections["system"].strip(),
        user_template=sections["user"].strip(),
    )
