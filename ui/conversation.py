"""What the S1 chat screen renders, as plain objects.

The templates get dataclasses, never an `Answer` and never a `Run`. That
split is doing real work rather than tidying: a Jinja template cannot be
unit-tested cheaply, so anything with a rule in it -- which variant, which
spans are highlighted, whether the disclaimer line appears -- is decided
here where a test can reach it, and the template only loops and escapes.

UX spec 6.2 fixes FOUR message variants: user, answer, refusal,
clarification. This module adds two more render kinds that are NOT message
variants and are not styled as one:

* `ERROR` is UX spec 5's `ErrorPanel` -- "plain message, the exact failing
  value, a fix hint, a retry action". Section 11 routes two failures here:
  "answering service unreachable" and any other break.
* `INTERRUPTED` is section 11's "answer interrupted mid-generation".

A REFUSAL IS NOT AN ERROR and the two must never share a style. Design
principle 2: "A refusal is a first-class answer ... If refusals look like
errors, users learn to distrust the honest path, which is the behaviour
the product exists to demonstrate." The refusal variant is bordered in
`notice`; the error panel is the only thing that gets `danger`.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agent.querying import ClarificationContext
from agent.state import Answer, AnswerKind, Source, Turn
from config import get_settings
from ui.routing import RouteCandidate
from ui.runs import Run, RunCancelled, find_span
from vector_store import SearchHit


class MessageKind(StrEnum):
    USER = "user"
    ANSWER = "answer"
    REFUSAL = "refusal"
    CLARIFICATION = "clarification"
    ERROR = "error"
    INTERRUPTED = "interrupted"
    # F-12: the confirmation-before-answer bubble. One kind for both
    # shapes it can take -- a ranked proposal (`route_candidates` non-
    # empty) and the plain "nothing matched" message (empty) -- because
    # both are the same event from the operator's point of view: Sanad
    # would not answer without asking first.
    ROUTE_PROPOSAL = "route_proposal"


# The three that come out of the agent, mapped one for one. A dict rather
# than an `if` chain so that a fourth `AnswerKind` is a KeyError here --
# loud, at the first render -- instead of quietly falling through to a
# default variant that renders an answer's styling around a refusal.
_VARIANT: Mapping[AnswerKind, MessageKind] = {
    AnswerKind.ANSWER: MessageKind.ANSWER,
    AnswerKind.REFUSAL: MessageKind.REFUSAL,
    AnswerKind.CLARIFICATION: MessageKind.CLARIFICATION,
}


@dataclass(frozen=True)
class Segment:
    """One run of section text, cited or not.

    The passage viewer is built from these instead of from HTML with
    `<mark>` spliced in, because splicing means building markup in Python
    and marking it safe, and the day a section contains a `<` that is an
    injection. Jinja escapes each segment; the template decides which ones
    get a `<mark>`."""

    text: str
    cited: bool

    def to_dict(self) -> dict[str, Any]:
        return {"text": self.text, "cited": self.cited}

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> Segment:
        return Segment(text=str(data["text"]), cited=bool(data["cited"]))


@dataclass(frozen=True)
class Passage:
    """One section the answer was written from, ready to display.

    `segments` already carries the highlight. `highlighted` says whether
    any span was located at all, so the viewer can state plainly that it
    is showing the whole section without a marked span rather than let
    the reader assume the highlight is missing because nothing matched."""

    file_name: str
    section_label: str | None
    segments: tuple[Segment, ...]
    highlighted: bool

    @property
    def text(self) -> str:
        return "".join(segment.text for segment in self.segments)

    def to_dict(self) -> dict[str, Any]:
        return {
            "file_name": self.file_name,
            "section_label": self.section_label,
            "segments": [segment.to_dict() for segment in self.segments],
            "highlighted": self.highlighted,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> Passage:
        return Passage(
            file_name=str(data["file_name"]),
            section_label=data["section_label"],
            segments=tuple(Segment.from_dict(item) for item in data["segments"]),
            highlighted=bool(data["highlighted"]),
        )


@dataclass(frozen=True)
class SourceCard:
    """One citation, and everything behind it (UX spec 5).

    `passages` is a LIST because `_sources_for` de-duplicates by file and
    section label, and one long article can be split across two parents
    that both carry the label "Article 235". Showing only the first would
    hide half of what the model read. Ordinary case: one passage."""

    index: int
    file_name: str
    section_label: str | None
    passages: tuple[Passage, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "file_name": self.file_name,
            "section_label": self.section_label,
            "passages": [passage.to_dict() for passage in self.passages],
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> SourceCard:
        return SourceCard(
            index=int(data["index"]),
            file_name=str(data["file_name"]),
            section_label=data["section_label"],
            passages=tuple(Passage.from_dict(item) for item in data["passages"]),
        )


@dataclass(frozen=True)
class ErrorDetail:
    """UX spec 5: "`ErrorPanel` always shows the offending value ... Never
    a bare 'something went wrong'"."""

    sentence: str
    attempted: str
    value: str
    hint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "sentence": self.sentence,
            "attempted": self.attempted,
            "value": self.value,
            "hint": self.hint,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> ErrorDetail:
        return ErrorDetail(
            sentence=str(data["sentence"]),
            attempted=str(data["attempted"]),
            value=str(data["value"]),
            hint=str(data["hint"]),
        )


@dataclass(frozen=True)
class Message:
    kind: MessageKind
    text: str
    sources: tuple[SourceCard, ...] = ()
    searched: tuple[str, ...] = ()
    # F-10: distinct file names any search step consulted, first-seen order
    # (agent.trace.Trace.files_consulted, already de-duplicated there).
    files_consulted: tuple[str, ...] = ()
    retries: int = 0
    disclaimer: bool = False
    error: ErrorDetail | None = None
    # UX spec 6.2 allows concrete reply buttons where they can be offered.
    # ST-22 currently generates one free-text question, not reply choices,
    # so this stays empty rather than being filled with guesses.
    choices: tuple[str, ...] = ()
    # F-10: true only for a message built from a real `Answer.trace` by
    # `message_for`. USER, ERROR and INTERRUPTED messages are built by hand
    # elsewhere in this module and never carry one; a future message
    # restored without its trace (e.g. from persisted session memory) would
    # also default to False here. The template renders no disclosure at
    # all rather than an empty one when this is False.
    has_trace: bool = False
    # F-12 ROUTE_PROPOSAL only. `route_question` is the exact text every
    # confirm button resubmits (the original question, verbatim -- never
    # re-typed by the operator, so a button click cannot ask something
    # different from what was proposed). `route_candidates` is ranked best
    # first and empty means no workspace had any hit at all.
    route_question: str = ""
    route_candidates: tuple[RouteCandidate, ...] = ()
    # F-15. The stable id `ui/feedback.py` keys a stored verdict on:
    # `db.repo.upsert_answer_feedback`'s ON CONFLICT target is this value,
    # not a message's position in `Conversation.messages`, because a
    # position shifts (a new conversation empties the list; a restored
    # session could reorder it) while this does not. A `uuid4` minted once
    # per message HERE, at construction, rather than looked up from
    # anywhere persistent -- there is nothing persistent to look it up
    # from, since `Conversation` lives only in process memory (PRD section
    # 6, single user on one machine). Every message gets one, not only
    # ANSWER/REFUSAL, so the dataclass has one id field and not a second,
    # optional one; `ui/feedback.py` is what restricts feedback to the two
    # kinds a citable claim can attach to.
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    # S6, INTERRUPTED only: `text` is the model's own half-written answer
    # (rendered like an answer, marked incomplete, no sources), not
    # Sanad's fixed INTERRUPTED_TEXT sentence.
    partial: bool = False

    def to_dict(self) -> dict[str, Any]:
        """S6 saved chat history: this message, JSON-safe, for `Conversation.to_payload`.

        `kind` is written as its plain string value (StrEnum), never the
        enum repr, so the stored row is ordinary JSON a human or another
        tool could read. `id` is written as-is rather than regenerated --
        it is F-15's feedback key, and a restored message must keep the
        same one or a stored verdict silently stops matching anything."""
        return {
            "kind": self.kind.value,
            "text": self.text,
            "sources": [card.to_dict() for card in self.sources],
            "searched": list(self.searched),
            "files_consulted": list(self.files_consulted),
            "retries": self.retries,
            "disclaimer": self.disclaimer,
            "error": self.error.to_dict() if self.error is not None else None,
            "choices": list(self.choices),
            "has_trace": self.has_trace,
            "route_question": self.route_question,
            "route_candidates": [
                {
                    "workspace_id": candidate.workspace_id,
                    "name": candidate.name,
                    "score": candidate.score,
                }
                for candidate in self.route_candidates
            ],
            "id": self.id,
            "partial": self.partial,
        }

    @staticmethod
    def from_dict(data: Mapping[str, Any]) -> Message:
        """The inverse of `to_dict`. Raises (KeyError, ValueError, ...) on
        anything unreadable -- a missing field, an unknown `kind` -- so the
        caller (`app.py::Runtime._load_conversation`) can catch it and
        start an empty conversation rather than crash the chat screen."""
        error_data = data.get("error")
        return Message(
            kind=MessageKind(data["kind"]),
            text=str(data["text"]),
            sources=tuple(
                SourceCard.from_dict(item) for item in data.get("sources", ())
            ),
            searched=tuple(data.get("searched", ())),
            files_consulted=tuple(data.get("files_consulted", ())),
            retries=int(data.get("retries", 0)),
            disclaimer=bool(data.get("disclaimer", False)),
            error=ErrorDetail.from_dict(error_data) if error_data is not None else None,
            choices=tuple(data.get("choices", ())),
            has_trace=bool(data.get("has_trace", False)),
            route_question=str(data.get("route_question", "")),
            route_candidates=tuple(
                RouteCandidate(
                    workspace_id=str(candidate["workspace_id"]),
                    name=str(candidate["name"]),
                    score=float(candidate["score"]),
                )
                for candidate in data.get("route_candidates", ())
            ),
            id=str(data["id"]),
            partial=bool(data.get("partial", False)),
        )


def merge_spans(spans: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    """Overlapping cited spans, collapsed into disjoint ones.

    Children overlap by `chunk_child_overlap_chars` (100) BY DESIGN, so
    two chunks of one section routinely share text. Without this the
    template would open a second `<mark>` inside an open one and the
    highlight would run to the end of the section."""
    ordered = sorted(span for span in spans if span[1] > span[0])
    merged: list[tuple[int, int]] = []
    for start, end in ordered:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def segments_for(text: str, spans: Sequence[tuple[int, int]]) -> tuple[Segment, ...]:
    """Cut one section into cited and uncited runs, in order.

    Empty runs are dropped so a highlight at the very start does not emit
    a leading blank segment for the template to render as a stray gap."""
    out: list[Segment] = []
    cursor = 0
    for start, end in merge_spans(spans):
        if start > cursor:
            out.append(Segment(text[cursor:start], cited=False))
        out.append(Segment(text[start:end], cited=True))
        cursor = end
    if cursor < len(text):
        out.append(Segment(text[cursor:], cited=False))
    return tuple(out)


class UncitableSourceError(Exception):
    """An answer cited a source with no passage behind it.

    This is a WIRING BUG, not a condition a user can cause, and it is
    raised rather than rendered because a source card that opens onto
    nothing is the one thing F-03's source line promises cannot happen.

    It should be unreachable: `answer.sources` is built by `_sources_for`
    from exactly the tuple `write_answer` was handed, and `Run` captures
    that same tuple at that same call. If it ever fires, the two have
    come apart and the answer is no longer safe to show."""


def _cards_for(
    sources: Sequence[Source],
    cited: Sequence[SearchHit],
    parents: Mapping[str, str],
) -> tuple[SourceCard, ...]:
    """One card per source, carrying the sections it was written from."""
    cards: list[SourceCard] = []
    for index, source in enumerate(sources):
        # Spans, grouped by the section they were found in. Two chunks of
        # one article become two highlights in one passage, not two
        # passages.
        spans: dict[str, list[tuple[int, int]]] = {}
        for hit in cited:
            if hit.source_file != source.file_name:
                continue
            if hit.section_label != source.section_label:
                continue
            section = parents.get(hit.parent_id)
            if section is None:
                continue
            found = find_span(section, hit.chunk_text)
            spans.setdefault(hit.parent_id, [])
            if found is not None:
                spans[hit.parent_id].append(found)
        if not spans:
            raise UncitableSourceError(
                f"the answer cites {source.file_name!r} "
                f"({source.section_label!r}) and no section behind it was "
                f"recorded. agent/nodes.py::make_answer builds the source "
                f"list and the writer's passages from ONE tuple, so this "
                f"means ui/runs.py captured a different one."
            )
        passages = tuple(
            Passage(
                file_name=source.file_name,
                section_label=source.section_label,
                segments=segments_for(parents[parent_id], found),
                highlighted=bool(found),
            )
            for parent_id, found in spans.items()
        )
        cards.append(
            SourceCard(
                index=index,
                file_name=source.file_name,
                section_label=source.section_label,
                passages=passages,
            )
        )
    return tuple(cards)


def message_for(
    answer: Answer,
    cited: Sequence[SearchHit] = (),
    parents: Mapping[str, str] | None = None,
) -> Message:
    """One `Answer` as one rendered message.

    UX spec 6.2 puts the line "directly under the answer body, above the
    source cards", and criterion 3 makes its absence just as binding: an
    unflagged workspace shows none anywhere."""
    return Message(
        kind=_VARIANT[answer.kind],
        text=answer.text,
        sources=_cards_for(answer.sources, cited, parents or {}),
        searched=answer.searched,
        files_consulted=answer.trace.files_consulted,
        retries=answer.retries,
        disclaimer=answer.disclaimer,
        has_trace=True,
    )


# F-12. "This looks like a question for {name}. Answer from there?" per the
# card's own copy -- primary button text is built at the template, from
# `route_candidates[0].name`, so there is one sentence rather than two that
# have to agree on the workspace name.
NO_MATCH_TEXT = (
    "None of your workspaces look like a match for this question. Pick one "
    "from the selector above and ask again."
)


def route_proposal_message(
    question: str, candidates: Sequence[RouteCandidate]
) -> Message:
    """F-12's confirmation-before-answer bubble.

    `candidates` is ranked best first (`ui.routing.propose_workspace`).
    Empty means no workspace had any hit at all: PRD F-12 is explicit that
    Sanad "asks for confirmation" rather than answering blind, and a
    proposal with nothing behind it would be a guess wearing a question's
    clothes -- so this shows the plain request to pick one instead."""
    if not candidates:
        return Message(
            kind=MessageKind.ROUTE_PROPOSAL, text=NO_MATCH_TEXT, route_question=question
        )
    lead = candidates[0]
    return Message(
        kind=MessageKind.ROUTE_PROPOSAL,
        text=f"This looks like a question for {lead.name}. Answer from there?",
        route_question=question,
        route_candidates=tuple(candidates),
    )


REDACTED = "[redacted]"


def redact_secrets(text: str) -> str:
    """Take the configured API key out of anything about to be displayed.

    THE ERROR PANEL PRINTS AN EXCEPTION VERBATIM, which is exactly what
    UX spec 5 asks for -- "always shows the offending value ... never a
    bare 'something went wrong'". The risk a cold review raised is that
    provider SDKs put the request URL in the exception text, and for
    Google AI Studio that URL carries `?key=...`. That would render the
    key on screen, into any screenshot, and into a defense projector.

    Redacting the CONFIGURED VALUE rather than pattern-matching for
    things that look like keys: an exact string comparison cannot have
    false negatives against the one secret this process actually holds,
    and a regex for "something key-shaped" would both miss real keys and
    censor innocent text. The empty key is skipped, or every message
    would have `[redacted]` spliced between all its characters.

    SCOPE, stated: this covers the key Sanad was configured with. It
    cannot cover a secret that reaches an exception from somewhere else,
    and it is a second line of defence rather than a reason to relax the
    core-law rule about never logging one."""
    key = get_settings().cloud_api_key
    if key and key in text:
        return text.replace(key, REDACTED)
    return text


def error_message(exc: BaseException, question: str) -> Message:
    """Any break in the answering pipeline, as UX spec 5's `ErrorPanel`.

    The exception's own text is shown as the offending value. That is the
    "exact failing value" the component inventory requires, and on the
    failure section 11 cares most about -- "answering service
    unreachable" -- `agent.chat.ChatUnavailableError` already writes a
    sentence naming the mode and the missing setting.

    Passed through `redact_secrets` first: verbatim is the requirement,
    but not verbatim enough to print an API key."""
    return Message(
        kind=MessageKind.ERROR,
        text="",
        error=ErrorDetail(
            sentence="Sanad could not answer this question.",
            attempted=f"Asked: {question}",
            value=redact_secrets(f"{type(exc).__name__}: {exc}"),
            hint=(
                "Nothing was fabricated in place of an answer. Check the "
                "model settings in .env, then use Retry."
            ),
        ),
    )


# Section 11's "answer interrupted mid-generation" row asks for the partial
# text to be kept and marked incomplete. Since S6 the writer streams, so a
# run cancelled while writing carries `Run.partial_text` and `settle` keeps
# THAT. This sentence is for the other case -- cancelled before any text
# was shown -- and says so rather than rendering an empty bubble labelled
# incomplete.
INTERRUPTED_TEXT = (
    "You stopped this answer. Nothing was written, so there is no partial "
    "text to show, and nothing here is a finished answer. Ask again to retry."
)


# S6 saved chat history: the shape `Conversation.to_payload` writes and
# `from_payload` reads. Bump this the day that shape changes; a stored row
# stamped with any other value is treated as unreadable rather than
# guessed at (`from_payload` raises), the same as corrupt JSON or an
# unknown enum value.
PAYLOAD_VERSION = 1


@dataclass
class Conversation:
    """One S1 conversation: what is on screen, and what is in flight.

    Held in memory for the life of the process. PRD section 6 is single
    user on one machine and LD-06 keeps data local, so there is no store
    to put this in. A new conversation (UX spec 6.2) is this object,
    emptied.

    ONE USER IS NOT ONE THREAD, and an earlier version of this docstring
    said "no second reader to race with" on exactly that mistaken step.
    Starlette runs a plain `def` route on a threadpool, and this screen
    generates concurrent requests all by itself: the poll fires every
    700ms while the page is open, and a refresh or a double-clicked Send
    lands beside it. A cold review found two live races here -- one answer
    appended twice, and two paid model runs started for one question. The
    lock below is what closes them, and every method that both READS and
    then WRITES this object holds it across both halves."""

    workspace_id: str
    session_id: str | None = None
    messages: list[Message] = field(default_factory=list)
    # Completed turns stay here only until the next successful run folds them
    # into this compact summary. The transcript remains in `messages`.
    summary: str = ""
    turns: list[Turn] = field(default_factory=list)
    run: Run | None = None
    pending_clarification: ClarificationContext | None = None
    # ST-53: which stored conversation this is, and whose. Neither is in
    # the payload: both are the row's own columns, so a transcript copied
    # between rows can never claim another row's identity. Empty on a
    # conversation that has never been given an id (the routing screen's,
    # which is never saved).
    id: str = ""
    user_id: str = ""
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def busy(self) -> bool:
        """A run is in flight, so the input is disabled and the stage hint
        is showing (UX spec 6.3).

        Read without the lock ON PURPOSE: this is a snapshot for
        rendering, one reference load, and any answer it gives was true a
        moment ago. Nothing DECIDES anything on it -- the decision to start
        a run is made inside `begin`, under the lock."""
        return self.run is not None and not self.run.done

    def reset(self) -> None:
        """New conversation. The session id goes too, which is what makes
        it new: `ask` mints a fresh one and F-07's memory starts clean."""
        with self._lock:
            if self.run is not None:
                self.run.cancel()
            self.messages.clear()
            self.summary = ""
            self.turns.clear()
            self.session_id = None
            self.run = None
            self.pending_clarification = None

    def begin(self, run: Run, question: str) -> bool:
        """Claim this conversation for one question. False if it is taken.

        THE CHECK AND THE CLAIM ARE ONE STEP, which is the whole point.
        Two Sends a few milliseconds apart both used to pass a `busy`
        check and both used to assign `self.run`; the first worker then
        ran to completion, spent a real provider call, and had its answer
        thrown away when the second overwrote it. The user saw one answer
        and paid for two.

        The user's message is appended here, under the same lock, so a
        transcript can never show a question whose run was never claimed."""
        with self._lock:
            # A finished run still owns its answer until `settle` saves it.
            # Replacing it here would erase both the answer and its memory.
            if self.run is not None:
                return False
            # Take the three memory fields under the same lock that claims the
            # run, so a poll cannot settle a prior answer between snapshots.
            run.session_id = self.session_id
            run.previous_summary = self.summary
            run.history = tuple(self.turns)
            run.clarification_context = self.pending_clarification
            self.pending_clarification = None
            self.messages.append(Message(kind=MessageKind.USER, text=question))
            self.run = run
            return True

    def begin_route(self, question: str, propose: Callable[[], Message]) -> bool:
        """F-12: ask the routing question and append its reply, atomically.

        Unlike `begin`, there is no `Run` and no worker thread. Routing is
        local embedding plus vector search, not a model call (the F-12
        card is explicit: no LLM call), so there is no stage to show and
        nothing a Cancel button could interrupt. Held under one lock for
        the same reason `begin` is: two rapid Sends must not both search
        and both append a proposal, which is the exact race `begin` closes
        for a real answer.

        False when a run is already in flight for this conversation --
        the sentinel routing conversation is not exempt from the rule that
        one question is answered before the next starts.

        `propose` runs INSIDE the lock, after the user's message is
        appended, so a caller whose `propose` raises (evidence-only mode:
        `agent.chat.ChatUnavailableError`) still leaves the question
        visible in the transcript; the exception propagates to the caller,
        which appends its own error message with `append_system`."""
        with self._lock:
            if self.run is not None:
                return False
            self.messages.append(Message(kind=MessageKind.USER, text=question))
            self.messages.append(propose())
            return True

    def append_system(self, message: Message) -> None:
        """One system-authored message, appended under the same lock as
        everything else here (F-12: the evidence-only refusal that follows
        a routing question `begin_route`'s `propose` could not answer)."""
        with self._lock:
            self.messages.append(message)

    def settle(self) -> bool:
        """Fold a finished run into the transcript. Returns whether it
        actually did -- False on every no-op call (no run, or one still in
        flight).

        Called on every render rather than by the worker thread, so the
        worker only ever writes its own `Run`. That includes the 700ms
        poll while the page is open (`Conversation` docstring), so the
        return value matters beyond idempotency: S6 saved chat history's
        caller (`app.py::_context`) saves the transcript to storage only when
        this returns True, or every poll tick would open a write
        transaction for nothing changed.

        IDEMPOTENT UNDER CONCURRENCY, not merely on a second sequential
        call. The run is detached under the lock BEFORE anything is
        appended, so of two threads arriving together exactly one comes
        away holding it; the other sees None and does nothing. Written the
        obvious way -- read, check, then clear -- both could pass the check
        and the answer appeared twice, once in the transcript and once in
        `turns`, which then fed a duplicated exchange back as F-07
        memory."""
        with self._lock:
            run = self.run
            if run is None or not run.done:
                return False
            self.run = None

            answer = run.answer
            if answer is not None:
                message = message_for(
                    answer,
                    run.reading.cited,
                    run.reading.parents,
                )
                self.messages.append(message)
                self.session_id = answer.session_id
                if run.updated_summary is not None:
                    self.summary = run.updated_summary
                    self.turns.clear()
                if answer.kind is AnswerKind.CLARIFICATION:
                    if run.clarification_context is not None:
                        raise RuntimeError(
                            "a resumed clarification asked a second question; "
                            "agent.nodes must skip clarification after the reply"
                        )
                    self.pending_clarification = ClarificationContext(
                        original=run.question, asked=answer.text
                    )
                if answer.kind is AnswerKind.ANSWER:
                    # F-07's in-session memory holds completed exchanges. A
                    # refusal or a clarifying question is not one, and
                    # feeding "I could not find this" back as history would
                    # teach the next turn a fact about the corpus that the
                    # corpus does not contain.
                    self.turns.append(
                        Turn(question=run.question_for_agent, answer=answer.text)
                    )
                return True
            if run.clarification_context is not None:
                self.pending_clarification = run.clarification_context
            error = run.error
            if isinstance(error, RunCancelled):
                partial = run.partial_text
                self.messages.append(
                    Message(kind=MessageKind.INTERRUPTED, text=partial, partial=True)
                    if partial
                    else Message(kind=MessageKind.INTERRUPTED, text=INTERRUPTED_TEXT)
                )
                return True
            if error is not None:
                self.messages.append(error_message(error, run.question))
            return True

    def to_payload(self) -> dict[str, Any]:
        """This conversation as JSON-safe data, for S6's storage row:
        `messages`, `summary`, `turns`, `session_id`. NOT `run` (in-flight
        state, meaningless once the process that started it is gone) and
        NOT `pending_clarification` (a clarifying question asked by a dead
        process is not worth resuming into -- the next question starts a
        fresh one, same as today when nothing is stored at all).

        `v` is the payload SHAPE version, stamped `PAYLOAD_VERSION` on
        every save. A future change to this shape bumps that constant;
        `from_payload` treats any other value (including a payload with no
        `v` at all, from before this field existed) as unreadable rather
        than guessing at a shape it was never written to expect.

        Locked, for the same reason `begin`/`settle` are: a poll thread
        could be reading `self.messages` while this copies it."""
        with self._lock:
            return {
                "v": PAYLOAD_VERSION,
                "session_id": self.session_id,
                "summary": self.summary,
                "turns": [
                    {"question": turn.question, "answer": turn.answer}
                    for turn in self.turns
                ],
                "messages": [message.to_dict() for message in self.messages],
            }

    def first_question(self) -> str | None:
        """The first question asked here, or None -- the automatic title
        of a stored conversation (`chat_history.title_from`)."""
        with self._lock:
            for message in self.messages:
                if message.kind is MessageKind.USER and message.text.strip():
                    return message.text
        return None

    @staticmethod
    def from_payload(
        workspace_id: str,
        data: Mapping[str, Any],
        *,
        conversation_id: str = "",
        user_id: str = "",
    ) -> Conversation:
        """The inverse of `to_payload`. Raises on anything unreadable --
        corrupt JSON already failed before this is called
        (`json.loads`), but a field of the wrong shape, an unknown enum
        value, or an unrecognized `v` raises here (KeyError, ValueError,
        TypeError) -- so the caller (`app.py::Runtime._load_conversation`)
        can catch it and start an empty conversation instead of crashing
        the chat screen."""
        if data.get("v") != PAYLOAD_VERSION:
            raise ValueError(
                f"unrecognized chat history payload version {data.get('v')!r}, "
                f"expected {PAYLOAD_VERSION!r}"
            )
        messages = [Message.from_dict(item) for item in data["messages"]]
        turns = [
            Turn(question=str(turn["question"]), answer=str(turn["answer"]))
            for turn in data["turns"]
        ]
        session_id = data.get("session_id")
        return Conversation(
            workspace_id=workspace_id,
            session_id=str(session_id) if session_id is not None else None,
            messages=messages,
            summary=str(data.get("summary", "")),
            turns=turns,
            id=conversation_id,
            user_id=user_id,
        )
