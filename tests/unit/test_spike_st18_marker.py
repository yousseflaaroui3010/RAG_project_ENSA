"""The ST-18 spike's article matcher, which decides a published number.

Reference: BUILD-PLAN line 66 (ST-18), PRD F-03 ("file name plus section
label"), and the right-article figure BUILD-STATE calls the most important
open number on the project.

WHY THIS FILE EXISTS AT ALL, and it is the point rather than a preamble:
`scripts/` had NO tests. Both spike scripts together are over 1,300 lines,
none of it exercised by anything, and the one number the whole ST-18
verdict rests on was computed by a plain `in` test. A cold review found it
and the collisions below were reproduced before the fix.

That is the argument for testing measurement code specifically: a defect
here does not crash and does not fail a gate. It quietly reports a better
number than the truth, and the number gets quoted in a report.

This file tests ONE function, deliberately. `marker_found` is the whole of
the judgement; everything else in that script needs a real corpus and a
paid model, which is why the rest stays unexercised and why BUILD-STATE
says so out loud.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from spike_st18 import PROBES, marker_found  # noqa: E402

# Text of the shape this corpus really contains: article numbers, a dahir
# number, and the second HR document naming itself.
CHILD_LABOUR = "Article 143 interdit d'employer des mineurs de moins de seize ans."
OTHER_DOCUMENT = "dahir n 1-72-184 relatif au regime de securite sociale"
NEARBY_ARTICLE = "les dispositions de l'article 139 du present code"
TRIAL_PERIOD = "Article 14 : la periode d'essai ne peut exceder trois mois."


@pytest.mark.parametrize(
    ("marker", "text"),
    [
        ("14", CHILD_LABOUR),
        ("143", "Article 1432 n'existe pas"),
        ("39", NEARBY_ARTICLE),
        ("72", OTHER_DOCUMENT),
        ("184", OTHER_DOCUMENT),
        ("205", "le decret 2-05-734 du 20 mai"),
    ],
    ids=[
        "14-inside-143", "143-inside-1432", "39-inside-139",
        "72-inside-the-dahir-number", "184-inside-the-dahir-number",
        "205-inside-a-decree-number",
    ],
)
def test_a_number_that_merely_appears_is_not_a_cited_article(marker, text):
    """Every row here scored a HIT before the fix, and each one inflates
    the published right-article figure by one.

    The two dahir rows are the worst of them: `1-72-184` is the NAME of
    another document in the same workspace, so a probe expecting an
    article of the labour code could be satisfied by retrieving a
    completely different file -- which is the exact failure the marker was
    added to detect."""
    assert marker_found(marker, text) is False


@pytest.mark.parametrize(
    ("marker", "text"),
    [
        ("14", TRIAL_PERIOD),
        ("143", CHILD_LABOUR),
        ("231", "Article 231 fixe la duree du conge annuel paye."),
        ("231", "ARTICLE 231 EN MAJUSCULES"),
        ("231", "l'article 231 du code du travail"),
        ("205", "Articles 203, 204 et 205 du present chapitre"),
    ],
    ids=[
        "plain", "three-digit", "sentence", "shouted", "lowercase-lartic",
        "inside-a-list-of-articles",
    ],
)
def test_a_genuinely_cited_article_is_found(marker, text):
    """The other direction, and it is what stops the fix from becoming
    "score nothing and look precise". A matcher that only ever says False
    would pass every row above and report 0/8, which is not an
    improvement -- it is the same defect pointing the other way."""
    assert marker_found(marker, text) is True


def test_an_accented_corpus_still_matches_an_ascii_probe():
    """The probes are typed in ASCII and the corpus is real French. This
    project has already shipped one measurement rigged by exactly that
    asymmetry -- a keyword baseline that could not match its own probes
    because `casefold()` folds case and not accents."""
    assert marker_found("231", "Article 231 : congés annuels payés") is True


def test_a_probe_with_no_marker_never_scores():
    """Ten of the twenty probes carry no article number, because their
    documents have no numbered unit. They must not score a free hit."""
    assert marker_found("", "Article 231 fixe la duree du conge") is False


def test_every_marker_in_the_real_probe_list_is_still_reachable():
    """A guard on the pattern itself rather than on my examples.

    If a future edit tightens `marker_found` so far that a real probe can
    never match, the spike would report a falling number and look like a
    retrieval regression. This pins that every marker actually shipped in
    `PROBES` can be satisfied by a well-formed citation of it."""
    markers = [probe.expect_marker for probe in PROBES if probe.expect_marker]

    assert markers, "the probe list must still carry article markers"
    for marker in markers:
        assert marker_found(marker, f"Article {marker} du present code") is True
