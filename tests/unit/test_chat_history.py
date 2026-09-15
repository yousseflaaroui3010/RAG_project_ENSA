"""S6 saved chat history: the retention POLICY (law 09-08).

Sits above tests/unit/test_db_repo.py's plain-CRUD tests exactly as
chat_history.py sits above db/repo.py: what a non-positive
`chat_history_retention_days` means, when a row counts as expired, and how
the cutoff is computed all belong here, not to the SQL layer's tests.
Moved out of test_db_repo.py by a cold review that found this policy had
leaked into db/repo.py itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import chat_history
import workspaces
from db import repo


def _workspace(db_path, name: str = "ws-history") -> str:
    return workspaces.create_workspace(name=name, folder_path="/tmp/ws", db_path=db_path).id


def test_save_then_load_round_trips(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)

    chat_history.save(
        user_id="local", workspace_id=ws_id, payload="hello", retention_days=30, db_path=db_path
    )

    assert (
        chat_history.load(user_id="local", workspace_id=ws_id, retention_days=30, db_path=db_path)
        == "hello"
    )


def test_retention_zero_save_stores_nothing(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)

    chat_history.save(
        user_id="local", workspace_id=ws_id, payload="anything", retention_days=0, db_path=db_path
    )

    with repo.session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 0
    assert (
        chat_history.load(user_id="local", workspace_id=ws_id, retention_days=0, db_path=db_path)
        is None
    )


def test_retention_zero_deletes_a_row_stored_under_a_larger_setting(tmp_path):
    """A row saved while retention was, say, 30 must be gone the moment the
    setting drops to 0 -- 0 is "keep nothing", not "keep what is already
    there"."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    chat_history.save(
        user_id="local", workspace_id=ws_id, payload="stored", retention_days=30, db_path=db_path
    )

    chat_history.save(
        user_id="local", workspace_id=ws_id, payload="stored", retention_days=0, db_path=db_path
    )

    with repo.session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 0


def test_retention_zero_load_never_queries_storage(tmp_path):
    """Even a row that WAS somehow left behind (an old setting, a sweep
    that has not run yet) must not come back once retention is 0."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    with repo.session(db_path) as conn:
        repo.upsert_chat_history(
            conn, user_id="local", workspace_id=ws_id, payload="leftover", updated_at=repo.utc_now()
        )

    assert (
        chat_history.load(user_id="local", workspace_id=ws_id, retention_days=0, db_path=db_path)
        is None
    )


def test_a_row_older_than_the_retention_window_is_expired_on_load(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    stale = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('local', ?, 'old', ?)",
            (ws_id, stale),
        )

    result = chat_history.load(
        user_id="local", workspace_id=ws_id, retention_days=30, db_path=db_path
    )

    assert result is None
    with repo.session(db_path) as conn:
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM chat_history WHERE workspace_id = ?", (ws_id,)
            ).fetchone()[0]
            == 0
        ), "an expired row must be deleted on read, not merely ignored"


def test_a_row_inside_the_retention_window_is_not_touched(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path)
    fresh = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('local', ?, 'recent', ?)",
            (ws_id, fresh),
        )

    assert (
        chat_history.load(user_id="local", workspace_id=ws_id, retention_days=30, db_path=db_path)
        == "recent"
    )


def test_delete_removes_only_that_one_workspace(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws1 = _workspace(db_path, "ws-del-a")
    ws2 = _workspace(db_path, "ws-del-b")
    chat_history.save(
        user_id="local", workspace_id=ws1, payload="a", retention_days=30, db_path=db_path
    )
    chat_history.save(
        user_id="local", workspace_id=ws2, payload="b", retention_days=30, db_path=db_path
    )

    chat_history.delete(user_id="local", workspace_id=ws1, db_path=db_path)

    assert (
        chat_history.load(user_id="local", workspace_id=ws1, retention_days=30, db_path=db_path)
        is None
    )
    assert (
        chat_history.load(user_id="local", workspace_id=ws2, retention_days=30, db_path=db_path)
        == "b"
    )


def test_delete_for_user_leaves_other_people_alone(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path, "ws-two-people")
    chat_history.save(
        user_id="alice", workspace_id=ws_id, payload="alice's", retention_days=30, db_path=db_path
    )
    chat_history.save(
        user_id="bob", workspace_id=ws_id, payload="bob's", retention_days=30, db_path=db_path
    )

    removed = chat_history.delete_for_user(user_id="alice", db_path=db_path)

    assert removed == 1
    assert (
        chat_history.load(user_id="alice", workspace_id=ws_id, retention_days=30, db_path=db_path)
        is None
    )
    assert (
        chat_history.load(user_id="bob", workspace_id=ws_id, retention_days=30, db_path=db_path)
        == "bob's"
    )


def test_sweep_expired_removes_only_stale_rows(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path, "ws-sweep")
    stale = (datetime.now(UTC) - timedelta(days=31)).isoformat()
    fresh = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('stale-user', ?, 'old', ?)",
            (ws_id, stale),
        )
        conn.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('fresh-user', ?, 'recent', ?)",
            (ws_id, fresh),
        )

    removed = chat_history.sweep_expired(retention_days=30, db_path=db_path)

    assert removed == 1
    assert (
        chat_history.load(
            user_id="fresh-user", workspace_id=ws_id, retention_days=30, db_path=db_path
        )
        == "recent"
    )


def test_sweep_expired_with_retention_zero_clears_the_table_outright(tmp_path):
    """0 is "keep nothing" for the sweep too, not just save/load -- a row
    left behind by a PAST, larger setting must not survive the very
    first start-up after retention drops to 0."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    ws_id = _workspace(db_path, "ws-sweep-zero")
    fresh = datetime.now(UTC).isoformat()
    with repo.session(db_path) as conn:
        conn.execute(
            "INSERT INTO chat_history (user_id, workspace_id, payload, updated_at) "
            "VALUES ('local', ?, 'recent', ?)",
            (ws_id, fresh),
        )

    removed = chat_history.sweep_expired(retention_days=0, db_path=db_path)

    assert removed == 1
    with repo.session(db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM chat_history").fetchone()[0] == 0
