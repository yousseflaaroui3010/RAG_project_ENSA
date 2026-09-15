"""S6 saved chat history exit gate: persisted per (person, workspace), law
09-08. Exercised at the `Runtime` level -- no HTTP, no scripted chat model
needed for most of these, since the persistence seam
(`Runtime.conversation` / `save_conversation` / `delete_all_history`) is
plain Python around real SQLite.

Route-level proof (New conversation dropping its row, the person's own
delete-history confirm page, admin sign-out, ordinary sign-out, and an
admin revoke deleting the revoked workspace's row) lives in
tests/integration/test_s1_chat_screen.py, test_s6_admin.py and
test_s6_auth.py, next to the routes they exercise.
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
from ui import screen
from ui.conversation import PAYLOAD_VERSION, Message, MessageKind
from ui.runs import Run


def _workspace(db_path, name: str = "HR") -> str:
    return workspaces.create_workspace(
        name=name, folder_path=str(db_path.parent), db_path=db_path
    ).id


def _answer(text: str, *, id: str | None = None) -> Message:
    return Message(kind=MessageKind.ANSWER, text=text, id=id or f"id-{text}")


# --- restart survival ---------------------------------------------------


def test_a_saved_conversation_survives_a_new_runtime_on_the_same_db(tmp_path):
    """The literal exit-gate proof: a SECOND `Runtime` instance, standing
    in for a process restart, reads what the first one wrote."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)

    first = Runtime(db_path=db_path)
    conversation = first.conversation(ws_id, "local")
    conversation.messages.append(_answer("Trois mois.", id="fixed-id"))
    conversation.session_id = "session-xyz"
    conversation.summary = "compact"
    first.save_conversation("local", conversation)

    second = Runtime(db_path=db_path)
    restored = second.conversation(ws_id, "local")

    assert second is not first
    assert restored is not conversation
    assert [m.text for m in restored.messages] == ["Trois mois."]
    assert restored.messages[0].id == "fixed-id"
    assert restored.session_id == "session-xyz"
    assert restored.summary == "compact"


def test_two_people_in_the_same_workspace_never_see_each_others_history(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)

    runtime = Runtime(db_path=db_path)
    alice = runtime.conversation(ws_id, "alice")
    alice.messages.append(_answer("Alice's answer"))
    runtime.save_conversation("alice", alice)

    bob = runtime.conversation(ws_id, "bob")
    bob.messages.append(_answer("Bob's answer"))
    runtime.save_conversation("bob", bob)

    fresh = Runtime(db_path=db_path)
    alice_restored = fresh.conversation(ws_id, "alice")
    bob_restored = fresh.conversation(ws_id, "bob")

    assert [m.text for m in alice_restored.messages] == ["Alice's answer"]
    assert [m.text for m in bob_restored.messages] == ["Bob's answer"]


# --- retention -----------------------------------------------------------


def test_retention_zero_stores_nothing(tmp_path, monkeypatch):
    import app as app_module

    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    settings = get_settings().model_copy(update={"chat_history_retention_days": 0})
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)

    first = Runtime(db_path=db_path)
    conversation = first.conversation(ws_id, "local")
    conversation.messages.append(_answer("x"))
    first.save_conversation("local", conversation)

    with repo.session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 0

    second = Runtime(db_path=db_path)
    assert second.conversation(ws_id, "local").messages == []


def test_a_row_past_the_retention_window_is_dropped_on_load(tmp_path, monkeypatch):
    import app as app_module

    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    settings = get_settings().model_copy(update={"chat_history_retention_days": 30})
    monkeypatch.setattr(app_module, "get_settings", lambda: settings)
    stale = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    payload = json.dumps(
        {"v": PAYLOAD_VERSION, "session_id": None, "summary": "", "turns": [], "messages": []}
    )
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('local', ?, ?, ?)",
            (ws_id, payload, stale),
        )

    runtime = Runtime(db_path=db_path)
    restored = runtime.conversation(ws_id, "local")

    assert restored.messages == []
    with repo.session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 0, (
            "an expired row must be deleted on read, not merely ignored"
        )


def test_start_up_sweeps_expired_chat_history(tmp_path):
    """`create_app`'s lifespan (app.py) runs the sweep once at start-up, so
    a row nobody ever loads again still stays bounded by the retention
    window."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    stale = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('local', ?, '{}', ?)",
            (ws_id, stale),
        )

    runtime = Runtime(ports_factory=lambda: None, db_path=db_path)
    with TestClient(create_app(runtime)):
        pass  # lifespan runs on entering/exiting the client context

    with repo.session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 0


# --- corrupt storage must not crash the chat screen -----------------------


def test_a_corrupt_json_payload_starts_empty_instead_of_crashing(tmp_path, caplog):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('local', ?, ?, ?)",
            (ws_id, "{not valid json at all", repo.utc_now()),
        )

    runtime = Runtime(db_path=db_path)
    with caplog.at_level(logging.WARNING):
        restored = runtime.conversation(ws_id, "local")

    assert restored.messages == []
    assert any("unreadable" in record.message for record in caplog.records)
    assert not any(
        "not valid json" in record.message for record in caplog.records
    ), "the raw stored payload must never be logged"


def test_an_unknown_message_kind_also_starts_empty_not_crashes(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    bad_payload = json.dumps(
        {
            "v": PAYLOAD_VERSION,
            "session_id": None,
            "summary": "",
            "turns": [],
            "messages": [{"kind": "not-a-real-kind", "text": "x", "id": "m1"}],
        }
    )
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('local', ?, ?, ?)",
            (ws_id, bad_payload, repo.utc_now()),
        )

    runtime = Runtime(db_path=db_path)
    assert runtime.conversation(ws_id, "local").messages == []


def test_an_unrecognized_payload_version_also_starts_empty_not_crashes(tmp_path):
    """The payload carries a REAL message, not an empty transcript --
    proven vacuous once already (a first version of this test used an
    empty `messages: []`, which reads back as `[]` whether or not the
    version guard does anything, so disabling the guard never turned it
    red). A non-empty payload is the only way "started empty" is
    distinguishable from "the guard did nothing and the payload just
    happened to be empty"."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    future_payload = json.dumps(
        {
            "v": PAYLOAD_VERSION + 1,
            "session_id": "session-future",
            "summary": "",
            "turns": [],
            "messages": [
                {
                    "kind": "answer",
                    "text": "a real answer from a future payload shape",
                    "id": "future-id",
                }
            ],
        }
    )
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('local', ?, ?, ?)",
            (ws_id, future_payload, repo.utc_now()),
        )

    runtime = Runtime(db_path=db_path)
    assert runtime.conversation(ws_id, "local").messages == []


# --- the person's and the admin's controls --------------------------------


def test_delete_all_history_removes_only_that_persons_rows_everywhere(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws1 = _workspace(db_path, "HR")
    ws2 = _workspace(db_path, "Legal")

    runtime = Runtime(db_path=db_path)
    for ws_id in (ws1, ws2):
        conversation = runtime.conversation(ws_id, "alice")
        conversation.messages.append(_answer("alice's"))
        runtime.save_conversation("alice", conversation)
    bob = runtime.conversation(ws1, "bob")
    bob.messages.append(_answer("bob's"))
    runtime.save_conversation("bob", bob)

    runtime.delete_all_history("alice")

    assert not any(key.startswith("alice|") for key in runtime.conversations), (
        "in-memory transcripts must be dropped too"
    )
    with repo.session(db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM chat_history WHERE user_id = 'alice'"
            ).fetchone()[0]
            == 0
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM chat_history WHERE user_id = 'bob'"
            ).fetchone()[0]
            == 1
        ), "another person's stored history must be untouched"


def test_forget_conversations_clears_memory_but_leaves_storage_alone(tmp_path):
    """Ordinary sign-out: the transcript comes back at the next sign-in
    because only the in-memory copy is dropped, not the stored row."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)

    runtime = Runtime(db_path=db_path)
    conversation = runtime.conversation(ws_id, "alice")
    conversation.messages.append(_answer("x"))
    runtime.save_conversation("alice", conversation)

    runtime.forget_conversations("alice")

    assert not any(key.startswith("alice|") for key in runtime.conversations)
    restored = runtime.conversation(ws_id, "alice")  # cache miss -> reloads
    assert [m.text for m in restored.messages] == ["x"]


# --- the routing sentinel is never persisted -------------------------------


def test_save_conversation_never_writes_the_routing_sentinel(tmp_path):
    """F-12's routing conversation has no real workspace behind it --
    `screen.ROUTE_SENTINEL` is never a row in `workspace` -- and
    `chat_history` is FK'd to it (db/schema.sql). A cold review found
    that reaching this with `settle()`-True would raise. Must be a silent
    no-op instead of trusting that no caller will ever reach it."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = runtime.conversation(screen.ROUTE_SENTINEL, "local")
    conversation.messages.append(_answer("should never be persisted"))

    runtime.save_conversation("local", conversation)  # must not raise

    with repo.session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 0


# --- cancelling an in-flight answer on delete (cold review) ---------------


def test_delete_all_history_cancels_any_run_still_being_written(tmp_path):
    """"Delete my saved history" while a paid answer is still being
    written must not let that answer keep running into a deleted
    conversation."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = runtime.conversation(ws_id, "alice")
    running = Run(question="q", workspace_id=ws_id, session_id=None)
    conversation.run = running

    runtime.delete_all_history("alice")

    assert running.cancelled is True


def test_delete_conversation_storage_cancels_any_run_still_being_written(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = runtime.conversation(ws_id, "alice")
    running = Run(question="q", workspace_id=ws_id, session_id=None)
    conversation.run = running

    runtime.delete_conversation_storage("alice", ws_id)

    assert running.cancelled is True


# --- a deleted workspace's conversations, every person's (cold review) ----


def test_forget_workspace_conversations_removes_every_persons_key_and_cancels_runs(tmp_path):
    """The old code did `runtime.conversations.pop(workspace_id, None)`,
    which matches nothing: every key is `"user_id|workspace_id"` since
    S6. Every person's entry for a deleted workspace must go, a
    different workspace's must not, and a run still writing into one
    must be cancelled rather than orphaned."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    other_ws_id = _workspace(db_path, "Legal")

    runtime = Runtime(db_path=db_path)
    runtime.conversation(ws_id, "alice")
    bob = runtime.conversation(ws_id, "bob")
    runtime.conversation(other_ws_id, "alice")
    running = Run(question="q", workspace_id=ws_id, session_id=None)
    bob.run = running

    runtime.forget_workspace_conversations(ws_id)

    assert f"alice|{ws_id}" not in runtime.conversations
    assert f"bob|{ws_id}" not in runtime.conversations
    assert f"alice|{other_ws_id}" in runtime.conversations, "a different workspace must survive"
    assert running.cancelled is True


# --- the two races a cold review reproduced ---------------------------------


def test_a_save_racing_a_delete_does_not_resurrect_deleted_history(tmp_path):
    """Reproduced deterministically with `_save_hook`, the test-only seam
    that runs between the snapshot and the write lock -- a real thread
    race is not reproducible on demand. Before the epoch/lock fix, this
    save would write the row back after the delete removed it."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = runtime.conversation(ws_id, "alice")
    conversation.messages.append(_answer("about to be deleted"))

    def delete_between_snapshot_and_write() -> None:
        # Simulates a concurrent "Delete my saved history" landing in the
        # exact gap between this save's snapshot and its write.
        runtime.delete_all_history("alice")

    runtime._save_hook = delete_between_snapshot_and_write
    runtime.save_conversation("alice", conversation)

    with repo.session(db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM chat_history WHERE user_id = 'alice'"
            ).fetchone()[0]
            == 0
        ), "the save must not resurrect what the concurrent delete just removed"


def test_a_save_racing_a_per_workspace_delete_also_does_not_resurrect_it(tmp_path):
    """Same race, the narrower delete ('New conversation' or an admin
    revoke): a save for THIS workspace must still be skipped, not only
    the whole-account delete."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)
    conversation = runtime.conversation(ws_id, "alice")
    conversation.messages.append(_answer("about to be deleted"))

    def delete_between_snapshot_and_write() -> None:
        runtime.delete_conversation_storage("alice", ws_id)

    runtime._save_hook = delete_between_snapshot_and_write
    runtime.save_conversation("alice", conversation)

    with repo.session(db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM chat_history WHERE user_id = 'alice'"
            ).fetchone()[0]
            == 0
        )


def test_two_concurrent_first_loads_create_only_one_conversation_object(tmp_path):
    """Reproduced deterministically: `_load_conversation` is slowed down
    and counted, and two threads are released together with a barrier so
    both reach `conversation()` with nothing in the cache yet. Before the
    lock/double-check fix, both threads would load and each end up
    holding a DIFFERENT `Conversation` object, with only one surviving in
    `runtime.conversations` -- silently discarding whatever the other
    thread went on to do to its own copy."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    runtime = Runtime(db_path=db_path)

    calls: list[int] = []
    original = runtime._load_conversation

    def slow_load(user_id: str, workspace_id: str):
        calls.append(1)
        threading.Event().wait(0.05)
        return original(user_id, workspace_id)

    runtime._load_conversation = slow_load  # test-only override, this instance alone

    results: list[object] = []
    barrier = threading.Barrier(2)

    def call() -> None:
        barrier.wait(timeout=5)
        results.append(runtime.conversation(ws_id, "alice"))

    threads = [threading.Thread(target=call) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert len(results) == 2, "both threads must return"
    assert len(calls) == 1, "the second thread must not load a second time"
    assert results[0] is results[1], "both callers must get the SAME Conversation object"
