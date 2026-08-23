"""ST-16 (first half) exit gate: parents resolve by id, and one
workspace's parents are unreachable from another.

Reference: docs/phase2/Sanad_Architecture_v1.0.md section 7.5 (parent
store at `data/parents/<workspace_id>/<parent_id>.json`, holding the
parent's full text plus `source_file` and `section_label`), ADR-08 (big
text blobs stay out of the registry), and PRD F-01 (workspace isolation is
absolute) / F-03 (every answer names its source).

Every test writes real JSON to a real directory under `tmp_path` and reads
it back through the module's own public functions. Nothing is mocked:
this module's entire job is what happens on a filesystem, so a mocked
filesystem would test the mock.
"""

from __future__ import annotations

import json

import pytest

import parent_store
from chunking import Parent

WS_HR = "11111111-1111-1111-1111-111111111111"
WS_MANUALS = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def store(tmp_path):
    return tmp_path / "parents"


def _parent(parent_id="aaaaaaaa-0000-0000-0000-000000000001", **overrides):
    fields = {
        "id": parent_id,
        "text": "# Article 1\n\nLa periode d'essai dure trois mois.",
        "source_file": "code-du-travail.pdf",
        "section_label": "Article 1",
    }
    fields.update(overrides)
    return Parent(**fields)


# --- the round trip ---------------------------------------------------


def test_a_saved_parent_comes_back_identical(store):
    """"Parents resolve by id" is half of ST-16's exit criterion.

    Asserted field by field rather than on the object, so a converter that
    dropped one field and defaulted it would fail here instead of passing
    on an equality that never looked inside."""
    original = _parent()

    parent_store.save_parents(workspace_id=WS_HR, parents=[original], base_path=store)
    loaded = parent_store.get_parent(
        workspace_id=WS_HR, parent_id=original.id, base_path=store
    )

    assert loaded.id == original.id
    assert loaded.text == original.text
    assert loaded.source_file == original.source_file
    assert loaded.section_label == original.section_label


def test_the_file_lands_where_section_7_5_says_it_should(store):
    """The path is part of the signed spec, not an implementation detail:
    ST-17 and any future recovery tooling navigate it directly."""
    parent = _parent()

    parent_store.save_parents(workspace_id=WS_HR, parents=[parent], base_path=store)

    assert (store / WS_HR / f"{parent.id}.json").is_file()


def test_a_parent_with_no_heading_round_trips_as_none(store):
    """`section_label=None` is a legal value (a preamble, or a TXT file
    with no headings at all), not missing data. It must not come back as
    the string "None" or as an empty string, because the UI decides
    whether to show a section in the citation by testing this field."""
    parent = _parent(section_label=None)

    parent_store.save_parents(workspace_id=WS_HR, parents=[parent], base_path=store)
    loaded = parent_store.get_parent(
        workspace_id=WS_HR, parent_id=parent.id, base_path=store
    )

    assert loaded.section_label is None


def test_a_file_with_no_section_label_key_at_all_loads_as_no_heading(store):
    """Absent is not corrupt. A parent file that never had the key -- one
    written by an older build, or hand-repaired -- means "no heading",
    which is a legal state, so it must load rather than crash.

    This needs a hand-written file: `save_parents` always writes the key
    with a null, so a round-trip through this module can never produce the
    absent case. Mutation testing is what exposed that: swapping `.get`
    for a plain lookup survived the whole suite, because no test had ever
    put a file on disk without the key."""
    directory = store / WS_HR
    directory.mkdir(parents=True)
    parent_id = "aaaaaaaa-4444-4444-4444-444444444444"
    (directory / f"{parent_id}.json").write_text(
        json.dumps({"id": parent_id, "text": "Corps.", "source_file": "notes.txt"}),
        encoding="utf-8",
    )

    loaded = parent_store.get_parent(
        workspace_id=WS_HR, parent_id=parent_id, base_path=store
    )

    assert loaded.section_label is None
    assert loaded.text == "Corps."


def test_accented_and_arabic_text_survives_the_round_trip(store):
    """Sanad's corpus is French, and F-14 puts Arabic on the roadmap. A
    store that mangles either is useless for the actual documents.

    Asserted on the FILE too, not only the round trip: `json.dumps` would
    round-trip escaped `\\u00e9` sequences perfectly well while making the
    file unreadable to a human debugging it at 2am."""
    parent = _parent(text="Conges payes: 18 jours. العربية")

    parent_store.save_parents(workspace_id=WS_HR, parents=[parent], base_path=store)
    loaded = parent_store.get_parent(
        workspace_id=WS_HR, parent_id=parent.id, base_path=store
    )

    assert loaded.text == parent.text
    on_disk = (store / WS_HR / f"{parent.id}.json").read_text(encoding="utf-8")
    assert "Conges payes" in on_disk
    assert "العربية" in on_disk


def test_saving_many_parents_writes_one_file_each(store):
    parents = [_parent(f"aaaaaaaa-0000-0000-0000-00000000000{n}") for n in range(1, 4)]

    written = parent_store.save_parents(
        workspace_id=WS_HR, parents=parents, base_path=store
    )

    assert written == 3
    assert len(list((store / WS_HR).glob("*.json"))) == 3


def test_saving_the_same_id_again_overwrites_in_place(store):
    """The behaviour ST-14's derived ids were built for: re-ingesting a
    changed document lands on the same file names and replaces them,
    rather than leaving the previous version behind as an orphan.

    Both halves asserted -- the text really changed AND no second file
    appeared."""
    first = _parent(text="original text")
    second = _parent(text="revised text")

    parent_store.save_parents(workspace_id=WS_HR, parents=[first], base_path=store)
    parent_store.save_parents(workspace_id=WS_HR, parents=[second], base_path=store)
    loaded = parent_store.get_parent(
        workspace_id=WS_HR, parent_id=first.id, base_path=store
    )

    assert loaded.text == "revised text"
    assert len(list((store / WS_HR).glob("*.json"))) == 1


def test_no_half_written_file_is_left_behind(store):
    """No temporary file survives a successful save.

    Weak on its own -- code that never wrote a temp file at all would also
    pass. The test below is the one that proves atomicity."""
    parent_store.save_parents(workspace_id=WS_HR, parents=[_parent()], base_path=store)

    assert list((store / WS_HR).glob("*.tmp")) == []


def test_a_failed_save_leaves_the_previous_version_readable(store, monkeypatch):
    """The real atomicity check, and the reason for the temp-file dance.

    Parents are read at ANSWER time while a sync may be rewriting them. A
    plain in-place write leaves a window where a reader opens half a JSON
    document; worse, a crash inside that window leaves the half document
    there permanently. Writing to a temporary name and moving it with
    `os.replace` means a reader sees the old complete file or the new
    complete file and nothing in between.

    Proven by breaking the move: with the atomic version the target still
    holds v1, because it was never opened for writing. An in-place write
    would already have destroyed it before failing."""
    parent_store.save_parents(
        workspace_id=WS_HR, parents=[_parent(text="v1 the good version")],
        base_path=store,
    )

    def refuse(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(parent_store.os, "replace", refuse)
    with pytest.raises(OSError):
        parent_store.save_parents(
            workspace_id=WS_HR, parents=[_parent(text="v2 never lands")],
            base_path=store,
        )

    survivor = parent_store.get_parent(
        workspace_id=WS_HR, parent_id=_parent().id, base_path=store
    )
    assert survivor.text == "v1 the good version"


# --- isolation (PRD F-01) ---------------------------------------------


def test_one_workspace_cannot_read_another_workspace_parent(store):
    """PRD F-01: isolation is absolute -- an HR question never pulls a
    passage from the manuals.

    Isolation here is a property of the FILESYSTEM, not of a filter
    somebody has to remember to apply: the id simply is not in the other
    workspace's directory. Both directions asserted, so a store that
    happened to hide one workspace from the other by accident of ordering
    still fails."""
    hr_parent = _parent("aaaaaaaa-0000-0000-0000-00000000000a")
    manuals_parent = _parent("bbbbbbbb-0000-0000-0000-00000000000b")

    parent_store.save_parents(workspace_id=WS_HR, parents=[hr_parent], base_path=store)
    parent_store.save_parents(
        workspace_id=WS_MANUALS, parents=[manuals_parent], base_path=store
    )

    with pytest.raises(parent_store.ParentNotFoundError):
        parent_store.get_parent(
            workspace_id=WS_HR, parent_id=manuals_parent.id, base_path=store
        )
    with pytest.raises(parent_store.ParentNotFoundError):
        parent_store.get_parent(
            workspace_id=WS_MANUALS, parent_id=hr_parent.id, base_path=store
        )


def test_two_workspaces_can_hold_the_same_parent_id_without_colliding(store):
    """Chunking derives parent ids from the file name and position, so two
    workspaces holding a file of the same name derive the SAME ids. §7.5's
    per-workspace directory is what keeps them apart, and this test is what
    stops anyone flattening that layout later without noticing."""
    shared_id = "cccccccc-0000-0000-0000-00000000000c"

    parent_store.save_parents(
        workspace_id=WS_HR,
        parents=[_parent(shared_id, text="HR version")],
        base_path=store,
    )
    parent_store.save_parents(
        workspace_id=WS_MANUALS,
        parents=[_parent(shared_id, text="manuals version")],
        base_path=store,
    )

    hr = parent_store.get_parent(
        workspace_id=WS_HR, parent_id=shared_id, base_path=store
    )
    manuals = parent_store.get_parent(
        workspace_id=WS_MANUALS, parent_id=shared_id, base_path=store
    )

    assert hr.text == "HR version"
    assert manuals.text == "manuals version"


# --- failures that must be loud ---------------------------------------


def test_a_missing_parent_raises_instead_of_returning_none(store):
    """A missing parent means a child chunk points at a section that is
    gone -- a broken citation. Returning None would let a caller render an
    answer whose source text silently failed to load, which is the one
    failure a sourced-answer product cannot absorb.

    The message is asserted to name the workspace and the id, because the
    person reading it is debugging a wrong answer, not the store."""
    with pytest.raises(parent_store.ParentNotFoundError) as caught:
        parent_store.get_parent(
            workspace_id=WS_HR, parent_id="dddddddd-0000-0000-0000-00000000000d",
            base_path=store,
        )

    assert "dddddddd-0000-0000-0000-00000000000d" in str(caught.value)
    assert WS_HR in str(caught.value)


def test_unreadable_json_is_reported_as_corrupt_not_missing(store):
    """"The file is not there" and "the file is there and wrong" need
    different answers: the first is a re-sync, the second is a damaged
    store. Collapsing them sends the user to fix the wrong thing."""
    directory = store / WS_HR
    directory.mkdir(parents=True)
    (directory / "eeeeeeee-0000-0000-0000-00000000000e.json").write_text(
        "{not json at all", encoding="utf-8"
    )

    with pytest.raises(parent_store.CorruptParentError):
        parent_store.get_parent(
            workspace_id=WS_HR, parent_id="eeeeeeee-0000-0000-0000-00000000000e",
            base_path=store,
        )


def test_a_parent_file_whose_id_disagrees_with_its_name_is_refused(store):
    """The check a filename alone cannot make. A file copied, renamed, or
    restored from another workspace's backup would otherwise be served as
    a section it is not, and the answer would cite the wrong source with
    complete confidence -- wrong, and confidently wrong, which is worse
    than an error."""
    directory = store / WS_HR
    directory.mkdir(parents=True)
    (directory / "ffffffff-0000-0000-0000-00000000000f.json").write_text(
        json.dumps(
            {
                "id": "aaaaaaaa-1111-1111-1111-111111111111",
                "text": "someone else's section",
                "source_file": "manuals.pdf",
                "section_label": "Chapter 9",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(parent_store.CorruptParentError) as caught:
        parent_store.get_parent(
            workspace_id=WS_HR, parent_id="ffffffff-0000-0000-0000-00000000000f",
            base_path=store,
        )

    assert "renamed" in str(caught.value) or "id" in str(caught.value)


def test_a_parent_file_missing_a_required_field_is_refused(store):
    directory = store / WS_HR
    directory.mkdir(parents=True)
    (directory / "aaaaaaaa-2222-2222-2222-222222222222.json").write_text(
        json.dumps({"id": "aaaaaaaa-2222-2222-2222-222222222222", "text": "no source"}),
        encoding="utf-8",
    )

    with pytest.raises(parent_store.CorruptParentError) as caught:
        parent_store.get_parent(
            workspace_id=WS_HR, parent_id="aaaaaaaa-2222-2222-2222-222222222222",
            base_path=store,
        )

    assert "source_file" in str(caught.value)


@pytest.mark.parametrize(
    "bad_id",
    ["../escape", "..", "a/b", "a\\b", "", "with space", "a:b"],
)
def test_an_id_that_could_escape_the_store_is_refused(store, bad_id):
    """Ids become path segments. Sanad generates them today, so this should
    never fire -- it is here because the day it does fire is the day
    something is putting outside text into a file path, and a store that
    quietly wrote through `../` would be handing over the disk.

    An allow-list, not a "reject .." blocklist: blocklists lose to
    encodings, alternate separators, and the next trick nobody thought of."""
    with pytest.raises(parent_store.UnsafeIdentifierError):
        parent_store.get_parent(
            workspace_id=WS_HR, parent_id=bad_id, base_path=store
        )
    with pytest.raises(parent_store.UnsafeIdentifierError):
        parent_store.get_parent(
            workspace_id=bad_id, parent_id="aaaaaaaa-3333-3333-3333-333333333333",
            base_path=store,
        )


def test_a_traversing_id_never_creates_a_file_outside_the_store(store):
    """The assertion that matters more than the exception type: prove
    nothing was written outside the store directory."""
    escaping = Parent(id="../../pwned", text="x", source_file="f.pdf")

    with pytest.raises(parent_store.UnsafeIdentifierError):
        parent_store.save_parents(
            workspace_id=WS_HR, parents=[escaping], base_path=store
        )

    assert not (store.parent / "pwned.json").exists()
    assert not (store / "pwned.json").exists()


# --- deletion ---------------------------------------------------------


def test_deleting_named_parents_removes_only_those(store):
    """Both bounds: the named one is gone AND the unnamed one survives.
    Asserting only the first would pass a delete that wiped the folder."""
    keep = _parent("aaaaaaaa-0000-0000-0000-00000000000a")
    remove = _parent("bbbbbbbb-0000-0000-0000-00000000000b")
    parent_store.save_parents(
        workspace_id=WS_HR, parents=[keep, remove], base_path=store
    )

    deleted = parent_store.delete_parents(
        workspace_id=WS_HR, parent_ids=[remove.id], base_path=store
    )

    assert deleted == 1
    assert parent_store.get_parent(
        workspace_id=WS_HR, parent_id=keep.id, base_path=store
    ).id == keep.id
    with pytest.raises(parent_store.ParentNotFoundError):
        parent_store.get_parent(
            workspace_id=WS_HR, parent_id=remove.id, base_path=store
        )


def test_deleting_an_already_deleted_parent_is_not_an_error(store):
    """Deletion is what a caller runs to reach a known end state, and it
    gets re-run after partial failures and crashes. "Already gone" is
    success -- raising would make the safe thing to do (run it again) the
    thing that fails."""
    parent = _parent()
    parent_store.save_parents(workspace_id=WS_HR, parents=[parent], base_path=store)

    first = parent_store.delete_parents(
        workspace_id=WS_HR, parent_ids=[parent.id], base_path=store
    )
    second = parent_store.delete_parents(
        workspace_id=WS_HR, parent_ids=[parent.id], base_path=store
    )

    assert (first, second) == (1, 0)


def test_deleting_a_workspace_removes_its_parents_and_leaves_the_other(store):
    """PRD F-01: deleting a workspace removes its derived data. Isolation
    applies to deletion as much as to reading -- wiping HR must not touch
    the manuals."""
    parent_store.save_parents(
        workspace_id=WS_HR,
        parents=[_parent("aaaaaaaa-0000-0000-0000-00000000000a")],
        base_path=store,
    )
    parent_store.save_parents(
        workspace_id=WS_MANUALS,
        parents=[_parent("bbbbbbbb-0000-0000-0000-00000000000b")],
        base_path=store,
    )

    removed = parent_store.delete_workspace_parents(
        workspace_id=WS_HR, base_path=store
    )

    assert removed == 1
    assert not (store / WS_HR).exists()
    assert (store / WS_MANUALS).is_dir()


def test_deleting_a_workspace_that_never_stored_anything_is_not_an_error(store):
    """A workspace deleted before its first sync has no directory. That is
    a normal path, not a fault."""
    assert (
        parent_store.delete_workspace_parents(workspace_id=WS_HR, base_path=store) == 0
    )


# --- config wiring ----------------------------------------------------


def test_the_store_location_comes_from_config(tmp_path, monkeypatch):
    """CLAUDE.md hard rule: tunables live in config.py, never hardcoded a
    second time. Run at a NON-default path so a mutation restoring the
    literal "data/parents/" fails here -- the ST-12 lesson about mutations
    that restore a plausible DEFAULT."""
    configured = tmp_path / "somewhere-else"
    settings = parent_store.get_settings().model_copy(
        update={"parent_store_path": str(configured)}
    )
    monkeypatch.setattr(parent_store, "get_settings", lambda: settings)
    parent = _parent()

    parent_store.save_parents(workspace_id=WS_HR, parents=[parent])

    assert (configured / WS_HR / f"{parent.id}.json").is_file()
    assert parent_store.get_parent(
        workspace_id=WS_HR, parent_id=parent.id
    ).text == parent.text


def test_chunking_output_saves_and_reloads_end_to_end(store):
    """The real seam this half exists for: whatever ST-14 produces must
    store and come back. Uses chunking's own output rather than a
    hand-built Parent, so a field added there without a matching change
    here shows up as a failure instead of a silent drop."""
    import chunking

    result = chunking.chunk_document(
        "# Article 1\n\n" + ("Le contenu. " * 400), source_file="code.pdf"
    )

    parent_store.save_parents(
        workspace_id=WS_HR, parents=result.parents, base_path=store
    )

    assert result.parents
    for original in result.parents:
        loaded = parent_store.get_parent(
            workspace_id=WS_HR, parent_id=original.id, base_path=store
        )
        assert loaded == original
