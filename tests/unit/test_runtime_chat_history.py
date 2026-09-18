"""S6 saved chat history exit gate, law 09-08 -- and since ST-53, many
conversations per person per workspace, each with its own id. Exercised at
the `Runtime` level -- no HTTP, no scripted chat model needed for most of
these, since the persistence seam (`open_conversation` / `new_conversation`
/ `save_conversation` / the deletes) is plain Python around real SQLite.

Route-level proof (New conversation, the person's own delete-history
confirm page, rename and delete of one conversation, admin sign-out,
ordinary sign-out, and an admin revoke deleting the revoked workspace's
conversations) lives in tests/integration/test_s1_chat_screen.py,
test_s6_admin.py and test_s6_auth.py, next to the routes they exercise.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

import workspaces
from app import Runtime, create_app
from config import get_settings
from db import repo
from ui.conversation import PAYLOAD_VERSION, Message, MessageKind
from ui.runs import Run


def _workspace(db_path, name: str = "HR") -> str:
    return workspaces.create_workspace(
        name=name, folder_path=str(db_path.parent), db_path=db_path
    ).id


def _db(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    return db_path


def _answer(text: str, *, id: str | None = None) -> Message:
    return Message(kind=MessageKind.ANSWER, text=text, id=id or f"id-{text}")


def _saved(runtime, user_id: str, workspace_id: str, text: str):
    """A conversation with one answer in it, live and stored."""
    conversation = runtime.new_conversation(user_id, workspace_id)
    conversation.messages.append(_answer(text))
    runtime.save_conversation(conversation)
    return conversation


def _insert(db_path, conversation_id, ws_id, payload, updated_at=None, user="local"):
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO conversation "
            "(id, user_id, workspace_id, title, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, NULL, ?, ?, ?)",
            (conversation_id, user, ws_id, payload, updated_at or repo.utc_now(),
             updated_at or repo.utc_now()),
        )


def _stored_rows(db_path, user_id: str) -> int:
    with repo.session(db_path) as conn:
        return conn.execute(
            "SELECT COUNT(*) FROM conversation WHERE user_id = ?", (user_id,)
        ).fetchone()[0]


def _stored_ids(db_path) -> set[str]:
    with repo.session(db_path) as conn:
        return {row[0] for row in conn.execute("SELECT id FROM conversation")}


def _theirs(runtime, user_id: str) -> list:
    return [c for c in runtime.conversations.values() if c.user_id == user_id]


# --- restart survival ---------------------------------------------------


def test_a_saved_conversation_survives_a_new_runtime_on_the_same_db(tmp_path):
    """The literal exit-gate proof: a SECOND `Runtime` instance, standing
    in for a process restart, reads what the first one wrote."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)

    first = Runtime(db_path=db_path)
    conversation = first.new_conversation("local", ws_id)
    conversation.messages.append(_answer("Trois mois.", id="fixed-id"))
    conversation.session_id = "session-xyz"
    conversation.summary = "compact"
    first.save_conversation(conversation)

    second = Runtime(db_path=db_path)
    restored = second.open_conversation("local", conversation.id)

    assert second is not first
    assert restored is not None and restored is not conversation
    assert (restored.id, restored.user_id, restored.workspace_id) == (
        conversation.id, "local", ws_id,
    )
    assert [m.text for m in restored.messages] == ["Trois mois."]
    assert restored.messages[0].id == "fixed-id"
    assert restored.session_id == "session-xyz"
    assert restored.summary == "compact"
    assert second.latest_conversation("local", ws_id) is restored


def test_many_conversations_in_one_workspace_each_keep_their_own_transcript(tmp_path):
    """ST-53's reason to exist: a second conversation no longer replaces
    the first. Both survive a restart, each with its own messages."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    first = Runtime(db_path=db_path)
    one = _saved(first, "local", ws_id, "first conversation")
    two = _saved(first, "local", ws_id, "second conversation")

    second = Runtime(db_path=db_path)

    assert one.id != two.id
    assert [m.text for m in second.open_conversation("local", one.id).messages] == [
        "first conversation"
    ]
    assert [m.text for m in second.open_conversation("local", two.id).messages] == [
        "second conversation"
    ]
    assert second.latest_conversation("local", ws_id).id == two.id


def test_two_people_in_the_same_workspace_never_see_each_others_history(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    alice = _saved(runtime, "alice", ws_id, "Alice's answer")
    bob = _saved(runtime, "bob", ws_id, "Bob's answer")

    fresh = Runtime(db_path=db_path)

    assert [m.text for m in fresh.latest_conversation("alice", ws_id).messages] == [
        "Alice's answer"
    ]
    assert [m.text for m in fresh.latest_conversation("bob", ws_id).messages] == [
        "Bob's answer"
    ]
    assert fresh.open_conversation("bob", alice.id) is None, "stored: an id alone reaches nothing"
    assert runtime.open_conversation("alice", bob.id) is None, "cached: nor does a live one"


def test_an_id_from_another_workspace_is_not_opened_there(tmp_path):
    db_path = _db(tmp_path)
    ws1 = _workspace(db_path, "HR")
    ws2 = _workspace(db_path, "Legal")
    runtime = Runtime(db_path=db_path)
    in_hr = _saved(runtime, "local", ws1, "HR answer")

    assert runtime.open_conversation("local", in_hr.id, ws2) is None
    assert runtime.open_conversation("local", in_hr.id, ws1) is in_hr
    assert runtime.open_conversation("local", in_hr.id) is in_hr


def test_the_title_is_the_first_question_asked(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = runtime.new_conversation("local", ws_id)
    conversation.messages.append(Message(kind=MessageKind.USER, text="Durée du préavis ?"))
    conversation.messages.append(_answer("Trois mois."))
    conversation.messages.append(Message(kind=MessageKind.USER, text="Et pour un cadre ?"))

    runtime.save_conversation(conversation)

    with repo.session(db_path) as conn:
        assert conn.execute("SELECT title FROM conversation").fetchone()[0] == (
            "Durée du préavis ?"
        )


# --- retention -----------------------------------------------------------


def test_retention_zero_stores_nothing(tmp_path, monkeypatch):
    import app as app_module

    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    settings = get_settings().model_copy(update={"chat_history_retention_days": 0})
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    first = Runtime(db_path=db_path)
    kept_in_memory = _saved(first, "local", ws_id, "x")

    assert _stored_ids(db_path) == set()
    assert first.latest_conversation("local", ws_id) is kept_in_memory, (
        "with nothing stored, the live one must still be found again"
    )
    second = Runtime(db_path=db_path)
    assert second.latest_conversation("local", ws_id) is None


def test_a_row_past_the_retention_window_is_dropped_on_load(tmp_path, monkeypatch):
    import app as app_module

    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    settings = get_settings().model_copy(update={"chat_history_retention_days": 30})
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    stale = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    payload = json.dumps(
        {"v": PAYLOAD_VERSION, "session_id": None, "summary": "", "turns": [],
         "messages": [{"kind": "answer", "text": "old", "id": "m1"}]}
    )
    _insert(db_path, "stale", ws_id, payload, stale)

    runtime = Runtime(db_path=db_path)

    assert runtime.open_conversation("local", "stale") is None
    assert _stored_ids(db_path) == set(), "an expired row must be deleted on read"


def test_start_up_sweeps_expired_chat_history(tmp_path):
    """`create_app`'s lifespan (app.py) runs the sweep once at start-up, so
    a row nobody ever loads again still stays bounded by the retention
    window."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _insert(db_path, "stale", ws_id, "{}", (datetime.now(UTC) - timedelta(days=31)).isoformat())
    _insert(db_path, "fresh", ws_id, "{}")

    runtime = Runtime(ports_factory=lambda: None, db_path=db_path)
    with TestClient(create_app(runtime)):
        pass  # lifespan runs on entering/exiting the client context

    assert _stored_ids(db_path) == {"fresh"}


# --- corrupt storage must not crash the chat screen -----------------------


def _opens_empty_under_its_own_id(tmp_path, payload):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _insert(db_path, "broken", ws_id, payload)
    runtime = Runtime(db_path=db_path)

    restored = runtime.open_conversation("local", "broken")

    assert restored is not None, "a stored row that cannot be read is still theirs"
    assert (restored.id, restored.workspace_id, restored.messages) == ("broken", ws_id, [])
    return restored


def test_a_corrupt_json_payload_starts_empty_instead_of_crashing(tmp_path, caplog):
    with caplog.at_level(logging.WARNING):
        _opens_empty_under_its_own_id(tmp_path, "{not valid json at all")

    assert any("unreadable" in record.message for record in caplog.records)
    assert not any(
        "not valid json" in record.message for record in caplog.records
    ), "the raw stored payload must never be logged"


def test_an_unknown_message_kind_also_starts_empty_not_crashes(tmp_path):
    _opens_empty_under_its_own_id(tmp_path, json.dumps(
        {"v": PAYLOAD_VERSION, "session_id": None, "summary": "", "turns": [],
         "messages": [{"kind": "not-a-real-kind", "text": "x", "id": "m1"}]}
    ))


def test_an_unrecognized_payload_version_also_starts_empty_not_crashes(tmp_path):
    """The payload carries a REAL message, not an empty transcript --
    proven vacuous once already (a first version of this test used an
    empty `messages: []`, which reads back as `[]` whether or not the
    version guard does anything, so disabling the guard never turned it
    red). A non-empty payload is the only way "started empty" is
    distinguishable from "the guard did nothing and the payload just
    happened to be empty"."""
    _opens_empty_under_its_own_id(tmp_path, json.dumps(
        {"v": PAYLOAD_VERSION + 1, "session_id": "session-future", "summary": "", "turns": [],
         "messages": [{"kind": "answer", "text": "a real answer from a future payload shape",
                       "id": "future-id"}]}
    ))


# --- the person's and the admin's controls --------------------------------


def test_delete_all_history_removes_only_that_persons_rows_everywhere(tmp_path):
    db_path = _db(tmp_path)
    ws1 = _workspace(db_path, "HR")
    ws2 = _workspace(db_path, "Legal")
    runtime = Runtime(db_path=db_path)
    for ws_id in (ws1, ws1, ws2):
        _saved(runtime, "alice", ws_id, "alice's")
    _saved(runtime, "bob", ws1, "bob's")
    runtime.routing_conversation("alice")

    runtime.delete_all_history("alice")

    assert not _theirs(runtime, "alice"), "in-memory transcripts must be dropped too"
    assert "alice" not in runtime.routing_conversations
    assert _stored_rows(db_path, "alice") == 0
    assert _stored_rows(db_path, "bob") == 1, "another person's stored history must be untouched"


def test_delete_conversation_removes_exactly_one_and_only_for_its_owner(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    gone = _saved(runtime, "alice", ws_id, "to delete")
    sibling = _saved(runtime, "alice", ws_id, "kept")

    assert runtime.delete_conversation("bob", gone.id) is False, "not bob's to delete"
    assert gone.id in _stored_ids(db_path)

    assert runtime.delete_conversation("alice", gone.id) is True
    assert _stored_ids(db_path) == {sibling.id}
    assert gone.id not in runtime.conversations
    assert sibling.id in runtime.conversations


def test_delete_workspace_history_takes_every_conversation_there_and_nothing_else(tmp_path):
    """An admin revoke: every one of the person's conversations in THAT
    workspace, stored and live -- there are two here, so deleting "the"
    conversation would leave one -- and nothing in another workspace or
    of another person."""
    db_path = _db(tmp_path)
    ws1 = _workspace(db_path, "HR")
    ws2 = _workspace(db_path, "Legal")
    runtime = Runtime(db_path=db_path)
    _saved(runtime, "alice", ws1, "a")
    _saved(runtime, "alice", ws1, "b")
    elsewhere = _saved(runtime, "alice", ws2, "c")
    bobs = _saved(runtime, "bob", ws1, "d")

    runtime.delete_workspace_history("alice", ws1)

    assert _stored_ids(db_path) == {elsewhere.id, bobs.id}
    assert {c.id for c in runtime.conversations.values()} == {elsewhere.id, bobs.id}


def test_forget_conversations_clears_memory_but_leaves_storage_alone(tmp_path):
    """Ordinary sign-out: the transcript comes back at the next sign-in
    because only the in-memory copy is dropped, not the stored row."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = _saved(runtime, "alice", ws_id, "x")
    runtime.routing_conversation("alice")

    runtime.forget_conversations("alice")

    assert not _theirs(runtime, "alice")
    assert "alice" not in runtime.routing_conversations
    restored = runtime.open_conversation("alice", conversation.id)  # cache miss -> reloads
    assert restored is not conversation
    assert [m.text for m in restored.messages] == ["x"]


# --- what is never persisted -------------------------------------------------


def test_save_conversation_never_writes_the_routing_conversation(tmp_path):
    """F-12's routing conversation has no real workspace behind it --
    `screen.ROUTE_SENTINEL` is never a row in `workspace` -- and
    `conversation` is FK'd to it (db/schema.sql). A cold review found
    that reaching this with `settle()`-True would raise. Must be a silent
    no-op instead of trusting that no caller will ever reach it -- even
    when the routing conversation is somehow given an id."""
    db_path = _db(tmp_path)
    runtime = Runtime(db_path=db_path)
    routing = runtime.routing_conversation("local")
    routing.messages.append(_answer("should never be persisted"))
    runtime.save_conversation(routing)  # must not raise
    routing.id = "given-an-id-anyway"
    runtime.conversations[routing.id] = routing
    runtime.save_conversation(routing)  # must not raise either

    assert _stored_ids(db_path) == set()


def test_a_conversation_with_no_id_is_never_saved(tmp_path):
    """The chat screen's empty chat has no id until its first question;
    saving it must write nothing rather than a row keyed ""."""
    from ui.conversation import Conversation

    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    blank = Conversation(workspace_id=ws_id, user_id="local")
    blank.messages.append(_answer("x"))
    runtime.conversations[""] = blank

    runtime.save_conversation(blank)

    assert _stored_ids(db_path) == set()


# --- cancelling an in-flight answer on delete (cold review) ---------------


def _running(runtime, user_id, ws_id):
    conversation = runtime.new_conversation(user_id, ws_id)
    run = Run(question="q", workspace_id=ws_id, session_id=None)
    conversation.run = run
    return run


def test_delete_all_history_cancels_any_run_still_being_written(tmp_path):
    """"Delete my saved history" while a paid answer is still being
    written must not let that answer keep running into a deleted
    conversation."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    running = _running(runtime, "alice", ws_id)

    runtime.delete_all_history("alice")

    assert running.cancelled is True


def test_delete_conversation_cancels_its_run_and_no_other(tmp_path):
    """ST-53 allows one answer per conversation at once: deleting one
    conversation stops ITS answer, not a sibling's."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    running = _running(runtime, "alice", ws_id)
    sibling = _running(runtime, "alice", ws_id)
    target = next(c for c in runtime.conversations.values() if c.run is running)

    runtime.delete_conversation("alice", target.id)

    assert running.cancelled is True
    assert sibling.cancelled is False


def test_delete_workspace_history_cancels_every_run_there(tmp_path):
    db_path = _db(tmp_path)
    ws1 = _workspace(db_path, "HR")
    ws2 = _workspace(db_path, "Legal")
    runtime = Runtime(db_path=db_path)
    first = _running(runtime, "alice", ws1)
    second = _running(runtime, "alice", ws1)
    elsewhere = _running(runtime, "alice", ws2)

    runtime.delete_workspace_history("alice", ws1)

    assert (first.cancelled, second.cancelled, elsewhere.cancelled) == (True, True, False)


# --- a deleted workspace's conversations, every person's (cold review) ----


def test_forget_workspace_conversations_removes_every_persons_and_cancels_runs(tmp_path):
    """Every person's conversation for a deleted workspace must go, a
    different workspace's must not, and a run still writing into one
    must be cancelled rather than orphaned. (Pre-ST-53, the old code
    popped a key that matched nothing and left all of them.)"""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    other_ws_id = _workspace(db_path, "Legal")
    runtime = Runtime(db_path=db_path)
    alices = runtime.new_conversation("alice", ws_id)
    running = _running(runtime, "bob", ws_id)
    survivor = runtime.new_conversation("alice", other_ws_id)

    runtime.forget_workspace_conversations(ws_id)

    assert alices.id not in runtime.conversations
    assert {c.id for c in runtime.conversations.values()} == {survivor.id}
    assert running.cancelled is True


# --- the two races a cold review reproduced ---------------------------------


def test_a_save_racing_a_delete_does_not_resurrect_deleted_history(tmp_path):
    """Reproduced deterministically with `_save_hook`, the test-only seam
    that runs between the snapshot and the write lock -- a real thread
    race is not reproducible on demand. Before the lock/live-check fix, this
    save would write the row back after the delete removed it."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = runtime.new_conversation("alice", ws_id)
    conversation.messages.append(_answer("about to be deleted"))

    runtime._save_hook = lambda: runtime.delete_all_history("alice")
    runtime.save_conversation(conversation)

    assert _stored_rows(db_path, "alice") == 0, (
        "the save must not resurrect what the concurrent delete just removed"
    )


def test_a_save_racing_a_single_conversation_delete_also_does_not_resurrect_it(tmp_path):
    """Same race, the narrower delete (one conversation): its save must
    still be skipped, not only the whole-account delete's."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = runtime.new_conversation("alice", ws_id)
    conversation.messages.append(_answer("about to be deleted"))

    runtime._save_hook = lambda: runtime.delete_conversation("alice", conversation.id)
    runtime.save_conversation(conversation)

    assert _stored_rows(db_path, "alice") == 0


def test_two_concurrent_first_loads_create_only_one_conversation_object(tmp_path):
    """Reproduced deterministically: `_load_conversation` is slowed down
    and counted, and two threads are released together with a barrier so
    both reach `open_conversation` with nothing in the cache yet. Before
    the lock/double-check fix, both threads would load and each end up
    holding a DIFFERENT `Conversation` object, with only one surviving in
    `runtime.conversations` -- silently discarding whatever the other
    thread went on to do to its own copy."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _saved(Runtime(db_path=db_path), "alice", ws_id, "stored")
    stored_id = next(iter(_stored_ids(db_path)))
    runtime = Runtime(db_path=db_path)

    calls: list[int] = []
    original = runtime._load_conversation

    def slow_load(user_id: str, conversation_id: str):
        calls.append(1)
        threading.Event().wait(0.05)
        return original(user_id, conversation_id)

    runtime._load_conversation = slow_load  # test-only override, this instance alone

    results: list[object] = []
    barrier = threading.Barrier(2)

    def call() -> None:
        barrier.wait(timeout=5)
        results.append(runtime.open_conversation("alice", stored_id))

    threads = [threading.Thread(target=call) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(results) == 2, "both threads must return"
    assert len(calls) == 1, "the second thread must not load a second time"
    assert results[0] is not None and results[0] is results[1], (
        "both callers must get the SAME Conversation object"
    )


# --- the gap a SECOND cold review reproduced --------------------------------


def _save_in_thread(runtime, conversation, errors: list) -> threading.Thread:
    """Start `save_conversation` on its own thread and RECORD any exception.
    An exception on a plain thread never reaches the test, so a save that
    crashed would leave the row count at 0 and pass (third review)."""

    def run() -> None:
        try:
            runtime.save_conversation(conversation)
        except BaseException as exc:  # noqa: BLE001 -- surfaced by the assert
            errors.append(exc)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_delete_all_leaves_nothing_of_the_person_before_its_lock_opens(tmp_path):
    """The second review reproduced deleted history coming back: the delete
    removed the stored row, RELEASED the lock, and only then dropped the
    in-memory copy -- so a save arriving in between found the conversation
    still live and wrote it back (1 row left after "Delete my saved
    history").

    `_delete_hook` runs inside the lock at the last moment before it opens.
    Kill test: move the in-memory removal back after the `with` block and
    the memory assertion goes red on every run -- deterministically, not by
    thread timing. The save started here then proves the behaviour: it
    must wait for the lock and write nothing."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = _saved(runtime, "alice", ws_id, "must stay deleted")
    assert _stored_rows(db_path, "alice") == 1

    seen: dict[str, object] = {}
    saver: list[threading.Thread] = []
    errors: list[BaseException] = []

    def at_the_last_locked_moment() -> None:
        seen["rows"] = _stored_rows(db_path, "alice")
        seen["in_memory"] = conversation.id in runtime.conversations
        saver.append(_save_in_thread(runtime, conversation, errors))

    runtime._delete_hook = at_the_last_locked_moment
    runtime.delete_all_history("alice")
    saver[0].join(timeout=5)
    assert not saver[0].is_alive(), "the save never finished"
    assert errors == [], f"the save crashed instead of skipping: {errors!r}"

    assert seen["rows"] == 0
    assert seen["in_memory"] is False, "the in-memory copy outlived the lock"
    assert _stored_rows(db_path, "alice") == 0, "a save after the delete wrote it back"


def test_a_single_conversation_delete_leaves_nothing_before_its_lock_opens(tmp_path):
    """Same gap on the narrower delete. Kill test: move the in-memory drop
    back after the lock and this goes red."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = _saved(runtime, "alice", ws_id, "must stay deleted")

    seen: dict[str, object] = {}
    saver: list[threading.Thread] = []
    errors: list[BaseException] = []

    def at_the_last_locked_moment() -> None:
        seen["in_memory"] = conversation.id in runtime.conversations
        saver.append(_save_in_thread(runtime, conversation, errors))

    runtime._delete_hook = at_the_last_locked_moment
    runtime.delete_conversation("alice", conversation.id)
    saver[0].join(timeout=5)
    assert not saver[0].is_alive(), "the save never finished"
    assert errors == [], f"the save crashed instead of skipping: {errors!r}"

    assert seen["in_memory"] is False, "the in-memory copy outlived the lock"
    assert _stored_rows(db_path, "alice") == 0, "a save after the delete wrote it back"


def test_deleting_one_conversation_does_not_skip_a_save_in_its_sibling(tmp_path):
    """A delete of conversation A must never make a save in flight for
    conversation B skip -- not even B in the SAME workspace, which ST-53
    now allows (second cold review: a per-person skip did exactly that, so
    B's newest answer never reached disk). Kill test: make
    `save_conversation` skip whenever ANY delete ran for the person and
    B's row is missing."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    in_a = runtime.new_conversation("alice", ws_id)
    in_a.messages.append(_answer("in A"))
    in_b = runtime.new_conversation("alice", ws_id)
    in_b.messages.append(_answer("in B"))

    runtime._save_hook = lambda: runtime.delete_conversation("alice", in_a.id)
    runtime.save_conversation(in_b)
    runtime._save_hook = None

    assert _stored_ids(db_path) == {in_b.id}, "B's save was skipped by a delete of A"


def test_a_save_that_fails_does_not_fail_the_page_and_logs_no_chat_text(
    tmp_path, monkeypatch, caplog
):
    """The save runs inside the chat screen's render after the answer is on
    screen; a busy database used to turn that render into a 500 (second cold
    review). Kill test: remove the try/except in `save_conversation` and the
    call raises."""
    import sqlite3

    import app as app_module

    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = runtime.new_conversation("alice", ws_id)
    conversation.messages.append(_answer("a private answer"))

    def locked(**_kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(app_module.chat_history, "save", locked)

    with caplog.at_level(logging.WARNING, logger="app"):
        runtime.save_conversation(conversation)

    messages = [r.getMessage() for r in caplog.records]
    lines = [m for m in messages if "could not save chat history" in m]
    assert lines, "a failed save must be logged"
    assert "OperationalError" in lines[0]
    assert "a private answer" not in " ".join(messages)
    # The traceback is logged too (so a save failing every time is
    # diagnosable); it must not carry the transcript either.
    assert caplog.records[-1].exc_info is not None
    assert "a private answer" not in caplog.text
