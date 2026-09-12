from db import repo
from recovery import ABANDONED_ERROR, RecoveryResult, recover_abandoned_runs


def test_startup_recovery_settles_abandoned_runs_and_keeps_saved_work(tmp_path):
    db_path = tmp_path / "sanad.db"
    with repo.session(db_path) as conn:
        workspace_id = repo.create_workspace(
            conn, name="Recovery", folder_path=str(tmp_path)
        )
        sync_id = repo.insert_sync_run(
            conn, workspace_id=workspace_id, started_at=repo.utc_now()
        )
        repo.insert_sync_item(
            conn,
            sync_run_id=sync_id,
            file_name="done.txt",
            result="added",
        )
        eval_id = repo.insert_eval_run(
            conn,
            workspace_id=workspace_id,
            status="running",
            question_total=3,
        )
        repo.insert_eval_result(
            conn,
            eval_run_id=eval_id,
            question_id="q1",
            kind="in_scope",
            passed=True,
        )

    recovered = recover_abandoned_runs(db_path=db_path)

    assert recovered == RecoveryResult(sync_runs=1, evaluation_runs=1)
    with repo.session(db_path) as conn:
        sync_run = repo.get_sync_run(conn, sync_id)
        eval_run = repo.get_eval_run(conn, eval_id)
        assert sync_run["finished_at"] is not None
        assert sync_run["added"] == 1
        assert eval_run["status"] == "partial"
        assert eval_run["failed_question_number"] == 2
        assert eval_run["error"] == ABANDONED_ERROR
        assert repo.eval_run_progress(conn, eval_id) == 1

    assert recover_abandoned_runs(db_path=db_path) == RecoveryResult(0, 0)
