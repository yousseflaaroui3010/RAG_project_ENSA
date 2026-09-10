"""Model-backed in-session conversation summary (ST-25)."""

from __future__ import annotations

import json
import unicodedata

from agent.chat import ChatModel
from agent.ports import Summarize
from agent.prompts import load_prompt
from agent.state import SessionMemory
from config import get_settings

SESSION_SUMMARIZER_PROMPT_ID = "session-summarizer"


class SessionSummaryReplyError(Exception):
    """Completed turns produced no memory for the next question."""


class SessionSummaryInputTooLargeError(Exception):
    """The unsummarized memory is too large to send safely to the model."""


def _has_visible_text(value: str) -> bool:
    """True when text contains more than whitespace or format controls."""
    return any(
        not character.isspace() and unicodedata.category(character) != "Cf"
        for character in value
    )


def build_summarize(model: ChatModel) -> Summarize:
    """Build F-07's summary port from the configured chat model."""
    prompt = load_prompt(SESSION_SUMMARIZER_PROMPT_ID)

    def summarize(memory: SessionMemory) -> str:
        settings = get_settings()
        previous = memory.summary.strip()
        if memory.summary and not _has_visible_text(previous):
            raise SessionSummaryReplyError(
                "the saved session summary is blank or invisible. The earlier "
                "context was not discarded."
            )
        if len(previous) > settings.session_summary_max_chars:
            raise SessionSummaryReplyError(
                f"the saved session summary has {len(previous)} characters and the "
                f"configured limit is {settings.session_summary_max_chars}. The "
                "earlier context was not discarded."
            )
        if not memory.turns:
            return previous
        payload = json.dumps(
            {
                "previous_summary": previous,
                "new_completed_turns": [
                    {"question": turn.question, "answer": turn.answer}
                    for turn in memory.turns
                ],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(payload) > settings.session_memory_input_max_chars:
            raise SessionSummaryInputTooLargeError(
                f"the pending session memory has {len(payload)} characters and the "
                "configured limit is "
                f"{settings.session_memory_input_max_chars}. Start a new "
                "conversation instead of sending an unbounded model request."
            )
        user = prompt.render(
            history=payload,
            max_summary_chars=str(settings.session_summary_max_chars),
        )
        summary = model.complete(prompt.system, user).strip()
        if not _has_visible_text(summary):
            raise SessionSummaryReplyError(
                "the session summarizer returned a blank or invisible reply for completed "
                f"history. Check the {SESSION_SUMMARIZER_PROMPT_ID!r} prompt; "
                "the earlier context was not discarded."
            )
        if len(summary) > settings.session_summary_max_chars:
            raise SessionSummaryReplyError(
                f"the session summarizer returned {len(summary)} characters and "
                f"the configured limit is {settings.session_summary_max_chars}. "
                "The oversized reply was not saved as memory."
            )
        return summary

    return summarize
