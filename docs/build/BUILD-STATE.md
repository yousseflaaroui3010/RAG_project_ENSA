# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: 868aab1 on main (docs sync + ST-02 + CI fixes + handbook, all merged)
Updated: 2026-07-25 by b2 (ST-10)

## Now (the one task in flight)
- Task: ST-10 SQLite schema + data access — done, exit gate green.
- Branch: worktree-agent-a4bca17a1b6e9dc03 (isolated build worktree cut from
  main @868aab1; the pre-existing `feat/S1-ST-10-db` ref is stale at 442abb0
  and was not used).
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
- What is NOT done yet: nothing for ST-10 scope. PR/merge is b1's job.

## Next (ordered queue, top 3 only)
1. ST-11 Workspaces create/rename/delete + legal flag (depends on ST-10,
   now unblocked) — owner MB.
2. ST-12 Content hashing + change-detection state machine (depends on
   ST-10, now unblocked).
3. ST-03 CI skeleton — gate.yml already satisfies it (ruff + pytest per PR,
   a failing test blocks); confirm and close, or extend minimally.

## Blockers / waiting on human
- None currently.
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
  tests; ruff + pytest green.
- SETUP-000: kit configured for Sanad (uv stack), safety walls tested, two
  Windows guard gaps found AND fixed, .gitignore added, origin re-pointed.
- Phase 3 kickoff Steps 0-2: intake gate passed (pack clean), repo indexed,
  BUILD-PLAN.md approved and filed.
- ST-02: uv project skeleton complete (pinned stack, config, .env.example, smoke
  test); Gemini + Ollama providers; exit gate green; PR #2 merged (#2).
- CI fix + docs: uv setup hardened in START-HERE (ByPass + pip fallback),
  PR #3 merged.
