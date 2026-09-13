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
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import workspaces
from db import repo


def format_when(value: str | None) -> str:
    """A stored ISO-8601 timestamp as a person reads it: "12 Sep 2026, 14:12 UTC".

    Every timestamp this app stores comes from `repo.utc_now()` and carries an
    offset, so it is shown in UTC and says so, rather than silently shifted
    into whatever zone the server happens to run in. A value that is not a
    timestamp is shown as it is: a display filter must never hide data it
    could not parse. Nothing at all becomes a dash."""
    if not value:
        return "\u2014"
    try:
        moment = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    if moment.tzinfo is None:
        return f"{moment.day} {moment:%b %Y, %H:%M}"
    moment = moment.astimezone(UTC)
    return f"{moment.day} {moment:%b %Y, %H:%M} UTC"

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
    # F-12: no workspace is selected (the shell's "Let Sanad choose" option)
    # and nothing has been asked in this pseudo-conversation yet. Distinct
    # from NO_DOCUMENTS -- there is no single active workspace whose
    # documents could be missing -- and only reachable pre-first-question;
    # once a question is asked `state_for` falls through to EMPTY/
    # CONVERSATION exactly as the normal path does, because at that point
    # there is a real transcript to show regardless of routing.
    ROUTING = "routing"


# F-12. The shell's workspace selector (base.html) offers this as an extra
# `<option>`, ONLY when two or more workspaces exist ("let Sanad choose"
# has nothing to choose between otherwise) -- `app.py::_active` treats it
# as "no workspace selected" rather than as an unknown id to fall back
# from. Mirrored as a literal in `ui/templates/base.html`'s `<option
# value="...">`: one Python constant plus one template literal is the
# second copy the core law allows without an abstraction; a third use
# anywhere should read this constant instead of typing the string again.
ROUTE_SENTINEL = "__route__"


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
    routing: bool = False,
) -> ScreenState:
    """The one value the template branches on.

    Order matters and it is the spec's: no workspace outranks no
    documents, which outranks an empty transcript. A workspace that does
    not exist cannot be missing documents.

    `routing` (F-12) is true when the shell has no active workspace AND at
    least one exists -- "let Sanad choose" is selected. It outranks
    NO_DOCUMENTS for the same reason NO_WORKSPACE does: `documents` is
    always `[]` in routing mode (there is no single workspace to read it
    from), and that must not be read as "the workspace has nothing
    synced". It does NOT outrank a real transcript: once a question has
    been asked, routing mode is done deciding and the ordinary EMPTY/
    CONVERSATION rule below is the truthful one to show."""
    if not options:
        return ScreenState.NO_WORKSPACE
    if routing:
        return ScreenState.CONVERSATION if has_messages else ScreenState.ROUTING
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
