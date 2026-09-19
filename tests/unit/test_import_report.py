"""scripts/import_report.py: a report measured elsewhere, put on this
server's Reports screen -- always with its note, never twice."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from db import repo
from scripts.import_report import ImportRefusedError, import_report, main
from ui import reports_screen

RELEASE = Path(__file__).resolve().parents[2] / "docs/evals/release-v3.1.0-2026-09-19.json"
NOTE = "a laptop copy of the same 3 documents"


@pytest.fixture
def server(tmp_path):
    db_path = tmp_path / "sanad.db"
    with repo.session(db_path) as conn:
        ws_id = repo.create_workspace(conn, name="Live HR", folder_path=str(tmp_path))
    return db_path, ws_id, tmp_path / "reports"


def _runs(db_path) -> int:
    with repo.session(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM eval_run").fetchone()[0]


def test_the_imported_run_shows_with_its_scores_its_answers_and_its_note(server):
    db_path, ws_id, reports_dir = server
    source = json.loads(RELEASE.read_text(encoding="utf-8"))

    run_id, written, backup = import_report(
        report=RELEASE, workspace_id=ws_id, note=NOTE,
        db_path=db_path, reports_dir=reports_dir,
    )

    [summary] = reports_screen.list_reports(db_path=db_path)
    assert summary.id == run_id and summary.workspace_id == ws_id
    assert summary.provenance == NOTE
    assert summary.passed is True
    assert summary.grounded_pass == source["grounded_pass"] == 39
    assert summary.refusal_pass == 20 and summary.sources_total == 39
    detail = reports_screen.report_detail(run_id, db_path=db_path)
    assert detail.file_error is None
    assert len(detail.questions) == source["question_total"] == 60
    snapshot = json.loads(written.read_text(encoding="utf-8"))
    assert snapshot["workspace_id"] == ws_id and snapshot["provenance"] == NOTE
    with repo.session(db_path) as conn:
        assert len(repo.list_eval_results(conn, run_id)) == 60
    assert backup.is_file()


def test_the_same_run_is_never_imported_twice(server):
    db_path, ws_id, reports_dir = server
    kwargs = dict(report=RELEASE, workspace_id=ws_id, note=NOTE,
                  db_path=db_path, reports_dir=reports_dir)
    import_report(**kwargs)

    with pytest.raises(ImportRefusedError, match="already on this workspace"):
        import_report(**kwargs)
    assert _runs(db_path) == 1


@pytest.mark.parametrize("note", ["", "   "])
def test_no_note_no_import(server, note):
    db_path, ws_id, reports_dir = server

    with pytest.raises(ImportRefusedError, match="--note"):
        import_report(report=RELEASE, workspace_id=ws_id, note=note,
                      db_path=db_path, reports_dir=reports_dir)
    assert _runs(db_path) == 0
    assert not reports_dir.exists()


def test_an_unknown_workspace_or_database_is_refused_before_writing(server, tmp_path):
    db_path, _ws_id, reports_dir = server

    with pytest.raises(ImportRefusedError, match="no workspace"):
        import_report(report=RELEASE, workspace_id="nope", note=NOTE,
                      db_path=db_path, reports_dir=reports_dir)
    missing = tmp_path / "elsewhere" / "sanad.db"
    with pytest.raises(ImportRefusedError, match="no database"):
        import_report(report=RELEASE, workspace_id="nope", note=NOTE,
                      db_path=missing, reports_dir=reports_dir)
    assert not missing.exists()
    assert _runs(db_path) == 0 and not reports_dir.exists()


def test_the_command_line_says_refused_and_exits_non_zero(server, capsys):
    db_path, ws_id, _reports_dir = server

    code = main(["--report", str(RELEASE), "--workspace-id", ws_id, "--note", " "])

    assert code == 1
    assert "REFUSED" in capsys.readouterr().err
