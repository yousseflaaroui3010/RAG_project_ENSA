"""Which state the S1 screen is in, decided in Python not in a template.

UX spec 6.3 gives S1 three named states and one of them has two shapes:

* **Empty**, with documents  -- three sample questions, one line saying
  every answer carries its sources.
* **Empty**, with NO documents -- "the sample questions are replaced by a
  pointer to S2 and the input is disabled with the reason shown inline".
  This is also section 11's "Empty workspace" row.
* **Loading** -- stage hints, input disabled with a visible reason, cancel.
* **Error** -- `ErrorPanel` with retry, no partial answer as final.

And UX spec 4 adds one above all of them: no workspace EXISTS at all, in
which case "navigation to S1 is disabled with a tooltip explaining why,
and S2 is the landing screen" (acceptance criterion 1).

Deciding this here rather than with `{% if %}` chains in the template is
the point of the module. A template that asks four questions about three
lists has the rule spread across markup nobody can unit-test; a screen
state a test can assert on is one value.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import workspaces
from db import repo

# `document.status` values that mean the file is really in the index and
# can be answered from. db/schema.sql allows four; the other three are
# 'failed', 'skipped' and 'removed', and a workspace holding nothing but
# those has nothing to answer WITH. Counting them would put the chat input
# in front of an operator whose every question can only be refused.
_ANSWERABLE = "active"

# UX spec 6.3's own words for the line under the sample questions.
SOURCES_PROMISE = "Every answer carries the sources it was written from."


class ScreenState(StrEnum):
    NO_WORKSPACE = "no_workspace"
    NO_DOCUMENTS = "no_documents"
    EMPTY = "empty"
    CONVERSATION = "conversation"


@dataclass(frozen=True)
class WorkspaceOption:
    """One entry in the shell's workspace selector (UX spec 4).

    `legal_flag` rides along because the selector shows "a small
    persistent marker" when it is set, and because the S1 disclaimer line
    (F-09) is decided from the same flag."""

    id: str
    name: str
    legal_flag: bool


def workspace_options(*, db_path: str | Path | None = None) -> list[WorkspaceOption]:
    return [
        WorkspaceOption(id=ws.id, name=ws.name, legal_flag=ws.legal_flag)
        for ws in workspaces.list_workspaces(db_path=db_path)
    ]


def answerable_documents(
    workspace_id: str, *, db_path: str | Path | None = None
) -> list[str]:
    """File names this workspace can actually answer from, sorted.

    `repo.list_documents` already orders by file_name and already scopes
    the read to one workspace (F-01), so there is no ordering or filtering
    rule reimplemented here beyond the status."""
    with repo.session(db_path) as conn:
        return [
            row["file_name"]
            for row in repo.list_documents(conn, workspace_id)
            if row["status"] == _ANSWERABLE
        ]


def sample_questions(file_names: list[str]) -> list[str]:
    """Three starting points, drawn from the active workspace (UX 6.3).

    DRAWN, not invented: each one names a file this workspace really
    holds. That is the whole design constraint and it is a tight one --
    Sanad has no model call to spare on the empty state, and a hardcoded
    list of French labour-law questions (which is what the React reference
    ships, `ChatScreen.tsx:76-79`) is wrong the moment the active
    workspace is the technical manuals one. A file name is the only thing
    about a workspace that is both free to read and certainly true.

    PARKED, with an owner: these are starting points, not good questions.
    The good ones are ST-19's golden set -- reviewed, French, and written
    against this corpus -- and when it exists this function should read
    three from it and fall back to the file names for a workspace the
    golden set does not cover.

    Fewer than three documents yields fewer than three questions rather
    than padding the list; two real prompts beat three with a filler."""
    return [f'What does "{name}" cover?' for name in file_names[:3]]


def state_for(
    *,
    options: list[WorkspaceOption],
    documents: list[str],
    has_messages: bool,
) -> ScreenState:
    """The one value the template branches on.

    Order matters and it is the spec's: no workspace outranks no
    documents, which outranks an empty transcript. A workspace that does
    not exist cannot be missing documents."""
    if not options:
        return ScreenState.NO_WORKSPACE
    if not documents:
        return ScreenState.NO_DOCUMENTS
    if not has_messages:
        return ScreenState.EMPTY
    return ScreenState.CONVERSATION


# UX spec 6.3 and PRD section 8 both require the disabled input to say WHY.
# Two reasons exist and they are different sentences on purpose: one is
# fixed by adding documents, the other by waiting.
NO_DOCUMENTS_REASON = (
    "This workspace has no synced documents yet, so there is nothing to "
    "answer from. Add a folder and run Sync on the Workspaces screen."
)
BUSY_REASON = "Sanad is answering your last question."
