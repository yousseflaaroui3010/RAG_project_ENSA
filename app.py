"""The Sanad host: FastAPI serving the server-rendered screens (CR-02).

`uv run python app.py` starts it, per architecture 12.1 step 5.

SCOPE, because this file will grow and the next story owns half of it.
ST-27 builds S1, the chat screen, and the template routes it needs.
ST-51 adds the `/api/v1` surface from docs/phase2/openapi.yaml and mounts
it on this same host, delegate-only; its exit gate is "UI unchanged when
mounted", which is why the screen routes live under their own prefix and
nothing here answers on `/api`.

WHY THE ROUTES ARE THIN. docs/phase2/CLAUDE.md's rule is "no business
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
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import sync
import vector_store
import workspaces
from agent.ports import AgentPorts
from config import get_settings
from db import repo
from ui import screen, workspaces_screen
from ui.conversation import Conversation, MessageKind
from ui.ports import build_default_ports
from ui.runs import Run

logger = logging.getLogger(__name__)

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "ui" / "templates"
STATIC = HERE / "ui" / "static"

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
    conversations: dict[str, Conversation] = field(default_factory=dict)
    active_workspace_id: str | None = None
    client: Any = None
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

    def ports(self) -> AgentPorts:
        if self.ports_factory is None:
            return build_default_ports(self.client)
        return self.ports_factory()

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
    selector showing nothing while workspaces exist is a broken shell."""
    options = screen.workspace_options(db_path=runtime.db_path)
    if not options:
        return None
    chosen = next(
        (opt for opt in options if opt.id == runtime.active_workspace_id), None
    )
    return chosen or options[0]


def _direction(request: Request) -> str:
    """The RTL PREVIEW UX spec 6.5 asks for, and nothing more.

    "Verify with an RTL preview even though V1 ships LTR, per PRD section
    5." A preview is what makes acceptance criterion 11 checkable at all
    -- without one, "layout mirrors under a right-to-left locale" can only
    ever be inspected by hand in a browser's devtools, and open risk 3
    already says RTL "is specified but never exercised until a late
    preview".

    This is deliberately NOT a locale switch. There is no Arabic copy, no
    translation layer and no language negotiation; assumption 3 in UX spec
    14 fixes the interface copy as English for V1, and ST-38 owns actually
    exercising RTL. All this does is set the `dir` attribute so the
    stylesheet's logical properties can be seen doing their job.

    Anything that is not "rtl" is "ltr", including a missing, empty or
    hostile value -- the attribute is written straight into the document
    element and only these two strings may ever reach it."""
    return "rtl" if request.query_params.get("dir") == "rtl" else "ltr"


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
    if active is not None:
        documents = screen.answerable_documents(active.id, db_path=runtime.db_path)
        conversation = runtime.conversation(active.id)
        conversation.settle(legal_workspace=active.legal_flag)
    state = screen.state_for(
        options=options,
        documents=documents,
        has_messages=bool(conversation and conversation.messages),
    )
    run = conversation.run if conversation else None
    busy = bool(conversation and conversation.busy)
    return {
        "request": request,
        "dir": _direction(request),
        "current_screen": "chat",
        # UX spec 4: "Changing it clears nothing and interrupts nothing,
        # but the chat area shows a one-line notice that the conversation
        # context has moved."
        "moved": request.query_params.get("moved") == "1",
        # openapi AskRequest bounds the question, and config.py is where
        # that bound lives (docs/phase2/CLAUDE.md: no magic literals in
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
        "stage_label": run.stage_label if (run and busy) else "",
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

    if selected_id is not None:
        selected = workspaces.get_workspace(workspace_id=selected_id, db_path=runtime.db_path)
        with repo.session(runtime.db_path) as conn:
            running = repo.get_running_sync_run(conn, selected_id)
            if running is not None:
                # Cache it NOW, while the row is still findable by the
                # `finished_at IS NULL` query -- once it finishes this is
                # the only place its id survives (see the Runtime field).
                runtime.last_sync_run_id[selected_id] = running["id"]
                running_count = len(repo.list_sync_items(conn, running["id"]))
            else:
                last_id = runtime.last_sync_run_id.get(selected_id)
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
        "dir": _direction(request),
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
        "sync_blocked": request.query_params.get("sync_blocked") == "1",
        "sync_error": runtime.sync_errors.get(selected_id) if selected_id else None,
        "file_rows": rows,
        "sort": request.query_params.get("sort"),
        "sort_dir": request.query_params.get("dir", "asc"),
        "report_finished_at": report_finished_at,
        "form_error": None,
        "form_values": None,
        "name_min_length": get_settings().workspace_name_min_length,
        "name_max_length": get_settings().workspace_name_max_length,
    }


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

        # ONE Qdrant client for the process (ADR-04). `open_store` raises
        # on a second client for the same path, so opening it here -- and
        # only here -- is what keeps that promise for the whole server.
        # A runtime that already carries a client is a test's, and is
        # left alone.
        if runtime.client is not None or runtime.ports_factory is not None:
            yield
            return
        with vector_store.open_store() as client:
            runtime.client = client
            yield
        runtime.client = None

    app = FastAPI(title="Sanad", lifespan=lifespan)
    app.state.runtime = runtime
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES))

    def render(request: Request, name: str = "chat.html") -> HTMLResponse:
        return templates.TemplateResponse(request, name, _context(runtime, request))

    @app.get("/", response_class=HTMLResponse)
    def chat(request: Request) -> HTMLResponse:
        """S1. UX spec 4 / acceptance criterion 1: with no workspace at
        all, S2 is the landing screen -- so this redirects there rather
        than rendering a local stand-in, now that ST-28 gives S2 somewhere
        real to send the operator."""
        if _active(runtime) is None:
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
        return _start(runtime, form.get("question", ""))

    @app.post("/chat/cancel")
    def cancel(request: Request) -> Response:
        active = _active(runtime)
        if active is not None:
            run = runtime.conversation(active.id).run
            if run is not None:
                run.cancel()
        return RedirectResponse("/", status_code=SEE_OTHER)

    @app.post("/chat/new")
    def new_conversation(request: Request) -> Response:
        active = _active(runtime)
        if active is not None:
            runtime.conversation(active.id).reset()
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
        try:
            sync.delete_workspace(
                workspace_id=workspace_id, db_path=runtime.db_path, client=runtime.client
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
        length of a run.

        THE DOUBLE-SYNC CHECK IS HERE, BEFORE THE THREAD STARTS, on
        purpose (F-02, UX spec 7.3: "blocked with a message, first run
        continues"). `sync_workspace` itself refuses a second concurrent
        run too (`SyncInProgressError`), but that refusal would fire
        inside the background thread where nothing reads it back to this
        request -- this pre-check is what turns "blocked" into a message
        the operator who clicked Sync actually sees. The tiny window
        between this read and the thread's own claim is the same one
        `sync._claim_sync_run`'s docstring already names and accepts."""
        with repo.session(runtime.db_path) as conn:
            running = repo.get_running_sync_run(conn, workspace_id)
        if running is not None:
            return RedirectResponse(
                f"/workspaces?ws={workspace_id}&sync_blocked=1", status_code=SEE_OTHER
            )
        runtime.sync_errors.pop(workspace_id, None)

        def _work() -> None:
            try:
                report = sync.sync_workspace(
                    workspace_id=workspace_id,
                    db_path=runtime.db_path,
                    client=runtime.client,
                )
            except Exception as exc:  # noqa: BLE001 -- mirrors _start's own catch-all
                # PRD section 11: "folder missing or unreadable shows the
                # exact path plus a fix hint" -- `FolderNotFoundError`'s
                # own message already carries both, so it is shown as-is
                # rather than re-worded here.
                logger.exception("sync failed for workspace %s", workspace_id)
                runtime.sync_errors[workspace_id] = str(exc)
            else:
                # THE LOAD-BEARING LINE, not a nicety: `sync_workspace`
                # hands back its own `sync_run_id` on the SyncReport it
                # returns, so the finished report is reachable even when
                # nobody polled while it was running (a small corpus can
                # finish before any request ever observes it as running,
                # which is exactly the gap a poll-only cache would have
                # -- proven by a real run in
                # tests/integration/test_s2_workspaces_screen.py).
                runtime.last_sync_run_id[workspace_id] = report.sync_run_id

        threading.Thread(target=_work, daemon=True, name="sanad-sync").start()
        return RedirectResponse(f"/workspaces?ws={workspace_id}", status_code=SEE_OTHER)

    return app


def _start(runtime: Runtime, question: str) -> Response:
    """Put one question in flight (or say why it cannot be).

    The user's message is appended HERE rather than by the worker, so the
    transcript shows what was asked the instant the page comes back --
    before any stage hint, and even if the run fails on its first call."""
    active = _active(runtime)
    if active is None:
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
        session_id=conversation.session_id,
        history=tuple(conversation.turns),
    )
    # THE CHECK AND THE CLAIM IN ONE STEP. Reading `busy` here and
    # assigning `conversation.run` on the next line is a race the screen
    # produces on its own: Starlette runs these routes on a threadpool, so
    # two Sends milliseconds apart both passed and both started a worker.
    # The first then ran to completion, spent a real provider call, and
    # had its answer discarded. See `Conversation.begin`.
    if not conversation.begin(run, asked):
        return RedirectResponse("/", status_code=SEE_OTHER)
    try:
        ports = runtime.ports()
    except Exception as exc:  # noqa: BLE001
        # UX spec 11, "answering service unreachable": the model could not
        # even be built -- no key, or a mode that is not one of the two
        # names. `Run` never starts, so the screen settles straight into
        # the error panel with the sentence `ChatUnavailableError` wrote.
        run.fail(exc)
        return RedirectResponse("/", status_code=SEE_OTHER)
    run.start(ports)
    return RedirectResponse("/", status_code=SEE_OTHER)


app = create_app()


def main() -> None:
    settings = get_settings()
    # 127.0.0.1 only (ADR-13, LD-07): single user, no authentication, and
    # nothing about this server is safe to expose on a network.
    uvicorn.run(app, host=settings.server_host, port=settings.server_port)


if __name__ == "__main__":
    main()
