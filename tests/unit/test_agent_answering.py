"""ST-24: the answer writer, on a scripted fake model.

Reference: PRD F-03 ("the answer is written only from passages found in
the active workspace"), F-05 ("it never fills a gap with invented
content"), architecture 5.2 box A and 7.5 (search the child, read the
parent), and docs/phase2/CLAUDE.md's hard rule: "Tests use the scripted
fake chat model. No API keys in tests, fixtures, or CI."

THE TWO TESTS THAT CARRY THIS FILE, and they are a pair on purpose:
`test_a_one_word_decline_is_not_an_answer` and
`test_an_answer_that_merely_mentions_the_token_is_still_an_answer`. They
push the decline parser in opposite directions. Asserting only the first
would pass for a parser that declines on ANY reply containing the word,
which would turn a legitimate answer quoting the token into a refusal;
asserting only the second would pass for a parser that never declines at
all, which is the F-05 hole this module exists to close. Neither test is
worth much without the other.

WHAT THIS FILE CANNOT PROVE, said plainly rather than left to be assumed:
that a real model declines when it should. Every reply here is scripted, so
these tests prove the module READS a decline correctly. Whether one is
produced is a question about a model and a prompt, and only the golden-set
evaluation (ST-32, PRD F-08's 20 out-of-scope questions) answers it.
"""

from __future__ import annotations

import pytest

from agent.answering import (
    ANSWER_PROMPT_ID,
    NOT_COVERED,
    build_write_answer,
)
from agent.ports import AnswerNotCoveredError
from agent.prompts import load_prompt
from tests.fake_chat import ScriptedChat
from vector_store import SearchHit

QUESTION = "Quelle est la duree de la periode d'essai ?"

# The chunk that matched and the section it came out of. The chunk text is
# deliberately NOT a substring of the section here, which it always is in
# production: that is what lets the tests below tell "the model read the
# section" apart from "the model read the chunk". With a realistic chunk
# the two assertions would both pass on either behaviour.
HIT = SearchHit(
    parent_id="p-1",
    source_file="code-du-travail.pdf",
    section_label="Article 13",
    chunk_text="TEXTE-DE-L-EXTRAIT-SEULEMENT",
    score=0.91,
)
SECTION = (
    "Article 13. La periode d'essai est de trois mois pour les cadres, "
    "renouvelable une seule fois. Elle est de un mois et demi pour les "
    "employes et de quinze jours pour les ouvriers."
)

OTHER_HIT = SearchHit(
    parent_id="p-2",
    source_file="guide-cnss.docx",
    section_label=None,
    chunk_text="AUTRE-EXTRAIT",
    score=0.55,
)
OTHER_SECTION = "Les cotisations sont versees trimestriellement."

ANSWER = "Trois mois pour les cadres, renouvelable une seule fois."


def _write(model, passages=(HIT,), parents=None):
    parents = {HIT.parent_id: SECTION} if parents is None else parents
    return build_write_answer(model)(QUESTION, passages, parents)


# --- F-03: what the model is actually shown ---------------------------


def test_the_model_reads_the_full_section_not_the_chunk_that_matched():
    """Architecture 7.5, at the seam that finally consumes it: the searched
    unit is a 500-character child and the READ unit is the section it came
    out of.

    Both directions are asserted, and the second is the one with teeth. A
    writer that pasted the chunk as well as the section would satisfy "the
    section reached the model" while doubling the context and letting the
    model answer from the smaller window."""
    model = ScriptedChat(ANSWER)

    _write(model)

    _system, user = model.calls[0]
    assert SECTION in user
    assert HIT.chunk_text not in user


def test_every_section_carries_the_file_and_label_it_will_be_cited_by():
    """The provenance the model reads is the provenance the reader is
    shown (F-03). A model handed anonymous text is reasoning about
    something the source cards will then name for it."""
    model = ScriptedChat(ANSWER)

    _write(
        model,
        passages=(HIT, OTHER_HIT),
        parents={HIT.parent_id: SECTION, OTHER_HIT.parent_id: OTHER_SECTION},
    )

    _system, user = model.calls[0]
    assert "code-du-travail.pdf -- Article 13" in user
    assert "guide-cnss.docx" in user
    assert OTHER_SECTION in user
    assert QUESTION in user


def test_a_section_without_a_label_is_named_by_its_file_alone():
    """`section_label` is optional in openapi's `Source` and absent for a
    document with no headings. It must not render as "None", which is what
    a plain f-string of the field would produce and what the model would
    then read as the section's name."""
    model = ScriptedChat(ANSWER)

    _write(model, passages=(OTHER_HIT,), parents={OTHER_HIT.parent_id: OTHER_SECTION})

    _system, user = model.calls[0]
    assert "guide-cnss.docx" in user
    assert "None" not in user


def test_one_section_appears_once_however_many_of_its_chunks_matched():
    """Four children of Article 13 are one article. Pasting it four times
    would spend the context window on repetition and invite the model to
    read a repeated claim as a better-supported one.

    Counted rather than asserted with `in`, because `in` is true of one
    copy and of four."""
    import dataclasses

    hits = tuple(
        dataclasses.replace(HIT, chunk_text=f"extrait {n}") for n in range(4)
    )
    model = ScriptedChat(ANSWER)

    _write(model, passages=hits)

    _system, user = model.calls[0]
    assert user.count(SECTION) == 1


def test_the_model_is_asked_exactly_once_per_answer():
    """One answer, one model call. A hidden retry inside the adapter would
    satisfy every assertion above and quietly double the cost and the
    latency of every question."""
    model = ScriptedChat(ANSWER)

    _write(model)

    assert len(model.calls) == 1


def test_the_answer_comes_back_as_the_model_wrote_it():
    """The writer is not an editor. Surrounding whitespace is trimmed
    because a leading blank line is a visibly broken message bubble, and
    nothing else is touched."""
    model = ScriptedChat(f"\n  {ANSWER}  \n")

    assert _write(model) == ANSWER


# --- F-05: the decline, in both directions ----------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "NOT_COVERED",
        "not_covered",
        "  NOT_COVERED  ",
        "NOT_COVERED.",
        "**NOT_COVERED**",
        '"NOT_COVERED"',
        "NOT COVERED",
        "NOT-COVERED",
        "Answer: NOT_COVERED",
        "NOT_COVERED\nLes sections ne parlent pas de ce sujet.",
        "NOT_COVERED - rien dans ces sections",
        "NOT_COVERED — rien dans ces sections",
        "NOT_COVERED (the sections do not mention it)",
        "not covered.",
        "NOT COVERED - rien dans ces sections",
        "NOT_COVERED les sections ne parlent pas de ce sujet.",
        "**NOT_COVERED** rien dans ces sections",
        "Reponse : NOT_COVERED",
        "Réponse : NOT_COVERED",
        "- NOT_COVERED",
        "1. NOT_COVERED",
        "# NOT_COVERED",
        "> NOT_COVERED",
        "﻿NOT_COVERED",
    ],
    ids=[
        "plain", "lowercase", "padded", "full-stop", "emphasised", "quoted",
        "spaced", "hyphenated", "labelled", "explained-on-a-second-line",
        "explained-after-a-hyphen", "explained-after-an-em-dash",
        "explained-in-brackets", "prose-spelling-alone-on-the-line",
        "shouted-then-explained",
        "explained-after-a-space", "emphasised-then-explained",
        "french-label", "french-label-accented",
        "bulleted", "numbered", "as-a-heading", "quoted-block",
        "byte-order-mark",
    ],
)
def test_a_one_word_decline_is_not_an_answer(reply):
    """Generous about form, strict about position.

    The forms are the ones a real model actually produces around a
    one-word instruction; ST-23 measured four out of four live Gemini
    replies obeying such an instruction exactly, so the decorated rows are
    tolerance rather than expectation."""
    with pytest.raises(AnswerNotCoveredError):
        _write(ScriptedChat(reply))


def test_an_answer_that_merely_mentions_the_token_is_still_an_answer():
    """The other half of the pair, and the reason the parser is positional
    rather than a substring search.

    A reply that quotes the word while answering the question is an
    ANSWER. Reading it as a decline would refuse a question the documents
    genuinely cover -- and the user would be told their workspace does not
    contain something it does."""
    reply = (
        "La periode d'essai est de trois mois. Le cas des stagiaires est "
        "NOT_COVERED par l'Article 13."
    )

    assert _write(ScriptedChat(reply)) == reply


def test_an_answer_beginning_with_those_two_words_in_a_sentence_still_answers():
    """The sharpest case, and the one that decides between "starts with the
    token" and "is the token".

    "Not covered by Article 13, but ..." opens with the same two words and
    is a real answer. The rule is that the token must be followed by a stop
    -- end of line, a full stop, a dash -- not by more of a sentence."""
    reply = "Not covered by Article 13, but Article 14 sets it at trois mois."

    assert _write(ScriptedChat(reply)) == reply


@pytest.mark.parametrize(
    "reply",
    [
        "Not covered: overtime rates. Article 13 sets the trial period at three months.",
        "Not covered, but Article 13 sets it at three months.",
        "Not covered - the sections list only the trial period, which is three months.",
        "**Not covered:** overtime. Article 13 says three months.",
    ],
    ids=["colon", "comma", "dash", "emphasised"],
)
def test_a_partial_answer_that_names_its_gap_first_is_not_thrown_away(reply):
    """FOUND BY A COLD REVIEW, and it was the worst defect in this story.

    This branch's own prompt tells the model: "if they answer part of the
    question, answer that part and state plainly which part they do not
    cover." A model obeying that in English, and naming the gap FIRST,
    opens with the words "Not covered". An early version of this parser
    read all four of these as declines and threw the answer away -- so the
    user's documents contained the answer, the model wrote it, and the
    product replied that nothing was found and suggested they add the
    missing document. The text was kept nowhere and nothing was logged.

    The fix is why there are two patterns rather than one: `NOT_COVERED`
    with an underscore or a hyphen is a TOKEN and may carry a trailing
    note; "not covered" with a space is ordinary prose and has to be the
    whole reply. Every row here is a real answer to a real question."""
    assert _write(ScriptedChat(reply)) == reply


@pytest.mark.parametrize(
    "reply",
    [
        "Not covered.\nArticle 13 sets the trial period at three months.",
        "# Not covered\nArticle 13 sets the trial period at three months.",
        "**Not covered**\nArticle 13 sets the trial period at three months.",
    ],
    ids=["plain", "as-a-heading", "emphasised"],
)
def test_a_gap_named_on_its_own_line_does_not_discard_the_answer_below_it(reply):
    """FOUND BY THE RULE-5 REVIEW, and it is the same defect as the test
    below surviving one round of fixing.

    The first fix said the prose spelling must be the whole first LINE.
    That is still too weak: a model that names the gap on line one and
    answers on line two passes a first-line test and loses its answer.
    The prompt asks for "NOT_COVERED and nothing else", so the rule is the
    whole REPLY -- a second line with anything in it settles it.

    Two rounds of review on one regex is worth recording. Each version
    looked obviously right until someone ran it on a reply nobody had
    thought of."""
    assert _write(ScriptedChat(reply)) == reply


def test_a_shouted_decline_with_a_note_is_still_a_decline():
    """CASE is the third discriminator, and this test exists because a
    review pointed out that the previous version of this file DENIED that.

    It asserted the opposite -- that "NOT COVERED - rien ici" had to be
    read as an answer, because it "cannot be told apart" from "Not
    covered: overtime rates. Article 13 sets the trial period at three
    months." That reason was simply false. They differ in case, and a
    model does not write an answer in capitals.

    Worth keeping as a lesson about decision records rather than about
    regexes: a wrong REASON is worse than a missing one, because the next
    reader inherits a constraint that was never real."""
    with pytest.raises(AnswerNotCoveredError):
        _write(ScriptedChat("NOT COVERED - rien dans ces sections"))


def test_a_shouted_gap_heading_above_a_real_answer_is_still_an_answer():
    """The guard on the rule above, and the reason the shouted form must
    still be a SINGLE-LINE reply.

    Letting capitals alone decide would re-open the defect two reviews
    have now closed: a model that heads its answer with the gap and then
    answers underneath would lose everything below the heading."""
    reply = (
        "NOT COVERED: overtime rates.\n"
        "Article 13 sets the trial period at three months."
    )

    assert _write(ScriptedChat(reply)) == reply


def test_stripping_a_bullet_does_not_invent_a_decline():
    """The guard on the leading-markup strip, and it is needed because
    that strip is what makes "- NOT_COVERED" a decline.

    A bulleted answer opening with the same two words must still be an
    answer. Without this, widening the tolerance for a decorated decline
    would quietly widen the tolerance for a false one, and false refusals
    are the direction that tells a user their documents lack something
    they have."""
    reply = "- Not covered by Article 13, but Article 14 sets it at trois mois."

    assert _write(ScriptedChat(reply)) == reply


def test_a_partial_answer_that_names_what_it_could_not_cover_is_still_an_answer():
    """Only the FIRST line decides, and this is the test that says so.

    The prompt asks a model with partial coverage to "answer that part and
    state plainly which part they do not cover", so a reply whose SECOND
    line opens with "Not covered:" is exactly what a well-behaved model
    produces. A parser that scanned every line would throw that whole
    answer away and tell the user their workspace covers nothing -- and
    every other test in this file passes with that bug in place."""
    reply = (
        "La periode d'essai est de trois mois pour les cadres.\n"
        "Not covered: le cas des contrats saisonniers."
    )

    assert _write(ScriptedChat(reply)) == reply


def test_a_discarded_reply_leaves_a_trace_in_the_log(caplog):
    """The branch where a mistake is otherwise PERMANENTLY invisible.

    If the parser reads an ANSWER as a decline, the model's text is thrown
    away, the user is told their documents do not cover the question, and
    nothing anywhere records what was lost. Two versions of this parser did
    exactly that, and both were found by a person reading the code -- never
    by anything the running product reported.

    The FIRST LINE only: docs/phase2/CLAUDE.md forbids logging a full
    request body, and the first line is what settles whether the
    classification was right."""
    import logging

    with caplog.at_level(logging.INFO, logger="agent.answering"):
        with pytest.raises(AnswerNotCoveredError):
            _write(ScriptedChat("NOT_COVERED les sections ne parlent pas."))

    assert "NOT_COVERED les sections ne parlent pas." in caplog.text


def test_the_decline_says_it_is_the_refusal_path_working_not_a_fault():
    """Whoever reads this error is looking at a log line, and the honest
    refusal is the product's headline feature rather than a breakage. An
    error that reads like a crash gets "fixed" by someone catching it."""
    with pytest.raises(AnswerNotCoveredError) as caught:
        _write(ScriptedChat(NOT_COVERED))

    assert "F-05" in str(caught.value)


def test_the_decline_word_in_the_code_is_the_word_the_prompt_asks_for():
    """A drift check, and it compares the two sides that can actually
    disagree: the constant this module matches on, and the registry file
    the model is told to obey.

    Rename the token in `PROMPT.md` alone and nothing breaks loudly -- the
    model starts declining in a word the parser does not know, every
    decline is read as prose, and the product answers "NOT_COVERED" to the
    user. Rename it here alone and no decline is ever produced."""
    assert NOT_COVERED in load_prompt(ANSWER_PROMPT_ID).system


def test_the_word_the_prompt_asks_for_is_the_word_the_parser_accepts():
    """The other half of that drift check, and it closes a gap a cold
    review found in the first one.

    The check above ties the CONSTANT to the prompt file. But the thing
    that actually decides a decline is the regex, which spells the token a
    third time -- so the constant and the prompt could agree perfectly
    while the regex accepted something else. This runs the real parser
    over the real word."""
    from agent.answering import _is_decline

    assert _is_decline(NOT_COVERED) is True


# --- the wiring faults ------------------------------------------------


def test_a_passage_with_no_section_text_is_refused_at_the_seam():
    """The graph hands over only the hits whose section it loaded, because
    the source list is built from that same tuple. A passage arriving here
    without text would be cited without ever having been read, which is the
    one thing F-03's source line promises cannot happen."""
    with pytest.raises(ValueError, match="no section text"):
        _write(
            ScriptedChat(ANSWER),
            passages=(HIT, OTHER_HIT),
            parents={HIT.parent_id: SECTION},
        )


@pytest.mark.parametrize("blank", ["", "   ", "\n\n"], ids=["empty", "spaces", "newlines"])
def test_a_section_that_loaded_as_nothing_is_refused_like_a_missing_one(blank):
    """A section that loads as nothing is not a section that loaded.

    `parent_store` only checks the `text` field is PRESENT, so a parent
    JSON whose text is blank arrives as a SUCCESSFUL read -- and every
    count downstream believes it. The trace says "loaded 1 of 1", the
    model gets a headed block with nothing under it, and the document is
    still printed as a source card: a citation to text nothing read.

    `agent/stores.py` omits these before the graph ever sees them; this is
    the backstop for a hand-wired port, and it has to treat blank and
    absent as one case because they are equally unread."""
    with pytest.raises(ValueError, match="no section text"):
        _write(ScriptedChat(ANSWER), parents={HIT.parent_id: blank})


def test_an_empty_reply_is_not_read_as_a_refusal():
    """The most dangerous confusion available in this module, asserted as
    a DIFFERENT outcome rather than as another decline.

    A cloud model returns an empty completion when a safety filter trips
    or a response is truncated. Turning that into `AnswerNotCoveredError`
    would tell the user, with the product's full confidence, that their
    documents do not cover the question -- when nothing judged anything.
    Same rule `agent/grading.py` applies to an unparseable verdict."""
    from agent.answering import EmptyAnswerError

    with pytest.raises(EmptyAnswerError) as caught:
        _write(ScriptedChat("   \n  "))

    assert not isinstance(caught.value, AnswerNotCoveredError)
    assert ANSWER_PROMPT_ID in str(caught.value)


def test_no_passages_at_all_is_a_wiring_fault_not_a_question():
    """`route_after_parents` refuses before reaching the writer when no
    section could be read, so an empty tuple here means a caller wired the
    port up by hand and got it wrong. It fails loudly rather than asking a
    model to answer from nothing."""
    with pytest.raises(ValueError, match="no passages"):
        _write(ScriptedChat(ANSWER), passages=(), parents={})


def test_the_model_is_never_asked_when_the_context_is_broken():
    """The guards run BEFORE the call, not after. A model asked to answer
    from nothing has already cost money and latency, and -- worse -- may
    well answer."""
    model = ScriptedChat(ANSWER)

    with pytest.raises(ValueError):
        _write(model, passages=(), parents={})

    assert model.calls == []


# --- the registry rule ------------------------------------------------


def test_the_prompt_comes_from_the_registry_not_from_the_code():
    """`prompts/README.md`: "inline prompt strings in app code fail
    review". Asserted on content the registry file carries and this module
    does not, so moving the text into `answering.py` turns this red."""
    model = ScriptedChat(ANSWER)

    _write(model)

    system, _user = model.calls[0]
    assert "ONLY the document sections" in system
    assert "language the question was asked in" in system


def test_the_prompt_forbids_bracketed_reference_numbers():
    """The UI renders source CARDS (UX spec 6.2), not a numbered
    bibliography, so "[1]" in the prose points at nothing the reader can
    open -- and a model that miscounts produces a citation to a source
    that does not exist. The rule lives in the prompt; this pins it there
    so a future version cannot drop it silently."""
    assert "[1]" in load_prompt(ANSWER_PROMPT_ID).system
