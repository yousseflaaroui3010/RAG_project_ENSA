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

import vector_store
from agent.ports import AgentPorts
from config import get_settings
from db import repo
from ui import screen
from ui.conversation import Conversation, MessageKind
from ui.ports import build_default_ports
from ui.runs import Run

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
        """S1. Also the landing screen, which UX spec 4 only makes S2 when
        no workspace exists -- and the no-workspace state is rendered
        here, with navigation to S1 disabled and the reason stated,
        because S2 itself arrives with ST-28."""
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
