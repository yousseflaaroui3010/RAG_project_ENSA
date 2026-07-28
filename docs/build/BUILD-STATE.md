# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: e7c777f on main (all four open PRs merged: #6 gitignore,
#7 ST-04, #8 ST-10, #9 attribution rule). No open PRs. No stranded branches.
Updated: 2026-07-28 by Phase 3 orchestrator

## Now (the one task in flight)
- Task: ST-11 Workspaces create/rename/delete + legal flag. NOT STARTED.
  Unblocked as of e7c777f; ST-10 landed, so `db/repo.py` and `session()`
  exist to build on.
- Owner: to be confirmed before a branch is cut. The build plan assigns ST-10
  to YL but MB wrote all of it, so ownership has already drifted once. Settle
  ST-11 and ST-12 ownership first so contribution stays attributable; this is
  graded work and the split has to be defensible.
- Branch: none cut yet. Use `feat/S1-ST-11-workspaces` from main @e7c777f.
- Carries the five ST-10 follow-ups below. Follow-up 1 is the one to read
  before touching the schema.
- What is proven working on main right now: `uv sync` resolves the pinned
  stack; config loads; the SQLite registry creates, cascades and rolls back
  under test. `uv run ruff check .` clean, `uv run pytest -q` 17 passed
  (2 config + 15 db). CI verify green on every PR.
- What does NOT exist yet: any workspace logic, any UI, any ingestion,
  any retrieval. `db/` is still a leaf package that nothing imports.

## Next (ordered queue, top 3 only)
1. ST-12 Content hashing + change-detection state machine. Unblocked; can run
   parallel to ST-11 since it touches different modules.
2. ST-03 CI skeleton - gate.yml already satisfies it (ruff + pytest per PR, a
   failing test blocks, INTENT check, dup gate, gitleaks). Almost certainly a
   confirm-and-close, not work. Verify against the story's exit criteria.
3. ST-13 onward per BUILD-PLAN, once ST-11 and ST-12 land.

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
- ST-10 SQLite schema + data access. MERGED, PR #8 (6746234). Six-table
  registry per Architecture 7.3 under the 7.4 deviations, `PRAGMA
  foreign_keys=ON` at the single connect site, `session()` transaction helper,
  17 tests green. Reviewed twice and the passes disagreed: MB's session graded
  it 9/10 "zero blocking defects"; an independent pre-merge re-review graded it
  8/10 NOT safe to merge and was right. It found `init_db` committing on a
  caller-owned connection, which silently defeated rollback inside `session()`.
  Dropping the explicit `commit()` was not enough, because `executescript()`
  issues its own implicit COMMIT; `init_db` now runs each DDL statement via
  `conn.execute()` and never commits. The rollback test was proven to fail
  before the fix and pass after. Keep running the second review.
- Three of MB's branches were recovered and landed. They had been pushed on
  2026-07-25 and sat invisible for three days because `gh` was never
  authenticated, so no PR was ever opened for any of them. All merged with
  `Co-authored-by: meriem-mb` preserved.
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
