"""F-15 answer feedback: thumbs up/down plus an optional comment, stored
per answer and reviewable on the Reports screen (PRD F-15, UX spec S1/S3).

Mirrors workspaces.py's split: domain rules and validation live here,
db/repo.py stays raw parameterised SQL. `ui/conversation.py`'s in-memory
`Message.id` (a uuid4 stamped when the message is built) is the "stable
id" this module keys feedback on -- see that field's docstring for why one
was added instead of addressing a message by its position in the
transcript.

WHY REFUSAL IS INCLUDED, NOT ONLY ANSWER. A refusal is a first-class
outcome in this product (ui/conversation.py's own docstring, design
principle 2) and it can be wrong too -- Sanad can refuse to answer a
question the corpus genuinely covers, and that is exactly the kind of
miss an operator should be able to flag. Nothing else -- USER,
CLARIFICATION, ERROR, INTERRUPTED -- carries a citable claim or a search
outcome to react to, so none of them is eligible; see
FEEDBACK_ELIGIBLE_KINDS below, the one place this rule lives.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from config import get_settings
from db import repo
from ui.conversation import Message, MessageKind

FEEDBACK_ELIGIBLE_KINDS = (MessageKind.ANSWER, MessageKind.REFUSAL)


class FeedbackError(Exception):
    """Base class for feedback domain errors. A route catches this (or a
    subclass) instead of letting a bad request reach db/repo.py or turn
    into an unhandled 500."""


class InvalidVerdictError(FeedbackError):
    def __init__(self, verdict: str):
        self.verdict = verdict
        super().__init__(f"verdict must be 'up' or 'down' (got {verdict!r})")


class CommentTooLongError(FeedbackError):
    def __init__(self, length: int, max_chars: int):
        self.length = length
        self.max_chars = max_chars
        super().__init__(
            f"comment is {length} characters, over the {max_chars} limit"
        )


class UnknownAnswerError(FeedbackError):
    """No ANSWER or REFUSAL message with this id is in this conversation
    right now -- a stale page from before New conversation reset the
    transcript, a workspace switch, or a tampered request. Never a bug on
    its own: `Conversation` is in-memory only (PRD section 6), so a
    message id from an earlier server run is expected to miss."""

    def __init__(self, message_id: str):
        self.message_id = message_id
        super().__init__(
            f"no answer found for id {message_id!r} in this conversation"
        )


def _find(
    messages: Sequence[Message], message_id: str
) -> tuple[int, Message] | None:
    for index, message in enumerate(messages):
        if message.id == message_id and message.kind in FEEDBACK_ELIGIBLE_KINDS:
            return index, message
    return None


def _question_for(messages: Sequence[Message], answer_index: int) -> str:
    """The question that produced this answer: the USER message directly
    before it in the transcript. `Conversation.begin` always appends the
    user's message before the run that will answer it, and `settle`
    appends exactly one message per finished run (ui/conversation.py), so
    the message right before an ANSWER/REFUSAL is that question -- except
    for a message built by hand outside that flow (a test fixture calling
    `_show`), where there may be no preceding USER message at all; that
    case returns "" rather than guessing."""
    if answer_index == 0:
        return ""
    previous = messages[answer_index - 1]
    return previous.text if previous.kind is MessageKind.USER else ""


def submit_feedback(
    *,
    messages: Sequence[Message],
    workspace_id: str,
    message_id: str,
    verdict: str,
    comment: str | None,
    db_path: str | Path | None = None,
) -> None:
    """Validate and store one verdict (plus optional comment) for one
    answer or refusal.

    IDEMPOTENT: a second call with the same `message_id` UPDATES the same
    row (db.repo.upsert_answer_feedback's ON CONFLICT), so clicking
    Helpful then Not helpful on one answer leaves exactly one row carrying
    the latest verdict, never two.

    Raises InvalidVerdictError, CommentTooLongError or UnknownAnswerError
    for anything a caller typed or tampered wrong -- never anything else,
    so a route can catch FeedbackError alone and never needs to turn this
    into a 500."""
    if verdict not in ("up", "down"):
        raise InvalidVerdictError(verdict)
    normalized_comment = (comment or "").strip() or None
    if normalized_comment is not None:
        max_chars = get_settings().feedback_comment_max_chars
        if len(normalized_comment) > max_chars:
            raise CommentTooLongError(len(normalized_comment), max_chars)
    found = _find(messages, message_id)
    if found is None:
        raise UnknownAnswerError(message_id)
    index, message = found
    with repo.session(db_path) as conn:
        repo.upsert_answer_feedback(
            conn,
            workspace_id=workspace_id,
            answer_key=message_id,
            question=_question_for(messages, index),
            answer_text=message.text,
            verdict=verdict,
            comment=normalized_comment,
        )


def verdicts_for(
    messages: Sequence[Message], *, db_path: str | Path | None = None
) -> dict[str, str]:
    """`{message.id: verdict}` for every message in this transcript that
    already carries feedback -- what `_conversation.html` reads to render
    "Thanks -- feedback saved" and `aria-pressed` on the matching button
    instead of a fresh, unanswered form."""
    keys = [m.id for m in messages if m.kind in FEEDBACK_ELIGIBLE_KINDS]
    if not keys:
        return {}
    with repo.session(db_path) as conn:
        rows = repo.get_answer_feedback_by_keys(conn, keys)
    return {row["answer_key"]: row["verdict"] for row in rows}
