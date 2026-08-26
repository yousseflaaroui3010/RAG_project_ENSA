"""ST-23: the relevance grader and the reword, on a scripted fake model.

Reference: PRD F-04 ("the system judges whether the passages it found
actually address the question ... off-topic results trigger a reworded
search"), architecture 5.2 boxes G and RW, and docs/phase2/CLAUDE.md's
hard rule: "Tests use the scripted fake chat model. No API keys in tests,
fixtures, or CI."

THE TEST THAT MATTERS MOST IN THIS FILE is the one asserting that an
unparseable reply RAISES rather than returning False. Those two outcomes
are one keystroke apart in the code and a world apart for the user: False
means "your documents do not cover this", said with the product's full
confidence, and a model that answered gibberish knows nothing of the kind.
If the unparseable case and the off-topic case were both asserted as
`is False`, the two would collapse and no test in this file could tell
them apart -- which is the "same error on both sides" shape from the
prove-it skill.
"""

from __future__ import annotations

import pytest

from agent.grading import (
    GRADER_PROMPT_ID,
    GraderReplyError,
    build_grade,
    build_reword,
)
from vector_store import SearchHit

QUESTION = "Quelle est la duree de la periode d'essai ?"

HIT = SearchHit(
    parent_id="p-1",
    source_file="code-du-travail.pdf",
    section_label="Article 13",
    chunk_text="La periode d'essai est de trois mois pour les cadres.",
    score=0.91,
)
OTHER_HIT = SearchHit(
    parent_id="p-2",
    source_file="guide-cnss.docx",
    section_label=None,
    chunk_text="Les cotisations sont versees trimestriellement.",
    score=0.55,
)


class _FakeChat:
    """The scripted fake chat model the hard rule requires.

    Answers from a script and records every call, so a test can assert
    both what the model was ASKED and how many times. The call count is
    what catches a retry hidden inside an adapter -- something the graph's
    own router tests structurally cannot see, because from the router's
    side one call and two calls look identical."""

    def __init__(self, *replies: str):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        index = min(len(self.calls) - 1, len(self.replies) - 1)
        return self.replies[index]


# --- the verdict, in both directions ----------------------------------


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        ("RELEVANT", True),
        (" relevant.", True),
        ("Answer: RELEVANT", True),
        ('"relevant"', True),
        ("OFF_TOPIC", False),
        ("off topic", False),
        ("OFF-TOPIC", False),
        ("**OFF_TOPIC**", False),
        ("Verdict: OFF_TOPIC", False),
    ],
    ids=[
        "plain-relevant", "lowercase-dotted", "labelled", "quoted",
        "plain-off-topic", "spaced", "hyphenated", "emphasised", "labelled-off",
    ],
)
def test_the_grader_reads_the_forms_a_real_model_actually_writes(reply, expected):
    """Generous about form, strict about meaning.

    The hyphenated row is here because it was FOUND BY RUNNING IT: the
    comment claimed hyphens folded, the pattern did not include one, and
    "OFF-TOPIC" -- the way an English-writing model most naturally spells
    it -- raised instead of grading."""
    grade = build_grade(_FakeChat(reply))

    assert grade(QUESTION, (HIT,)) is expected


def test_a_reply_that_is_not_a_verdict_raises_and_is_not_read_as_off_topic():
    """The most important line in this module, asserted as a DIFFERENT
    outcome from off-topic rather than as another `is False`.

    An off-topic verdict is a claim about the user's documents. A model
    that replied with prose has made no such claim, and letting the parse
    failure impersonate one produces an honest-looking refusal that lists
    the searches it ran -- indistinguishable, to the reader, from the
    product working."""
    grade = build_grade(_FakeChat("I think passage [1] might be useful here"))

    with pytest.raises(GraderReplyError, match="neither RELEVANT nor OFF_TOPIC"):
        grade(QUESTION, (HIT,))


def test_the_error_names_the_prompt_and_quotes_what_the_model_said():
    """Whoever reads this error is debugging a model or a prompt, so the
    message has to name both. A bare "parse error" sends them into the
    graph, which is the one place the fault cannot be."""
    grade = build_grade(_FakeChat("peut-etre"))

    with pytest.raises(GraderReplyError) as caught:
        grade(QUESTION, (HIT,))

    assert GRADER_PROMPT_ID in str(caught.value)
    assert "peut-etre" in str(caught.value)


# --- what the model is actually shown ---------------------------------


def test_every_passage_reaches_the_grader_with_its_file_and_section():
    """The grader judges passages it can tell apart. Provenance is not
    decoration here: it is the same file-and-section pair F-03 will cite,
    so a grader shown anonymous text is judging something the reader will
    never see."""
    model = _FakeChat("RELEVANT")
    grade = build_grade(model)

    grade(QUESTION, (HIT, OTHER_HIT))

    _system, user = model.calls[0]
    assert HIT.chunk_text in user
    assert OTHER_HIT.chunk_text in user
    assert "code-du-travail.pdf -- Article 13" in user
    assert "guide-cnss.docx" in user
    assert QUESTION in user


def test_the_grader_prompt_comes_from_the_registry_not_from_the_code():
    """`prompts/README.md`: "inline prompt strings in app code fail
    review". Asserted on content the registry file carries and the module
    does not, so moving the text into `grading.py` would turn this red."""
    model = _FakeChat("RELEVANT")

    build_grade(model)(QUESTION, (HIT,))

    system, _user = model.calls[0]
    assert "RELEVANT" in system and "OFF_TOPIC" in system
    assert "one word" in system.lower()


def test_the_grader_is_asked_exactly_once_per_call():
    """One judgement, one model call. A hidden retry inside the adapter
    would satisfy every behavioural assertion above and quietly double the
    cost and latency of every question."""
    model = _FakeChat("RELEVANT")

    build_grade(model)(QUESTION, (HIT,))

    assert len(model.calls) == 1


# --- the reword -------------------------------------------------------


def test_the_reword_returns_one_query_per_line():
    """Section 5.2's reword feeds the split-capable retrieve seam, so a
    model answering with two lines means two searches, not one string with
    a newline in it."""
    model = _FakeChat("duree essai cadres\nrenouvellement periode essai")
    reword = build_reword(model)

    assert list(reword(QUESTION, ("periode d'essai",), 1)) == [
        "duree essai cadres",
        "renouvellement periode essai",
    ]


def test_blank_lines_and_padding_in_the_reply_are_not_searches():
    """A model that separates its lines with blank ones would otherwise
    produce empty queries -- which the graph refuses at the seam, turning
    a cosmetic reply habit into a failed question."""
    model = _FakeChat("  duree essai  \n\n\n  essai cadres\n \n")
    reword = build_reword(model)

    assert list(reword(QUESTION, ("x",), 1)) == ["duree essai", "essai cadres"]


def test_the_reword_is_told_what_was_already_tried_and_which_attempt():
    """Both are in the prompt for a reason: without the tried list a model
    happily returns the query that just failed, and without the attempt
    number it cannot widen as the retries go on."""
    model = _FakeChat("nouvelle recherche")
    reword = build_reword(model)

    reword(QUESTION, ("essai", "periode essai"), 2)

    _system, user = model.calls[0]
    assert "essai" in user and "periode essai" in user
    assert "attempt 2" in user
    assert QUESTION in user
