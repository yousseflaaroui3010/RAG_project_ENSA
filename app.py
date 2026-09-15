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
import functools
import hashlib
import hmac
import json
import logging
import secrets
import sqlite3
import threading
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, unquote

import jinja2
import uvicorn
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import chat_history
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
from ui import (
    admin_screen,
    auth,
    documents,
    i18n,
    oidc,
    reports_screen,
    routing,
    rtl,
    screen,
    workspaces_screen,
)
from ui import feedback as feedback_module
from ui.access_gate import AccessGate
from ui.answer_format import render_answer
from ui.auth_gate import AuthGate
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


@functools.cache
def _static_url(name: str) -> str:
    """`/static/<name>?v=<first 12 hex of its SHA-256>`.

    Found by watching the S6 streaming draft freeze in a real browser: the
    page was new and `sanad.js` was the copy the browser had cached hours
    earlier, from before the draft code existed. A fingerprint of the
    file's own bytes changes exactly when the file does, so a deploy can
    never pair new templates with an old script or stylesheet. Read once
    per process; a changed file ships with a restart anyway."""
    digest = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:12]
    return f"/static/{name}?v={digest}"
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
    # S6: the Keycloak seam. None means "build the configured one"; tests
    # pass a scripted fake, exactly as they pass a scripted chat model.
    oidc_provider: Any = None
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
    # S6 saved chat history concurrency (cold review). One lock per person,
    # never a global one, so two different people's saves never wait on
    # each other -- created lazily and guarded by `_person_locks_guard`
    # itself (a dict of locks, guarded by one lock, per `_person_lock`).
    # The guard against a save resurrecting a concurrent delete is NOT a
    # counter: every delete drops the in-memory `Conversation` inside this
    # lock, and a save writes only if the object it snapshotted is still
    # the live one (see `save_conversation`).
    _person_locks: dict[str, threading.Lock] = field(
        default_factory=dict, repr=False, compare=False
    )
    _person_locks_guard: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False
    )
    # Test-only seam: if set, called between snapshotting a transcript and
    # taking the person lock to write it, so a test can deterministically
    # run a delete in that exact gap (a real thread race is not
    # reproducible on demand). None in every real run.
    _save_hook: Any = field(default=None, repr=False, compare=False)
    # Test-only seam, the other side of the same race (second cold review):
    # called by both deletes INSIDE the person lock, after BOTH the stored
    # row and the in-memory copy are gone and before the lock is released,
    # so a test can check that nothing of the person is left at that moment
    # and start a save there. None in every real run.
    _delete_hook: Any = field(default=None, repr=False, compare=False)

    def _person_lock(self, user_id: str) -> threading.Lock:
        """The one lock for this person's saved-history writes, created on
        first use. Guarded by `_person_locks_guard` so two threads racing
        to create the FIRST lock for a brand new user cannot each end up
        with a different Lock object -- which would make the per-person
        lock no lock at all."""
        with self._person_locks_guard:
            lock = self._person_locks.get(user_id)
            if lock is None:
                lock = threading.Lock()
                self._person_locks[user_id] = lock
            return lock

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

    def conversation(self, workspace_id: str, user_id: str = "local") -> Conversation:
        """This person's conversation in this workspace.

        Keyed by workspace alone until S6, because PRD section 6 was
        single user on one machine. With `AUTH_MODE=keycloak` there IS a
        second person, so the key carries the user id too: two people
        signed in to one server must never see each other's transcript,
        and a shared key is how they would. The separator cannot appear in
        either half (both are UUIDs or the literal "local", and F-12's
        sentinel), so two different pairs cannot collide on one key.

        S6: on a cache miss this now LOADS whatever was stored for this
        exact (person, workspace) pair rather than always starting empty --
        the law 09-08 ruling (DECISIONS 2026-09-15) that a person's
        transcript survives a restart. Loaded once per process per key;
        every later call this process makes for the same key returns the
        same in-memory object, exactly as before this story.

        LOADED UNDER A LOCK, DOUBLE-CHECKED: the fast path (a key already
        in `self.conversations`) takes no lock at all, but two threads
        racing on the FIRST call for one key -- both seeing `None` before
        either has stored anything -- used to both load and both build a
        `Conversation`, with only one surviving in the dict and the other
        going on to mutate an object nobody else could ever see again.
        `_person_lock` serializes exactly that gap; the `get` is repeated
        once the lock is held in case another thread already finished
        loading while this one was waiting."""
        key = f"{user_id}|{workspace_id}"
        existing = self.conversations.get(key)
        if existing is not None:
            return existing
        with self._person_lock(user_id):
            existing = self.conversations.get(key)
            if existing is None:
                existing = self._load_conversation(user_id, workspace_id)
                self.conversations[key] = existing
            return existing

    def _load_conversation(self, user_id: str, workspace_id: str) -> Conversation:
        """`conversation`'s cache-miss path: the stored row for this key,
        or a fresh empty `Conversation` when there is none, retention is 0,
        the row has expired, or the payload cannot be read.

        A corrupt or unreadable payload (bad JSON, an unknown enum value,
        an unknown payload version -- `Conversation.from_payload` raises
        on any of these) must not crash the chat screen (task rule):
        caught here, logged as one line naming only the workspace and the
        exception TYPE -- never the payload itself, which could hold a
        question or an answer (core law: never log a full request body)."""
        payload = chat_history.load(
            user_id=user_id,
            workspace_id=workspace_id,
            retention_days=get_settings().chat_history_retention_days,
            db_path=self.db_path,
        )
        if payload is None:
            return Conversation(workspace_id=workspace_id)
        try:
            return Conversation.from_payload(workspace_id, json.loads(payload))
        except Exception as exc:  # noqa: BLE001 -- logged, never left silent
            logger.warning(
                "stored chat history for workspace %s is unreadable (%s); "
                "starting an empty conversation",
                workspace_id,
                type(exc).__name__,
            )
            return Conversation(workspace_id=workspace_id)

    def save_conversation(self, user_id: str, conversation: Conversation) -> None:
        """Persist one settled transcript (S6). Called only when
        `Conversation.settle()` just returned True, from `_context`, so
        this never runs on a no-op render or the 700ms poll's common case
        of nothing having changed.

        NEVER for the F-12 routing sentinel: `screen.ROUTE_SENTINEL` is
        not a real workspace id, and `chat_history` is FK'd to `workspace`
        (db/schema.sql), so writing it would raise. `settle()` never
        returns True for that conversation today (`_start_routing` calls
        `begin_route`, never `begin`, so `run` is never set) -- this is a
        defensive guard against a future path reaching here anyway,
        proven by a test that calls this directly rather than trusting
        that today's routes never do.

        THE RACE THIS CLOSES (cold review): a save that snapshots the
        transcript, then writes it, has a gap in between where a
        concurrent "Delete my saved history" or "New conversation" can
        remove the very rows this save is about to (re)write -- the
        delete finishes first, then the stale save resurrects what was
        just deleted. Closed by ONE check, made under the same per-person
        lock every delete holds: the write happens only if this
        `Conversation` is still the one live in `self.conversations`.
        Every delete drops that object inside the lock, in the same step
        as the stored rows, and nothing ever puts the same object back --
        so a save that snapshotted before a delete, or arrives while one
        runs, finds it gone and skips. The next settled answer saves fine;
        this one does not get to un-delete anything.

        (A per-person "delete counter" used to sit beside this check. A
        cold review removed it and every test still passed: once the
        in-memory drop moved inside the lock it guarded nothing, and a
        comment crediting it could have led someone to weaken the real
        guard. It is gone.)"""
        if conversation.workspace_id == screen.ROUTE_SENTINEL:
            return
        key = f"{user_id}|{conversation.workspace_id}"
        payload = conversation.to_payload()
        if self._save_hook is not None:
            self._save_hook()
        with self._person_lock(user_id):
            if self.conversations.get(key) is not conversation:
                return
            # A FAILED SAVE MUST NOT FAIL THE PAGE (second cold review).
            # This runs inside the chat screen's render, after the finished
            # answer is already on screen; a busy database or a workspace
            # deleted a moment ago used to turn that render into a 500.
            # The answer stays on screen and is saved with the next one.
            # Logged with the workspace, the error type AND the traceback,
            # so a save that fails EVERY time (a read-only or full disk, a
            # renamed argument) is diagnosable rather than a quiet warning
            # (third review). Never the transcript: the payload is not in
            # the message, and a traceback carries code lines, not locals.
            # `json.dumps` is inside the try too, so an unserialisable
            # transcript cannot fail the page either.
            try:
                chat_history.save(
                    user_id=user_id,
                    workspace_id=conversation.workspace_id,
                    payload=json.dumps(payload),
                    retention_days=get_settings().chat_history_retention_days,
                    db_path=self.db_path,
                )
            except Exception as exc:  # noqa: BLE001 -- a save is best effort
                logger.warning(
                    "could not save chat history for workspace %s (%s)",
                    conversation.workspace_id,
                    type(exc).__name__,
                    exc_info=True,
                )

    def delete_conversation_storage(self, user_id: str, workspace_id: str) -> None:
        """Drop the stored row for just this one (person, workspace)
        pair, and the in-memory copy with it -- used by `/chat/new` (New
        conversation touches only the active workspace) and by an admin
        revoking a person's access to one workspace (the stored
        transcript quotes passages they should no longer hold).

        Under this person's lock it deletes the stored row AND drops the
        in-memory `Conversation`, in one step, so a save already in flight
        for this conversation finds it gone and cannot write it back (see
        `save_conversation`). Any run still being written is cancelled
        AFTER the lock is released, so the lock is never held while a
        run's own lock is taken."""
        key = f"{user_id}|{workspace_id}"
        # The in-memory copy is dropped INSIDE the lock, in the same step
        # as the stored row (second cold review). Dropping it after the
        # lock was released left a gap where a fresh save still found this
        # conversation live and wrote the deleted transcript back.
        with self._person_lock(user_id):
            chat_history.delete(user_id=user_id, workspace_id=workspace_id, db_path=self.db_path)
            conversation = self.conversations.pop(key, None)
            if self._delete_hook is not None:
                self._delete_hook()
        if conversation is not None and conversation.run is not None:
            conversation.run.cancel()

    def forget_conversations(self, user_id: str) -> None:
        """Drop every IN-MEMORY transcript belonging to one person
        (ordinary sign-out). Storage is untouched on purpose -- that is
        the point of an ordinary sign-out: the transcript comes back at
        the next sign-in. See `delete_all_history` for the law 09-08
        control that removes the stored copy too."""
        prefix = f"{user_id}|"
        # `list(...)` copies the keys in one step first: another person's
        # first page load can add to this shared dict at any moment, and
        # iterating the live dict raised "dictionary changed size during
        # iteration" (second cold review).
        for key in [k for k in list(self.conversations) if k.startswith(prefix)]:
            self.conversations.pop(key, None)

    def forget_workspace_conversations(self, workspace_id: str) -> None:
        """Drop every IN-MEMORY conversation for one workspace, whoever it
        belongs to, and cancel any run still writing into one of them.
        `db/schema.sql`'s `ON DELETE CASCADE` already takes the STORED
        rows with the workspace when `sync.delete_workspace` runs; this is
        the in-memory half.

        Cold review: the old code did
        `runtime.conversations.pop(workspace_id, None)`, a leftover from
        before S6 keyed this dict by workspace alone. Since S6 every key
        is `"{user_id}|{workspace_id}"`, so that pop matched nothing and
        every signed-in person's conversation for a deleted workspace
        stayed in memory -- reachable again if the same workspace id were
        ever reused (uuid4, so vanishingly unlikely, but a leaked
        reference regardless) and, worse, `Conversation.run` inside it was
        never cancelled."""
        suffix = f"|{workspace_id}"
        for key in [k for k in list(self.conversations) if k.endswith(suffix)]:
            conversation = self.conversations.pop(key, None)
            if conversation is not None and conversation.run is not None:
                conversation.run.cancel()

    def delete_all_history(self, user_id: str) -> None:
        """Law 09-08: every stored conversation this person has, in every
        workspace, gone -- plus their in-memory transcripts, so nothing of
        theirs is left in the running process either. Used by the
        person's own "Delete my saved history" control (`/chat/history/
        delete`) and by admin "sign out everywhere" (`admin_sign_out_route`),
        the two places this project has ruled a person's data must be
        taken out.

        Under this person's lock it deletes every stored row AND drops
        every in-memory conversation of theirs, in one step, so no save in
        flight can write one back (see `save_conversation`). Every run of
        theirs still being written is then cancelled, after the lock is
        released -- otherwise a question already being answered keeps
        running and spends a paid call writing into a `Conversation`
        nothing can reach any more (a cold review found this)."""
        prefix = f"{user_id}|"
        # Stored rows AND in-memory copies go in one locked step (second
        # cold review): removing memory after releasing the lock let a
        # fresh save find a conversation still live and write it back.
        with self._person_lock(user_id):
            chat_history.delete_for_user(user_id=user_id, db_path=self.db_path)
            dropped = [
                self.conversations.pop(key, None)
                for key in list(self.conversations)
                if key.startswith(prefix)
            ]
            if self._delete_hook is not None:
                self._delete_hook()
        for conversation in dropped:
            if conversation is not None and conversation.run is not None:
                conversation.run.cancel()


def _signed_in_as(request: Request) -> auth.Principal | None:
    """The person to name in the header, or None in the login-free modes.

    `request.state.principal` rather than `principal_of`: the fallback
    there is the unrestricted LOCAL principal, and naming "local" in the
    header of a single-user desktop app would be noise.

    The UNRESTRICTED check is what makes that true. `AuthGate` attaches
    `auth.LOCAL` to every request in the none and password modes, so the
    bare attribute was never None there: the header named "local", offered
    a Sign out that signs nobody out, and linked an admin page whose
    activity log is only ever written with accounts on (`_log_activity`)."""
    principal = getattr(request.state, "principal", None)
    if principal is None or principal.unrestricted:
        return None
    return principal


def _shell_context(runtime: Runtime, request: Request) -> dict:
    """Just enough for `base.html` on a page with no workspace behind it
    (the sign-in page, the no-role page). No workspace list: a person who
    is not signed in has no business seeing workspace NAMES."""
    return {
        "request": request,
        "dir": "rtl" if context_language(request) == "ar" else "ltr",
        "lang": context_language(request),
        "current_screen": "auth",
        "workspaces": [],
        "active": None,
        "busy": False,
        "signed_in_as": _signed_in_as(request),
    }


def _flow_secret() -> bytes:
    """What the sign-in cookie is signed with.

    The client secret: it is already the thing that proves this server is
    the one Keycloak knows, it never leaves the machine, and using it here
    means there is no second secret for an operator to configure and
    forget."""
    return get_settings().keycloak_client_secret.encode("utf-8")


def _sign_flow(state: str, nonce: str) -> str:
    body = f"{state}:{nonce}"
    signature = hmac.new(_flow_secret(), body.encode("utf-8"), "sha256").hexdigest()
    return f"{body}:{signature}"


def _read_flow(cookie: str | None) -> tuple[str, str] | None:
    """The (state, nonce) this browser was given, or None if the cookie is
    absent, malformed, or not the one this server signed."""
    if not cookie:
        return None
    state, _, rest = cookie.partition(":")
    nonce, _, signature = rest.partition(":")
    if not state or not nonce or not signature:
        return None
    expected = hmac.new(
        _flow_secret(), f"{state}:{nonce}".encode(), "sha256"
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    return state, nonce


def _refuse_action(runtime: Runtime, request: Request) -> Response:
    """What a refused action returns: the screen it came from, unchanged.

    A 403 PAGE IS NOT USED for a form post, on purpose. Every action here
    is posted from a screen the person is already on, and the honest
    outcome is "nothing happened" plus the screen as it now is -- an error
    page would lose the workspace they were looking at. The refusal is
    recorded in the activity log, which is where an admin looks."""
    _log_activity(runtime, request, "refused", detail=request.url.path)
    return RedirectResponse("/", status_code=SEE_OTHER)


def principal_of(request: Request) -> auth.Principal:
    """Who is asking. `auth.LOCAL` (everything allowed) in the two modes
    without accounts, which is every release before S6."""
    return getattr(request.state, "principal", None) or auth.LOCAL


def _granted_ids(runtime: Runtime, principal: auth.Principal) -> set[str]:
    if principal.unrestricted or principal.is_admin:
        return set()
    with repo.session(runtime.db_path) as conn:
        return repo.granted_workspace_ids(conn, principal.id)


def visible_options(
    runtime: Runtime, request: Request
) -> list[screen.WorkspaceOption]:
    """The workspaces this person may use, in the screens' own order.

    ONE FILTER, USED BY EVERY SCREEN. A workspace nobody granted is not
    listed, not routable (F-12), and not selectable -- refusing the action
    later would still have leaked its NAME through the selector."""
    principal = principal_of(request)
    options = screen.workspace_options(db_path=runtime.db_path)
    if principal.unrestricted or principal.is_admin:
        return options
    granted = _granted_ids(runtime, principal)
    return [option for option in options if option.id in granted]


def _log_activity(
    runtime: Runtime,
    request: Request,
    action: str,
    *,
    workspace_id: str | None = None,
    detail: str | None = None,
) -> None:
    """One activity row, and never the content of a question or answer."""
    if get_settings().auth_mode != auth.MODE_KEYCLOAK:
        return
    principal = principal_of(request)
    with repo.session(runtime.db_path) as conn:
        repo.record_activity(
            conn,
            user_id=None if principal.unrestricted else principal.id,
            username=principal.username,
            action=action,
            workspace_id=workspace_id,
            detail=detail,
        )


def _active(runtime: Runtime, request: Request) -> screen.WorkspaceOption | None:
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
    options = visible_options(runtime, request)
    if not options:
        return None
    if runtime.active_workspace_id == screen.ROUTE_SENTINEL and len(options) >= 2:
        return None
    chosen = next(
        (opt for opt in options if opt.id == runtime.active_workspace_id), None
    )
    return chosen or options[0]


def _conversation_key(runtime: Runtime, request: Request) -> str | None:
    """Which `Runtime.conversations` entry the shell is showing right now:
    the active workspace's id, or F-12's routing sentinel when no
    workspace is selected and there is something to route between. None
    only when no workspace exists at all -- there is nothing to show."""
    active = _active(runtime, request)
    if active is not None:
        return active.id
    if visible_options(runtime, request):
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
    options = visible_options(runtime, request)
    active = _active(runtime, request)
    principal = principal_of(request)
    documents: list[str] = []
    conversation = None
    # F-12: no active workspace while at least one exists is routing mode
    # ("let Sanad choose"), not the no-workspace-at-all case `state_for`
    # already handles from an empty `options`.
    is_routing = active is None and bool(options)
    if active is not None:
        documents = screen.answerable_documents(active.id, db_path=runtime.db_path)
        conversation = runtime.conversation(active.id, principal.id)
        # S6 saved chat history: persist only when settle() actually folded
        # a finished run into the transcript, not on every render -- this
        # function also runs on the 700ms poll while the page is open.
        if conversation.settle():
            runtime.save_conversation(principal.id, conversation)
    elif is_routing:
        conversation = runtime.conversation(screen.ROUTE_SENTINEL, principal.id)
        # The routing sentinel conversation never gets a real `Run`
        # (`_start_routing` calls `begin_route`, never `begin`), so
        # `settle()` is always a no-op here -- never persisted, and there
        # is nothing FK-safe to persist it against (ROUTE_SENTINEL is not
        # a real workspace id).
        if conversation.settle():
            runtime.save_conversation(principal.id, conversation)
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
        "signed_in_as": _signed_in_as(request),
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
        # S6 streaming: the answer as written so far, "" until it is safe
        # to show (agent.answering._safe_to_show).
        "partial_text": run.partial_text if (run and busy) else "",
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
    options = visible_options(runtime, request)
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
        "signed_in_as": _signed_in_as(request),
        # base.html's <noscript> refresh (UX spec 6.3's no-JS path) is keyed
        # on this same name for S1; a Sync in flight is the same kind of
        # fact for S2, so it reuses the hook rather than teaching base.html
        # a second word for one idea.
        "busy": running is not None,
        "active": _active(runtime, request),
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
        # S6 documents. The drop zone is not offered where uploads are
        # refused anyway (evidence-only); `doc_error` is a catalog key from
        # the remove route's redirect, accepted only if it is one of the
        # document errors so a hand-edited URL cannot print another key.
        "uploads_enabled": not get_settings().evidence_only,
        "upload_max_mb": get_settings().upload_max_bytes // (1024 * 1024),
        "upload_accept": ",".join(
            f".{ext}" for ext in get_settings().supported_document_extensions
        ),
        "removed_name": request.query_params.get("removed", ""),
        "doc_error": (
            request.query_params.get("doc_error")
            if request.query_params.get("doc_error", "").startswith("docs.error.")
            else None
        ),
        # S6: a control nobody may use is not rendered at all (the rule the
        # theme toggle and the drop zone already follow). The routes refuse
        # the same actions server-side; this only keeps the screen honest.
        "may_manage_workspaces": principal_of(request).may_manage_workspaces(),
        "may_manage_documents": bool(
            selected_id
            and principal_of(request).may_manage_documents(
                selected_id, _granted_ids(runtime, principal_of(request))
            )
        ),
    }


def _reports_context(runtime: Runtime, request: Request) -> dict:
    """Everything one render of the read-only S3 Reports screen needs."""
    # S6: None for an admin and for the login-free modes ("everything");
    # a set for anyone else, so Reports never names a workspace the rest of
    # the screens correctly hide.
    principal = principal_of(request)
    visible_ids = (
        None
        if principal.unrestricted or principal.is_admin
        else {option.id for option in visible_options(runtime, request)}
    )
    reports = reports_screen.list_reports(
        db_path=runtime.db_path, visible_ids=visible_ids
    )
    feedback_rows = reports_screen.list_feedback(
        db_path=runtime.db_path, visible_ids=visible_ids
    )
    active = _active(runtime, request)
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
        "signed_in_as": _signed_in_as(request),
        "busy": any(report.is_running for report in reports),
        "workspaces": visible_options(runtime, request),
        "active": active,
        "state": reports_screen.screen_state(report_count=len(reports)),
        "ReportsScreenState": reports_screen.ReportsScreenState,
        "reports": reports,
        # F-15. Independent of `reports`/`state` above -- see
        # ui/reports_screen.py's module note on why feedback is never
        # gated by the eval-run empty state. Pure SQLite reads, same as
        # `reports` itself, so this never loads the embedding model and
        # renders fine in evidence-only mode (ST-05).
        "feedback": feedback_rows,
        # S6: tiles and trend lines built from the same rows the tables print.
        "dashboard": reports_screen.dashboard(reports, feedback_rows),
    }


_SLUG_UNSAFE = "\"'\\/:*?<>|\n\r\t "


def _slug(value: str) -> str:
    """A filename-safe stand-in for whatever the workspace was named --
    Content-Disposition's `filename=` breaks on quotes and path
    separators, and a workspace name is operator-chosen free text."""
    return "".join("-" if ch in _SLUG_UNSAFE else ch for ch in value) or "report"


async def _form(request: Request, *, multi: bool = False) -> dict[str, str] | dict[str, list[str]]:
    """One posted form, decoded, with no third-party parser.

    WHY NOT FastAPI's `Form(...)` OR `await request.form()`: both require
    `python-multipart` -- FastAPI checks for it at import time and
    Starlette asserts on it inside `form()`, whatever the content type. It
    exists to parse `multipart/form-data`, which is the file-upload
    encoding. Since S6 Sanad does accept uploads (CR-03), but sanad.js sends
    each file as the raw request body (`upload_document_route`), so the
    multipart format -- and the package that parses it -- is still never
    needed.

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
    pairs = parse_qsl(body, keep_blank_values=True, encoding="utf-8")
    if multi:
        # S6 admin grants: a form of checkboxes posts one `workspace_id`
        # per ticked box, and `dict()` would keep only the last -- one
        # workspace granted out of five ticked, silently.
        grouped: dict[str, list[str]] = {}
        for key, value in pairs:
            grouped.setdefault(key, []).append(value)
        return grouped
    return dict(pairs)


# Any short, non-blank string works: warm-up cares about walking the same
# loading path a question uses, not about the text itself, and the E5 and
# BM25 models are both loaded regardless of what string triggers them.
_WARM_UP_TEXT = "warm-up"


def _warm_up_models() -> None:
    """Load both search encoders, then the document readers, off the request path.

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
    else:
        logger.info("model warm-up ready in %.1fs", time.monotonic() - started)

    # The document readers, AFTER the encoders and in their OWN try: a model
    # that cannot download (no network on a first run) says nothing about
    # whether the PDF and Word readers load, so one failing must not skip
    # the other. Encoders first because a question is the common first act
    # and their 23 s is the bigger wait; the readers' ~14 s follows. See
    # `sync.warm_up_document_readers` for the measurement.
    started = time.monotonic()
    try:
        sync.warm_up_document_readers()
    except Exception:  # noqa: BLE001 -- warm-up must never crash the server
        logger.exception(
            "document reader warm-up failed; the first Sync will load them instead"
        )
        return
    logger.info("document reader warm-up ready in %.1fs", time.monotonic() - started)


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

        # S6 (law 09-08): sweep stored chat history past its retention
        # window at every start-up, not only when a row happens to be
        # loaded again -- a workspace nobody reopens must not keep its
        # transcript past `chat_history_retention_days` just because
        # nothing ever read it.
        swept = chat_history.sweep_expired(
            retention_days=get_settings().chat_history_retention_days,
            db_path=runtime.db_path,
        )
        if swept:
            logger.warning("swept %s expired chat history row(s)", swept)

        # ST-39: on the real server only (see `Runtime.warm_up`), load both
        # search encoders, then the document readers, on a background thread
        # now rather than paying for them on the first real question or
        # Sync. Daemon and fire-and-forget --
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
    # S6: attaches who is signed in, and refuses anything that is not,
    # when AUTH_MODE is 'keycloak'. Inert in the other two modes.
    app.add_middleware(AuthGate, db_path=runtime.db_path)
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
    templates.env.globals["static_url"] = _static_url
    # S6: an answer's bold, lists and tables, with HTML, links and images off.
    templates.env.filters["answer_html"] = render_answer

    def render(request: Request, name: str = "chat.html") -> HTMLResponse:
        denied = _no_role_page(request)
        if denied is not None:
            return denied
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
        if not visible_options(runtime, request):
            return RedirectResponse("/workspaces", status_code=SEE_OTHER)
        return render(request)

    def _no_role_page(request: Request) -> Response | None:
        """The page a signed-in person with no Sanad role sees.

        Nobody is anything by default (ui/auth.py), so this is what a
        newly created Keycloak account gets until an administrator grants
        a role -- one honest sentence, rather than an empty workspace
        selector that looks like a broken product."""
        if principal_of(request).has_any_role:
            return None
        return templates.TemplateResponse(
            request,
            "no_role.html",
            {**_shell_context(runtime, request), "who": principal_of(request)},
            status_code=403,
        )

    def _may_manage(request: Request, workspace_id: str) -> bool:
        principal = principal_of(request)
        return principal.may_manage_documents(
            workspace_id, _granted_ids(runtime, principal)
        )

    def _may_see(request: Request, workspace_id: str) -> bool:
        principal = principal_of(request)
        return principal.has_any_role and principal.may_see_workspace(
            workspace_id, _granted_ids(runtime, principal)
        )

    def _provider():
        """The Keycloak seam, injectable for tests (`Runtime.oidc_provider`)."""
        return runtime.oidc_provider or oidc.build_provider()

    def _login_failed(request: Request, reason: str, status: int = 503) -> Response:
        """One page for every sign-in failure, naming what went wrong.

        The reason is a sentence about the SERVICE ("could not be
        reached", "did not accept this sign-in"), never about the person:
        a login page that speculates about the user is how "wrong
        password" gets shown to someone whose provider was simply down."""
        logger.warning("sign-in failed: %s", reason)
        return templates.TemplateResponse(
            request,
            "login.html",
            {**_shell_context(runtime, request), "login_error": reason},
            status_code=status,
        )

    @app.get("/auth/login")
    def auth_login(request: Request) -> Response:
        """Start the authorization-code flow (docs/design/S6-auth-rbac.md).

        `state` and `nonce` are minted here and carried in a SHORT-LIVED,
        SIGNED cookie. Signed with the client secret, because an attacker
        who can set a cookie could otherwise plant their own `state` and
        complete a sign-in the person never started (login CSRF)."""
        if get_settings().auth_mode != auth.MODE_KEYCLOAK:
            return RedirectResponse("/", status_code=SEE_OTHER)
        if principal_of(request).has_any_role and getattr(
            request.state, "principal", None
        ):
            return RedirectResponse("/", status_code=SEE_OTHER)
        try:
            provider = _provider()
            state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
            target = provider.authorization_url(
                state=state,
                nonce=nonce,
                redirect_uri=get_settings().keycloak_redirect_url,
            )
        except oidc.ProviderUnavailableError as exc:
            return _login_failed(request, str(exc))
        response = RedirectResponse(target, status_code=SEE_OTHER)
        response.set_cookie(
            auth.FLOW_COOKIE,
            _sign_flow(state, nonce),
            max_age=auth.FLOW_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
            path="/auth",
        )
        return response

    @app.get("/auth/callback")
    def auth_callback(request: Request) -> Response:
        """Finish the flow: verify `state`, exchange the code, read roles."""
        if get_settings().auth_mode != auth.MODE_KEYCLOAK:
            return RedirectResponse("/", status_code=SEE_OTHER)
        expected = _read_flow(request.cookies.get(auth.FLOW_COOKIE))
        supplied = request.query_params.get("state", "")
        code = request.query_params.get("code", "")
        if expected is None or not code or not secrets.compare_digest(
            expected[0], supplied
        ):
            # One message for "no cookie", "tampered cookie" and "wrong
            # state": telling a caller which one it was tells an attacker
            # how close they got.
            return _login_failed(request, "this sign-in could not be verified.", 400)
        try:
            tokens = _provider().exchange_code(
                code=code, redirect_uri=get_settings().keycloak_redirect_url
            )
            access_token = tokens.get("access_token", "")
            if not access_token:
                raise oidc.ProviderUnavailableError(
                    "the login service returned no access token."
                )
            claims = _provider().introspect(access_token)
        except oidc.ProviderUnavailableError as exc:
            return _login_failed(request, str(exc))
        if not claims.get("active"):
            return _login_failed(request, "this sign-in is no longer valid.", 400)

        user_id = str(claims.get("sub") or "")
        username = str(claims.get("preferred_username") or claims.get("username") or "")
        if not user_id or not username:
            return _login_failed(request, "the login service named no user.", 400)
        roles = auth.roles_from_claims(claims)
        token, token_hash = auth.new_session_token()
        with repo.session(runtime.db_path) as conn:
            repo.upsert_user(
                conn,
                user_id=user_id,
                username=username,
                email=claims.get("email"),
                display_name=claims.get("name"),
                roles=" ".join(roles),
            )
            repo.create_session(
                conn,
                token_hash=token_hash,
                user_id=user_id,
                expires_at=auth.session_expiry(),
            )
            repo.record_activity(
                conn, user_id=user_id, username=username, action="signed in"
            )
        response = RedirectResponse("/", status_code=SEE_OTHER)
        response.set_cookie(
            auth.SESSION_COOKIE,
            token,
            max_age=get_settings().session_ttl_hours * 3600,
            httponly=True,
            samesite="lax",
            secure=request.url.scheme == "https",
            path="/",
        )
        response.delete_cookie(auth.FLOW_COOKIE, path="/auth")
        return response

    @app.post("/auth/logout")
    def auth_logout(request: Request) -> Response:
        """Delete the session, the cookie and this person's transcripts."""
        principal = principal_of(request)
        token = request.cookies.get(auth.SESSION_COOKIE)
        if token:
            with repo.session(runtime.db_path) as conn:
                repo.delete_session(conn, auth.hash_token(token))
                if not principal.unrestricted:
                    repo.record_activity(
                        conn,
                        user_id=principal.id,
                        username=principal.username,
                        action="signed out",
                    )
        if not principal.unrestricted:
            # A shared machine: the next person to sign in must not find
            # the previous one's conversation in memory.
            runtime.forget_conversations(principal.id)
        # END KEYCLOAK'S SESSION TOO, not only ours. Found in a real
        # browser against a real realm: deleting our cookie alone left the
        # realm's own SSO session alive, so the very next click on Sign in
        # was answered silently with the SAME person -- a sign-out button
        # that signs nobody out on the shared demo machine. Where the realm
        # publishes no end-session endpoint, we still land on our own
        # sign-in page, which is the old behaviour.
        target = "/auth/login"
        with contextlib.suppress(oidc.ProviderUnavailableError, AttributeError):
            end_session = _provider().end_session_url(
                redirect_uri=str(request.base_url).rstrip("/") + "/auth/login"
            )
            target = end_session or target
        response = RedirectResponse(target, status_code=SEE_OTHER)
        response.delete_cookie(auth.SESSION_COOKIE, path="/")
        return response

    @app.get("/admin", response_class=HTMLResponse)
    def admin_route(request: Request) -> Response:
        """Who may use Sanad, what they hold, and what has been done."""
        if not principal_of(request).is_admin:
            return _refuse_action(runtime, request)
        return templates.TemplateResponse(
            request,
            "admin.html",
            {
                **_shell_context(runtime, request),
                # NOT the shell context's empty list: that exists for pages
                # with nobody signed in. Seen in a real browser, 2026-09-15:
                # an admin on this page, with a workspace existing, got a
                # header saying "no workspace yet", a disabled selector and
                # a disabled Chat link telling them to create one.
                "workspaces": visible_options(runtime, request),
                "active": _active(runtime, request),
                "current_screen": "admin",
                "people": admin_screen.people(db_path=runtime.db_path),
                "activity": admin_screen.activity(db_path=runtime.db_path),
                "workspaces_all": screen.workspace_options(db_path=runtime.db_path),
            },
        )

    @app.post("/admin/grants")
    async def admin_grants_route(request: Request) -> Response:
        """Set one person's workspaces to exactly what was ticked."""
        if not principal_of(request).is_admin:
            return _refuse_action(runtime, request)
        form = await _form(request, multi=True)
        user_id = (form.get("user_id") or [""])[0]
        wanted = set(form.get("workspace_id") or [])
        if not user_id:
            return RedirectResponse("/admin", status_code=SEE_OTHER)
        added, removed = admin_screen.set_grants(
            user_id=user_id, workspace_ids=wanted, db_path=runtime.db_path
        )
        # The action names come from admin_screen, which resolves `detail`
        # to a username for exactly these: one list, not two in step by hand.
        for workspace_id in added:
            _log_activity(runtime, request, admin_screen.GRANTED_ACCESS,
                          workspace_id=workspace_id, detail=user_id)
        for workspace_id in removed:
            _log_activity(runtime, request, admin_screen.REVOKED_ACCESS,
                          workspace_id=workspace_id, detail=user_id)
            # S6, law 09-08 (cold review): a revoked workspace's stored
            # transcript quotes passages this person should no longer
            # hold, so it leaves with the grant -- not just their access.
            runtime.delete_conversation_storage(user_id, workspace_id)
        return RedirectResponse("/admin", status_code=SEE_OTHER)

    @app.post("/admin/people/{user_id}/sign-out")
    def admin_sign_out_route(request: Request, user_id: str) -> Response:
        """End every session this person has, and drop their transcripts,
        in memory AND stored (S6 saved chat history).

        Also the law 09-08 answer for "take this person's data out of the
        running process": what is left afterwards is their account row and
        the activity log, which records actions and never questions."""
        if not principal_of(request).is_admin:
            return _refuse_action(runtime, request)
        with repo.session(runtime.db_path) as conn:
            repo.delete_sessions_for_user(conn, user_id)
        runtime.delete_all_history(user_id)
        _log_activity(runtime, request, admin_screen.SIGNED_OUT_EVERYWHERE, detail=user_id)
        return RedirectResponse("/admin", status_code=SEE_OTHER)

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
        return _start(
            runtime, request, form.get("question", ""), form.get("workspace_id") or None
        )

    @app.post("/chat/cancel")
    def cancel(request: Request) -> Response:
        key = _conversation_key(runtime, request)
        if key is not None:
            run = runtime.conversation(key, principal_of(request).id).run
            if run is not None:
                run.cancel()
        return RedirectResponse("/", status_code=SEE_OTHER)

    @app.post("/chat/new")
    def new_conversation(request: Request) -> Response:
        key = _conversation_key(runtime, request)
        if key is not None:
            principal_id = principal_of(request).id
            runtime.conversation(key, principal_id).reset()
            # S6 saved chat history: a new conversation also drops the
            # stored row for this one workspace, so it is not silently
            # resurrected on the next load -- only this workspace's row,
            # never this person's others (that is `/chat/history/delete`,
            # below).
            runtime.delete_conversation_storage(principal_id, key)
        return RedirectResponse("/", status_code=SEE_OTHER)

    @app.get("/chat/history/delete", response_class=HTMLResponse)
    def confirm_delete_history(request: Request) -> Response:
        """S6 saved chat history, law 09-08: the no-JS `ConfirmDialog` (UX spec 5, 7.2)
        before wiping every stored conversation this person has, in every
        workspace. Same pattern as `confirm_delete_workspace` and
        `confirm_remove_document` -- a real page, one action, one way
        back -- and, like those, a GET here never deletes anything; only
        the POST below does."""
        return templates.TemplateResponse(
            request, "chat_history_delete_confirm.html", _ws_context(runtime, request)
        )

    @app.post("/chat/history/delete")
    def delete_history_route(request: Request) -> Response:
        """The person's own law 09-08 control: every stored conversation
        they have, gone, plus what is currently in memory."""
        runtime.delete_all_history(principal_of(request).id)
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
        if not _may_see(request, workspace_id):
            return _refuse_action(runtime, request)
        if get_settings().evidence_only:
            return RedirectResponse("/", status_code=SEE_OTHER)
        message_id = form.get("message_id", "")
        verdict = form.get("verdict", "")
        comment = form.get("comment") or None
        conversation = runtime.conversations.get(
            f"{principal_of(request).id}|{workspace_id}"
        )
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
            visible_options(runtime, request)
        ) < 2:
            chosen = None
        moved = chosen is not None and chosen != (
            _active(runtime, request).id if _active(runtime, request) else None
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
        # S6: this person's transcript in that workspace, never anyone
        # else's -- the passage a card opens must come from the answer the
        # SAME reader was given.
        conversation = runtime.conversations.get(
            f"{principal_of(request).id}|{workspace_id}"
        )
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
        denied = _no_role_page(request)
        if denied is not None:
            return denied
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
        if not principal_of(request).may_manage_workspaces():
            return _refuse_action(runtime, request)
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
        if not principal_of(request).may_manage_workspaces():
            return _refuse_action(runtime, request)
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
        if not principal_of(request).may_manage_workspaces():
            return _refuse_action(runtime, request)
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
        if not principal_of(request).may_manage_workspaces():
            return _refuse_action(runtime, request)

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
        runtime.forget_workspace_conversations(workspace_id)
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
        if not _may_manage(request, workspace_id):
            return _refuse_action(runtime, request)
        _log_activity(runtime, request, "started a sync", workspace_id=workspace_id)
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
    def cancel_sync_route(request: Request, workspace_id: str) -> Response:
        if not _may_manage(request, workspace_id):
            return _refuse_action(runtime, request)
        event = runtime.sync_cancel_events.get(workspace_id)
        if event is not None:
            event.set()
        return RedirectResponse(f"/workspaces?ws={workspace_id}", status_code=SEE_OTHER)

    # --- S6 documents: upload, download, remove (ui/documents.py) --------

    @app.post("/workspaces/{workspace_id}/documents")
    async def upload_document_route(request: Request, workspace_id: str) -> Response:
        """One file, sent by sanad.js as the raw request body.

        RAW BYTES, NOT A MULTIPART FORM: parsing `multipart/form-data`
        needs `python-multipart`, which this project deliberately does not
        carry (see `_form`). The name travels percent-encoded in
        `X-File-Name`, so an Arabic or accented name survives the header.
        A custom header is also what keeps another site from posting here:
        a cross-origin page cannot send one without a CORS preflight this
        app never approves.

        Answers JSON for the script: 201 with the reader's sentence, or a
        4xx whose `error` is the translated reason. No row is written and
        no Sync is started here; sanad.js starts one Sync after the whole
        batch."""
        lang = context_language(request)

        def refused(key: str, status: int, **params: object) -> JSONResponse:
            return JSONResponse(
                status_code=status, content={"error": i18n.translate(lang, key, **params)}
            )

        if get_settings().evidence_only:
            return refused("docs.error.evidence", 409)
        if not _may_manage(request, workspace_id):
            return refused("docs.error.forbidden", 403)
        try:
            target = workspaces.get_workspace(workspace_id=workspace_id, db_path=runtime.db_path)
        except workspaces.WorkspaceNotFoundError:
            return refused("docs.error.workspace", 404)
        declared = request.headers.get("content-length", "")
        try:
            saved = await documents.save_document(
                target.folder_path,
                unquote(request.headers.get("x-file-name", "")),
                request.stream(),
                declared_size=int(declared) if declared.isdigit() else None,
            )
        except documents.DocumentError as exc:
            return refused(exc.key, exc.status, **exc.params)
        _log_activity(
            runtime,
            request,
            "uploaded a document",
            workspace_id=workspace_id,
            detail=saved.file_name,
        )
        key = "docs.upload.replaced" if saved.replaced else "docs.upload.saved"
        return JSONResponse(
            status_code=201,
            content={
                "file_name": saved.file_name,
                "size_bytes": saved.size_bytes,
                "replaced": saved.replaced,
                "message": i18n.translate(lang, key, name=saved.file_name),
            },
        )

    @app.get("/workspaces/{workspace_id}/documents/{file_name}")
    def download_document_route(request: Request, workspace_id: str, file_name: str) -> Response:
        """The original file, as an attachment -- never rendered inline, so
        a document can never run as a page on this origin."""
        lang = context_language(request)
        if not _may_see(request, workspace_id):
            return PlainTextResponse(
                i18n.translate(lang, "docs.error.forbidden"), status_code=403
            )
        try:
            target = workspaces.get_workspace(workspace_id=workspace_id, db_path=runtime.db_path)
            path = documents.existing_document(target.folder_path, file_name)
        except workspaces.WorkspaceNotFoundError:
            return PlainTextResponse(i18n.translate(lang, "docs.error.workspace"), status_code=404)
        except documents.DocumentError as exc:
            return PlainTextResponse(
                i18n.translate(lang, exc.key, **exc.params), status_code=exc.status
            )
        return FileResponse(
            path,
            filename=path.name,
            content_disposition_type="attachment",
            headers={"X-Content-Type-Options": "nosniff"},
        )

    @app.get("/workspaces/{workspace_id}/documents/{file_name}/remove", response_class=HTMLResponse)
    def confirm_remove_document(request: Request, workspace_id: str, file_name: str) -> Response:
        """The confirmation page, the same no-JS pattern as deleting a
        workspace: a removal always costs a deliberate second step."""
        if not _may_manage(request, workspace_id):
            return _refuse_action(runtime, request)
        try:
            target = workspaces.get_workspace(workspace_id=workspace_id, db_path=runtime.db_path)
            path = documents.existing_document(target.folder_path, file_name)
        except (workspaces.WorkspaceNotFoundError, documents.DocumentError):
            return RedirectResponse(f"/workspaces?ws={workspace_id}", status_code=SEE_OTHER)
        return templates.TemplateResponse(
            request,
            "document_remove_confirm.html",
            {**_ws_context(runtime, request), "target": target, "file_name": path.name},
        )

    @app.post("/workspaces/{workspace_id}/documents/{file_name}/remove")
    def remove_document_route(request: Request, workspace_id: str, file_name: str) -> Response:
        """Delete the file from the folder, then start a Sync so answers
        stop citing it. A Sync that cannot start (one already running,
        evidence-only) is not an error here: the file is gone either way
        and the next Sync removes it."""
        base = f"/workspaces?ws={workspace_id}"
        if not _may_manage(request, workspace_id):
            return _refuse_action(runtime, request)
        if get_settings().evidence_only:
            return RedirectResponse(f"{base}&doc_error=docs.error.evidence", status_code=SEE_OTHER)
        try:
            target = workspaces.get_workspace(workspace_id=workspace_id, db_path=runtime.db_path)
            removed = documents.remove_document(target.folder_path, file_name)
        except workspaces.WorkspaceNotFoundError:
            return RedirectResponse("/workspaces", status_code=SEE_OTHER)
        except documents.DocumentError as exc:
            return RedirectResponse(f"{base}&doc_error={exc.key}", status_code=SEE_OTHER)
        _log_activity(
            runtime,
            request,
            "removed a document",
            workspace_id=workspace_id,
            detail=removed,
        )
        with contextlib.suppress(sync.SyncInProgressError, sync.EvidenceOnlyError):
            runtime.start_sync(workspace_id)
        return RedirectResponse(
            f"{base}&removed={quote(removed)}", status_code=SEE_OTHER
        )

    @app.get("/reports", response_class=HTMLResponse)
    def reports_route(request: Request) -> HTMLResponse:
        """S3 (ST-34): the list of evaluation runs `scripts/run_evaluation.py`
        has already written. Read-only -- see ui/reports_screen.py for why
        there is no "run now" action here."""
        denied = _no_role_page(request)
        if denied is not None:
            return denied
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
                # S6: the question grid, grouped in the table's own order.
                "question_groups": (
                    reports_screen.question_groups(detail.questions) if detail else ()
                ),
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
    runtime: Runtime,
    request: Request,
    question: str,
    workspace_override: str | None = None,
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
    options = visible_options(runtime, request)
    if workspace_override and any(opt.id == workspace_override for opt in options):
        runtime.active_workspace_id = workspace_override

    active = _active(runtime, request)
    if active is None:
        if options:
            return _start_routing(runtime, request, question, options)
        return RedirectResponse("/", status_code=SEE_OTHER)
    principal = principal_of(request)
    if not principal.may_ask(active.id, _granted_ids(runtime, principal)):
        # Unreachable through the screen -- a workspace this person may not
        # use is not in `options` and so cannot be active -- and refused
        # anyway, because "unreachable through the screen" is a statement
        # about today's templates, not about what a POST can carry.
        return _refuse_action(runtime, request)
    conversation = runtime.conversation(active.id, principal.id)
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
    runtime: Runtime,
    request: Request,
    question: str,
    options: list[screen.WorkspaceOption],
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
    conversation = runtime.conversation(screen.ROUTE_SENTINEL, principal_of(request).id)
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
