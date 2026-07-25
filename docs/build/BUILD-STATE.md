# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: 868aab1 on main (docs sync + ST-02 + CI fixes + handbook, all merged)
Updated: 2026-07-25 by b1 (ST-10 integration)

## Now (the one task in flight)
- Task: ST-10 SQLite schema + data access — code done, exit gate green,
  reviewed 9/10 MERGE with zero blocking defects. Status: PR OPEN,
  AWAITING HUMAN MERGE. Not merged. Nothing lands on main until a human
  presses the button; the PR is set to squash-merge only.
- Branch: feat/S1-ST-10-db (cut from main @868aab1), pushed to origin at
  7182b47. Built in an isolated worktree on a temporary ref, then moved
  onto the story branch to satisfy the one-story-one-branch rule before
  review. The worktree has since been deregistered and deleted.
- b1 re-ran the exit gate independently on 7182b47: `uv run ruff check .`
  -> "All checks passed!"; `uv run pytest -q` -> 14 passed.
- Follow-ups deferred to ST-11 (reviewer's five non-blocking notes, do
  not lose these):
  1. db/repo.py:76 `session()` has no callers and no rollback test.
     Add a rollback test or drop the helper.
  2. db/repo.py:55 the config-path default in `get_connection()` is
     never exercised; every test passes an explicit tmp_path.
  3. tests/unit/test_db_repo.py:59 the cascade test needs pre-delete
     `== 1` assertions so a degenerate `_count` cannot pass vacuously.
  4. `init_db` has no bootstrap caller outside tests; app startup never
     creates the registry.
  5. tests/unit/test_db_repo.py:76 uses inline SQL because
     `delete_document` does not exist yet.
- Side branch: chore/gitignore-worktrees (one commit 545446c off main,
  pushed) adds `.claude/worktrees/` to .gitignore. Kept off the ST-10
  branch on purpose so the reviewed diff stays clean. Also PR-pending.
- Delivered: db/schema.sql (6 tables, arch §7.3 DDL translated per §7.4
  deviations: uuid->TEXT app-generated, timestamptz->TEXT ISO-8601 UTC
  app-set, boolean->INTEGER, numeric(4,3)->REAL, CHECK/FK unchanged);
  db/repo.py (single `_connect_raw()` sqlite3.connect call site, PRAGMA
  foreign_keys=ON on every open, `session()` txn context manager, minimal
  create/insert/delete per table, path from config.get_settings()
  .sqlite_db_path, no hardcoded literal); tests/unit/test_db_repo.py
  (12 tests: PRAGMA on, cascade delete workspace -> document/sync_run/
  sync_item/eval_run/eval_result, SET NULL on sync_item.document_id per
  reference DDL line 314, all six sync_item.result values + seventh-value
  rejection, unique (workspace_id, file_name) rejected in-workspace /
  allowed cross-workspace).
- Verify: `uv run ruff check .` clean; `uv run pytest -q` 14 passed
  (12 new + 2 existing test_config.py).
- Absence check done: grep for schema/repo.py/sqlite3/PRAGMA across the
  repo (pre-task) hit only docs/phase2 and docs/build refs. Confirmed
  greenfield for db/ before writing.
- What is NOT done yet for ST-10: the merge itself. The PR is open and
  squash-merge is the only allowed strategy; a human presses it.

## Next (ordered queue, top 3 only)
0. HUMAN: merge the ST-10 PR (squash), then the chore/gitignore-worktrees
   PR. ST-11 and ST-12 should start from main only after that lands.
1. ST-11 Workspaces create/rename/delete + legal flag (depends on ST-10;
   unblocks once the ST-10 PR is merged) — owner MB. Carries the five
   ST-10 follow-ups listed above.
2. ST-12 Content hashing + change-detection state machine (depends on
   ST-10; unblocks once the ST-10 PR is merged).
3. ST-03 CI skeleton — gate.yml already satisfies it (ruff + pytest per PR,
   a failing test blocks); confirm and close, or extend minimally.

## Blockers / waiting on human
- Nothing blocking ST-11/ST-12; the item below only degrades tooling.
- codebase-memory-mcp (map layer / graph search) is configured in .mcp.json
  but the binary is not installed on this machine; a web search for the
  install source turned up a suspicious result (apparent prompt-injection
  text in a fetched install.ps1 description) so installation was declined.
  Graph tools (search_graph/trace_path/impact) are unavailable until a
  human supplies a trusted install source. Working around it with grep/find
  in the meantime.

## Done this week
- ST-10: SQLite schema + repo.py data access, PRAGMA foreign_keys enforced
  at the single connect call site, cascade + SET NULL verified by 12 unit
  tests; ruff + pytest green. Built and reviewed, NOT merged — PR open.
- SETUP-000: kit configured for Sanad (uv stack), safety walls tested, two
  Windows guard gaps found AND fixed, .gitignore added, origin re-pointed.
- Phase 3 kickoff Steps 0-2: intake gate passed (pack clean), BUILD-PLAN.md
  approved and filed. Correction: the repo is NOT indexed. The
  codebase-memory graph is unavailable (see Blockers) and no index marker
  exists, so every absence check in this project currently runs on grep +
  find, not on graph search. An earlier "repo indexed" line here was wrong.
- ST-02: uv project skeleton complete (pinned stack, config, .env.example, smoke
  test); Gemini + Ollama providers; exit gate green; PR #2 merged (#2).
- CI fix + docs: uv setup hardened in START-HERE (ByPass + pip fallback),
  PR #3 merged.
