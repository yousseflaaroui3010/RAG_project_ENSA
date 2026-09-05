"""The groundedness/relevancy judge (G1), behind one seam (ST-32).

**CHANGE REQUEST, 2026-09-05 (docs/journal/DECISIONS.md):** architecture
line 379 names `ragas` for this metric. `ragas==0.4.3` -- the current
release, verified against PyPI, there is no newer one to wait for -- has a
top-level import in a core module (`ragas/llms/base.py:12`) for a
LangChain class that no longer exists at that path, so `import ragas`
fails outright, unconditionally, for every caller. Downgrading does not
fix it (0.3.9 and 0.4.0 fail identically, tested); the only version that
imports needs `langchain-community==0.2.19`, a two-major downgrade of a
package this project's running app depends on. That trade was rejected:
do not risk a working product to keep a metrics library. `docs/phase2/` is
signed and write-locked, so line 379 itself is not edited; this is the
change request against it, and the deviation is recorded, not hidden.

**WHAT REPLACES IT.** `LLMJudgeScorer` asks the SAME chat model that
answers questions (`agent.chat.build_chat_model`) to judge its own answer
against the passages it was given, through the `prompts/eval-judge`
registry entry -- never an inline string (docs/phase2/CLAUDE.md, ADR-13's
"no business logic inside a route body" cousin for prompts). `Scorer` and
`ScoreResult` keep the exact shape `evaluation/runner.py` already expects,
so nothing outside this module changes.

**WHAT IS LOST, said plainly rather than implied away.** RAGAS is a
published, citable, independently-authored method: a defense committee or
a paper reviewer can look up what "faithfulness" means without reading
this project's prompt. A judge built from the same model family that
wrote the answer is NOT that -- it is this project's own opinion of its
own output, run through one extra prompt. A model that hallucinates a
detail can, in principle, fail to notice the same invented detail when
asked to grade it; an independent metric does not share that blind spot.
This is not a lesser INSTRUMENT so much as a DIFFERENT KIND of instrument,
and the evaluation report must say so plainly (G1's number is "our model's
self-judged groundedness", not "RAGAS faithfulness") rather than let a
0.00-1.00 score imply the two are interchangeable. Whoever reads the
report at the defense should be told this in the same breath as the
number.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from agent.chat import ChatModel, build_chat_model
from agent.prompts import load_prompt

JUDGE_PROMPT_ID = "eval-judge"

# Generous about FORM, strict about MEANING -- the same rule
# `agent/grading.py::_verdict` uses and the same reason: a parse failure
# must never be silently read as a score, because a 0.00-1.00 number looks
# exactly as confident whether or not anything computed it. Each label is
# searched for independently rather than as one two-line pattern, so the
# model naming them in either order, or with a blank line between, still
# parses -- "relevance" and "relevancy" both read, matching how a model is
# actually likely to spell it.
_GROUNDEDNESS = re.compile(r"groundedness\s*[:\-]?\s*([01](?:\.\d+)?)", re.IGNORECASE)
_RELEVANCY = re.compile(r"relevanc(?:y|e)\s*[:\-]?\s*([01](?:\.\d+)?)", re.IGNORECASE)


class JudgeReplyError(Exception):
    """The judge model said something that is not two parseable scores.

    A distinct error rather than a default score, for the same reason
    `agent.grading.GraderReplyError` exists: a confused reply must stop
    the run loudly, not impersonate a real judgement (F-08's numbers are
    a claim about the product; a parse failure is a fact about the model)."""


@dataclass(frozen=True)
class ScoreResult:
    """Both 0.0-1.0 (architecture 7.1's `score` neutral type)."""

    groundedness: float
    relevancy: float


class Scorer(Protocol):
    """What the runner needs from a judge, and nothing else -- narrowed
    the same way `agent.chat.ChatModel` narrows the answering model seam,
    so a test double can satisfy it with no real model call anywhere in a
    test."""

    def score(
        self, *, question: str, answer_text: str, contexts: Sequence[str]
    ) -> ScoreResult:
        """`contexts` must be the section text the writer actually read
        (`evaluation.capture.Captured.contexts`), never the wider set
        retrieval found -- scoring the wider set would judge the answer
        against text the model never saw."""
        ...


def _passage_block(contexts: Sequence[str]) -> str:
    if not contexts:
        # A refusal or a clarification never reaches the writer, so this
        # case is unreachable from `evaluation.runner` today (it only
        # scores kind=ANSWER rows) -- kept honest rather than assumed,
        # the same way `agent.grading._passage_block` has no empty-input
        # caller either but does not silently mishandle one.
        return "(no passages -- the answer was written from none)"
    return "\n\n".join(f"[{number}]\n{text}" for number, text in enumerate(contexts, start=1))


def _parse(reply: str) -> ScoreResult:
    grounded_match = _GROUNDEDNESS.search(reply or "")
    relevancy_match = _RELEVANCY.search(reply or "")
    missing = [
        label
        for label, match in (("GROUNDEDNESS", grounded_match), ("RELEVANCY", relevancy_match))
        if match is None
    ]
    if missing:
        raise JudgeReplyError(
            f"the eval judge replied {reply[:200]!r}, missing a parseable "
            f"{' and '.join(missing)} line. Check the model and the "
            f"{JUDGE_PROMPT_ID!r} prompt."
        )
    groundedness = float(grounded_match.group(1))
    relevancy = float(relevancy_match.group(1))
    for name, value in (("groundedness", groundedness), ("relevancy", relevancy)):
        if not 0.0 <= value <= 1.0:
            raise JudgeReplyError(
                f"the eval judge's {name} score is {value}, outside the "
                f"0.00-1.00 range the prompt asked for: {reply[:200]!r}"
            )
    return ScoreResult(groundedness=groundedness, relevancy=relevancy)


class LLMJudgeScorer:
    """Scores one question with a chat model, through the `eval-judge`
    registry prompt. See the module docstring for what this can and
    cannot stand in for."""

    def __init__(self, model: ChatModel):
        self._model = model
        self._prompt = load_prompt(JUDGE_PROMPT_ID)

    def score(
        self, *, question: str, answer_text: str, contexts: Sequence[str]
    ) -> ScoreResult:
        user = self._prompt.render(
            question=question,
            answer=answer_text,
            contexts=_passage_block(contexts),
        )
        reply = self._model.complete(self._prompt.system, user)
        return _parse(reply)


def build_llm_judge_scorer(model: ChatModel | None = None) -> Scorer:
    """The real scorer. `model` lets a caller share ONE `ChatModel`
    instance between answering and judging (`scripts/run_evaluation.py`
    does exactly that, via `ui.ports.build_ports`'s `model` parameter);
    omit it to build a fresh one from config, same as `agent.chat.
    build_chat_model`'s other callers do.

    Can raise `agent.chat.ChatUnavailableError` if the configured mode has
    no usable model (ADR-06) -- allowed out unchanged, the same way
    `ui.ports.build_default_ports` lets it out, rather than being wrapped
    into a second exception type for the same fact."""
    return LLMJudgeScorer(model if model is not None else build_chat_model())
