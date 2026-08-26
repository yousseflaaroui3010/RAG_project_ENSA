"""The parent-fetch port, against a REAL parent store on disk (ST-21).

Architecture 5.2 box P. Every other seam in this story is exercised with a
fake, because every other seam needs a model. This one reads files that
ST-16 wrote, so it is tested against files that ST-16's own `save_parents`
wrote -- no fake store, no hand-built JSON. A test that invented the file
layout itself would pass on a layout the real writer never produces, which
is the "self-referential" shape in the prove-it skill.
"""

from __future__ import annotations

import pytest

import parent_store
from agent.stores import parent_texts
from chunking import Parent

WORKSPACE = "ws-hr"
ARTICLE_13 = Parent(
    id="p-1",
    text="Article 13. La periode d'essai est de trois mois pour les cadres.",
    source_file="code-du-travail.pdf",
    section_label="Article 13",
)
ARTICLE_14 = Parent(
    id="p-2",
    text="Article 14. Le preavis est d'un mois.",
    source_file="code-du-travail.pdf",
    section_label="Article 14",
)


def _store(tmp_path, *parents: Parent):
    parent_store.save_parents(
        parents=list(parents), workspace_id=WORKSPACE, base_path=tmp_path
    )
    return tmp_path


def test_the_full_section_comes_back_keyed_by_parent_id(tmp_path):
    """The whole point of box P: what comes back is the SECTION, not the
    chunk that matched. Asserted on the text itself, because a mapping
    with the right keys and the wrong values would satisfy a shape
    check."""
    base = _store(tmp_path, ARTICLE_13, ARTICLE_14)

    texts = parent_texts(WORKSPACE, ("p-1", "p-2"), base_path=base)

    assert texts == {"p-1": ARTICLE_13.text, "p-2": ARTICLE_14.text}


def test_the_same_id_twice_is_read_once(tmp_path, monkeypatch):
    """Four chunks of one article open, read and parse ONE file.

    COUNTS THE READS, and that is the whole test. The first version
    asserted on the returned mapping, which cannot fail: writing the same
    text into the same dictionary key three times produces exactly the
    dictionary that writing it once produces, so the assertion was blind
    to whether the de-duplication happened at all. A review proved it by
    deleting `dict.fromkeys` and watching the assertion still pass. That
    is the "degenerate count" shape from the prove-it skill.

    What it costs when it breaks: a question whose top hits are four
    chunks of one article re-reads and re-parses that JSON file four
    times, per question, with the suite green throughout."""
    base = _store(tmp_path, ARTICLE_13)
    reads: list[str] = []
    real = parent_store.get_parent

    def counting_get_parent(**kwargs):
        reads.append(kwargs["parent_id"])
        return real(**kwargs)

    monkeypatch.setattr(parent_store, "get_parent", counting_get_parent)

    texts = parent_texts(WORKSPACE, ("p-1", "p-1", "p-1"), base_path=base)

    assert reads == ["p-1"]
    assert texts == {"p-1": ARTICLE_13.text}


def test_a_missing_section_is_left_out_rather_than_faked(tmp_path):
    """The store drifting from the index by one file is a real state --
    `parent_store.get_parent` names it: "its chunk may have been indexed
    before the parent was written". Answering from the sections that ARE
    there beats refusing outright, and an empty string in its place would
    be the model reading a section that says nothing."""
    base = _store(tmp_path, ARTICLE_13)

    texts = parent_texts(WORKSPACE, ("p-1", "p-2"), base_path=base)

    assert texts == {"p-1": ARTICLE_13.text}
    assert "p-2" not in texts


def test_a_corrupt_section_raises_instead_of_being_skipped(tmp_path):
    """The opposite decision from the one above, and the reason both are
    written down: a file that is MISSING is a store that has drifted, a
    file that exists and is unreadable is a store that may be lying.
    Skipping the second would risk citing a section that is not the
    section it claims to be."""
    base = _store(tmp_path, ARTICLE_13)
    corrupt = base / WORKSPACE / "p-1.json"
    corrupt.write_text("{ this is not json", encoding="utf-8")

    with pytest.raises(parent_store.CorruptParentError):
        parent_texts(WORKSPACE, ("p-1",), base_path=base)


def test_asking_for_nothing_reads_nothing(tmp_path):
    """A question whose hits were all judged off-topic never reaches this
    function, but a caller passing an empty tuple must not blow up on the
    way to a refusal."""
    base = _store(tmp_path, ARTICLE_13)

    assert parent_texts(WORKSPACE, (), base_path=base) == {}


def test_one_workspace_cannot_read_another_workspace_s_section(tmp_path):
    """PRD F-01 isolation, at this seam. The id exists -- in the other
    workspace -- and asking for it here must come back empty rather than
    returning the neighbour's text."""
    parent_store.save_parents(
        parents=[ARTICLE_13], workspace_id="ws-manuals", base_path=tmp_path
    )

    assert parent_texts(WORKSPACE, ("p-1",), base_path=tmp_path) == {}
