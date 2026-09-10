"""Model-backed clarification and query splitting (ST-22)."""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any

from agent.chat import ChatModel
from agent.ports import Clarify, Rewrite
from agent.prompts import load_prompt
from config import get_settings

QUERY_PLANNER_PROMPT_ID = "query-planner"


class QueryPlannerReplyError(Exception):
    """The model returned neither one clarification nor usable searches."""


@dataclass(frozen=True)
class _QueryPlan:
    clarification: str | None
    queries: tuple[str, ...]


@dataclass(frozen=True)
class ClarificationContext:
    """The first question and the one the assistant asked about it."""

    original: str
    asked: str


def clarified_question(context: ClarificationContext, reply: str) -> str:
    """Keep the exchange as data without letting a value forge a boundary."""
    return json.dumps(
        {
            "original_question": context.original,
            "clarifying_question": context.asked,
            "clarification_reply": reply,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _reply_error(reply: str, reason: str) -> QueryPlannerReplyError:
    return QueryPlannerReplyError(
        f"the query planner replied {reply[:160]!r}: {reason}. This is not "
        "being treated as a clear or ambiguous question because either guess "
        f"could change the user's meaning. Check the {QUERY_PLANNER_PROMPT_ID!r} prompt."
    )


def _parse_plan(reply: str) -> _QueryPlan:
    try:
        value: Any = json.loads(reply)
    except (TypeError, json.JSONDecodeError) as exc:
        raise _reply_error(reply, "the reply is not one JSON object") from exc
    if not isinstance(value, dict) or set(value) != {"clarification", "queries"}:
        raise _reply_error(reply, "the object must contain only clarification and queries")

    clarification = value["clarification"]
    queries = value["queries"]
    if not isinstance(queries, list) or any(not isinstance(item, str) for item in queries):
        raise _reply_error(reply, "queries must be a JSON list of strings")
    cleaned_queries = tuple(item.strip() for item in queries)

    if clarification is None:
        if not cleaned_queries or any(not item for item in cleaned_queries):
            raise _reply_error(reply, "a clear question needs one or more non-blank queries")
        return _QueryPlan(clarification=None, queries=cleaned_queries)

    if not isinstance(clarification, str) or not clarification.strip():
        raise _reply_error(reply, "clarification must be null or one non-blank string")
    if cleaned_queries:
        raise _reply_error(reply, "an ambiguous question cannot also carry search queries")
    return _QueryPlan(clarification=clarification.strip(), queries=())


class _QueryPlanning:
    """Share one paid plan between the graph's two existing ST-22 ports."""

    def __init__(self, model: ChatModel) -> None:
        self._model = model
        self._prompt = load_prompt(QUERY_PLANNER_PROMPT_ID)
        self._pending = threading.local()

    def _complete(self, question: str, summary: str) -> _QueryPlan:
        user = self._prompt.render(
            question=question,
            summary=json.dumps(summary, ensure_ascii=False) if summary else "(none)",
            max_sub_queries=str(get_settings().max_sub_queries),
        )
        return _parse_plan(self._model.complete(self._prompt.system, user))

    def clarify(self, question: str, summary: str) -> str | None:
        plan = self._complete(question, summary)
        self._pending.value = (question, summary, plan) if plan.clarification is None else None
        return plan.clarification

    def rewrite(self, question: str, summary: str) -> tuple[str, ...]:
        pending = getattr(self._pending, "value", None)
        self._pending.value = None
        if pending is not None and pending[:2] == (question, summary):
            plan = pending[2]
        else:
            plan = self._complete(question, summary)
        if plan.clarification is not None:
            raise _reply_error(
                plan.clarification,
                "a resumed clarification flow asked a second question instead of searching",
            )
        return plan.queries


def build_query_planning(model: ChatModel) -> tuple[Clarify, Rewrite]:
    """Build the paired ports that share one model decision per question."""
    planning = _QueryPlanning(model)
    return planning.clarify, planning.rewrite
