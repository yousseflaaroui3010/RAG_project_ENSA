# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: 1a4f3fb on main (ST-11 workspaces module merged, PR #11).
Updated: 2026-08-01 by Phase 3 orchestrator

## Now (the one task in flight)
- ST-12 content hashing + change detection, on branch
  `feat/S1-ST-12-hashing`, pushed, PR #14 OPEN. Code complete and green
  locally; NOT reviewed, NOT merged. Next action is a reviewer pass, then b1.
- What is proven working on main right now: `uv sync` resolves the pinned
  stack; config loads; the SQLite registry creates, cascades and rolls back
  under test; workspaces create, rename, delete, list, get and toggle their
  legal flag, with names normalized and the F-01 criteria demonstrated at
  module level. `uv run ruff check .` clean, `uv run pytest -q` 51 passed
  (2 config + 17 db + 32 workspaces -- the previous entry's per-file split,
  "15 db + 34 workspaces", was miscounted; the 51 total was right).
- On the ST-12 branch: ruff clean, 85 passed (2 config + 17 db + 32
  workspaces + 34 change detection).
- What does NOT exist yet: any UI, any conversion, any chunking, any
  embeddings, any retrieval, any sync engine. ST-12 decides what needs
  ingesting but nothing consumes that decision yet -- `detect_changes` has
  no caller until ST-17.

## Next (ordered queue, top 3 only)
1. Review + merge `feat/S1-ST-12-hashing`. Owner MB by agreement 2026-07-28,
   a deliberate deviation: BUILD-PLAN line 60 assigns ST-12 to YL. Recorded
   in DECISIONS. The deviation rebalances the split after MB wrote all of
   ST-10 while the plan assigned it to YL.
2. ST-03 CI skeleton - gate.yml already satisfies it (ruff + pytest per PR, a
   failing test blocks, INTENT check, dup gate, gitleaks). Almost certainly a
   confirm-and-close, not work. Verify against the story's exit criteria.
3. ST-13 Conversion ladder PDF/DOCX/TXT/MD, once ST-12 lands.

## Data-layer follow-ups (do not lose these)
Carried from ST-10, plus two the ST-11 reviewer surfaced. 3 and 4 were CLOSED
by ST-11, 5 and 7 by ST-12; all kept here so the closures stay auditable.
1, 2 and 6 remain OPEN and now have no story assigned -- fold them into
ST-13 (the next story that touches the data layer) or raise them as a chore.

1. OPEN. db/repo.py - `init_db` splits schema.sql on `;` after stripping
   full-line comments. Verified safe for the current schema (no triggers, no
   views, no semicolons inside string literals) but it WILL break the first
   time a trigger or a view is added. Harden the splitter or move to a real
   migration runner before extending the schema.
2. OPEN. The config-path default in `get_connection()` is exercised by exactly
   one test; most tests still pass an explicit tmp_path.
3. CLOSED by ST-11. Cascade tests now assert `== 1` pre-delete and `== 0`
   post-delete across all five child tables, so a degenerate count cannot pass
   vacuously.
4. CLOSED by ST-11. `ensure_schema()` now bootstraps the registry explicitly
   and `session()` calls it, so a fresh install works with no manual step.
   Deliberately NOT done inside `_connect_raw`: reads must never create a
   registry, or a mistyped path is indistinguishable from a fresh install.
5. CLOSED by ST-12. `repo.delete_document` exists;
   `test_delete_document_sets_sync_item_document_id_null` calls it instead of
   inline SQL, so the ON DELETE SET NULL test now exercises the real code
   path it claims to cover.
6. OPEN, new from the ST-11 review. `ensure_schema` can leave a half-built
   registry if `schema.sql` is truncated: the file then exists, so
   `get_connection` accepts it and reads succeed against a partial schema. It
   self-heals on the next write and needs a corrupt signed artifact to trigger,
   so it is low severity. Durable fix: `get_connection` should validate that
   the expected tables are present, not merely that the file exists. That also
   closes the `RegistryNotFoundError` blind spot.
7. CLOSED by ST-12. `_connect_raw` now passes
   `timeout=config.sqlite_busy_timeout_seconds` (default 30.0) instead of
   inheriting sqlite3's 5 second default, so ST-17's concurrent sync/UI
   writes no longer surface as a bare `database is locked`. Set before
   ST-17, as planned. Note it is NOT covered by a regression test: a
   deterministic writer-contention test needs two real connections racing
   and would be slow and flaky as a unit test. If it belongs anywhere it is
   ST-17's integration suite, where the contention is real.

## Blockers / waiting on human
- None blocking.
- RESOLVED 2026-07-28: the `gh` gap. This was the single reason MB's three
  branches never reached main - `gh` was unauthenticated, so b1 could not
  open a PR and handed over a prefilled compare URL that was never clicked.
  The branches sat pushed and invisible for three days. `gh` now works;
  PRs #6 and #7 were opened and merged through it. Note for the record that
  b1 correctly refused to extract the stored Git Credential Manager token to
  work around this - that is credential exfiltration, not authorization.
- MACHINE-SPECIFIC, not a blocker, found 2026-08-01: `gh` is installed and
  authenticated on this machine but is NOT on PATH for the agent shell, so
  a bare `gh` call fails with "command not found" and looks exactly like the
  old unauthenticated gh gap. It is not that. Call it by full path:
  `C:\Program Files\GitHub CLI\gh.exe`. Do not conclude gh is missing and do
  not hand over a compare URL -- that is what stranded three branches for
  three days in July.
- MACHINE-SPECIFIC, not a project blocker: the codebase-memory graph is
  indexed and working on YL's machine (357 nodes / 365 edges at 40e4ac0) but
  the MCP server is not installed on MB's machine, so MB's agents run the
  absence protocol on grep and find alone. An earlier journal line stating
  flatly "the repo is NOT indexed" was true only of that machine. Installing
  it there is optional; the earlier refusal to install from an untrusted
  source that carried apparent prompt-injection text was the right call and
  still stands.

## Done this week
- ST-12 Content hashing + change detection. ON BRANCH, not merged. New
  `change_detection.py` implements the architecture §5.1 hash-vs-registry
  decision and returns NEW/CHANGED/UNCHANGED/REMOVED per file. It decides and
  never acts: no write transaction, no conversion, no chunk deletion, so the
  four transitions are testable with no converter, embedder or vector store
  in existence. Fingerprint is `sha256:<digest>:<size>` packed into the
  existing `content_hash` column rather than a new `file_size` column,
  because §7.3's DDL is signed and write-locked (DECISIONS).
  34 tests, 51 -> 85. Every non-obvious assertion was mutation-proven: 12
  deliberate defects injected one at a time (size dropped from the compare,
  digest dropped, `removed` status ignored, recursive scan, missing folder
  treated as empty, last partial chunk dropped from the hash loop,
  `list_documents` losing its workspace scope, a write smuggled into
  `detect_changes`, and four more) and each turned the suite red. Three
  things worth carrying forward:
  (a) an `!r` in the folder-not-found message rendered a Windows path as
      'C:\\\\Users\\\\...'; only a test asserting the real path caught it;
  (b) the first mutation round produced one false "vacuous test" alarm --
      the mutation was weak, not the test. Mutate the DECISION site, not a
      helper whose output still compares unequal;
  (c) the dangerous near-miss is a missing folder vs an emptied folder. Both
      scan to zero files, but one means "report nothing" and the other means
      "delete every chunk in this workspace". It raises.
- ST-11 Workspaces module. MERGED, PR #11 (1a4f3fb). Owner YL. `workspaces.py`
  holds the rules, `db/repo.py` stays pure SQL. All three signed F-01 criteria
  demonstrated at module level, including a delete test that writes real bytes
  to disk and verifies they survive byte-for-byte. Tests went 17 to 51.
  Reviewed three times, 7/10 then 8/10 then 9/10, and every pass found
  something the previous one missed WHILE THE SUITE WAS GREEN THROUGHOUT:
  (a) the scoping test was vacuous, it only ever fetched the first workspace;
  (b) reads fabricated a registry, so a mistyped path created an empty database
      and returned an empty list, making a typo indistinguishable from a fresh
      install and corrupting the exact criterion the story demonstrates;
  (c) the fix for a whitespace finding introduced a defect of the same shape,
      validating a stripped name while persisting the raw one.
  Every fix was mutation-proven in both directions, mutation applied AFTER
  fixture setup. Read that list before writing the next story's tests.
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
