"""The `grade` and `reword` ports (ST-23): the F-04 retry loop's judgement.

Architecture 5.2 boxes G and RW. Both ask the model something and read the
answer back, and both live here because they share the one hard problem in
this file: **a reply that is not what we asked for.**

THE RULE THAT DECIDES EVERYTHING ELSE HERE: an unparseable grader reply
RAISES. It does not count as "off topic".

That looks like a harsh choice until you write out what the alternative
does. Treating a confused reply as off-topic means a broken or
misconfigured model silently produces the honest-refusal path -- the user
is told "your documents do not cover this", stated with the product's full
confidence, when what actually happened is that nobody could read the
model's answer. F-05's refusal is a CLAIM ABOUT THE CORPUS. Letting a
parse failure impersonate it is the most damaging thing in this module,
because it looks exactly like the product working correctly. The retry
ceiling makes it worse: three unparseable replies produce a refusal that
lists three searches, as if the corpus had been examined three times.

So the parse is generous about FORM and strict about MEANING. "relevant",
" RELEVANT.", "Verdict: OFF_TOPIC", "OFF-TOPIC", quoted and asterisked
forms are all read; anything that is not one of the two verdicts stops the
answer with a named error.

NO LONGER UNVERIFIED, as of 2026-08-27. This docstring used to say a real
model's chattiness could not be measured here, because there was no cloud
key and no Ollama. A key arrived, and the question was settled by running
it rather than by reasoning about it.

MEASURED: four live calls against Google AI Studio, two models
(gemini-2.5-flash and gemini-3.5-flash), each graded one on-topic and one
off-topic case. All four replies were EXACTLY the one word asked for --
"RELEVANT" and "OFF_TOPIC", no prose, no punctuation, no preamble -- and
all four verdicts were correct, including correctly rejecting a pump
maintenance manual as off-topic for a labour-law question. Zero parse
failures.

So the strict parser costs nothing against a real model with this prompt,
and the lenient alternative -- accepting a leading verdict followed by
prose -- would have bought tolerance nobody needs while making a confused
reply harder to notice. The decision stands, now on evidence.

WHAT IS STILL UNVERIFIED, narrowed rather than closed: this was four
calls on two models with one prompt and short passages. It says nothing
about behaviour on a 4,000-character parent section, under load, or on
the local Ollama path, which is still unreachable on this machine. If a
real corpus run starts throwing GraderReplyError, the fix is a measured
one -- read the raw replies first, then decide -- not a guess at the
regex.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence

from agent.chat import ChatModel
from agent.prompts import load_prompt
from vector_store import SearchHit

GRADER_PROMPT_ID = "relevance-grader"
REWORD_PROMPT_ID = "query-reword"

# The two verdicts, as the prompt states them.
_RELEVANT = "relevant"
_OFF_TOPIC = "off_topic"

# Strip anything that is decoration rather than the verdict: surrounding
# whitespace, a trailing full stop, quotes, markdown emphasis, and a
# leading "verdict:" label. Spaces, hyphens and underscores all fold to
# one separator, so "OFF_TOPIC", "off topic" and "OFF-TOPIC" read as the
# single word the prompt asked for.
#
# The hyphen is in that list because RUNNING IT put it there. The comment
# claimed hyphens folded while the pattern did not include one, so
# "OFF-TOPIC" -- which is how an English-writing model most naturally
# spells it -- raised instead of grading. A docstring describing
# behaviour the code does not have is worse than no docstring: it is the
# reason nobody re-reads the line.
_LABEL = re.compile(r"^\s*(verdict|answer|response)\s*[:\-]\s*", re.IGNORECASE)
_DECORATION = re.compile(r"[\s`*\"'.!]+")
_SEPARATOR = re.compile(r"[-_\s]+")


class GraderReplyError(Exception):
    """The model said something that is not a verdict.

    A distinct error rather than a False, because False is a claim about
    the user's documents and this is a fact about the model."""


def _verdict(reply: str) -> bool:
    """RELEVANT -> True, OFF_TOPIC -> False, anything else -> raise."""
    cleaned = _LABEL.sub("", reply or "")
    cleaned = _DECORATION.sub(" ", cleaned).strip().lower()
    cleaned = _SEPARATOR.sub("_", cleaned)
    if cleaned == _RELEVANT:
        return True
    if cleaned == _OFF_TOPIC:
        return False
    raise GraderReplyError(
        f"the relevance grader replied {reply[:120]!r}, which is neither "
        f"RELEVANT nor OFF_TOPIC. This is NOT being treated as off-topic: "
        f"an off-topic verdict tells the user their documents do not cover "
        f"the question (F-05), and nothing here knows that. Check the model "
        f"and the {GRADER_PROMPT_ID!r} prompt."
    )


def _passage_block(passages: Sequence[SearchHit]) -> str:
    """The passages as the grader sees them.

    Each one is labelled with the file and section it came from, because
    a passage with no provenance is a passage the model can confuse with
    another, and because the same labelling is what F-03 will cite."""
    lines = []
    for number, hit in enumerate(passages, start=1):
        where = hit.source_file
        if hit.section_label:
            where = f"{where} -- {hit.section_label}"
        lines.append(f"[{number}] ({where})\n{hit.chunk_text}")
    return "\n\n".join(lines)


def build_grade(model: ChatModel) -> Callable[[str, tuple[SearchHit, ...]], bool]:
    """The `grade` port, bound to one chat model (F-04).

    The graph never calls this with an empty passage list -- `make_grade`
    in agent/nodes.py short-circuits that case precisely so no model call
    is spent asking whether nothing is relevant."""
    prompt = load_prompt(GRADER_PROMPT_ID)

    def grade(question: str, passages: tuple[SearchHit, ...]) -> bool:
        user = prompt.render(question=question, passages=_passage_block(passages))
        return _verdict(model.complete(prompt.system, user))

    return grade


def build_reword(model: ChatModel) -> Callable[[str, tuple[str, ...], int], Sequence[str]]:
    """The `reword` port, bound to one chat model (F-04).

    Returns one query per non-empty line, capped by `config.max_sub_queries`
    upstream in `agent/nodes.py` -- so a model that ignores "between 1 and
    3" and writes twelve lines fails at the seam that already owns that
    rule, rather than having a second cap here that could disagree with it.

    A reply with no usable line also fails upstream, in `_queries`, with a
    message naming this port."""
    prompt = load_prompt(REWORD_PROMPT_ID)

    def reword(question: str, previous: tuple[str, ...], attempt: int) -> Sequence[str]:
        user = prompt.render(
            question=question,
            previous_queries="\n".join(previous),
            attempt=str(attempt),
        )
        reply = model.complete(prompt.system, user)
        return [line.strip() for line in reply.splitlines() if line.strip()]

    return reword
