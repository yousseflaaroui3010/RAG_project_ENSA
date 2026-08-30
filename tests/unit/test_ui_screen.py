"""Which state the S1 screen is in (ST-27, UX spec 6.3 and 4).

The order these are resolved in is the spec's, and it is the part worth a
test: a workspace that does not exist cannot be missing documents, so
"no workspace" has to outrank "no documents" or an operator with an empty
database is told to run Sync on a workspace they never created.
"""

from __future__ import annotations

import pytest

import workspaces
from db import repo
from ui.screen import (
    ScreenState,
    WorkspaceOption,
    answerable_documents,
    sample_questions,
    state_for,
    workspace_options,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "sanad.db"
    repo.ensure_schema(path)
    return path


def _workspace(db, *, legal_flag: bool = False) -> str:
    """A real workspace row, and its real id.

    The id is whatever `workspaces.create_workspace` minted rather than a
    constant this file chose: `document.workspace_id` is a foreign key, so
    a made-up id would either fail the insert or, worse, register
    documents against a workspace that does not exist."""
    return workspaces.create_workspace(
        name="HR", folder_path="/tmp/hr", legal_flag=legal_flag, db_path=db
    ).id


def _document(db, workspace_id: str, name: str, status: str = "active") -> None:
    with repo.session(db) as conn:
        repo.insert_document(
            conn,
            workspace_id=workspace_id,
            file_name=name,
            file_type="pdf",
            content_hash="hash-" + name,
            page_count=1,
            status=status,
        )


# --- the ordering rule ------------------------------------------------


def test_no_workspace_outranks_no_documents():
    assert (
        state_for(options=[], documents=[], has_messages=False)
        is ScreenState.NO_WORKSPACE
    )


def test_a_workspace_with_no_documents_is_its_own_state():
    """UX spec 6.3: the sample questions are replaced by a pointer to S2
    and the input is disabled with the reason inline. That is a different
    screen from an empty transcript, not a variation of it."""
    option = WorkspaceOption(id="ws", name="HR", legal_flag=False)
    assert (
        state_for(options=[option], documents=[], has_messages=False)
        is ScreenState.NO_DOCUMENTS
    )


def test_documents_but_no_messages_is_the_empty_state():
    option = WorkspaceOption(id="ws", name="HR", legal_flag=False)
    assert (
        state_for(options=[option], documents=["a.pdf"], has_messages=False)
        is ScreenState.EMPTY
    )


def test_a_transcript_wins_over_the_empty_state():
    option = WorkspaceOption(id="ws", name="HR", legal_flag=False)
    assert (
        state_for(options=[option], documents=["a.pdf"], has_messages=True)
        is ScreenState.CONVERSATION
    )


# --- what counts as something to answer from --------------------------


def test_only_active_documents_count_as_something_to_answer_from(db):
    """A workspace holding nothing but failed and skipped files has
    nothing to answer WITH. Counting those would put a working chat input
    in front of an operator whose every question can only be refused --
    and Sanad would be blamed for the refusal, not the sync."""
    ws = _workspace(db)
    _document(db, ws, "broken.pdf", status="failed")
    _document(db, ws, "scan.pdf", status="skipped")
    assert answerable_documents(ws, db_path=db) == []

    _document(db, ws, "code.pdf", status="active")
    assert answerable_documents(ws, db_path=db) == ["code.pdf"]


def test_the_selector_lists_every_workspace_with_its_legal_flag(db):
    """UX spec 4: the selector shows the name and, when the legal flag is
    set, a small persistent marker. The flag has to travel with the
    option or the marker is decided somewhere else."""
    _workspace(db, legal_flag=True)
    options = workspace_options(db_path=db)
    assert [(o.name, o.legal_flag) for o in options] == [("HR", True)]


# --- sample questions -------------------------------------------------


def test_sample_questions_name_files_this_workspace_really_holds():
    """UX spec 6.3: "three sample questions drawn from the active
    workspace". DRAWN -- each names a real file. A hardcoded list of
    French labour-law questions (which is what the React reference ships)
    is wrong the moment the active workspace is the manuals one."""
    questions = sample_questions(["code-du-travail.pdf", "guide-cnss.txt"])
    assert len(questions) == 2
    assert all("code-du-travail.pdf" in q or "guide-cnss.txt" in q for q in questions)


def test_three_is_the_ceiling_not_a_quota():
    """Fewer than three documents yields fewer than three questions.
    Padding to three would mean inventing one."""
    assert len(sample_questions(["a.pdf", "b.pdf", "c.pdf", "d.pdf"])) == 3
    assert sample_questions([]) == []
