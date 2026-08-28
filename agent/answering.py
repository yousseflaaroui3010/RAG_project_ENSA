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

READING THE DECLINE is the hard part of this file, and it took three
attempts. The grader can compare its whole reply to two known words; here
the ordinary reply is free prose, so both naive rules are wrong. "Does the
reply contain NOT_COVERED" misreads an answer that quotes the token.
"Does the reply start with the words not covered" throws away a correct
answer -- see `_DECLINE_TOKEN` and `_DECLINE_WORDS` below, which carry the
worked examples and the reason there are two of them.

The shape, in one line: the decline must be the FIRST line with anything
in it; a TOKEN spelling (`NOT_COVERED`, `NOT-COVERED`) may carry a
trailing note; the PROSE spelling ("not covered") must be the whole line.

WHAT IS NOW VERIFIED, and this paragraph used to say the opposite. It said
a real model's behaviour could not be measured here. It was measured, on
2026-08-28, by running it rather than by reasoning about it: five live
calls to `gemini-3.6-flash` through this module and `agent/grading.py` --
one French covered, one English covered, two not covered, one partly
covered. Both not-covered cases came back as a bare `NOT_COVERED`,
including a genuine near-miss where the sections mention the questioned
term inside an unrelated rule. The English question was answered in
English and the French ones in French. The partly-covered case answered
the covered half and named the uncovered half in prose WITHOUT tripping
the decline parser, which is the interaction no unit test reaches. No
bracketed reference numbers appeared in any reply.

WHAT IS STILL UNVERIFIED, narrowed rather than closed: that was FIVE calls
on one model with short sections and no retrieval underneath. It says
nothing about a 4,000-character parent section, about the local Ollama
path (still unreachable on this machine), or about how often a real corpus
produces the partial-answer shape. Every reply in the test suite is
scripted, so the suite proves this module READS a decline correctly and
proves nothing about one being produced. ST-32's golden-set evaluation is
what settles it, and F-08's out-of-scope half is exactly that measurement.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping

from agent.chat import ChatModel
from agent.ports import AnswerNotCoveredError
from agent.prompts import load_prompt
from vector_store import SearchHit

logger = logging.getLogger(__name__)

ANSWER_PROMPT_ID = "answer-writer"

# The word the prompt asks for when the sections do not answer the
# question. Written here once and rendered into no string: the prompt file
# carries its own copy for the model, and a test asserts the two agree, so
# renaming it in one place turns the suite red instead of silently
# disabling the decline.
NOT_COVERED = "NOT_COVERED"


class EmptyAnswerError(Exception):
    """The model returned nothing at all.

    A distinct type rather than a decline, for the reason
    `agent/grading.py` gives about an unparseable verdict: a refusal is a
    claim about the USER'S DOCUMENTS, and an empty completion is a fact
    about the MODEL. Letting one impersonate the other emits the most
    damaging thing this product can produce -- an honest-looking refusal,
    listing the searches it ran, when nothing actually judged anything.

    It lives here rather than in `agent/ports.py` because, unlike
    `AnswerNotCoveredError`, no node routes on it: the graph lets it
    through to the caller, which `test_a_port_that_raises_is_not_papered_
    over` already pins, and turning it into a clear error with a retry
    action for the reader is the API layer's job (PRD section 11)."""


# Decoration a model may wrap a one-word reply in. Stripped from the
# candidate line before matching, never from the answer itself -- an
# answer's asterisks are the model's formatting and belong to the reader.
_DECORATION = re.compile(r"[`*\"']+")
# Markup a model may put in FRONT of a one-word reply: a bullet, a list
# dash, a heading marker, a blockquote, a byte-order mark. Stripped only
# from the START of the line and never from the middle, because a `-`
# removed anywhere would turn "NOT-COVERED" into "NOTCOVERED" and break
# the very spelling the fold below exists to accept.
#
# A LIST NUMBER counts as markup too ("1. NOT_COVERED"). The lookahead is
# what keeps it from eating a decimal: "1.5 hours" has no space after the
# stop, so nothing is stripped.
_LEADING_MARKUP = re.compile(r"^(?:[\s\ufeff>#+*\-]|\d+[.)](?=\s))+")
# A leading "Verdict:" / "Answer -" style label, same shape as the one
# `agent/grading.py` tolerates on a verdict.
#
# THE FRENCH WORDS ARE HERE BECAUSE THE PROMPT PUT THEM THERE. It tells
# the model to reply in the language the question was asked in, and this
# product's questions are mostly French -- so "R\u00e9ponse : NOT_COVERED" is a
# shape the prompt itself invites, and an English-only label list would
# have read it as prose. Accented and unaccented spellings both, because
# a model is as likely to write one as the other.
_LABEL = re.compile(
    r"^\s*(verdict|answer|response|r[\u00e9e]ponse|r[\u00e9e]sultat)\s*[:\-]\s*",
    re.IGNORECASE,
)

# TWO SPELLINGS, READ UNDER TWO DIFFERENT RULES, and the split is the most
# important thing in this file. It was NOT the first design; a cold review
# found the first one throwing away correct answers.
#
# `NOT_COVERED` and `NOT-COVERED` are TOKENS. The underscore and the
# hyphen are what make them tokens: no French or English sentence produces
# either by accident, so text after one is a model adding a note to its
# verdict, and the verdict still stands.
#
# `not covered` with a SPACE is ordinary prose, and this branch's own
# prompt is what makes that dangerous. It instructs the model: "if they
# answer part of the question, answer that part and state plainly which
# part they do not cover." A model obeying that in English, naming the gap
# first, writes
#
#     Not covered: overtime rates. Article 13 sets the trial period at
#     three months.
#
# -- a CORRECT answer, from the user's own documents, which an earlier
# version of this parser read as a refusal and discarded. The user was
# then told their workspace does not cover something it does, and the
# answer the model wrote was kept nowhere.
#
# SO THE PROSE SPELLING MUST BE THE WHOLE REPLY. "The whole first LINE"
# was the version before this one and it was still wrong, caught by a
# second review: a model that writes
#
#     Not covered.
#     Article 13 sets the trial period at three months.
#
# passes a first-line test and loses its answer on line two. The prompt
# asks for "NOT_COVERED and nothing else", so nothing else is the rule.
#
# The TOKEN side needs no stop list at all any more, and dropping it
# closed three real misses in one go: `NOT_COVERED les sections ne
# parlent pas` and `**NOT_COVERED** rien` were both being shipped to the
# reader as answer text. Once the separator is an underscore or a hyphen
# there is nothing to disambiguate -- the model is not writing a sentence
# -- so whatever follows is an annotation on a verdict that stands.
#
# WHAT IS DELIBERATELY LEFT OUT, recorded rather than silently accepted:
# `NOT COVERED - rien ici`, the SPACED spelling with a trailing note, is
# read as an answer. It cannot be told apart from `Not covered: overtime
# rates. Article 13 sets the trial period at three months.`, which is a
# correct answer on one line, and losing that is the worse error. Both
# directions are pinned by tests; see the DECISIONS row.
_DECLINE_TOKEN = re.compile(r"^not[-_]covered\b", re.IGNORECASE)
_DECLINE_PROSE = re.compile(r"^not\s+covered\s*[.!?]?$", re.IGNORECASE)


def _is_decline(reply: str) -> bool:
    """Did the model decline to answer from these sections?

    Only the FIRST line with anything in it is considered. A decline is a
    whole reply, so a token buried on line four is a quotation, not a
    verdict -- and a line that is only decoration ("***", "---") has
    nothing left in it, so it is skipped rather than answered."""
    lines = [
        _LEADING_MARKUP.sub("", _DECORATION.sub("", line)).strip()
        for line in (reply or "").splitlines()
    ]
    lines = [line for line in lines if line]
    if not lines:
        return False
    first = _LABEL.sub("", lines[0])
    if _DECLINE_TOKEN.match(first):
        return True
    # The prose spelling has to be the WHOLE reply, so a second line with
    # anything in it settles the question: this is an answer whose author
    # happened to open by naming what it could not cover.
    return len(lines) == 1 and bool(_DECLINE_PROSE.match(first))


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
        section = parent_texts.get(hit.parent_id) or ""
        if not section.strip():
            # ABSENT AND BLANK ARE ONE CASE HERE, deliberately. `agent/
            # stores.py` already omits a section that loads with no text,
            # so this is the backstop for a hand-wired port -- and it has
            # to catch both, because a blank section is exactly as unread
            # as a missing one while looking, to every count downstream,
            # like a section that loaded.
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
        blocks.append(f"[{where}]\n{section}")
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
        if not reply or not reply.strip():
            # AN EMPTY COMPLETION IS A FACT ABOUT THE MODEL, not a claim
            # about the user's documents, and the two must not share an
            # outcome -- the same rule `agent/grading.py` applies to an
            # unparseable verdict. A cloud model returns nothing when a
            # safety filter trips or a response is truncated, so this is
            # an ordinary Tuesday rather than a broken port.
            #
            # It is NOT turned into a decline. A refusal is the product
            # telling the user their workspace does not cover the
            # question, stated with full confidence, and nothing here
            # knows that. Left to `_spoken` in agent/nodes.py it would
            # have raised "the write_answer port returned a blank string"
            # -- sending whoever reads it to THIS module for a fault that
            # belongs to the model.
            raise EmptyAnswerError(
                f"the answer model returned an empty completion for a "
                f"question with {len(parent_texts)} section(s) of context. "
                f"This is not a refusal and is not being turned into one: "
                f"an honest refusal (F-05) is a claim about the user's "
                f"documents, and nothing here knows anything about them. A "
                f"cloud model returns nothing when a safety filter trips or "
                f"the response is cut short -- retry, or check the "
                f"{ANSWER_PROMPT_ID!r} prompt."
            )
        if _is_decline(reply):
            # LOG THE FIRST LINE BEFORE DISCARDING THE REPLY, because this
            # is the branch where a mistake is permanently invisible: if
            # the parser reads an ANSWER as a decline, the model's text is
            # thrown away, the user is told their documents do not cover
            # the question, and nothing anywhere records what was lost.
            # Two versions of this parser did exactly that, and both were
            # found by someone reading the code rather than by anything
            # the running product reported.
            #
            # The FIRST LINE only, never the body: docs/phase2/CLAUDE.md
            # forbids logging a full request body, and the first line is
            # what settles whether the classification was right.
            logger.info(
                "the answer writer declined; first line of the reply was %r",
                reply.strip().splitlines()[0][:200],
            )
            raise AnswerNotCoveredError(
                f"the answer writer read {len(parent_texts)} section(s) and "
                f"replied {NOT_COVERED}: they do not answer the question. "
                f"This is the F-05 path working, not a fault -- the graph "
                f"turns it into an honest refusal that discloses what was "
                f"searched."
            )
        return reply.strip()

    return write_answer
