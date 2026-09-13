"""The Sanad host: FastAPI serving the server-rendered screens (CR-02).

`uv run python app.py` starts it, per architecture 12.1 step 5.

SCOPE, because this file will grow and the next story owns half of it.
ST-27 builds S1, the chat screen, and the template routes it needs.
ST-51 adds the `/api/v1` surface from docs/phase2/openapi.yaml and mounts
it on this same host, delegate-only; its exit gate is "UI unchanged when
mounted", which is why the screen routes live under their own prefix and
nothing here answers on `/api`.

WHY THE ROUTES ARE THIN. docs/phase2/ENGINEERING-RULES.md's rule is "no business
logic inside a route body". Every rule the screen has -- which state it is
in, which message variant, which spans are highlighted, whether the
disclaimer line shows -- lives in `ui/screen.py` and `ui/conversation.py`
where a test can call it without an HTTP request. A route here reads the
session, calls one of those, and renders.

ADR-13 IS WHAT MAKES THIS SMALL. The UI calls `agent.graph.ask`
IN-PROCESS. There is no HTTP client, no serialization of an `Answer`, and
no second copy of the openapi contract to keep in step: the screen holds
the real object the graph returned.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import jinja2
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import embeddings
import recovery
import sync
import vector_store
import watcher
import workspaces
from agent.chat import ChatUnavailableError
from agent.ports import AgentPorts
from api.routes import build_router
from api.service import ApiService
from config import get_settings
from db import repo
from ui import feedback as feedback_module
from ui import i18n, reports_screen, routing, rtl, screen, workspaces_screen
from ui.access_gate import AccessGate
from ui.answer_format import render_answer
from ui.conversation import (
    Conversation,
    Message,
    MessageKind,
    error_message,
    route_proposal_message,
)
from ui.i18n.request import LanguageMiddleware, context_language, language_links
from ui.ports import build_default_ports
from ui.runs import STAGE_LABELS, Run, Stage

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "ui" / "templates"
STATIC = HERE / "ui" / "static"
OPENAPI_CONTRACT = HERE / "docs" / "phase2" / "openapi.yaml"
APP_VERSION = tomllib.loads((HERE / "pyproject.toml").read_text(encoding="utf-8"))[
    "project"
]["version"]

# 303, not 302: every mutating route here answers a POST and redirects to a
# GET, and 303 is the status that says "fetch the result with GET" rather
# than leaving the method to the browser's discretion. Without it, a
# refresh after asking re-submits the question.
SEE_OTHER = 303

# The most a posted form may carry. Sanad's largest field is a question,
# which openapi bounds at `question_max_length` characters; 64 KiB leaves
# room for percent-escaped multibyte French and every other field on the
# page many times over. A body past this is dropped rather than buffered.
MAX_FORM_BYTES = 64 * 1024

# ST-05 (Railway hosting). The one sentence both refusals show, written
# once. Sync and Chat decline for the SAME reason, so two hand-written
# strings would be two things free to drift apart -- and the operator
# would be told two different stories about one limit. See
# `config.evidence_only` for why the limit exists and why it is not a bug
# to be worked around.
EVIDENCE_ONLY_MESSAGE = (
    "This published instance is read-only: it shows evaluation reports and "
    "workspace details, but cannot answer questions or run a Sync. Both need "
    "the embedding model, which is larger than this container's memory "
    "limit. Run Sanad locally to ask questions or index documents."
)


@dataclass
class Runtime:
    """Everything the app needs that is not a request.

    A single object rather than module-level globals so a test can build a
    whole app around a scripted model and a `tmp_path` store, which is
    what `tests/integration/test_s1_chat_screen.py` does. The default
    values are the running server's.

    `ports_factory` is a callable, not an `AgentPorts`, so that
    `agent.chat.ChatUnavailableError` is raised when a question is asked
    rather than when the process starts -- UX spec 11 routes an
    unreachable answering service to an `ErrorPanel` on S1, which an
    operator can only read if the server came up."""

    ports_factory: Any = None
    db_path: str | Path | None = None
    # ST-39 warm-up. Off by default so a test that builds a `Runtime`
    # directly -- which is every test in this codebase -- never spends a
    # real model download by accident. `main()` is the only place that
    # turns it on, because that is the only caller building the real
    # server rather than a test double.
    warm_up: bool = False
    conversations: dict[str, Conversation] = field(default_factory=dict)
    active_workspace_id: str | None = None
    client: Any = None
    # Guards the three fields below, never a whole operation. See `store`.
    store_lock: threading.Lock = field(default_factory=threading.Lock)
    _store_users: int = field(default=0, repr=False, compare=False)
    _store_client: Any = field(default=None, repr=False, compare=False)
    _store_exit: contextlib.ExitStack | None = field(
        default=None, repr=False, compare=False
    )
    # ST-28, S2. Sync has no per-request object the way chat's `Run` is one
    # (sync_workspace is one blocking call handed to a background thread,
    # not something the request that started it keeps a handle on), so the
    # two facts a render needs that are not already in the registry live
    # here, keyed by workspace, exactly like `conversations` above.
    # `last_sync_run_id` is set from the `SyncReport.sync_run_id` the
    # background thread's own call returns, which is what makes the
    # finished report reachable even when nobody polled while it was
    # running (a small corpus can finish before any request ever sees it
    # as running -- `repo.get_running_sync_run`'s `finished_at IS NULL`
    # query would otherwise be the only way to learn the id, and it stops
    # answering the instant the run ends). Lost on a server restart, which
    # is recorded rather than hidden -- see `ui/workspaces_screen.py` and
    # BUILD-STATE.
    sync_errors: dict[str, str] = field(default_factory=dict)
    last_sync_run_id: dict[str, str] = field(default_factory=dict)
    sync_cancel_events: dict[str, threading.Event] = field(default_factory=dict)
    # F-15. Mirrors `sync_errors` above: the last feedback POST for this
    # workspace failed validation, keyed so a stale error from a different
    # workspace never shows on this one. Cleared on the next successful
    # submit for that workspace (see `feedback_route`), never on a plain
    # render -- a render can happen many times (the poll) before the
    # operator retries.
    feedback_errors: dict[str, str] = field(default_factory=dict)

    @contextlib.contextmanager
    def ports(self) -> Iterator[AgentPorts]:
        # ST-05 evidence-only mode. Checked HERE, before the ports_factory
        # branch a test double uses, because this is the one seam both the
        # chat screen (`_start` -> `start_with`) and the `/api/v1/ask`
        # route (`api.service.ApiService.ask`) call: raising the SAME
        # exception type a missing model key raises means one error path,
        # one template, and one set of tests, not a second way for either
        # caller to say no. `_work_with` (ui/runs.py) and `ApiService.ask`
        # both already catch whatever entering this context manager raises
        # and settle the run as failed -- UX spec 11's "answering service
        # unreachable" panel, and 503 MODEL_UNREACHABLE over the API.
        if get_settings().evidence_only:
            raise ChatUnavailableError(EVIDENCE_ONLY_MESSAGE)
        if self.ports_factory is not None:
            yield self.ports_factory()
            return
        with self.store() as client:
            yield build_default_ports(client)

    @contextlib.contextmanager
    def routing_client(self) -> Iterator[Any]:
        """F-12: the raw store client for proposing a workspace.

        Routing needs the EMBEDDING model, never the chat model -- it
        makes no LLM call (see `ui/routing.py`) -- so this does not go
        through `ports()` / `build_default_ports`, which would build a
        chat model routing never calls and could fail for a reason that
        has nothing to do with routing (a missing cloud key, say).

        Checks the SAME `evidence_only` guard `ports()` does, raising the
        IDENTICAL exception with the IDENTICAL message: one refusal
        sentence for every seam that needs the embedding model, not a
        second way to say no."""
        if get_settings().evidence_only:
            raise ChatUnavailableError(EVIDENCE_ONLY_MESSAGE)
        with self.store() as client:
            yield client

    @contextlib.contextmanager
    def store(self) -> Iterator[Any]:
        """Share one embedded index between the Chat, Sync and delete
        operations running in this process; close it when the last ends.

        OPEN ONLY WHILE SOMETHING NEEDS IT, so the separate command-line
        evaluator can own the index while this server keeps showing
        Reports. If the evaluator has it, `open_store` raises
        `StoreAlreadyOpenError` at once and the caller shows that.

        SHARED, NOT ONE AT A TIME: a lock held for a whole Sync -- minutes
        on a real corpus -- made a Chat question wait silently behind it and
        a delete hang, with nothing on screen saying why (rule-5 review of
        57187cf). One client per process is still the ADR-04 rule: a second
        in-process `open_store` on the same path raises, which is why this
        counts users instead of opening per operation.

        SHARED, BUT ONE CALL AT A TIME: embedded Qdrant is not safe for a
        search and a write at the same instant, so the shared client is a
        `vector_store.SerializedClient` (see why there)."""
        if self.client is not None:
            yield self.client
            return
        with self.store_lock:
            if self._store_users == 0:
                stack = contextlib.ExitStack()
                self._store_client = vector_store.SerializedClient(
                    stack.enter_context(vector_store.open_store())
                )
                self._store_exit = stack
            self._store_users += 1
            client = self._store_client
        try:
            yield client
        finally:
            with self.store_lock:
                self._store_users -= 1
                if self._store_users == 0:
                    stack, self._store_exit = self._store_exit, None
                    self._store_client = None
                    if stack is not None:
                        stack.close()

    def start_sync(self, workspace_id: str) -> sync.SyncClaim:
        """Claim a Sync run in the caller's thread, then do the work on a
        background thread; return the claim.

        CLAIMED HERE, BEFORE THE THREAD, so a second click is refused with
        `sync.SyncInProgressError` while the first is still waiting for the
        index, instead of both being accepted with no run row, no progress
        and a cancel event the second click silently replaced (rule-5
        review of 57187cf; F-02, UX spec 7.3). Also raises
        `workspaces.WorkspaceNotFoundError` for an unknown id.

        A claim is a promise to finish the run row. `sync_workspace`
        keeps it once it starts; `_finish_unstarted` keeps it when the
        index cannot even be opened, or no run would ever start again.

        Raises `sync.EvidenceOnlyError` FIRST, before any claim, when
        `config.evidence_only` is on -- the one seam both the S2 Sync
        button (`start_sync_route`) and the `/api/v1` startSync route
        (`api.service.ApiService.start_sync`) call, so neither has to
        re-check the setting itself and a caller cannot race a claim in
        ahead of the refusal."""
        if get_settings().evidence_only:
            raise sync.EvidenceOnlyError(EVIDENCE_ONLY_MESSAGE)
        claim = sync.claim_sync(workspace_id=workspace_id, db_path=self.db_path)
        self.sync_errors.pop(workspace_id, None)
        cancel_event = threading.Event()
        self.sync_cancel_events[workspace_id] = cancel_event

        def _work() -> None:
            try:
                with self.store() as client:
                    report = sync.sync_workspace(
                        workspace_id=workspace_id,
                        db_path=self.db_path,
                        client=client,
                        cancel_requested=cancel_event.is_set,
                        claim=claim,
                    )
            except Exception as exc:  # noqa: BLE001 -- mirrors _start's own catch-all
                # PRD section 11: "folder missing or unreadable shows the
                # exact path plus a fix hint" -- `FolderNotFoundError`'s
                # own message already carries both, so it is shown as-is.
                logger.exception("sync failed for workspace %s", workspace_id)
                self.sync_errors[workspace_id] = str(exc)
                self._finish_unstarted_logged(claim)
            else:
                # THE LOAD-BEARING LINE: the finished report stays reachable
                # even when nobody polled while it ran (a small corpus can
                # finish before any request observes it as running).
                self.last_sync_run_id[workspace_id] = report.sync_run_id
            finally:
                if self.sync_cancel_events.get(workspace_id) is cancel_event:
                    self.sync_cancel_events.pop(workspace_id, None)

        try:
            threading.Thread(target=_work, daemon=True, name="sanad-sync").start()
        except BaseException:
            self.sync_cancel_events.pop(workspace_id, None)
            self._finish_unstarted_logged(claim)
            raise
        return claim

    def _finish_unstarted_logged(self, claim: sync.SyncClaim) -> None:
        """`_finish_unstarted`, but a failure to close the row is logged
        rather than raised: it must not replace the error that got us
        here, and there is nothing better to do with it in a worker thread.
        The row it could not close is then settled by start-up recovery."""
        try:
            self._finish_unstarted(claim)
        except Exception:  # noqa: BLE001 -- logged; the original error wins
            logger.exception(
                "could not finish unstarted sync run %s", claim.sync_run_id
            )

    def _finish_unstarted(self, claim: sync.SyncClaim) -> None:
        """Close a claimed run that never reached `sync_workspace`, with
        zero counts. A run that did start is already finished by
        `sync_workspace`'s own `finally`, so this leaves it alone."""
        with repo.session(self.db_path) as conn:
            run = repo.get_sync_run(conn, claim.sync_run_id)
            if run is None or run["finished_at"] is not None:
                return
            repo.finish_sync_run(
                conn,
                sync_run_id=claim.sync_run_id,
                finished_at=repo.utc_now(),
                added=0,
                changed=0,
                unchanged=0,
                failed=0,
                removed=0,
                skipped=0,
            )

    def conversation(self, workspace_id: str) -> Conversation:
        """The one conversation for this workspace.

        Keyed by workspace rather than by browser session because PRD
        section 6 is single user on one machine: there is no second
        person whose transcript this could collide with, and inventing a
        cookie session would add a failure mode with no user behind it."""
        existing = self.conversations.get(workspace_id)
        if existing is None:
            existing = Conversation(workspace_id=workspace_id)
            self.conversations[workspace_id] = existing
        return existing


def _active(runtime: Runtime) -> screen.WorkspaceOption | None:
    """The workspace the shell is pointed at.

    Falls back to the first one so that a fresh process lands somewhere
    real; UX spec 4 keeps the selector visible at all times, and a
    selector showing nothing while workspaces exist is a broken shell.

    F-12: returns None ALSO when `active_workspace_id` is the routing
    sentinel ("let Sanad choose") and at least two workspaces exist --
    that is "no workspace selected", not "unknown id, fall back to the
    first one". Guarded on `len(options) >= 2` so a workspace count that
    has shrunk to one under a stale sentinel (e.g. the other workspace was
    deleted while routing was selected) self-heals to the ordinary
    fallback below rather than stranding the shell in routing mode with
    nothing left to route between."""
    options = screen.workspace_options(db_path=runtime.db_path)
    if not options:
        return None
    if runtime.active_workspace_id == screen.ROUTE_SENTINEL and len(options) >= 2:
        return None
    chosen = next(
        (opt for opt in options if opt.id == runtime.active_workspace_id), None
    )
    return chosen or options[0]


def _conversation_key(runtime: Runtime) -> str | None:
    """Which `Runtime.conversations` entry the shell is showing right now:
    the active workspace's id, or F-12's routing sentinel when no
    workspace is selected and there is something to route between. None
    only when no workspace exists at all -- there is nothing to show."""
    active = _active(runtime)
    if active is not None:
        return active.id
    if screen.workspace_options(db_path=runtime.db_path):
        return screen.ROUTE_SENTINEL
    return None


def _workspace_is_arabic(workspace_id: str | None) -> bool:
    """F-14's real trigger, in one place so `_direction` and `_lang` never
    answer it two different ways: is the workspace whose content this
    screen is actually showing majority Arabic script (`ui.rtl`)?

    `workspace_id` is `None` for a screen with nothing to show (no
    workspace exists yet) or, for S3's list view, no single content
    workspace at all (it spans every workspace -- see the DECISIONS row);
    either way that is an honest "not Arabic". Takes the bare id rather
    than a `WorkspaceOption`/`Workspace` object because the three screens
    reach this from two different domain types (S1/S3's shell selector is
    `screen.WorkspaceOption`, S2's `selected` is `workspaces.Workspace`)
    and both already have the id in hand at the call site."""
    return workspace_id is not None and rtl.workspace_is_arabic(workspace_id)


def _direction(request: Request, workspace_id: str | None) -> str:
    """Which way the WHOLE SCREEN reads (F-14 PRD acceptance criterion:
    "the surrounding screen mirrors").

    Two sources, in priority order:

    1. The `?dir=rtl`/`?dir=ltr` query override -- the ST-38 RTL PREVIEW
       UX spec 6.5 asks for ("Verify with an RTL preview even though V1
       ships LTR"). This predates F-14 and stays exactly what it was: NOT
       a locale switch, no Arabic copy, no translation layer -- a QA tool
       for looking at the mirrored CSS, and it affects `dir` ONLY (see
       `_lang`). Anything that is not the literal string "rtl" or "ltr" is
       treated as "ltr" here, including a missing, empty or hostile value;
       only these two strings may ever reach the document element.
    2. Failing that, F-14's real trigger: `_workspace_is_arabic`."""
    override = request.query_params.get("dir")
    if override in ("rtl", "ltr"):
        return override
    return "rtl" if _workspace_is_arabic(workspace_id) else "ltr"


def _lang(workspace_id: str | None) -> str:
    """The document's `lang`, computed from the SAME real signal
    `_direction` uses -- `_workspace_is_arabic` -- but NEVER from the
    `?dir=` preview override.

    The two are one fact when the fact is real ("this workspace's content
    is Arabic" is the only reason this product ever sets `dir="rtl"`,
    there being no other RTL script in scope per PRD section 5) but they
    must stay two separate reads of it: the preview override exists
    precisely so the mirrored CSS can be inspected with NO Arabic copy on
    the page at all, and stamping `lang="ar"` on English preview text
    would misinform a screen reader rather than test anything. A real
    Arabic workspace gets `lang="ar"` whether or not anyone is previewing
    `dir` that request."""
    return "ar" if _workspace_is_arabic(workspace_id) else "en"


def _context(runtime: Runtime, request: Request) -> dict:
    """Everything one render of S1 needs, assembled once.

    Both the full page and the conversation partial are rendered from
    this, so the two cannot disagree about which state the screen is in --
    the failure mode that a second, "just for the partial" context
    function would introduce."""
    options = screen.workspace_options(db_path=runtime.db_path)
    active = _active(runtime)
    documents: list[str] = []
    conversation = None
    # F-12: no active workspace while at least one exists is routing mode
    # ("let Sanad choose"), not the no-workspace-at-all case `state_for`
    # already handles from an empty `options`.
    is_routing = active is None and bool(options)
    if active is not None:
        documents = screen.answerable_documents(active.id, db_path=runtime.db_path)
        conversation = runtime.conversation(active.id)
        conversation.settle()
    elif is_routing:
        conversation = runtime.conversation(screen.ROUTE_SENTINEL)
        conversation.settle()
    state = screen.state_for(
        options=options,
        documents=documents,
        has_messages=bool(conversation and conversation.messages),
        routing=is_routing,
    )
    run = conversation.run if conversation else None
    busy = bool(conversation and conversation.busy)
    stage = run.shown_stage if (run and busy) else None
    active_id = active.id if active else None
    return {
        "request": request,
        "dir": _direction(request, active_id),
        "lang": _lang(active_id),
        "current_screen": "chat",
        # UX spec 4: "Changing it clears nothing and interrupts nothing,
        # but the chat area shows a one-line notice that the conversation
        # context has moved."
        "moved": request.query_params.get("moved") == "1",
        # F-15. `feedback_verdicts` is `{message.id: "up"|"down"}` for every
        # ANSWER/REFUSAL already given feedback in THIS conversation, read
        # fresh on every render so a redirect after POST /chat/feedback
        # shows the saved state immediately. `feedback_error` is the last
        # rejected attempt for the active workspace, if any (see
        # `Runtime.feedback_errors`).
        "feedback_verdicts": (
            feedback_module.verdicts_for(conversation.messages, db_path=runtime.db_path)
            if conversation
            else {}
        ),
        "feedback_error": (
            runtime.feedback_errors.get(active.id) if active else None
        ),
        "feedback_comment_max_chars": get_settings().feedback_comment_max_chars,
        # openapi AskRequest bounds the question, and config.py is where
        # that bound lives (docs/phase2/ENGINEERING-RULES.md: no magic literals in
        # module code). `ask` enforces it server-side too -- this only
        # stops the browser sending something the graph will reject.
        "question_max_length": get_settings().question_max_length,
        "workspaces": options,
        "active": active,
        "documents": documents,
        "samples": screen.sample_questions(documents),
        "sources_promise": screen.SOURCES_PROMISE,
        "state": state,
        "ScreenState": screen.ScreenState,
        "MessageKind": MessageKind,
        "messages": conversation.messages if conversation else [],
        "busy": busy,
        "stage_label": STAGE_LABELS[stage] if stage else "",
        # S6 waiting animation: which of the four real stages is current.
        "stage_key": stage.value if stage else "",
        "stage_steps": [step.value for step in Stage],
        "input_reason": (
            screen.BUSY_REASON
            if busy
            else screen.NO_DOCUMENTS_REASON
            if state is screen.ScreenState.NO_DOCUMENTS
            else ""
        ),
    }


def _ws_selected_id(
    runtime: Runtime,
    request: Request,
    options: list[screen.WorkspaceOption],
    *,
    override: str | None = None,
) -> str | None:
    """Which workspace S2's detail region shows.

    `override` wins when a route already knows the answer (a rename or a
    legal-flag POST re-rendering its own workspace on a validation
    failure, without a redirect to carry `?ws=` on the URL). Otherwise
    `?ws=` on the URL wins, then the shell's active workspace, then the
    first one -- the same fallback order `_active` uses for the shell
    selector, so the two screens never show two different "current"
    workspaces from the same state."""
    if override and any(opt.id == override for opt in options):
        return override
    requested = request.query_params.get("ws")
    if requested and any(opt.id == requested for opt in options):
        return requested
    if runtime.active_workspace_id and any(
        opt.id == runtime.active_workspace_id for opt in options
    ):
        return runtime.active_workspace_id
    return options[0].id if options else None


def _ws_context(
    runtime: Runtime, request: Request, *, selected_override: str | None = None
) -> dict:
    """Everything one render of S2 needs, assembled once -- the full page
    and the polled detail partial share it, for the same reason `_context`
    is shared on S1: two context functions is how a stage and a report
    disagree about which state they are in.

    THE PROGRESS COUNTER IS A COUNT, NOT A FRACTION. `list_sync_items`
    tells us how many files a running sync has already committed a row
    for, which is real and never faked -- but not which one, because its
    own order is by file_name (UX spec 7.2's reading order), not the order
    files were processed in, and not how many are left, because that would
    mean re-running the folder scan ourselves while the real one is still
    going. "N files processed so far" is the whole honest sentence
    available; see design principle 3."""
    options = screen.workspace_options(db_path=runtime.db_path)
    selected_id = _ws_selected_id(runtime, request, options, override=selected_override)
    selected: workspaces.Workspace | None = None
    running: sqlite3.Row | None = None
    running_count = 0
    rows: list[workspaces_screen.FileRow] = []
    report_finished_at: str | None = None
    capacity_warning: str | None = None

    if selected_id is not None:
        selected = workspaces.get_workspace(workspace_id=selected_id, db_path=runtime.db_path)
        with repo.session(runtime.db_path) as conn:
            capacity_warning = workspaces_screen.capacity_warning(
                folder_path=selected.folder_path,
                documents=repo.list_documents(conn, selected_id),
            )
            running = repo.get_running_sync_run(conn, selected_id)
            if running is not None:
                # Cache it NOW, while the row is still findable by the
                # `finished_at IS NULL` query -- once it finishes this is
                # the only place its id survives (see the Runtime field).
                runtime.last_sync_run_id[selected_id] = running["id"]
                running_count = len(repo.list_sync_items(conn, running["id"]))
            else:
                last_id = runtime.last_sync_run_id.get(selected_id)
                if last_id is None:
                    previous = repo.list_sync_runs(conn, selected_id)
                    last_id = previous[0]["id"] if previous else None
                last_run = repo.get_sync_run(conn, last_id) if last_id else None
                if last_run is not None and last_run["finished_at"] is not None:
                    report_finished_at = last_run["finished_at"]
                    rows = workspaces_screen.sort_rows(
                        workspaces_screen.file_rows(
                            folder_path=selected.folder_path,
                            items=repo.list_sync_items(conn, last_id),
                        ),
                        sort=request.query_params.get("sort"),
                        direction=request.query_params.get("dir", "asc"),
                    )

    return {
        "request": request,
        # S2's own screen shows ONE workspace's detail (`selected`), which
        # can differ from the shell's `active` (UX spec 4 lets the file
        # table browse a workspace without switching the chat context) --
        # so mirroring follows what is actually ON the screen, not the
        # shell selector, unlike S1/S3 below where they are the same
        # workspace by construction.
        "dir": _direction(request, selected_id),
        "lang": _lang(selected_id),
        "current_screen": "workspaces",
        # base.html's <noscript> refresh (UX spec 6.3's no-JS path) is keyed
        # on this same name for S1; a Sync in flight is the same kind of
        # fact for S2, so it reuses the hook rather than teaching base.html
        # a second word for one idea.
        "busy": running is not None,
        "active": _active(runtime),
        "workspaces": options,
        "state": workspaces_screen.screen_state(workspace_count=len(options)),
        "WorkspaceScreenState": workspaces_screen.WorkspaceScreenState,
        "selected": selected,
        "selected_id": selected_id,
        "running": running,
        "running_count": running_count,
        "sync_can_cancel": bool(
            selected_id and selected_id in runtime.sync_cancel_events
        ),
        "sync_blocked": request.query_params.get("sync_blocked") == "1",
        "sync_error": runtime.sync_errors.get(selected_id) if selected_id else None,
        "capacity_warning": capacity_warning,
        "file_rows": rows,
        "sort": request.query_params.get("sort"),
        "sort_dir": request.query_params.get("dir", "asc"),
        "report_finished_at": report_finished_at,
        "form_error": None,
        "form_values": None,
        "name_min_length": get_settings().workspace_name_min_length,
        "name_max_length": get_settings().workspace_name_max_length,
        # F-13: a one-line status only, per the story's own scope -- there
        # is no route to toggle it here (`watch_folders` is a config-file
        # setting, not a per-request one, and no new /api/v1 route is
        # allowed), so this is read-only display of the running process's
        # own setting.
        # Evidence-only mode never starts the watcher (watcher.start_if_enabled),
        # so the line must not claim "on" there even if watch_folders is set.
        "watch_enabled": get_settings().watch_folders and not get_settings().evidence_only,
    }


def _reports_context(runtime: Runtime, request: Request) -> dict:
    """Everything one render of the read-only S3 Reports screen needs."""
    reports = reports_screen.list_reports(db_path=runtime.db_path)
    active = _active(runtime)
    # S3's list spans every workspace at once (UX spec 8.1), so there is
    # no single content workspace to detect a script from the way S1's
    # active conversation or S2's selected detail have one -- the shell's
    # active workspace is the documented fallback (DECISIONS row).
    active_id = active.id if active else None
    return {
        "request": request,
        "dir": _direction(request, active_id),
        "lang": _lang(active_id),
        "current_screen": "reports",
        "busy": any(report.is_running for report in reports),
        "workspaces": screen.workspace_options(db_path=runtime.db_path),
        "active": active,
        "state": reports_screen.screen_state(report_count=len(reports)),
        "ReportsScreenState": reports_screen.ReportsScreenState,
        "reports": reports,
        # F-15. Independent of `reports`/`state` above -- see
        # ui/reports_screen.py's module note on why feedback is never
        # gated by the eval-run empty state. Pure SQLite reads, same as
        # `reports` itself, so this never loads the embedding model and
        # renders fine in evidence-only mode (ST-05).
        "feedback": reports_screen.list_feedback(db_path=runtime.db_path),
    }


_SLUG_UNSAFE = "\"'\\/:*?<>|\n\r\t "


def _slug(value: str) -> str:
    """A filename-safe stand-in for whatever the workspace was named --
    Content-Disposition's `filename=` breaks on quotes and path
    separators, and a workspace name is operator-chosen free text."""
    return "".join("-" if ch in _SLUG_UNSAFE else ch for ch in value) or "report"


async def _form(request: Request) -> dict[str, str]:
    """One posted form, decoded, with no third-party parser.

    WHY NOT FastAPI's `Form(...)` OR `await request.form()`: both require
    `python-multipart` -- FastAPI checks for it at import time and
    Starlette asserts on it inside `form()`, whatever the content type. It
    exists to parse `multipart/form-data`, which is the file-upload
    encoding, and Sanad has no upload: UX spec 13 rules out drag-and-drop
    file upload outright, "because workspaces point at folders on disk".
    So the package would be a dependency added for a format the product
    refuses to accept.

    This is NOT a hand-rolled parser. `urllib.parse.parse_qsl` is the
    standard library's own decoder for `application/x-www-form-urlencoded`
    -- percent-escapes, `+` for space, repeated keys and all. The only
    line of judgement here is the charset, and it is UTF-8 because that is
    what `base.html` declares and what a browser therefore encodes in.

    THE BODY IS READ IN BOUNDED CHUNKS rather than with
    `await request.body()`, which buffers whatever arrives before anything
    checks its size. The cap is generous next to the largest field this
    app has -- a question, bounded at `question_max_length` characters by
    openapi -- and it exists so that a client which keeps sending cannot
    grow this process's memory without limit. LD-07 binds the server to
    127.0.0.1 and PRD section 6 is single-user, so this is a guard rail
    rather than a defence against anyone; the reason to have it is that
    "nobody hostile can reach it" is an assumption about deployment, and
    the cheaper habit is not to rely on one."""
    seen = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        seen += len(chunk)
        if seen > MAX_FORM_BYTES:
            return {}
        chunks.append(chunk)
    body = b"".join(chunks).decode("utf-8", errors="replace")
    return dict(parse_qsl(body, keep_blank_values=True, encoding="utf-8"))


# Any short, non-blank string works: warm-up cares about walking the same
# loading path a question uses, not about the text itself, and the E5 and
# BM25 models are both loaded regardless of what string triggers them.
_WARM_UP_TEXT = "warm-up"


def _warm_up_models() -> None:
    """Load both search encoders once, off the request path.

    THE LIVE RUN, 2026-08-30 (BUILD-STATE): a fresh process's first
    question paid 23s loading `sentence-transformers` (dense E5) and
    `fastembed` (sparse BM25) with the server serving nothing else
    meanwhile. Calling the exact PUBLIC functions a real question goes
    through -- `embeddings.embed_query` and `embeddings.embed_sparse_query`,
    the same two `vector_store.hybrid_search` calls -- walks the identical
    `_load_model` / `_load_sparse_model` path, so the models a question
    finds are the ones this already loaded, not a second copy.

    Runs on its own daemon thread (see the lifespan below): this function
    itself blocks for the length of the load, and it must not hold up
    start-up or any request being served while it works.

    A FAILURE HERE IS LOGGED AND SWALLOWED, NEVER RAISED. This is a
    latency optimization, not a required step -- the first real question
    loads the model itself exactly as it did before this existed, so a
    warm-up that cannot finish (no network for a first-ever download, a
    corrupt cache, anything) must not take the server down with it."""
    started = time.monotonic()
    try:
        embeddings.embed_query(_WARM_UP_TEXT)
        embeddings.embed_sparse_query(_WARM_UP_TEXT)
    except Exception:  # noqa: BLE001 -- warm-up must never crash the server
        logger.exception(
            "model warm-up failed; the first question will load it instead"
        )
        return
    logger.info("model warm-up ready in %.1fs", time.monotonic() - started)


def create_app(runtime: Runtime | None = None) -> FastAPI:
    """Build the host. One function so tests get a real app, not a mock."""
    runtime = runtime or Runtime()

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> Iterator[None]:
        # THE REGISTRY MUST EXIST BEFORE THE FIRST PAGE RENDERS, and this
        # line was added after a real failure rather than from foresight:
        # on a machine with no `data/sanad.db`, `GET /` raised
        # `RegistryNotFoundError` instead of rendering "No workspace yet".
        # That is acceptance criterion 1's screen -- the FIRST thing a new
        # operator ever sees -- failing with a stack trace. `ensure_schema`
        # is idempotent, so an existing database is untouched.
        repo.ensure_schema(runtime.db_path)
        # A Sync or evaluation stranded by a killed process would otherwise
        # read Running forever (and a stranded Sync blocks every later one).
        # Recovery leaves an evaluation alone while another process still
        # holds the index -- that is the live command-line evaluator.
        recovered = recovery.recover_abandoned_runs(db_path=runtime.db_path)
        if recovered.sync_runs or recovered.evaluation_runs:
            logger.warning(
                "recovered %s abandoned sync run(s) and %s evaluation run(s)",
                recovered.sync_runs,
                recovered.evaluation_runs,
            )

        # ST-39: on the real server only (see `Runtime.warm_up`), load both
        # search encoders on a background thread now rather than paying for
        # it on the first real question. Daemon and fire-and-forget --
        # nothing here waits on it, which is what keeps start-up at ~2s.
        if runtime.warm_up:
            threading.Thread(
                target=_warm_up_models, daemon=True, name="sanad-warmup"
            ).start()

        # Reports and workspace metadata do not need Qdrant. Keeping the
        # embedded store closed here lets the separate evaluation command
        # own it while this server remains available to display progress.
        yield

    app = FastAPI(title="Sanad", lifespan=lifespan)
    app.state.runtime = runtime

    # ST-05 (Railway hosting). Installed ALWAYS, active only when a
    # password is configured. Adding it unconditionally is the point: a
    # gate you have to remember to switch on at deploy time is a gate that
    # gets forgotten exactly once. With `access_password` empty -- the
    # default, and what every test and every laptop gets -- this
    # middleware passes every request straight through, so ADR-13's
    # local-first behaviour is unchanged.
    app.add_middleware(AccessGate, password=get_settings().access_password)
    # Added after the gate, so it wraps it: a 401 page is in the visitor's
    # language too, and a valid ?lang= still sets its cookie.
    app.add_middleware(LanguageMiddleware)

    api_service = ApiService(runtime)
    app.include_router(build_router(api_service, version=APP_VERSION))

    @app.exception_handler(HTTPException)
    async def api_http_error(request: Request, exc: HTTPException) -> Response:
        if request.url.path.startswith("/api/v1") and isinstance(exc.detail, dict):
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def api_validation_error(request: Request, exc: RequestValidationError) -> Response:
        if request.url.path.startswith("/api/v1"):
            detail = [
                {field: issue[field] for field in ("loc", "msg", "type")}
                for issue in exc.errors()
            ]
            return JSONResponse(status_code=422, content={"detail": detail})
        return await request_validation_exception_handler(request, exc)

    contract = yaml.safe_load(OPENAPI_CONTRACT.read_text(encoding="utf-8"))
    app.openapi = lambda: contract
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES))
    # F-14: lets a template ask, per element, "is this piece of text
    # Arabic?" so a `dir="auto"` message bubble or search-query line can
    # also carry `lang="ar"` when it truly is one (see `ui.rtl.text_is_arabic`
    # docstring for why this is decided at render time, not stored).
    templates.env.globals["is_arabic"] = rtl.text_is_arabic
    # Stored ISO timestamps rendered for people (S2 sync times, S3 report
    # dates, feedback dates); see ui.screen.format_when.
    # S6 interface language. Every template reads the request's language
    # through these, so no context builder has to pass it along.
    @jinja2.pass_context
    def _t(ctx, key, **params):
        return i18n.translate(context_language(ctx["request"]), key, **params)

    @jinja2.pass_context
    def _th(ctx, key, **params):
        return i18n.translate_markup(context_language(ctx["request"]), key, **params)

    @jinja2.pass_context
    def _tx(ctx, text):
        return i18n.translate_text(context_language(ctx["request"]), text)

    @jinja2.pass_context
    def _ui_lang(ctx):
        return context_language(ctx["request"])

    @jinja2.pass_context
    def _language_links(ctx):
        return language_links(ctx["request"])

    @jinja2.pass_context
    def _when(ctx, value):
        return screen.format_when(value, context_language(ctx["request"]))

    @jinja2.pass_context
    def _js_strings(ctx):
        return i18n.js_strings(context_language(ctx["request"]))

    templates.env.globals.update(t=_t, th=_th, tx=_tx, ui_lang=_ui_lang,
                                 language_links=_language_links, js_strings=_js_strings)
    templates.env.filters["when"] = _when
    # S6: an answer's bold, lists and tables, with HTML, links and images off.
    templates.env.filters["answer_html"] = render_answer

    def render(request: Request, name: str = "chat.html") -> HTMLResponse:
        return templates.TemplateResponse(request, name, _context(runtime, request))

    @app.get("/", response_class=HTMLResponse)
    def chat(request: Request) -> HTMLResponse:
        """S1. UX spec 4 / acceptance criterion 1: with no workspace at
        all, S2 is the landing screen -- so this redirects there rather
        than rendering a local stand-in, now that ST-28 gives S2 somewhere
        real to send the operator.

        Checks `workspace_options` directly rather than `_active(runtime)
        is None`: F-12's routing mode also makes `_active` return None
        while workspaces exist, and that case renders S1 (asking a
        question and getting proposed a workspace), it does not redirect
        away from it."""
        if not screen.workspace_options(db_path=runtime.db_path):
            return RedirectResponse("/workspaces", status_code=SEE_OTHER)
        return render(request)

    @app.get("/chat/messages", response_class=HTMLResponse)
    def messages(request: Request) -> HTMLResponse:
        """The conversation area alone, for the poll to swap in.

        The same partial the full page includes, so a stage hint or a
        finished answer cannot render one way inside the page and another
        way through the poll."""
        return render(request, "_conversation.html")

    @app.post("/chat/ask")
    async def ask(request: Request) -> Response:
        # `_form`, not FastAPI's `Form(...)` and not Starlette's
        # `request.form()`: both require `python-multipart`. See `_form`.
        form = await _form(request)
        # F-12: the confirmation bubble's buttons post the SAME action with
        # an extra `workspace_id` field, naming which candidate to answer
        # from. Ordinary asks never carry this field, so `form.get`
        # returns None and nothing here changes for them.
        return _start(runtime, form.get("question", ""), form.get("workspace_id") or None)

    @app.post("/chat/cancel")
    def cancel(request: Request) -> Response:
        key = _conversation_key(runtime)
        if key is not None:
            run = runtime.conversation(key).run
            if run is not None:
                run.cancel()
        return RedirectResponse("/", status_code=SEE_OTHER)

    @app.post("/chat/new")
    def new_conversation(request: Request) -> Response:
        key = _conversation_key(runtime)
        if key is not None:
            runtime.conversation(key).reset()
        return RedirectResponse("/", status_code=SEE_OTHER)

    @app.post("/chat/feedback")
    async def feedback_route(request: Request) -> Response:
        """F-15: thumbs up/down plus an optional comment on one answer or
        refusal. Plain POST-redirect-GET, exactly like `/chat/ask` above
        (CR-02) -- a real `<form>` per button in `_conversation.html`, no
        script required.

        NOT an /api/v1 route on purpose: docs/phase2/openapi.yaml is
        signed and F-15 is V2, and `tests/integration/test_api.py`'s
        route-inventory test only enumerates `/api/v1/*`, so this needs no
        contract change (recorded in DECISIONS.md).

        EVIDENCE-ONLY MODE (ST-05): refused here, explicitly, rather than
        relying on the fact that no ANSWER/REFUSAL message can exist in
        that mode today (`Runtime.ports` already raises before a question
        is ever asked). Harmless either way -- no row is written -- but an
        explicit check does not depend on that coincidence surviving a
        later change, the same reasoning `watcher.start_if_enabled`
        gives for re-checking the flag itself. No error is surfaced: the
        controls this posts from never render in evidence-only mode (no
        answer ever exists to attach them to), so a rejection reaching a
        real user here would mean something forged the request, not that
        it made a normal mistake.
        """
        form = await _form(request)
        workspace_id = form.get("workspace_id", "")
        if get_settings().evidence_only:
            return RedirectResponse("/", status_code=SEE_OTHER)
        message_id = form.get("message_id", "")
        verdict = form.get("verdict", "")
        comment = form.get("comment") or None
        conversation = runtime.conversations.get(workspace_id)
        messages = conversation.messages if conversation is not None else []
        try:
            feedback_module.submit_feedback(
                messages=messages,
                workspace_id=workspace_id,
                message_id=message_id,
                verdict=verdict,
                comment=comment,
                db_path=runtime.db_path,
            )
        except feedback_module.UnknownAnswerError:
            runtime.feedback_errors[workspace_id] = (
                "This answer is no longer on screen, so feedback could "
                "not be saved."
            )
        except feedback_module.CommentTooLongError as exc:
            runtime.feedback_errors[workspace_id] = (
                "Feedback could not be saved: the comment is longer than "
                f"{exc.max_chars} characters."
            )
        except feedback_module.InvalidVerdictError:
            runtime.feedback_errors[workspace_id] = (
                "Feedback could not be saved: invalid response."
            )
        else:
            runtime.feedback_errors.pop(workspace_id, None)
        return RedirectResponse("/", status_code=SEE_OTHER)

    @app.post("/workspace")
    async def switch(request: Request) -> Response:
        """UX spec 4: changing the workspace "clears nothing and interrupts
        nothing". The conversation for each workspace is kept, so switching
        away and back returns to the transcript that was there.

        The same sentence continues: "but the chat area shows a one-line
        notice that the conversation context has moved". That notice is
        carried on the redirect as `?moved=1` rather than in server state,
        because it belongs to ONE render -- a flag on the Runtime would
        still be set when the operator came back to this screen an hour
        later, announcing a move that happened long ago."""
        form = await _form(request)
        chosen = form.get("workspace_id", "") or None
        # F-12: the sentinel is only a real choice with something to route
        # between (base.html only offers the option then). A posted
        # sentinel below that count -- a stale page, or a hand-crafted
        # form -- is treated as "not chosen" rather than trusted at face
        # value, so the shell cannot be stranded in routing mode with
        # nothing left to route between.
        if chosen == screen.ROUTE_SENTINEL and len(
            screen.workspace_options(db_path=runtime.db_path)
        ) < 2:
            chosen = None
        moved = chosen is not None and chosen != (
            _active(runtime).id if _active(runtime) else None
        )
        runtime.active_workspace_id = chosen
        return RedirectResponse(
            "/?moved=1" if moved else "/", status_code=SEE_OTHER
        )

    @app.get(
        "/chat/passage/{workspace_id}/{message}/{index}", response_class=HTMLResponse
    )
    def passage(
        request: Request, workspace_id: str, message: int, index: int
    ) -> HTMLResponse:
        """One source card's sections, as a page of their own.

        The no-JavaScript path for the passage viewer: the card is a real
        link, so it works with scripting off, and `ui/static/sanad.js`
        upgrades it to the `<dialog>` overlay UX spec 5 asks for. Both
        render `_passage.html`, so there is one description of a passage
        and not two.

        ADDRESSED BY WORKSPACE, THEN MESSAGE, THEN CARD. Every one of the
        three is load-bearing and each was added after the previous
        addressing scheme was shown to open the wrong text:

        * by card alone, an older answer's card opened the NEWEST answer's
          section, because every answer keeps its own cards visible (UX
          spec 6.2);
        * by message and card, the link resolved against whatever
          workspace was ACTIVE when it was followed -- so switching
          workspace and pressing Back served message 3, card 1 of a
          different conversation entirely.

        Both failures look completely correct on screen, which is what
        makes them worth the extra path segment: the reader has no way to
        tell they are reading the wrong document's section."""
        conversation = runtime.conversations.get(workspace_id)
        messages = conversation.messages if conversation else []
        card = None
        if 0 <= message < len(messages):
            cards = messages[message].sources
            if 0 <= index < len(cards):
                card = cards[index]
        return templates.TemplateResponse(
            request, "passage.html", {**_context(runtime, request), "card": card}
        )

    @app.get("/workspaces", response_class=HTMLResponse)
    def workspaces_screen_route(request: Request) -> HTMLResponse:
        """S2 (ST-28): the workspace list, the detail region, Sync."""
        return templates.TemplateResponse(
            request, "workspaces.html", _ws_context(runtime, request)
        )

    @app.get("/workspaces/panel", response_class=HTMLResponse)
    def workspaces_panel(request: Request) -> HTMLResponse:
        """The detail region alone, for the poll to swap in while a Sync
        runs -- the same reason `/chat/messages` exists for S1: one
        template renders both the full page and the poll target, so a
        report cannot look different depending on how it arrived."""
        return templates.TemplateResponse(
            request, "_workspace_detail.html", _ws_context(runtime, request)
        )

    @app.post("/workspaces")
    async def create_workspace_route(request: Request) -> Response:
        form = await _form(request)
        submitted = {
            "name": form.get("name", ""),
            "folder_path": form.get("folder_path", ""),
            "legal_flag": form.get("legal_flag") == "on",
        }
        try:
            created = workspaces.create_workspace(db_path=runtime.db_path, **submitted)
        except workspaces.WorkspaceError as exc:
            return templates.TemplateResponse(
                request,
                "workspaces.html",
                {
                    **_ws_context(runtime, request),
                    "form_error": str(exc),
                    "form_values": submitted,
                },
                status_code=422,
            )
        runtime.active_workspace_id = created.id
        return RedirectResponse(f"/workspaces?ws={created.id}", status_code=SEE_OTHER)

    @app.post("/workspaces/{workspace_id}/rename")
    async def rename_workspace_route(request: Request, workspace_id: str) -> Response:
        form = await _form(request)
        try:
            workspaces.rename_workspace(
                workspace_id=workspace_id,
                new_name=form.get("name", ""),
                db_path=runtime.db_path,
            )
        except workspaces.WorkspaceError as exc:
            return templates.TemplateResponse(
                request,
                "workspaces.html",
                {
                    **_ws_context(runtime, request, selected_override=workspace_id),
                    "form_error": str(exc),
                },
                status_code=422,
            )
        return RedirectResponse(f"/workspaces?ws={workspace_id}", status_code=SEE_OTHER)

    @app.post("/workspaces/{workspace_id}/legal-flag")
    async def legal_flag_route(request: Request, workspace_id: str) -> Response:
        form = await _form(request)
        try:
            workspaces.set_legal_flag(
                workspace_id=workspace_id,
                legal_flag=form.get("legal_flag") == "on",
                db_path=runtime.db_path,
            )
        except workspaces.WorkspaceNotFoundError:
            pass
        return RedirectResponse(f"/workspaces?ws={workspace_id}", status_code=SEE_OTHER)

    @app.get("/workspaces/{workspace_id}/delete", response_class=HTMLResponse)
    def confirm_delete_workspace(request: Request, workspace_id: str) -> Response:
        """The no-JS `ConfirmDialog` (UX spec 5, 7.2): a real page, so a
        destructive action always needs a deliberate second step even with
        scripting off, never a hand-rolled focus trap that only works with
        it on."""
        try:
            target = workspaces.get_workspace(workspace_id=workspace_id, db_path=runtime.db_path)
        except workspaces.WorkspaceNotFoundError:
            return RedirectResponse("/workspaces", status_code=SEE_OTHER)
        return templates.TemplateResponse(
            request,
            "workspace_delete_confirm.html",
            {**_ws_context(runtime, request), "target": target},
        )

    @app.post("/workspaces/{workspace_id}/delete")
    def delete_workspace_route(request: Request, workspace_id: str) -> Response:
        def refused(message: str) -> Response:
            try:
                target = workspaces.get_workspace(
                    workspace_id=workspace_id, db_path=runtime.db_path
                )
            except workspaces.WorkspaceNotFoundError:
                return RedirectResponse("/workspaces", status_code=SEE_OTHER)
            return templates.TemplateResponse(
                request,
                "workspace_delete_confirm.html",
                {
                    **_ws_context(runtime, request),
                    "target": target,
                    "delete_error": message,
                },
                status_code=409,
            )

        # A delete beside a running Sync of the same workspace drops the
        # collection while the Sync keeps writing; its next file quietly
        # re-creates the collection, leaving index data no registry row
        # names -- the state `sync.delete_workspace` calls unrecoverable.
        # Refused here, now that operations share the index instead of
        # queueing behind one lock (review of d790e05).
        with repo.session(runtime.db_path) as conn:
            running = repo.get_running_sync_run(conn, workspace_id)
        if running is not None:
            return refused(
                "This workspace cannot be deleted while a Sync of it is running. "
                "Cancel the Sync or wait for it to finish, then try again."
            )
        try:
            with runtime.store() as client:
                sync.delete_workspace(
                    workspace_id=workspace_id,
                    db_path=runtime.db_path,
                    client=client,
                )
        except vector_store.StoreAlreadyOpenError:
            return refused(
                "This workspace cannot be deleted while its document index is "
                "in use by the evaluation command. Wait for it to finish, then "
                "try again."
            )
        except workspaces.WorkspaceNotFoundError:
            pass
        runtime.sync_errors.pop(workspace_id, None)
        runtime.last_sync_run_id.pop(workspace_id, None)
        runtime.conversations.pop(workspace_id, None)
        if runtime.active_workspace_id == workspace_id:
            runtime.active_workspace_id = None
        return RedirectResponse("/workspaces", status_code=SEE_OTHER)

    @app.post("/workspaces/{workspace_id}/sync")
    def start_sync_route(request: Request, workspace_id: str) -> Response:
        """Start a Sync in the background and return immediately, mirroring
        `ui.runs.Run.start` -- the request thread never blocks for the
        length of a run. The double-sync refusal (F-02, UX spec 7.3:
        "blocked with a message, first run continues") is the claim
        `Runtime.start_sync` makes in THIS thread, so the operator who
        clicked sees it; see that method for why the claim moved here."""
        try:
            runtime.start_sync(workspace_id)
        except sync.EvidenceOnlyError as exc:
            # Reuses `sync_errors`, the channel the S2 panel already
            # renders (PRD section 11's "Sync could not run" box), so this
            # needs no new template and no new state -- the operator sees
            # the same box a missing folder produces, carrying a sentence
            # that explains the limit instead of a path.
            runtime.sync_errors[workspace_id] = str(exc)
            return RedirectResponse(
                f"/workspaces?ws={workspace_id}", status_code=SEE_OTHER
            )
        except sync.SyncInProgressError:
            return RedirectResponse(
                f"/workspaces?ws={workspace_id}&sync_blocked=1", status_code=SEE_OTHER
            )
        except workspaces.WorkspaceNotFoundError:
            return RedirectResponse("/workspaces", status_code=SEE_OTHER)
        return RedirectResponse(f"/workspaces?ws={workspace_id}", status_code=SEE_OTHER)

    @app.post("/workspaces/{workspace_id}/sync/cancel")
    def cancel_sync_route(workspace_id: str) -> Response:
        event = runtime.sync_cancel_events.get(workspace_id)
        if event is not None:
            event.set()
        return RedirectResponse(f"/workspaces?ws={workspace_id}", status_code=SEE_OTHER)

    @app.get("/reports", response_class=HTMLResponse)
    def reports_route(request: Request) -> HTMLResponse:
        """S3 (ST-34): the list of evaluation runs `scripts/run_evaluation.py`
        has already written. Read-only -- see ui/reports_screen.py for why
        there is no "run now" action here."""
        return templates.TemplateResponse(
            request, "reports.html", _reports_context(runtime, request)
        )

    @app.get("/reports/{eval_run_id}", response_class=HTMLResponse)
    def report_detail_route(request: Request, eval_run_id: str) -> HTMLResponse:
        detail = reports_screen.report_detail(eval_run_id, db_path=runtime.db_path)
        return templates.TemplateResponse(
            request,
            "report_detail.html",
            {
                **_reports_context(runtime, request),
                "detail": detail,
                "eval_run_id": eval_run_id,
                "busy": detail is not None and detail.summary.is_running,
            },
            status_code=404 if detail is None else 200,
        )

    @app.get("/reports/{eval_run_id}/export")
    def report_export_route(eval_run_id: str) -> Response:
        """UX spec 8.2: "the action states what it produces before it
        runs" -- report_detail.html's link says "Markdown for the report
        annex" before this is ever followed; this route only produces
        exactly that. A plain link with no JavaScript (CR-02): the
        browser's own download handling is the whole delivery mechanism."""
        detail = reports_screen.report_detail(eval_run_id, db_path=runtime.db_path)
        if detail is None:
            return Response(
                f"No such report: {eval_run_id}",
                status_code=404,
                media_type="text/plain; charset=utf-8",
            )
        body = reports_screen.export_markdown(detail)
        run_at_safe = detail.summary.run_at.replace(":", "-")
        filename = f"sanad-eval-{_slug(detail.summary.workspace_name)}-{run_at_safe}.md"
        return Response(
            body,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app


def _start(
    runtime: Runtime, question: str, workspace_override: str | None = None
) -> Response:
    """Put one question in flight (or say why it cannot be).

    The user's message is appended HERE rather than by the worker, so the
    transcript shows what was asked the instant the page comes back --
    before any stage hint, and even if the run fails on its first call.

    `workspace_override` (F-12) is a confirmation button's chosen
    workspace id. Applied BEFORE `_active` is read, and only when it names
    a real workspace, so confirming a proposal both answers from that
    workspace AND makes it the selected one (the F-12 card's own words) in
    one step -- a stale or hand-crafted id is silently ignored rather than
    switching the shell to nothing, and the request then falls through to
    ordinary routing-mode handling exactly as if nothing had been chosen."""
    options = screen.workspace_options(db_path=runtime.db_path)
    if workspace_override and any(opt.id == workspace_override for opt in options):
        runtime.active_workspace_id = workspace_override

    active = _active(runtime)
    if active is None:
        if options:
            return _start_routing(runtime, question, options)
        return RedirectResponse("/", status_code=SEE_OTHER)
    conversation = runtime.conversation(active.id)
    asked = question.strip()
    # A blank submit is not an error to show the operator; the input is
    # `required` and an empty box means they pressed Send by accident.
    # `ask` would raise on it (openapi AskRequest, minLength 1) and that
    # would print an error panel for a question nobody asked.
    if not asked:
        return RedirectResponse("/", status_code=SEE_OTHER)
    run = Run(
        question=asked,
        workspace_id=active.id,
        session_id=None,
        legal_workspace=active.legal_flag,
    )
    # THE CHECK AND THE CLAIM IN ONE STEP. Reading `busy` here and
    # assigning `conversation.run` on the next line is a race the screen
    # produces on its own: Starlette runs these routes on a threadpool, so
    # two Sends milliseconds apart both passed and both started a worker.
    # The first then ran to completion, spent a real provider call, and
    # had its answer discarded. See `Conversation.begin`.
    if not conversation.begin(run, asked):
        return RedirectResponse("/", status_code=SEE_OTHER)
    # The worker enters this context itself, so embedded Qdrant stays open
    # through every split query and closes only after the answer settles.
    # Opening errors reach the same visible ErrorPanel as model-call errors.
    run.start_with(runtime.ports())
    return RedirectResponse("/", status_code=SEE_OTHER)


def _start_routing(
    runtime: Runtime, question: str, options: list[screen.WorkspaceOption]
) -> Response:
    """F-12: propose a workspace instead of answering, when none is
    selected.

    Runs synchronously in the request thread, unlike `_start`'s worker
    thread -- routing is one embedding call plus one vector search per
    workspace (`ui.routing.propose_workspace`), never a model call, so
    there is no long operation to move off the request path and no stage
    to show while it runs.

    Evidence-only mode refuses through `Runtime.routing_client`, the same
    exception (`agent.chat.ChatUnavailableError`) and the same sentence
    `Runtime.ports()` uses for chat -- one refusal path, not a second one
    invented for routing."""
    asked = question.strip()
    if not asked:
        return RedirectResponse("/", status_code=SEE_OTHER)
    conversation = runtime.conversation(screen.ROUTE_SENTINEL)
    # The length bound is normally enforced by the graph when a run starts
    # (agent/graph.py). Routing never starts a run, so without this an
    # over-long question would be proposed a workspace and only fail after
    # the operator confirmed. Same sentence as the graph's.
    max_length = get_settings().question_max_length
    if len(asked) > max_length:
        too_long = ValueError(
            f"a question may be at most {max_length} characters "
            f"(openapi AskRequest.question); this one is {len(asked)}."
        )
        conversation.append_system(error_message(too_long, asked))
        return RedirectResponse("/", status_code=SEE_OTHER)

    def propose() -> Message:
        with runtime.routing_client() as client:
            candidates = routing.propose_workspace(
                client, options=options, question=asked
            )
        return route_proposal_message(asked, candidates)

    try:
        # The return value (False means a run is already in flight for this
        # conversation, see `Conversation.begin_route`) needs no separate
        # branch: every outcome here, including that race, redirects to "/"
        # the same way `_start` redirects on its own equivalent race.
        conversation.begin_route(asked, propose)
    except ChatUnavailableError as exc:
        # `begin_route` already appended the user's question before
        # `propose` raised (see there); this is the same ErrorPanel a
        # failed real answer gets, just appended directly rather than
        # through a `Run` that never existed for routing.
        conversation.append_system(error_message(exc, asked))
    return RedirectResponse("/", status_code=SEE_OTHER)


app = create_app()


def main() -> None:
    settings = get_settings()
    # ST-39: a fresh `Runtime` with warm-up ON, rather than reusing the
    # module-level `app` above -- that one keeps `warm_up=False` so any
    # other importer of this module (every test in this codebase builds its
    # own `Runtime` directly) never downloads a model by accident. Only the
    # real server built here does.
    #
    # ST-05: EXCEPT in evidence-only mode. Warm-up loads the full
    # embedding model on a background thread, and `config.evidence_only`
    # exists precisely because that model does not fit this container's
    # memory limit -- warming it up would still spend the memory and still
    # get the process killed, just before the first question does instead
    # of because of it. `Runtime.ports()` already refuses every question
    # in this mode, so there is nothing for a warm model to serve.
    real_app = create_app(Runtime(warm_up=not settings.evidence_only))
    runtime: Runtime = real_app.state.runtime
    # F-13: the one seam that starts the folder-watching poller at all.
    # `start_if_enabled` re-checks `evidence_only` itself (never started
    # on a memory-capped container, `watch_folders` notwithstanding) and
    # is a no-op unless `watch_folders` is also on -- see there.
    watcher_thread = watcher.start_if_enabled(
        settings, db_path=runtime.db_path, trigger=runtime.start_sync
    )
    try:
        # 127.0.0.1 only (ADR-13, LD-07): single user, no authentication, and
        # nothing about this server is safe to expose on a network.
        uvicorn.run(real_app, host=settings.server_host, port=settings.server_port)
    finally:
        if watcher_thread is not None:
            watcher_thread.stop()


if __name__ == "__main__":
    main()
