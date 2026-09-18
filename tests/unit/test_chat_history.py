"""S6 saved chat history: the retention POLICY (law 09-08), and since
ST-53 the rules of many conversations per person -- titles, rename, the
list, and that an id alone never reaches someone else's conversation.

Sits above tests/unit/test_db_repo.py's plain-CRUD tests exactly as
chat_history.py sits above db/repo.py: what a non-positive
`chat_history_retention_days` means, when a row counts as expired, how the
cutoff is computed and what a valid title is all belong here, not to the
SQL layer's tests. Moved out of test_db_repo.py by a cold review that found
this policy had leaked into db/repo.py itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

import chat_history
import workspaces
from db import repo


def _workspace(db_path, name: str = "ws-history") -> str:
    return workspaces.create_workspace(name=name, folder_path="/tmp/ws", db_path=db_path).id


def _db(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    return db_path


def _save(db_path, conversation_id, ws_id, *, user="local", payload="p", question=None, days=30):
    chat_history.save(
        conversation_id=conversation_id,
        user_id=user,
        workspace_id=ws_id,
        payload=payload,
        first_question=question,
        retention_days=days,
        db_path=db_path,
    )


def _load(db_path, conversation_id, *, user="local", days=30):
    return chat_history.load(
        conversation_id=conversation_id, user_id=user, retention_days=days, db_path=db_path
    )


def _insert(db_path, conversation_id, ws_id, updated_at, *, user="local", payload="p"):
    """A row written straight to the table, with a chosen age."""
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO conversation "
            "(id, user_id, workspace_id, title, payload, created_at, updated_at) "
            "VALUES (?, ?, ?, NULL, ?, ?, ?)",
            (conversation_id, user, ws_id, payload, updated_at, updated_at),
        )


def _count(db_path) -> int:
    with repo.session(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM conversation").fetchone()[0]


# --- retention (law 09-08) ---------------------------------------------------


def test_save_then_load_round_trips(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)

    _save(db_path, "c1", ws_id, payload="hello")

    stored = _load(db_path, "c1")
    assert stored is not None
    assert (stored.id, stored.workspace_id, stored.payload) == ("c1", ws_id, "hello")


def test_retention_zero_save_stores_nothing(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)

    _save(db_path, "c1", ws_id, payload="anything", days=0)

    assert _count(db_path) == 0
    assert _load(db_path, "c1", days=0) is None


def test_retention_zero_deletes_a_row_stored_under_a_larger_setting(tmp_path):
    """A row saved while retention was, say, 30 must be gone the moment the
    setting drops to 0 -- 0 is "keep nothing", not "keep what is already
    there"."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _save(db_path, "c1", ws_id, payload="stored")

    _save(db_path, "c1", ws_id, payload="stored", days=0)

    assert _count(db_path) == 0


def test_retention_zero_load_never_queries_storage(tmp_path):
    """Even a row that WAS somehow left behind (an old setting, a sweep
    that has not run yet) must not come back once retention is 0."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _insert(db_path, "c1", ws_id, repo.utc_now(), payload="leftover")

    assert _load(db_path, "c1", days=0) is None


def test_a_row_older_than_the_retention_window_is_expired_on_load(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _insert(db_path, "c1", ws_id, (datetime.now(UTC) - timedelta(days=31)).isoformat())

    assert _load(db_path, "c1") is None
    assert _count(db_path) == 0, "an expired row must be deleted on read, not merely ignored"


def test_a_row_inside_the_retention_window_is_not_touched(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _insert(
        db_path, "c1", ws_id, (datetime.now(UTC) - timedelta(days=1)).isoformat(), payload="recent"
    )

    stored = _load(db_path, "c1")
    assert stored is not None and stored.payload == "recent"


def test_sweep_expired_removes_only_stale_rows(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path, "ws-sweep")
    _insert(db_path, "old", ws_id, (datetime.now(UTC) - timedelta(days=31)).isoformat())
    _insert(db_path, "new", ws_id, (datetime.now(UTC) - timedelta(days=1)).isoformat())

    removed = chat_history.sweep_expired(retention_days=30, db_path=db_path)

    assert removed == 1
    assert _load(db_path, "new") is not None


def test_sweep_expired_with_retention_zero_clears_the_table_outright(tmp_path):
    """0 is "keep nothing" for the sweep too, not just save/load -- a row
    left behind by a PAST, larger setting must not survive the very
    first start-up after retention drops to 0."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path, "ws-sweep-zero")
    _insert(db_path, "c1", ws_id, datetime.now(UTC).isoformat())

    removed = chat_history.sweep_expired(retention_days=0, db_path=db_path)

    assert removed == 1
    assert _count(db_path) == 0


# --- ownership: an id alone reaches nothing (ST-53) ------------------------


def test_another_persons_id_loads_renames_and_deletes_nothing(tmp_path):
    """Knowing someone's conversation id must not be enough to read,
    rename or delete it: every operation also matches the owner."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _save(db_path, "alices", ws_id, user="alice", payload="alice's", question="Q?")

    assert _load(db_path, "alices", user="bob") is None
    assert not chat_history.rename(
        conversation_id="alices", user_id="bob", title="mine now", db_path=db_path
    )
    assert not chat_history.delete(conversation_id="alices", user_id="bob", db_path=db_path)

    stored = _load(db_path, "alices", user="alice")
    assert stored is not None and stored.payload == "alice's" and stored.title == "Q?"


def test_a_save_under_someone_elses_id_never_overwrites_their_row(tmp_path):
    """The upsert's update half is scoped to the same owner: a colliding
    id from another person leaves the row as it was."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _save(db_path, "shared-id", ws_id, user="alice", payload="alice's")

    _save(db_path, "shared-id", ws_id, user="bob", payload="bob's")

    assert _load(db_path, "shared-id", user="alice").payload == "alice's"
    assert _load(db_path, "shared-id", user="bob") is None


def test_delete_removes_only_that_one_conversation(tmp_path):
    db_path = _db(tmp_path)
    ws1 = _workspace(db_path, "ws-del-a")
    ws2 = _workspace(db_path, "ws-del-b")
    _save(db_path, "a1", ws1)
    _save(db_path, "a2", ws1)
    _save(db_path, "b1", ws2)

    assert chat_history.delete(conversation_id="a1", user_id="local", db_path=db_path)

    assert _load(db_path, "a1") is None
    assert _load(db_path, "a2") is not None, "a sibling in the same workspace must stay"
    assert _load(db_path, "b1") is not None


def test_delete_in_workspace_removes_every_conversation_there_for_that_person(tmp_path):
    db_path = _db(tmp_path)
    ws1 = _workspace(db_path, "ws-rev-a")
    ws2 = _workspace(db_path, "ws-rev-b")
    _save(db_path, "a1", ws1)
    _save(db_path, "a2", ws1)
    _save(db_path, "b1", ws2)
    _save(db_path, "other", ws1, user="bob")

    removed = chat_history.delete_in_workspace(user_id="local", workspace_id=ws1, db_path=db_path)

    assert removed == 2
    assert _load(db_path, "b1") is not None
    assert _load(db_path, "other", user="bob") is not None


def test_delete_for_user_leaves_other_people_alone(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path, "ws-two-people")
    _save(db_path, "a1", ws_id, user="alice")
    _save(db_path, "a2", ws_id, user="alice")
    _save(db_path, "b1", ws_id, user="bob", payload="bob's")

    removed = chat_history.delete_for_user(user_id="alice", db_path=db_path)

    assert removed == 2
    assert _load(db_path, "a1", user="alice") is None
    assert _load(db_path, "b1", user="bob").payload == "bob's"


# --- titles and the list (ST-53) ------------------------------------------


def test_the_title_is_the_first_question_and_a_later_save_never_changes_it(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)

    _save(db_path, "c1", ws_id, question="  Durée   du préavis ?  ")
    _save(db_path, "c1", ws_id, question="a different first question", payload="later")

    stored = _load(db_path, "c1")
    assert stored.title == "Durée du préavis ?"
    assert stored.payload == "later"


def test_a_rename_survives_the_next_save(tmp_path):
    """The next answer being saved must not put the automatic title back."""
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _save(db_path, "c1", ws_id, question="first question")

    assert chat_history.rename(
        conversation_id="c1", user_id="local", title="  My   notes ", db_path=db_path
    )
    _save(db_path, "c1", ws_id, question="first question", payload="after")

    assert _load(db_path, "c1").title == "My notes"


def test_a_long_first_question_is_cut_to_the_title_limit(tmp_path):
    long_question = "mot " * 60

    title = chat_history.title_from(long_question)

    assert len(title) == chat_history.TITLE_MAX_CHARS
    assert title.endswith("…")
    assert chat_history.title_from("   ") is None
    assert chat_history.title_from(None) is None


@pytest.mark.parametrize("bad", ["", "   ", "x" * (chat_history.TITLE_MAX_CHARS + 1)])
def test_an_empty_or_over_long_rename_is_refused_and_changes_nothing(tmp_path, bad):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _save(db_path, "c1", ws_id, question="kept")

    with pytest.raises(chat_history.InvalidTitleError):
        chat_history.rename(conversation_id="c1", user_id="local", title=bad, db_path=db_path)

    assert _load(db_path, "c1").title == "kept"


def test_a_title_of_exactly_the_limit_is_accepted(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _save(db_path, "c1", ws_id)
    exact = "x" * chat_history.TITLE_MAX_CHARS

    assert chat_history.rename(conversation_id="c1", user_id="local", title=exact, db_path=db_path)
    assert _load(db_path, "c1").title == exact


def test_the_list_is_newest_first_one_person_one_workspace_and_skips_expired(tmp_path):
    db_path = _db(tmp_path)
    ws1 = _workspace(db_path, "ws-list-a")
    ws2 = _workspace(db_path, "ws-list-b")
    now = datetime.now(UTC)
    _insert(db_path, "older", ws1, (now - timedelta(days=2)).isoformat())
    _insert(db_path, "newer", ws1, (now - timedelta(days=1)).isoformat())
    _insert(db_path, "expired", ws1, (now - timedelta(days=40)).isoformat())
    _insert(db_path, "elsewhere", ws2, now.isoformat())
    _insert(db_path, "bobs", ws1, now.isoformat(), user="bob")

    listed = chat_history.list_for(
        user_id="local", workspace_id=ws1, retention_days=30, db_path=db_path
    )

    assert [item.id for item in listed] == ["newer", "older"]
    assert chat_history.latest_id(
        user_id="local", workspace_id=ws1, retention_days=30, db_path=db_path
    ) == "newer"


def test_renaming_does_not_move_a_conversation_up_the_list(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    now = datetime.now(UTC)
    _insert(db_path, "older", ws_id, (now - timedelta(days=2)).isoformat())
    _insert(db_path, "newer", ws_id, (now - timedelta(days=1)).isoformat())

    chat_history.rename(conversation_id="older", user_id="local", title="renamed", db_path=db_path)

    listed = chat_history.list_for(
        user_id="local", workspace_id=ws_id, retention_days=30, db_path=db_path
    )
    assert [item.id for item in listed] == ["newer", "older"]


def test_the_list_is_empty_when_retention_is_zero(tmp_path):
    db_path = _db(tmp_path)
    ws_id = _workspace(db_path)
    _insert(db_path, "c1", ws_id, repo.utc_now())

    assert chat_history.list_for(
        user_id="local", workspace_id=ws_id, retention_days=0, db_path=db_path
    ) == []
