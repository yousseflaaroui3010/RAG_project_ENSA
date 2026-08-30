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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from agent.state import Answer, AnswerKind, Source, Turn
from ui.runs import Run, RunCancelled, find_span
from vector_store import SearchHit


class MessageKind(StrEnum):
    USER = "user"
    ANSWER = "answer"
    REFUSAL = "refusal"
    CLARIFICATION = "clarification"
    ERROR = "error"
    INTERRUPTED = "interrupted"


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


@dataclass(frozen=True)
class ErrorDetail:
    """UX spec 5: "`ErrorPanel` always shows the offending value ... Never
    a bare 'something went wrong'"."""

    sentence: str
    attempted: str
    value: str
    hint: str


@dataclass(frozen=True)
class Message:
    kind: MessageKind
    text: str
    sources: tuple[SourceCard, ...] = ()
    searched: tuple[str, ...] = ()
    retries: int = 0
    disclaimer: bool = False
    error: ErrorDetail | None = None
    # UX spec 6.2: a clarification carries "two or three concrete choices
    # as buttons" only "where the system can offer them". ST-22 owns the
    # clarify port and is not built, so nothing can offer any, and this
    # stays empty rather than being filled with plausible-looking guesses.
    # The React reference invents three (`ChatScreen.tsx:163`).
    choices: tuple[str, ...] = ()


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
    *,
    legal_workspace: bool = False,
) -> Message:
    """One `Answer` as one rendered message.

    `legal_workspace` rather than `answer.disclaimer`: F-09's wiring is
    ST-26's and `Answer.disclaimer` is documented in agent/state.py as a
    default nobody has exercised. Reading the workspace's own flag here
    means the line appears when the flag is set, today, without this story
    pretending to have done ST-26's job. When ST-26 lands, this argument
    is where it plugs in.

    UX spec 6.2 puts the line "directly under the answer body, above the
    source cards", and criterion 3 makes its absence just as binding: an
    unflagged workspace shows none anywhere."""
    return Message(
        kind=_VARIANT[answer.kind],
        text=answer.text,
        sources=_cards_for(answer.sources, cited, parents or {}),
        searched=answer.searched,
        retries=answer.retries,
        # Only an answer carries it. A refusal states what was searched and
        # has no legal content to disclaim.
        disclaimer=legal_workspace and answer.kind is AnswerKind.ANSWER,
    )


def error_message(exc: BaseException, question: str) -> Message:
    """Any break in the answering pipeline, as UX spec 5's `ErrorPanel`.

    The exception's own text is shown as the offending value. That is the
    "exact failing value" the component inventory requires, and on the
    failure section 11 cares most about -- "answering service
    unreachable" -- `agent.chat.ChatUnavailableError` already writes a
    sentence naming the mode and the missing setting."""
    return Message(
        kind=MessageKind.ERROR,
        text="",
        error=ErrorDetail(
            sentence="Sanad could not answer this question.",
            attempted=f"Asked: {question}",
            value=f"{type(exc).__name__}: {exc}",
            hint=(
                "Nothing was fabricated in place of an answer. Check the "
                "model settings in .env, then use Retry."
            ),
        ),
    )


# Section 11's "answer interrupted mid-generation" row asks for the partial
# text to be kept and marked incomplete. THERE IS NO PARTIAL TEXT IN V1 and
# this says so rather than rendering an empty bubble labelled incomplete:
# `agent.answering.build_write_answer` calls the model once and returns a
# whole string, so nothing streams and there is never a half-written answer
# in memory to keep. When a story adds streaming, the text goes here.
INTERRUPTED_TEXT = (
    "You stopped this answer. Nothing was written, so there is no partial "
    "text to show, and nothing here is a finished answer. Ask again to retry."
)


@dataclass
class Conversation:
    """One S1 conversation: what is on screen, and what is in flight.

    Held in memory for the life of the process. PRD section 6 is single
    user on one machine and LD-06 keeps data local, so there is no store
    to put this in and no second reader to race with. A new conversation
    (UX spec 6.2) is this object, emptied."""

    workspace_id: str
    session_id: str | None = None
    messages: list[Message] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    run: Run | None = None

    @property
    def busy(self) -> bool:
        """A run is in flight, so the input is disabled and the stage hint
        is showing (UX spec 6.3)."""
        return self.run is not None and not self.run.done

    def reset(self) -> None:
        """New conversation. The session id goes too, which is what makes
        it new: `ask` mints a fresh one and F-07's memory starts clean."""
        self.messages.clear()
        self.turns.clear()
        self.session_id = None
        self.run = None

    def settle(self, *, legal_workspace: bool = False) -> None:
        """Fold a finished run into the transcript.

        Called on every render rather than by the worker thread, so the
        thread only ever writes its own `Run` and the message list has one
        writer. Idempotent: a settled run is cleared, so a second call
        does nothing."""
        run = self.run
        if run is None or not run.done:
            return
        self.run = None
        answer = run.answer
        if answer is not None:
            self.messages.append(
                message_for(
                    answer,
                    run.reading.cited,
                    run.reading.parents,
                    legal_workspace=legal_workspace,
                )
            )
            self.session_id = answer.session_id
            if answer.kind is AnswerKind.ANSWER:
                # F-07's in-session memory holds completed exchanges. A
                # refusal or a clarifying question is not one, and feeding
                # "I could not find this" back as conversational history
                # would teach the next turn a fact about the corpus that
                # the corpus does not contain.
                self.turns.append(Turn(question=run.question, answer=answer.text))
            return
        error = run.error
        if isinstance(error, RunCancelled):
            self.messages.append(
                Message(kind=MessageKind.INTERRUPTED, text=INTERRUPTED_TEXT)
            )
            return
        if error is not None:
            self.messages.append(error_message(error, run.question))
