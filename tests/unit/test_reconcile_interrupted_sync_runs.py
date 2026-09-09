"""`repo.reconcile_interrupted_sync_runs`: closing runs a kill left open.

THE PRODUCTION INCIDENT, because the invariant only makes sense next to
it. On 2026-09-07 the published container was killed by its memory limit
partway through a Sync. `sync._run` stamps `finish_sync_run` from a
`finally:` block, so every ORDINARY failure already closes its row -- but
a killed process never reaches `finally`. The row stayed
`finished_at IS NULL`, `get_running_sync_run` kept answering "running",
the S2 panel polled "Scanning the workspace folder..." for two days, and
the double-sync guard refused every retry. One dead row locked that
workspace out of syncing with no way back through the UI.
"""

from __future__ import annotations

from db import repo


def _run(conn, workspace_id: str, *, finished: bool) -> str:
    sync_run_id = repo.insert_sync_run(conn, workspace_id=workspace_id)
    if finished:
        repo.finish_sync_run(conn, sync_run_id=sync_run_id, added=1)
    return sync_run_id


def _workspace(conn) -> str:
    return repo.create_workspace(conn, name="HR", folder_path="/tmp/corpus")


def test_an_unfinished_run_is_closed_and_stops_reading_as_running(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)

    with repo.session(db_path) as conn:
        workspace_id = _workspace(conn)
        sync_run_id = _run(conn, workspace_id, finished=False)
        assert repo.get_running_sync_run(conn, workspace_id) is not None

        closed = repo.reconcile_interrupted_sync_runs(conn)

        assert closed == [sync_run_id]
        assert repo.get_running_sync_run(conn, workspace_id) is None
        assert repo.get_sync_run(conn, sync_run_id)["finished_at"] is not None


def test_the_recovered_counts_come_from_the_files_that_really_landed(tmp_path):
    """Not zeros. `sync_item` rows are written per file as a run goes, so a
    run killed halfway leaves a true record of what it finished. Stamping
    six zeros would contradict rows sitting in the same database."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)

    with repo.session(db_path) as conn:
        workspace_id = _workspace(conn)
        sync_run_id = _run(conn, workspace_id, finished=False)
        for name, result in (
            ("a.pdf", "added"),
            ("b.pdf", "added"),
            ("c.pdf", "skipped"),
            ("d.pdf", "failed"),
        ):
            repo.insert_sync_item(
                conn, sync_run_id=sync_run_id, file_name=name, result=result
            )

        repo.reconcile_interrupted_sync_runs(conn)

        row = repo.get_sync_run(conn, sync_run_id)
        assert row["added"] == 2
        assert row["skipped"] == 1
        assert row["failed"] == 1
        assert row["changed"] == 0
        assert row["removed"] == 0


def test_a_run_that_finished_normally_is_left_completely_alone(tmp_path):
    """The control probe. Without it, a function that stamped EVERY row
    would pass both tests above while silently rewriting good history."""
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)

    with repo.session(db_path) as conn:
        workspace_id = _workspace(conn)
        sync_run_id = _run(conn, workspace_id, finished=True)
        before = dict(repo.get_sync_run(conn, sync_run_id))

        closed = repo.reconcile_interrupted_sync_runs(conn)

        assert closed == []
        assert dict(repo.get_sync_run(conn, sync_run_id)) == before


def test_nothing_to_do_is_not_an_error(tmp_path):
    db_path = tmp_path / "sanad.db"
    repo.ensure_schema(db_path)
    with repo.session(db_path) as conn:
        assert repo.reconcile_interrupted_sync_runs(conn) == []
