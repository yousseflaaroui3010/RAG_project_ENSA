"""ST-51 exit gate: chat history persisted per (person, workspace), law
09-08. Exercised at the `Runtime` level -- no HTTP, no scripted chat model
needed for most of these, since the persistence seam
(`Runtime.conversation` / `save_conversation` / `delete_all_history`) is
plain Python around real SQLite.

Route-level proof (New conversation dropping its row, the person's own
delete-history confirm page, admin sign-out and ordinary sign-out) lives
in tests/integration/test_s1_chat_screen.py, test_s6_admin.py and
test_s6_auth.py, next to the routes they exercise.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

import workspaces
from app import Runtime, create_app
from config import get_settings
from db import repo
from ui.conversation import Message, MessageKind


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
    payload = json.dumps({"session_id": None, "summary": "", "turns": [], "messages": []})
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
