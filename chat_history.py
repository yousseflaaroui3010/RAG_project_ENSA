"""S6 saved chat history business rules (law 09-08), ST-53 conversations.

Sits above db/repo.py exactly as workspaces.py and sync.py do: this module
owns the retention POLICY -- what a non-positive `chat_history_retention_days`
means, when a stored row counts as expired, and how a cutoff timestamp is
computed -- plus, since ST-53, how a conversation's title is derived and
what a valid new title is. It calls the plain operations in db/repo.py to
do the actual reads and writes. db/repo.py's own module docstring says it
carries no business logic; a cold review found four chat-history functions
there had grown exactly that, and this module is the fix.

ST-53: a person now has MANY conversations per workspace, each with its
own id, instead of one transcript per workspace that "New conversation"
deleted. Every function that names one conversation also names its owner,
and the repo layer matches both, so knowing someone else's id reaches
nothing.

Concurrency is NOT this module's job. The per-person lock and the
"is this still the live conversation?" check that stop a save from
resurrecting a concurrent delete (app.py Runtime) are in-process state;
this module has none and is safe to call from any thread as long as the
caller serializes its own writes the way Runtime does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from db import repo

# A title is a label in a list, not a transcript: long enough to recognise
# a question by ("Durée du préavis pour un cadre après cinq ans ?"), short
# enough to fit one line of the history panel. A module constant rather
# than a setting because nothing about a deployment should change it.
TITLE_MAX_CHARS = 80
_ELLIPSIS = "…"
_WHITESPACE = re.compile(r"\s+")


class InvalidTitleError(ValueError):
    """A rename that cannot be accepted: empty after trimming, or longer
    than `TITLE_MAX_CHARS`. The message is safe to show the person."""


@dataclass(frozen=True)
class StoredConversation:
    """One stored conversation, as far as the app needs to know it."""

    id: str
    workspace_id: str
    title: str | None
    payload: str


@dataclass(frozen=True)
class ConversationSummary:
    """One row of the history list: enough to show it and open it."""

    id: str
    title: str | None
    updated_at: str


def _cutoff(retention_days: int) -> str:
    """Rows with `updated_at` at or before this are expired.

    `retention_days == 0` (config.py's "keep nothing between restarts"
    switch) is folded into "everything up to right now" rather than
    special-cased: a real row's `updated_at` can never be later than the
    instant this runs, so a cutoff of "now" deletes every row that
    exists -- exactly what 0 means -- through the SAME single
    time-based primitive a positive window uses, rather than a second
    "delete everything" primitive that could drift out of step."""
    days = max(retention_days, 0)
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def title_from(question: str | None) -> str | None:
    """A conversation's automatic title: its first question, whitespace
    collapsed, cut to `TITLE_MAX_CHARS` with an ellipsis. None when there
    is no question to take it from (the list then shows "untitled")."""
    if question is None:
        return None
    text = _WHITESPACE.sub(" ", question).strip()
    if not text:
        return None
    if len(text) <= TITLE_MAX_CHARS:
        return text
    return text[: TITLE_MAX_CHARS - 1].rstrip() + _ELLIPSIS


def clean_title(title: str) -> str:
    """A title a person typed, normalised the same way as an automatic
    one -- or `InvalidTitleError`. Over-long is REFUSED rather than cut:
    a person who typed a title should see what they typed or be told why
    not, never find it silently shortened."""
    text = _WHITESPACE.sub(" ", title or "").strip()
    if not text:
        raise InvalidTitleError("a title cannot be empty.")
    if len(text) > TITLE_MAX_CHARS:
        raise InvalidTitleError(
            f"a title may be at most {TITLE_MAX_CHARS} characters; this one is {len(text)}."
        )
    return text


def save(
    *,
    conversation_id: str,
    user_id: str,
    workspace_id: str,
    payload: str,
    first_question: str | None,
    retention_days: int,
    db_path: str | Path | None = None,
) -> None:
    """Persist one conversation's whole transcript.

    `first_question` sets the title on the FIRST save only (the repo
    layer never overwrites a title on a later save), so a rename survives.

    `retention_days == 0` means nothing survives a restart: a save then
    DELETES any existing row for this conversation instead of writing one,
    so the setting is provably "stores nothing" rather than "stores it,
    just briefly"."""
    with repo.session(db_path) as conn:
        if retention_days <= 0:
            repo.delete_conversation(conn, conversation_id=conversation_id, user_id=user_id)
            return
        repo.upsert_conversation(
            conn,
            conversation_id=conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
            title=title_from(first_question),
            payload=payload,
            updated_at=repo.utc_now(),
        )


def load(
    *,
    conversation_id: str,
    user_id: str,
    retention_days: int,
    db_path: str | Path | None = None,
) -> StoredConversation | None:
    """This person's stored conversation with this id, or None.

    None too when the id belongs to someone else (the repo matches the
    owner), when retention is 0 (nothing is meant to survive a restart,
    so storage is not even queried), and when the row is OLDER than the
    retention window -- which is then deleted here, on read, so an old
    transcript nobody has swept yet can never come back into memory just
    because it was asked for before the next start-up sweep."""
    if retention_days <= 0:
        return None
    with repo.session(db_path) as conn:
        row = repo.get_conversation(conn, conversation_id=conversation_id, user_id=user_id)
        if row is None:
            return None
        if row["updated_at"] <= _cutoff(retention_days):
            repo.delete_conversation(conn, conversation_id=conversation_id, user_id=user_id)
            return None
        return StoredConversation(
            id=row["id"],
            workspace_id=row["workspace_id"],
            title=row["title"],
            payload=row["payload"],
        )


def list_for(
    *,
    user_id: str,
    workspace_id: str,
    retention_days: int,
    db_path: str | Path | None = None,
) -> list[ConversationSummary]:
    """This person's conversations in this workspace, newest first,
    excluding any past the retention window (the sweep removes those; the
    list must not show them in the meantime). Empty when retention is 0."""
    if retention_days <= 0:
        return []
    with repo.session(db_path) as conn:
        rows = repo.list_conversations(
            conn,
            user_id=user_id,
            workspace_id=workspace_id,
            newer_than=_cutoff(retention_days),
        )
    return [
        ConversationSummary(id=row["id"], title=row["title"], updated_at=row["updated_at"])
        for row in rows
    ]


def latest_id(
    *,
    user_id: str,
    workspace_id: str,
    retention_days: int,
    db_path: str | Path | None = None,
) -> str | None:
    """The id of this person's most recent conversation in this
    workspace, or None -- what the chat screen opens when no conversation
    is named in its address."""
    summaries = list_for(
        user_id=user_id,
        workspace_id=workspace_id,
        retention_days=retention_days,
        db_path=db_path,
    )
    return summaries[0].id if summaries else None


def id_taken(conversation_id: str, *, db_path: str | Path | None = None) -> bool:
    """Whether any stored conversation, anyone's, already has this id."""
    with repo.session(db_path) as conn:
        return repo.conversation_exists(conn, conversation_id=conversation_id)


def rename(
    *, conversation_id: str, user_id: str, title: str, db_path: str | Path | None = None
) -> bool:
    """Set this person's conversation's title. `InvalidTitleError` on a
    title that is empty or too long; False when the conversation is not
    theirs or does not exist; True when renamed."""
    cleaned = clean_title(title)
    with repo.session(db_path) as conn:
        changed = repo.rename_conversation(
            conn, conversation_id=conversation_id, user_id=user_id, title=cleaned
        )
    return changed > 0


def delete(*, conversation_id: str, user_id: str, db_path: str | Path | None = None) -> bool:
    """Drop one of this person's conversations. False if it was not
    theirs or did not exist."""
    with repo.session(db_path) as conn:
        return repo.delete_conversation(
            conn, conversation_id=conversation_id, user_id=user_id
        ) > 0


def delete_for_user(*, user_id: str, db_path: str | Path | None = None) -> int:
    """Every stored conversation belonging to one person, across every
    workspace -- law 09-08's "Delete my saved history" and admin
    "sign out everywhere" both call this. Returns the row count deleted."""
    with repo.session(db_path) as conn:
        return repo.delete_conversations_for_user(conn, user_id=user_id)


def sweep_expired(*, retention_days: int, db_path: str | Path | None = None) -> int:
    """Every conversation past the retention window, gone (app.py
    start-up sweep). `retention_days == 0` clears the table outright,
    through the same cutoff-based primitive a positive window uses."""
    with repo.session(db_path) as conn:
        return repo.delete_conversations_older_than(conn, cutoff=_cutoff(retention_days))
