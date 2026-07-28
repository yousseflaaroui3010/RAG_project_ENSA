# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: 7a51935 on main (ST-04 PR template merged, PR #7)
Updated: 2026-07-28 by Phase 3 orchestrator

## Now (the one task in flight)
- Task: ST-10 SQLite schema + data access. Code complete, independently
  re-reviewed, all blocking defects fixed, exit gate green. Awaiting PR
  and squash-merge into main.
- Branch: feat/S1-ST-10-db, pushed. Built by MB 2026-07-25; the build plan
  assigns ST-10 to YL, so ownership drifted. Not a code defect, but worth
  settling before ST-11 so contribution stays attributable.
- Review history, both passes recorded on purpose:
  - 2026-07-25, MB's session: 9/10 MERGE, "zero blocking defects".
  - 2026-07-28, independent re-review before merge: 8/10, NOT safe to merge,
    five must-fix items. The re-review was right; the first pass missed a
    real transaction bug. Two reviews disagreeing is why the second one runs.
- The bug that mattered: `init_db` committed on a caller-owned connection,
  so a write made earlier inside `session()` could not be rolled back by a
  later exception. Reproduced, then fixed. Dropping the explicit `commit()`
  was NOT sufficient - `executescript()` issues its own implicit COMMIT of
  any pending transaction, verified empirically against this schema. `init_db`
  now executes each DDL statement individually via `conn.execute()` and never
  commits or rolls back; the caller's `session()` owns the transaction
  outright. See db/repo.py:64 and its docstring.
- Also fixed: `session()` commit and rollback now have tests (the rollback
  test was proven to fail pre-fix and pass post-fix - that is the regression
  proof); the PRAGMA assertion now runs on a second freshly opened connection,
  which is the risk the story actually names; a negative FK test rejects an
  orphan `insert_document`; `_count` whitelists table and column identifiers
  instead of f-string-interpolating them.
- Verify: `uv run ruff check .` clean; `uv run pytest -q` 17 passed (2 config
  + 15 db). Re-run independently by the orchestrator, not taken on report.
- Delivered: db/schema.sql (6 tables, arch §7.3 DDL under the §7.4 deviations:
  uuid->TEXT app-generated, timestamptz->TEXT ISO-8601 UTC, boolean->INTEGER,
  numeric(4,3)->REAL, CHECK/FK unchanged - byte-checked against the signed
  pack and NOT modified by the fixes); db/repo.py (single `_connect_raw()`
  connect site, PRAGMA foreign_keys=ON on every open, `session()` transaction
  context manager, typed insert/delete per table, path from
  config.get_settings().sqlite_db_path); tests/unit/test_db_repo.py.
- Blast radius: `db/` is a new leaf package. Nothing on main imports it, so
  regression risk to existing code is zero; the risk is forward, onto ST-11
  and ST-12, which will build on `session()`.

## Next (ordered queue, top 3 only)
1. ST-11 Workspaces create/rename/delete + legal flag - owner MB. Unblocks
   the moment ST-10 lands. Carries the ST-10 follow-ups listed below.
2. ST-12 Content hashing + change-detection state machine. Also depends on
   ST-10.
3. ST-03 CI skeleton - gate.yml already satisfies it (ruff + pytest per PR,
   a failing test blocks). Confirm and close, or extend minimally.

## ST-10 follow-ups (do not lose these; fold into ST-11)
1. db/repo.py:64 - `init_db` splits schema.sql on `;` after stripping
   full-line comments. Verified safe for the current schema (no triggers, no
   views, no semicolons inside string literals) but it WILL break the first
   time ST-11+ adds a trigger or a view. Harden the splitter or move to a
   migration runner before extending the schema.
2. db/repo.py:55 - the config-path default in `get_connection()` is still
   never exercised; every test passes an explicit tmp_path.
3. The cascade test needs pre-delete `== 1` assertions so a degenerate
   `_count` cannot pass vacuously.
4. `init_db` still has no bootstrap caller outside tests - app startup never
   creates the registry.
5. A test still uses inline SQL because `delete_document` does not exist yet.

## Blockers / waiting on human
- None blocking.
- RESOLVED 2026-07-28: the `gh` gap. This was the single reason MB's three
  branches never reached main - `gh` was unauthenticated, so b1 could not
  open a PR and handed over a prefilled compare URL that was never clicked.
  The branches sat pushed and invisible for three days. `gh` now works;
  PRs #6 and #7 were opened and merged through it. Note for the record that
  b1 correctly refused to extract the stored Git Credential Manager token to
  work around this - that is credential exfiltration, not authorization.
- MACHINE-SPECIFIC, not a project blocker: the codebase-memory graph is
  indexed and working on YL's machine (357 nodes / 365 edges at 40e4ac0) but
  the MCP server is not installed on MB's machine, so MB's agents run the
  absence protocol on grep and find alone. An earlier journal line stating
  flatly "the repo is NOT indexed" was true only of that machine. Installing
  it there is optional; the earlier refusal to install from an untrusted
  source that carried apparent prompt-injection text was the right call and
  still stands.

## Done this week
- ST-02: uv project skeleton (pinned stack, config, .env.example, smoke test),
  Gemini + Ollama providers. MERGED, PR #2 (3eb19f2).
- CI gate repaired: jscpd flags (--ignore/--exit-code), .venv excluded,
  gitleaks GITHUB_TOKEN. The verify job passes on every PR.
- Team handbook docs/START-HERE.md added, uv setup hardened. MERGED, PR #3
  (442abb0). Journal sync MERGED, PR #4 (868aab1).
- Root README.md with the three-phase Mermaid pipeline diagram (ingestion,
  vector retrieval, LLM prompt generation) from Architecture 5.1/5.2/7.5 and
  ADR-04/05/07. Diagram validated by rendering, not by eye. MERGED, PR #5
  (40e4ac0).
- MB's `.claude/worktrees/` and `.claude/agent-memory/` gitignore. MERGED,
  PR #6 (c844922).
- ST-04 PR template carrying the §12.2 checklist verbatim. MERGED, PR #7
  (7a51935). Its last open exit-gate item, branch protection on main, is
  satisfied: the active `protect-main` ruleset enforces required PRs, the
  strict `verify` status check, non-fast-forward, no deletion, and linear
  history, so direct push to main is rejected. ST-04 is closeable.
- SETUP-000: kit configured for Sanad (uv stack), safety walls tested, two
  Windows guard gaps found AND fixed, .gitignore added, origin re-pointed.
- Phase 3 kickoff Steps 0-2: intake gate passed (pack clean), BUILD-PLAN.md
  approved and filed, repo indexed on YL's machine.
- Workflow rule added: no AI attribution in commits, PRs, or issues - no
  `Co-Authored-By` trailer naming an assistant, no `[AI]` subject marker, no
  "generated with" footer. This is graded academic work and the history
  carries the team's names only. Human co-authorship is still credited
  normally. Written into CLAUDE.md rule 6, .claude/rules/git-discipline.md,
  and the b1 merge checklist. History already on main was left unrewritten
  by decision - see DECISIONS.
