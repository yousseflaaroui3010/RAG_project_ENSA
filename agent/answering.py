"""The `write_answer` port (ST-24): the answer, written from the sections.

Architecture 5.2 box A, PRD F-03 ("the answer is written only from
passages found in the active workspace") and F-05 ("it never fills a gap
with invented content"). This is the last seam on the critical path: with
it filled, a question goes in and a sourced answer comes out.

THE ONE RULE THAT SHAPES THIS FILE: **the model is never given the option
of writing an answer it cannot source.** It gets the sections, and it gets
one licensed way out -- the single word `NOT_COVERED`, which this module
turns into `AnswerNotCoveredError` and the graph turns into the honest
refusal.

That escape hatch is not politeness. A model told "answer only from these
sections", handed sections that do not answer the question, and given no
other move, will produce something: that is the whole mechanism behind an
invented answer. F-05 is the feature this product is built to demonstrate,
and it is gated at 20 out of 20 on the out-of-scope golden set (PRD F-08),
so one escape blocks a release. The grader (ST-23) is the first filter and
this is the second, and they filter different things: the grader judges
500-character CHILD chunks, the writer reads the full parent sections.

TWO THINGS THIS MODULE DELIBERATELY DOES NOT DO.

1. **It does not decide what is cited.** The source list is built by
   `agent/nodes.py` from the very tuple of passages handed in here, so a
   model that named a file could not add it to the citations and a model
   that ignored a section could not remove it. F-03 calls the source line
   the product's contract with the user; a contract the model can edit is
   not one.
2. **It does not ask the model for reference markers.** The prompt forbids
   `[1]`-style numbers on purpose. The UI renders source CARDS (UX spec
   6.2), not a numbered bibliography, so a bracketed number in the prose
   would point at nothing the reader can open -- and a model that
   miscounts them produces a citation to a source that does not exist.
   Naming the article in a sentence is what a human would do and is what
   the reader can check.

READING THE DECLINE, and this is the line most worth arguing about. The
grader can compare its whole reply to two known words; here the ordinary
reply is free prose, so "does the reply contain NOT_COVERED" would misread
an answer that merely quotes the token. The rule is therefore POSITIONAL:
the token must open the reply and be followed by end-of-line or a
separator. So

    "NOT_COVERED"              -> decline
    "**NOT_COVERED.**"         -> decline
    "NOT_COVERED - rien ici"   -> decline
    "Not covered by Article 13, but the trial period is three months"
                               -> an ANSWER, because "covered" is followed
                                  by a word rather than by a stop

The last row is the one the rule exists for, and it is deliberately
resolved towards ANSWER: `NOT_COVERED` is what the prompt asks for
literally, and ST-23 measured four out of four live Gemini replies obeying
an exactly-one-word instruction with no decoration at all, so a partial
match is far more likely to be prose than a decline.

UNVERIFIED, and it stays that way until a real corpus run: whether a real
model declines when it should. Every test here scripts the reply, which
proves this module reads a decline correctly and proves nothing about a
model producing one. ST-32's golden-set evaluation is what settles it, and
F-08's out-of-scope half is exactly that measurement.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping

from agent.chat import ChatModel
from agent.ports import AnswerNotCoveredError
from agent.prompts import load_prompt
from vector_store import SearchHit

ANSWER_PROMPT_ID = "answer-writer"

# The word the prompt asks for when the sections do not answer the
# question. Written here once and rendered into no string: the prompt file
# carries its own copy for the model, and a test asserts the two agree, so
# renaming it in one place turns the suite red instead of silently
# disabling the decline.
NOT_COVERED = "NOT_COVERED"

# Decoration a model may wrap a one-word reply in. Stripped from the
# candidate line before matching, never from the answer itself -- an
# answer's asterisks are the model's formatting and belong to the reader.
_DECORATION = re.compile(r"[`*\"']+")
# Markup a model may put in FRONT of a one-word reply: a bullet, a list
# dash, a heading marker, a blockquote, a byte-order mark. Stripped only
# from the START of the line and never from the middle, because a `-`
# removed anywhere would turn "NOT-COVERED" into "NOTCOVERED" and break
# the very spelling the fold below exists to accept.
_LEADING_MARKUP = re.compile("^[\\s﻿>#+*\\-]+")
# A leading "Verdict:" / "Answer -" style label, same shape as the one
# `agent/grading.py` tolerates on a verdict.
_LABEL = re.compile(r"^\s*(verdict|answer|response)\s*[:\-]\s*", re.IGNORECASE)
# The decline itself: at the START of the line, and followed by a stop
# rather than by more words. See the module docstring for why the position
# matters and which way the ambiguous case is resolved.
#
# BOTH DASHES ARE IN THE STOP LIST, and the em dash is there because
# RUNNING the parser put it there rather than because it was reasoned
# about: `NOT_COVERED - rien` was read as a decline and
# `NOT_COVERED — rien` was not, and an em dash is what a model writing
# fluent prose actually reaches for. Every gap in this class fails in the
# SAME dangerous direction -- a decline read as an answer, shipped to the
# reader as a bubble saying "NOT_COVERED" with source cards under it, and
# scored as a non-refusal by F-08's out-of-scope half.
_DECLINE = re.compile(
    "^not[-_ ]?covered\\s*(?:[.!?,:;–—-]|$)", re.IGNORECASE
)


def _is_decline(reply: str) -> bool:
    """Did the model decline to answer from these sections?

    Only the FIRST line with anything in it is considered. A decline is a
    whole reply, so a token buried on line four is a quotation, not a
    verdict -- and a line that is only decoration ("***", "---") has
    nothing left in it, so it is skipped rather than answered."""
    for line in (reply or "").splitlines():
        candidate = _LEADING_MARKUP.sub("", _DECORATION.sub("", line)).strip()
        if not candidate:
            continue
        return bool(_DECLINE.match(_LABEL.sub("", candidate)))
    return False


def _section_block(
    passages: tuple[SearchHit, ...], parent_texts: Mapping[str, str]
) -> str:
    """The sections as the model sees them, one block per section.

    ONE BLOCK PER PARENT, not per hit: four child chunks of Article 13 are
    one article, and pasting it four times would spend the context window
    on repetition and invite the model to treat a repeated claim as a
    better-supported one.

    Each block is headed with the file and section label the answer will be
    CITED by, so what the model reads and what the reader is told are the
    same provenance. `agent/grading.py` labels its passages the same way
    and the two are deliberately not shared -- see the DECISIONS row: the
    registry versions each prompt separately, and a shared formatter would
    mean tuning one prompt's layout silently changes the other's input."""
    blocks: list[str] = []
    seen: set[str] = set()
    for hit in passages:
        if hit.parent_id in seen:
            continue
        if hit.parent_id not in parent_texts:
            raise ValueError(
                f"the write_answer port was handed passage {hit.parent_id!r} "
                f"from {hit.source_file!r} with no section text for it. The "
                f"graph passes only the hits whose section it loaded, because "
                f"the source list is built from this same tuple -- a passage "
                f"here with no text would be cited without ever being read "
                f"(PRD F-03)."
            )
        seen.add(hit.parent_id)
        where = hit.source_file
        if hit.section_label:
            where = f"{where} -- {hit.section_label}"
        blocks.append(f"[{where}]\n{parent_texts[hit.parent_id]}")
    if not blocks:
        raise ValueError(
            "the write_answer port was given no passages. An answer with "
            "nothing behind it cannot be sourced, and the graph refuses "
            "before reaching here when no section could be read "
            "(agent/nodes.py::route_after_parents); arriving with an empty "
            "tuple is a wiring fault, not a question the model can take."
        )
    return "\n\n".join(blocks)


def build_write_answer(
    model: ChatModel,
) -> Callable[[str, tuple[SearchHit, ...], Mapping[str, str]], str]:
    """The `write_answer` port, bound to one chat model (F-03).

    Bound at build time like the grader and the reword, so the model's
    lifetime belongs to whoever composes the application and no module
    here holds a singleton (see `agent/chat.py::build_chat_model`).

    Raises `AnswerNotCoveredError` when the model declines. That is not an
    error condition in the ordinary sense -- it is the honest refusal
    arriving through the only channel a `-> str` seam has."""
    prompt = load_prompt(ANSWER_PROMPT_ID)

    def write_answer(
        question: str,
        passages: tuple[SearchHit, ...],
        parent_texts: Mapping[str, str],
    ) -> str:
        user = prompt.render(
            question=question, sections=_section_block(passages, parent_texts)
        )
        reply = model.complete(prompt.system, user)
        if _is_decline(reply):
            raise AnswerNotCoveredError(
                f"the answer writer read {len(parent_texts)} section(s) and "
                f"replied {NOT_COVERED}: they do not answer the question. "
                f"This is the F-05 path working, not a fault -- the graph "
                f"turns it into an honest refusal that discloses what was "
                f"searched."
            )
        return reply.strip()

    return write_answer
