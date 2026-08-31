"""One question in flight: the real stage, cancellation, and what was read.

WHY THIS FILE EXISTS AT ALL, because a chat screen is usually just a form.
UX spec 6.3 requires stage hints -- "Searching the workspace", then
"Checking the answer", then "Writing" -- and design principle 3 bans the
alternative in one sentence: "A spinner with no stage is banned." Principle
3's first line is stricter still: "Never fake progress. Stage hints during
a long operation say what is actually happening."

The React reference in `designrag-main/` fails exactly that clause. Its
stages are two `setTimeout` calls at 650ms and 1300ms
(`src/components/ChatScreen.tsx:111-112`), so the label says "Verifying
retrieved passages" at 700ms whatever the pipeline is really doing. A
timer that has never met the agent is the definition of faked progress.

WHAT THIS DOES INSTEAD. `agent.graph.ask` is synchronous and every place
it needs the outside world is one callable on `AgentPorts`. So the stage
is read AT THE SEAM: entering `retrieve` IS searching, entering `grade` IS
checking, entering `write_answer` IS writing. Nothing is estimated and
nothing is timed. If the grader takes nine seconds the screen says
"Checking the answer" for nine seconds, which is the truth.

The run happens on a worker thread so the page can be served while it is
in flight. That is the only reason for the thread; there is no concurrency
model here beyond one lock around one dataclass.

THREE THINGS THIS FILE DELIBERATELY DOES NOT DO:

1. It does not touch `agent/`. The observation is a wrapper built with
   `dataclasses.replace`, so the graph, the nodes and the ports keep the
   exact behaviour their own tests pin.
2. It does not re-derive which passages were cited. `make_answer` builds
   ONE tuple and uses it for both jobs -- what the writer is shown and
   what the sources are built from (agent/nodes.py:418) -- precisely so
   that two filters cannot drift apart. This records that same tuple, by
   reading the arguments `write_answer` is called with. Not a copy of the
   rule: the arguments themselves.
3. It does not invent a partial answer. `write_answer` returns a whole
   string or raises; nothing streams in V1. So cancelling during the
   writing stage leaves no partial text, and the screen says so rather
   than showing an empty bubble marked "incomplete".
"""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from agent.graph import ask
from agent.ports import AgentPorts
from agent.state import Answer, Turn
from vector_store import SearchHit


class Stage(StrEnum):
    """The three stage hints UX spec 6.3 names, in order.

    A StrEnum rather than free strings because the label shown to the user
    and the value the poll returns must be the same thing; two spellings
    of "checking" is how a screen ends up announcing a stage that never
    ran."""

    SEARCHING = "searching"
    CHECKING = "checking"
    WRITING = "writing"


# UX spec 6.3, verbatim. The wording is the spec's, not a paraphrase: it is
# what the live region announces (6.4) and what a jury reads off the
# screen.
STAGE_LABELS: Mapping[Stage, str] = {
    Stage.SEARCHING: "Searching the workspace",
    Stage.CHECKING: "Checking the answer",
    Stage.WRITING: "Writing",
}


class RunCancelled(Exception):
    """The operator pressed Cancel and the run stopped at a seam.

    UX spec 6.3: "A cancel action is available and stops after the current
    stage." Raised at the NEXT port boundary rather than mid-call, because
    a port call is either a model round trip or a store read and neither
    can be interrupted from outside without leaving the thing it was
    talking to in an unknown state."""


@dataclass
class Reading:
    """Exactly what the answer was written from.

    Both fields are the ARGUMENTS `write_answer` was called with, captured
    at the seam. `cited` is `make_answer`'s one tuple -- the passages whose
    section box P could load -- and `parents` is the section text keyed by
    parent id. That tuple is also what `answer.sources` is built from, so
    a source card and its passage are two views of one list rather than
    two lists that agree.

    Empty on every path that never reaches the writer: a clarification, an
    off-topic refusal, a workspace whose sections are all gone. Those
    answers carry no sources either, so there is nothing to open.

    Recorded rather than re-fetched because re-running retrieval to open a
    source card would search again, possibly find something else, and show
    the user a passage the answer was not written from."""

    cited: tuple[SearchHit, ...] = ()
    parents: Mapping[str, str] = field(default_factory=dict)


@dataclass
class Run:
    """One question, from submitted to settled.

    Every SCALAR a request thread reads is guarded by `_lock`, because the
    worker writes `stage` while the page renders it. The lock is held for
    single assignments only -- it never spans a port call, or Cancel could
    not be recorded while the model is thinking, which is the one moment
    it is needed.

    `reading` IS THE EXCEPTION AND IT IS NOT GUARDED. An earlier version
    of this docstring said "every field", which was not true and is the
    kind of sentence a later reader trusts instead of checking. What makes
    it safe is ordering, not the lock: the worker fills `reading` inside
    `write_answer` and only then sets `_done` under the lock, and nothing
    outside reads `reading` until it has seen `done` -- `Conversation.
    settle` is the only reader and it checks `run.done` first. So the
    lock release that publishes `_done` is what publishes `reading` with
    it. If a future caller ever reads `reading` on a run that is still in
    flight, that argument evaporates and this needs the lock."""

    question: str
    workspace_id: str
    session_id: str | None
    history: tuple[Turn, ...] = ()

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _stage: Stage | None = None
    _cancelled: bool = False
    _done: bool = False
    _answer: Answer | None = None
    _error: BaseException | None = None
    reading: Reading = field(default_factory=Reading)

    # --- what the page reads -------------------------------------------

    @property
    def stage(self) -> Stage | None:
        with self._lock:
            return self._stage

    @property
    def stage_label(self) -> str:
        """What the screen shows. Never blank while a run is in flight:
        before the first port is entered the honest answer is the first
        stage, because `ask` has been called and the search is what it
        does first."""
        stage = self.stage or Stage.SEARCHING
        return STAGE_LABELS[stage]

    @property
    def done(self) -> bool:
        with self._lock:
            return self._done

    @property
    def cancelled(self) -> bool:
        with self._lock:
            return self._cancelled

    @property
    def answer(self) -> Answer | None:
        with self._lock:
            return self._answer

    @property
    def error(self) -> BaseException | None:
        with self._lock:
            return self._error

    # --- driving it ----------------------------------------------------

    def cancel(self) -> None:
        """Ask the run to stop at its next seam.

        Idempotent, and safe to call on a run that has already finished --
        the page can only offer Cancel from a snapshot that was already
        one render out of date."""
        with self._lock:
            self._cancelled = True

    def fail(self, exc: BaseException) -> None:
        """Settle this run as failed without ever having started it.

        The one case: the ports could not be BUILT, so there is nothing to
        run and no thread to run it on (`app.py::_start`). Recorded on the
        run rather than appended straight to the transcript so that every
        outcome -- answered, cancelled, failed -- leaves the same object in
        the same shape and `Conversation.settle` stays the single place
        that turns a finished run into a message."""
        with self._lock:
            self._error = exc
            self._done = True

    def _checkpoint(self) -> None:
        with self._lock:
            if self._cancelled:
                raise RunCancelled(
                    f"cancelled during {self._stage or Stage.SEARCHING}"
                )

    def _enter(self, stage: Stage) -> None:
        self._checkpoint()
        with self._lock:
            self._stage = stage

    def observed(self, ports: AgentPorts) -> AgentPorts:
        """The same ports, with three of them announcing themselves.

        `dataclasses.replace` on a frozen dataclass, so the callables
        underneath are ST-23's and ST-24's untouched. The two ports that
        set no stage are deliberate:

        * `fetch_parents` reads a few JSON files in milliseconds and has
          no name in UX spec 6.3's vocabulary of three. Leaving the stage
          on "Checking the answer" through it is the last true thing the
          user was told; inventing a fourth hint would be adding a stage
          the spec does not have. It is still wrapped, for the cancel
          checkpoint alone.
        * `summarize`, `clarify`, `rewrite` and `reword` are either
          stubbed (ST-22, ST-25) or instantaneous, and none of them is a
          stage a user waits through."""

        def searching(retrieve: Any) -> Any:
            def wrapped(workspace_id: str, query: str) -> Sequence[SearchHit]:
                self._enter(Stage.SEARCHING)
                return retrieve(workspace_id, query)

            return wrapped

        def checking(grade: Any) -> Any:
            def wrapped(question: str, passages: tuple[SearchHit, ...]) -> bool:
                self._enter(Stage.CHECKING)
                return grade(question, passages)

            return wrapped

        def stoppable(fetch_parents: Any) -> Any:
            def wrapped(
                workspace_id: str, parent_ids: tuple[str, ...]
            ) -> Mapping[str, str]:
                self._checkpoint()
                return fetch_parents(workspace_id, parent_ids)

            return wrapped

        def writing(write_answer: Any) -> Any:
            def wrapped(
                question: str,
                passages: tuple[SearchHit, ...],
                parent_texts: Mapping[str, str],
            ) -> str:
                self._enter(Stage.WRITING)
                # THE CAPTURE, and the reason it is here rather than at
                # `fetch_parents`: these two arguments ARE `make_answer`'s
                # single tuple and the mapping behind it. `answer.sources`
                # is built from the same tuple three lines later, so a
                # source card and the passage it opens cannot disagree
                # about what was read.
                self.reading.cited = tuple(passages)
                self.reading.parents = dict(parent_texts)
                written = write_answer(question, passages, parent_texts)
                # CANCEL HAS TO WORK ON THE LAST STAGE TOO. Writing is the
                # final port, so without this checkpoint the flag set
                # during it is never read again and the answer lands as if
                # Cancel had not been pressed -- a button that does nothing
                # on the one stage a user actually waits through. UX spec
                # 6.3 says Cancel "stops after the current stage", and this
                # is that sentence: the stage finishes, then it stops.
                # The cost is real and is accepted: a completed answer that
                # was paid for is discarded. Showing it anyway would make
                # the button a lie, which is worse.
                self._checkpoint()
                return written

            return wrapped

        return dataclasses.replace(
            ports,
            retrieve=searching(ports.retrieve),
            grade=checking(ports.grade),
            fetch_parents=stoppable(ports.fetch_parents),
            write_answer=writing(ports.write_answer),
        )

    def _work(self, ports: AgentPorts) -> None:
        try:
            answer = ask(
                workspace_id=self.workspace_id,
                question=self.question,
                ports=self.observed(ports),
                session_id=self.session_id,
                history=self.history,
            )
        except BaseException as exc:  # noqa: BLE001 -- see below
            # EVERY failure is caught, including the ones a library author
            # never meant to be caught, because the alternative is a
            # thread that dies silently and a page that says "Searching
            # the workspace" until the operator gives up. PRD section 11's
            # rule is that a failure names itself; a hung stage hint is
            # the one outcome worse than an error panel.
            with self._lock:
                self._error = exc
                self._done = True
            return
        with self._lock:
            self._answer = answer
            self._done = True

    def start(self, ports: AgentPorts) -> None:
        """Run the question on a worker thread and return immediately.

        Daemon, so a Ctrl-C on the server does not wait for a model call
        that may take thirty seconds."""
        threading.Thread(
            target=self._work, args=(ports,), daemon=True, name="sanad-ask"
        ).start()


def find_span(section: str, chunk: str) -> tuple[int, int] | None:
    """Where the retrieved chunk sits inside its section, or nothing.

    `chunking._windows` slices the parent with plain string slicing, so a
    child IS a verbatim substring of its parent and a `find` is the whole
    algorithm. This still returns None rather than guessing when the text
    does not match -- an index rebuilt under different chunking settings,
    or a store that has drifted, would otherwise get a highlight drawn
    over the wrong sentence. UX spec 5 asks for the CITED span; a
    highlight in the wrong place is worse than no highlight, because the
    reader has no way to tell it is wrong."""
    if not chunk:
        return None
    start = section.find(chunk)
    if start < 0:
        return None
    return start, start + len(chunk)
