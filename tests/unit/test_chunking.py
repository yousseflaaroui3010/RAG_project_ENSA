"""ST-14 exit gate: boundary tests at 2,000 and 4,000 characters, and the
100-character child overlap verified.

Reference: docs/phase2/Sanad_Architecture_v1.0.md section 7.5 -- "parents
split on markdown headings H1-H3, merged below 2,000 characters, split
above 4,000; children 500 characters with 100 overlap".

Every boundary is asserted on BOTH sides (1999 and 2000, 4000 and 4001).
That is the ST-12 lesson recorded in BUILD-STATE: a mutation that ignores
the configured value and restores a plausible DEFAULT cannot be seen by a
one-sided assertion. "It made one parent" is true of a great many broken
splitters; "it made one parent at 1999 and two at 2000" is true of
exactly one.
"""

from __future__ import annotations

import pytest

import chunking
from chunking import Child, Parent
from config import get_settings

SOURCE = "code-du-travail.pdf"


def _body(size: int, filler: str = "a") -> str:
    """A section body of exactly `size` characters, with no leading or
    trailing whitespace for `_split_on_headings` to strip away."""
    return filler * size


def _doc(*sections: tuple[str, str]) -> str:
    """Assemble a markdown document from (heading, body) pairs."""
    return "\n\n".join(f"# {heading}\n\n{body}" for heading, body in sections)


def _chunk(markdown: str):
    return chunking.chunk_document(markdown, source_file=SOURCE)


def _with_settings(monkeypatch, **overrides):
    """Point the module at non-default chunking settings.

    Tests that care about a number run at a value the code cannot have
    hardcoded, so a mutation replacing `get_settings().x` with the default
    literal turns them red."""
    settings = get_settings().model_copy(update=overrides)
    monkeypatch.setattr(chunking, "get_settings", lambda: settings)
    return settings


# --- splitting on headings (section 7.5: H1-H3) -----------------------


def test_h1_h2_and_h3_each_start_a_new_section():
    """All three levels split. Asserted by label, not by count alone: a
    splitter that cut in the right number of places but attached the wrong
    heading to each piece would satisfy a count and produce wrong
    citations (PRD F-03 puts the label next to the file name)."""
    markdown = (
        "# Premier\n\n" + _body(2500) + "\n\n"
        "## Deuxieme\n\n" + _body(2500) + "\n\n"
        "### Troisieme\n\n" + _body(2500)
    )

    parents = _chunk(markdown).parents

    assert [p.section_label for p in parents] == ["Premier", "Deuxieme", "Troisieme"]


def test_h4_and_deeper_do_not_start_a_new_section():
    """Section 7.5 says H1-H3, and the boundary matters: `####` is a
    subsection of the section it sits in, and promoting it would shred a
    document into fragments too small to answer from.

    Both sides asserted -- the `###` above it DOES split, so this cannot
    pass by a splitter that simply never splits."""
    markdown = (
        "### Vraie section\n\n" + _body(1200) + "\n\n"
        "#### Sous-titre\n\n" + _body(1200)
    )

    parents = _chunk(markdown).parents

    assert len(parents) == 1
    assert parents[0].section_label == "Vraie section"
    assert "#### Sous-titre" in parents[0].text


def test_a_hash_inside_a_code_fence_is_not_a_heading():
    """A Python comment inside a fenced block starts with `# `, which is
    exactly an H1. Splitting there would cut the document at a line that
    is not a section at all -- and converted markdown really does contain
    fences."""
    markdown = (
        "# Guide\n\n"
        + _body(1200)
        + "\n\n```python\n# ceci est un commentaire, pas un titre\nx = 1\n```\n\n"
        + _body(1200)
    )

    parents = _chunk(markdown).parents

    assert len(parents) == 1
    assert parents[0].section_label == "Guide"
    assert "# ceci est un commentaire" in parents[0].text


def test_text_before_the_first_heading_is_never_dropped():
    """A preamble must survive. A short one merges into the parent that
    follows it, exactly as any other short section does -- see
    `test_a_short_preamble_inherits_the_label_of_the_section_it_merges_into`
    for the citation cost of that, which is bounded and deliberate."""
    markdown = "Texte d'introduction avant tout titre.\n\n# Article 1\n\n" + _body(2500)

    parents = _chunk(markdown).parents

    assert any("Texte d'introduction" in p.text for p in parents)


def test_a_preamble_long_enough_to_stand_alone_keeps_no_label():
    """`None` is the honest label for text the document never put under a
    heading. Inventing one would put a heading in a citation that does not
    exist in the source."""
    markdown = _body(2500) + "\n\n# Article 1\n\n" + _body(2500)

    parents = _chunk(markdown).parents

    assert len(parents) == 2
    assert parents[0].section_label is None
    assert parents[1].section_label == "Article 1"


def test_a_short_preamble_inherits_the_label_of_the_section_it_merges_into():
    """Pins the one place where the label is deliberately imprecise, so a
    future reader meets it as a decision rather than a surprise.

    A preamble too short to stand alone merges forward, and the parent
    carries the heading of the section holding the bulk of its text. The
    alternative is a parent of a few dozen characters, which gives the
    answering model nothing to answer from. It is bounded: a document has
    at most ONE unlabelled preamble, so at most one parent per file can be
    affected, and only when that preamble is under the merge threshold."""
    markdown = "Note liminaire.\n\n# Article 1\n\n" + _body(2500)

    parents = _chunk(markdown).parents

    assert len(parents) == 1
    assert parents[0].section_label == "Article 1"


def test_a_document_with_no_headings_becomes_one_parent():
    """Not an edge case: a converted TXT file has no headings at all, so
    this path carries entire documents."""
    result = _chunk("Une note simple, sans aucun titre, mais avec du contenu.")

    assert len(result.parents) == 1
    assert result.parents[0].section_label is None
    assert result.children


# --- the 2,000 character merge boundary -------------------------------


def test_sections_below_the_merge_threshold_are_merged():
    """Two 1,999-character sections reach 3,998 together and become ONE
    parent. Without merging, a document of forty short articles yields
    forty parents so thin that retrieving one tells the model nothing."""
    markdown = _doc(("Article 1", _body(1999)), ("Article 2", _body(1999)))

    parents = _chunk(markdown).parents

    assert len(parents) == 1


def test_sections_at_exactly_the_merge_threshold_stand_alone():
    """The other side of the same boundary. 2,000 is "not below 2,000", so
    each section keeps its own parent -- and its own correct heading.

    This pair of tests is the exit criterion: 1,999 merges, 2,000 does
    not. Either test alone is satisfied by a splitter that always merges
    or never merges."""
    markdown = _doc(("Article 1", _body(2000)), ("Article 2", _body(2000)))

    parents = _chunk(markdown).parents

    assert len(parents) == 2
    assert [p.section_label for p in parents] == ["Article 1", "Article 2"]


def test_the_merge_threshold_is_read_from_config():
    """Run at a non-default threshold so a hardcoded 2000 cannot pass.
    Both sides again: just under merges, exactly at it does not."""
    merged = _doc(("A", _body(299)), ("B", _body(299)))
    standalone = _doc(("A", _body(300)), ("B", _body(300)))

    with pytest.MonkeyPatch.context() as mp:
        _with_settings(mp, parent_merge_below_chars=300)
        assert len(_chunk(merged).parents) == 1
        assert len(_chunk(standalone).parents) == 2


def test_a_trailing_short_section_joins_the_previous_parent():
    """A final run that never reaches the threshold has to go somewhere. A
    parent under the threshold is precisely what merging exists to
    prevent, so it joins the parent before it rather than standing alone."""
    markdown = _doc(
        ("Article 1", _body(2000)),
        ("Article 2", _body(50)),
    )

    parents = _chunk(markdown).parents

    assert len(parents) == 1
    assert _body(50) in parents[0].text


def test_a_merged_parent_is_labelled_with_the_range_it_covers():
    """PRD F-03: the section label is shown to the user as the source of
    the passage. A parent spanning Articles 1 to 3 labelled only
    "Article 1" would cite a sentence from Article 3 under the wrong
    heading -- a quietly wrong citation in a product whose whole promise
    is honest sourcing.

    Both ends asserted, so a label built from only the first or only the
    last heading fails.

    Headings here deliberately carry their own dashes, the way real ones
    do ("Article 2 - Duree"). An earlier version used tidy "Article 1"
    headings and a " - " range separator, and on a realistic document the
    result read "Article 2 - Duree - Article 4 - Rupture" -- a citation
    where the reader cannot tell the range separator from the heading's
    own punctuation. The tests never saw it; running the thing did."""
    markdown = _doc(
        ("Article 1 - Periode d'essai", _body(600)),
        ("Article 2 - Duree", _body(600)),
        ("Article 3 - Rupture", _body(600)),
    )

    parents = _chunk(markdown).parents

    assert len(parents) == 1
    assert parents[0].section_label == "Article 1 - Periode d'essai ... Article 3 - Rupture"


def test_an_unmerged_parent_keeps_its_plain_heading():
    """The range wording must not leak onto a parent that covers exactly
    one section -- "Article 1 - Article 1" in a citation would read as a
    bug to the user."""
    markdown = _doc(("Article 1", _body(2500)))

    assert _chunk(markdown).parents[0].section_label == "Article 1"


# --- the 4,000 character split boundary -------------------------------


def test_a_section_at_exactly_the_split_threshold_is_not_split():
    """4,000 is "not above 4,000". Two 1,999 bodies joined by the
    two-character paragraph break land on exactly 4,000."""
    markdown = _doc(("Article 1", _body(1999)), ("Article 2", _body(1999)))

    parents = _chunk(markdown).parents

    assert len(parents) == 1
    assert len(parents[0].text) == 4000


def test_a_section_above_the_split_threshold_is_split():
    """One character more, and it splits. The pair is the exit criterion;
    either alone would pass a splitter that always splits or never does."""
    markdown = _doc(("Article 1", _body(4001)))

    parents = _chunk(markdown).parents

    assert len(parents) == 2
    assert all(len(p.text) <= 4000 for p in parents)


def test_the_split_threshold_is_read_from_config():
    """Non-default value, both sides of it."""
    with pytest.MonkeyPatch.context() as mp:
        _with_settings(mp, parent_merge_below_chars=1, parent_split_above_chars=500)
        assert len(_chunk(_doc(("A", _body(500)))).parents) == 1
        assert len(_chunk(_doc(("A", _body(501)))).parents) == 2


def test_split_pieces_keep_the_section_label():
    """Both halves of a split section came from the same heading, so both
    cite it. Dropping the label on the tail would make the second half
    uncitable."""
    parents = _chunk(_doc(("Article 7", _body(9000)))).parents

    assert len(parents) > 1
    assert {p.section_label for p in parents} == {"Article 7"}


def test_an_oversized_section_is_cut_at_paragraph_breaks_when_it_can_be():
    """A parent is what the answering model READS. A cut through the
    middle of a sentence loses that sentence from both pieces -- neither
    half says anything complete -- so paragraph breaks are preferred.

    Asserted by content, not by piece count: every paragraph must survive
    whole inside some parent."""
    paragraphs = [f"Paragraphe {n}. " + _body(900) for n in range(6)]
    markdown = "# Article 1\n\n" + "\n\n".join(paragraphs)

    parents = _chunk(markdown).parents

    assert len(parents) > 1
    for paragraph in paragraphs:
        assert any(paragraph in p.text for p in parents)


def test_splitting_an_oversized_section_loses_not_one_character():
    """The pieces must rejoin into exactly the original section.

    This became load-bearing once mutation testing showed the `<=` early
    return in `_split_oversized` to be an EQUIVALENT mutant: at exactly the
    threshold the early return and the paragraph packer produce identical
    output, so the packer -- not the fast path -- is what actually
    guarantees the text survives. A `.strip()` in the packer, a changed
    separator, or a dropped paragraph all vanish from a
    "does every paragraph appear somewhere" check and all fail here.

    Runs at a small, non-default limit so the piece boundaries are
    arithmetic rather than luck: the blank-line run is placed where it is
    GUARANTEED to start a piece. An earlier version of this test used the
    real 4,000 limit and a run somewhere in the middle, and a mutation
    that stripped every piece survived it -- the run happened to land
    mid-piece, where stripping does nothing. A whitespace bug that only
    shows at a boundary needs a test that puts it on the boundary."""
    # Three 40-char paragraphs at a 50-char limit: one paragraph per piece.
    # The middle one is preceded by a blank-line RUN, so after splitting on
    # the paragraph break it begins with a newline -- and therefore so does
    # the piece it lands in.
    section = _body(40, "A") + "\n\n\n" + _body(40, "B") + "\n\n" + _body(40, "C")

    with pytest.MonkeyPatch.context() as mp:
        _with_settings(mp, parent_merge_below_chars=1, parent_split_above_chars=50)
        parents = _chunk("# Article 1\n\n" + section).parents

    assert [p.text for p in parents] == [
        _body(40, "A"),
        "\n" + _body(40, "B"),
        _body(40, "C"),
    ]
    assert "\n\n".join(p.text for p in parents) == section


def test_paragraphs_packed_into_one_piece_keep_the_blank_line_between_them():
    """The companion to the test above, and it exists because that one
    could not see this bug: there, every piece held a single paragraph, so
    the code that REJOINS two paragraphs never ran on a piece that
    survived. A mutation joining them with a single newline sailed through.

    At a 100-char limit two 40-char paragraphs pack together, which is the
    only configuration where the separator is observable. Losing the blank
    line here would silently glue two paragraphs into one wall of text in
    the context the answering model reads."""
    section = _body(40, "A") + "\n\n" + _body(40, "B") + "\n\n" + _body(40, "C")

    with pytest.MonkeyPatch.context() as mp:
        _with_settings(mp, parent_merge_below_chars=1, parent_split_above_chars=100)
        parents = _chunk("# Article 1\n\n" + section).parents

    assert [p.text for p in parents] == [
        _body(40, "A") + "\n\n" + _body(40, "B"),
        _body(40, "C"),
    ]


def test_a_single_paragraph_larger_than_the_limit_is_still_cut():
    """A wall-of-text PDF page with no blank lines cannot be split at a
    paragraph break, and must not be allowed to sail past the limit."""
    parents = _chunk(_doc(("Article 1", _body(10000)))).parents

    assert all(len(p.text) <= 4000 for p in parents)
    assert len(parents) == 3


# --- children: 500 characters, 100 overlap ----------------------------


def test_consecutive_children_overlap_by_exactly_the_configured_amount():
    """The exit criterion, asserted as an equality on the shared text
    rather than on a length. A window that overlapped by the right NUMBER
    of characters but the wrong ones would still be a broken splitter."""
    settings = get_settings()
    overlap = settings.chunk_child_overlap_chars
    children = _chunk(_doc(("Article 1", _body(3000, filler="abcde")))).children

    assert len(children) > 2
    for earlier, later in zip(children, children[1:], strict=False):
        assert earlier.text[-overlap:] == later.text[:overlap]


def test_no_child_exceeds_the_configured_size():
    """The ceiling that keeps every embedded input under E5's 512-token
    limit (section 7.5). A child over the size is a silently truncated
    embedding later."""
    size = get_settings().chunk_child_size_chars
    children = _chunk(_doc(("Article 1", _body(3000)))).children

    assert children
    assert all(len(c.text) <= size for c in children)


def test_the_child_size_and_overlap_are_read_from_config():
    """Non-default values for both knobs, and the overlap asserted at the
    new value. A mutation restoring 500/100 makes the sizes wrong here."""
    with pytest.MonkeyPatch.context() as mp:
        _with_settings(
            mp,
            parent_merge_below_chars=1,
            parent_split_above_chars=100000,
            chunk_child_size_chars=50,
            chunk_child_overlap_chars=10,
        )
        children = _chunk(_doc(("A", _body(200, filler="xyz")))).children

        assert all(len(c.text) <= 50 for c in children)
        assert any(len(c.text) == 50 for c in children)
        for earlier, later in zip(children, children[1:], strict=False):
            assert earlier.text[-10:] == later.text[:10]


def test_the_windows_cover_the_whole_parent_with_nothing_lost():
    """Reassembles the parent from the children's non-overlapping strides.
    This is the assertion that catches a dropped TAIL -- the exact defect
    ST-12 found in its own hashing loop, where the last partial chunk was
    silently skipped."""
    settings = get_settings()
    stride = settings.chunk_child_size_chars - settings.chunk_child_overlap_chars
    result = _chunk(_doc(("Article 1", _body(2300, filler="abcdefg"))))

    for parent in result.parents:
        windows = [c.text for c in result.children if c.parent_id == parent.id]
        rebuilt = "".join(w[:stride] for w in windows[:-1]) + windows[-1]
        assert rebuilt == parent.text


def test_a_parent_shorter_than_one_window_makes_exactly_one_child():
    result = _chunk("Une note courte.")

    assert len(result.children) == 1
    assert result.children[0].text == result.parents[0].text


def test_a_parent_of_exactly_one_window_makes_no_duplicate_second_child():
    """A text whose length is exactly the window size must not emit a
    trailing window made entirely of already-covered overlap: that child
    would be embedded and searchable twice, and would surface as a
    duplicate source in an answer."""
    size = get_settings().chunk_child_size_chars
    with pytest.MonkeyPatch.context() as mp:
        _with_settings(mp, parent_merge_below_chars=1, parent_split_above_chars=100000)
        result = _chunk(_doc(("A", _body(size))))

    assert len(result.children) == 1


@pytest.mark.parametrize(
    ("overrides", "expected_in_message"),
    [
        ({"chunk_child_size_chars": 100, "chunk_child_overlap_chars": 100}, "100"),
        ({"chunk_child_size_chars": 0}, "chunk_child_size_chars"),
        ({"chunk_child_overlap_chars": -5}, "negative"),
        ({"parent_split_above_chars": 0}, "parent_split_above_chars"),
    ],
    ids=["overlap-equals-size", "zero-size", "negative-overlap", "zero-split-limit"],
)
def test_a_configuration_that_cannot_split_correctly_is_refused_loudly(
    overrides, expected_in_message
):
    """Every one of these fails SILENTLY without the check, which is the
    whole reason they are checked:

      - overlap >= size, and a zero split limit, both HANG. Sync never
        finishes and never errors; there is nothing in a log to follow.
      - a zero child size produces no children at all, so the document is
        indexed and completely unsearchable -- it looks like a successful
        sync.
      - a negative overlap leaves GAPS between windows: the text is in the
        parent but was never embedded, and the only symptom is the
        assistant saying "not covered here" about a passage it is holding.

    Found by self-review after the suite was green. `_windows` had guarded
    its own infinite loop from the start; `_split_oversized` contained the
    identical loop with no guard, and no test had ever asked."""
    with pytest.MonkeyPatch.context() as mp:
        _with_settings(mp, **overrides)
        with pytest.raises(chunking.InvalidChunkSettingsError) as caught:
            _chunk(_doc(("A", _body(500))))

    assert expected_in_message in str(caught.value)


# --- the parent/child relationship ------------------------------------


def test_every_child_points_at_a_parent_in_the_same_result():
    """The pair is only meaningful together: a child whose `parent_id`
    resolves to nothing is a search hit that cannot be turned into an
    answer at retrieval time (ST-16 looks the parent up by this id)."""
    result = _chunk(
        _doc(("Article 1", _body(3000)), ("Article 2", _body(3000)))
    )
    parent_ids = {p.id for p in result.parents}

    assert result.children
    assert all(c.parent_id in parent_ids for c in result.children)


def test_chunking_the_same_document_twice_gives_the_same_parent_ids():
    """Idempotency, and it is a data-safety property, not a nicety.

    §7.5 keys the parent store on this id
    (`data/parents/<workspace_id>/<parent_id>.json`) and puts it in the
    Qdrant payload. When ids were random, re-syncing a CHANGED file minted
    a whole new set: every previous JSON orphaned on disk, and any vector
    surviving the rewrite pointed at a parent file that no longer existed
    -- a search hit that resolves to nothing, which a sourced answer
    cannot survive.

    Asserted as full equality of the id LIST, not as a count or a set: the
    order carries the position each id was derived from, so a splitter that
    produced the right ids in the wrong order would still be wrong."""
    markdown = _doc(("Article 1", _body(3000)), ("Article 2", _body(3000)))

    first = _chunk(markdown).parents
    second = _chunk(markdown).parents

    assert [p.id for p in first] == [p.id for p in second]
    assert len(first) > 1


def test_a_changed_document_reuses_the_ids_of_the_parents_it_still_has():
    """The case the random ids actually broke. An edited file re-chunks to
    the same ids for the parents that still exist, so ST-17 overwrites them
    in place rather than leaving the originals behind as litter.

    Both halves asserted: the ids are reused AND the text really did
    change, so this cannot pass by the document being identical."""
    before = _doc(("Article 1", _body(3000)), ("Article 2", _body(3000)))
    after = _doc(("Article 1", _body(3000)), ("Article 2 revise", _body(3200)))

    old = _chunk(before).parents
    new = _chunk(after).parents

    assert [p.id for p in new[: len(old)]] == [p.id for p in old]
    assert new[-1].text != old[-1].text


def test_two_different_files_never_share_a_parent_id():
    """The id is derived from the file name and the position, so two files
    must not collide even when their content is identical -- otherwise one
    document's parents would overwrite another's in the store."""
    markdown = _doc(("Article 1", _body(3000)))

    a = chunking.chunk_document(markdown, source_file="hr.pdf").parents
    b = chunking.chunk_document(markdown, source_file="manuals.pdf").parents

    assert {p.id for p in a}.isdisjoint({p.id for p in b})


def test_parent_ids_are_unique():
    """They are filenames in the parent store
    (`data/parents/<workspace_id>/<parent_id>.json`, section 7.5): a
    collision silently overwrites one section's text with another's."""
    result = _chunk(_doc(("Article 1", _body(9000)), ("Article 2", _body(9000))))
    ids = [p.id for p in result.parents]

    assert len(ids) == len(set(ids))


def test_the_source_file_travels_to_every_parent_and_child():
    """Section 7.5 puts `source_file` in the Qdrant point payload so a hit
    is citable without a second lookup, and PRD F-03 requires the file
    name in every citation."""
    result = _chunk(_doc(("Article 1", _body(3000))))

    assert {p.source_file for p in result.parents} == {SOURCE}
    assert {c.source_file for c in result.children} == {SOURCE}


def test_the_section_label_travels_to_the_children():
    """The child is what retrieval returns; it has to carry its own label,
    or the citation needs a second lookup the payload was designed to
    avoid."""
    result = _chunk(_doc(("Article 9", _body(3000))))

    assert {c.section_label for c in result.children} == {"Article 9"}


def test_children_carry_no_embedding_prefix():
    """CLAUDE.md hard rule: every embedded chunk starts with `passage: `.
    That prefix belongs to ST-15 and must be added exactly ONCE. If
    chunking added it too, every embedded input would read
    "passage: passage: ..." and drift from the model card's contract."""
    children = _chunk(_doc(("Article 1", _body(3000)))).children

    assert children
    assert not any(c.text.startswith("passage: ") for c in children)


# --- degenerate input --------------------------------------------------


@pytest.mark.parametrize("markdown", ["", "   \n\n \t \n"])
def test_empty_input_produces_nothing(markdown):
    """Conversion already reports such a file as Skipped (ST-13's
    emptiness gate), so reaching here empty means the caller skipped that
    check. Inventing an empty parent would put a citable source with no
    content into the index."""
    result = _chunk(markdown)

    assert result == chunking.ChunkedDocument(parents=[], children=[])


def test_a_heading_with_no_body_does_not_create_an_empty_parent():
    """A trailing heading is common in converted PDFs (a section title on
    the last line of the last page). It must not become a parent with no
    text."""
    markdown = "# Article 1\n\n" + _body(2500) + "\n\n# Article 2 sans corps\n"

    parents = _chunk(markdown).parents

    assert all(p.text.strip() for p in parents)


def test_the_dataclasses_are_frozen():
    """Parents and children are handed to the embedder, the vector store
    and the parent store in turn. Making them immutable is what stops a
    later stage from quietly editing chunk text that has already been
    embedded, leaving the index and the store disagreeing."""
    parent = Parent(id="1", text="t", source_file=SOURCE)
    child = Child(text="t", parent_id="1", source_file=SOURCE)

    with pytest.raises(AttributeError):
        parent.text = "changed"
    with pytest.raises(AttributeError):
        child.text = "changed"
