# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: 868aab1 on main (ST-02 + CI fixes + handbook, all merged)
Updated: 2026-07-25 by Phase 3 orchestrator (ST-04)

NOTE ON THIS COPY: this is the ST-04 branch's view of the flight recorder.
The fuller current copy lives on branch feat/S1-ST-10-db (head e4448e5) and
merges to main first. Three branches are in flight at once, which is one more
than the one-story rule allows; the orchestrator rebases this branch onto main
after ST-10 lands so the human never resolves a journal conflict.

## Now (the one task in flight)
- Task: ST-04 PR template — template half done, exit gate half met.
- Branch: feat/S0-ST-04-pr-template (cut from main @868aab1), pushed at 6d4754c.
- Delivered: .github/pull_request_template.md carrying the five-point checklist
  from architecture §12.2 lines 480-484 verbatim (byte-checked by the reviewer),
  plus INTENT/VERIFY fields per .claude/rules/git-discipline.md, squash-only and
  Conventional-Commit-title guidance per §12.2 line 475, and a reviewer grade
  block matching the review split at §12.2 line 486.
- Written directly by the orchestrator under CLAUDE.md iron rule 7 (single file,
  no schema or route change), then sent to the reviewer like any other branch.
- Reviewer: 8/10 SEND BACK on first pass. The file itself needed no change; the
  single blocking defect was this missing journal entry plus the CHANGELOG line.
  Both are now written. Non-blocking notes recorded below.
- Verify: `uv run ruff check .` clean; `uv run pytest -q` 2 passed (this branch
  is cut from main, so db/ and its 12 tests are not here yet).
- Absence check: no PR template existed. Checked grep for pull_request_template,
  PULL_REQUEST_TEMPLATE, CONTRIBUTING, ISSUE_TEMPLATE and a find over .github/,
  which held only workflows/gate.yml. Graph unavailable, so grep and find only.
- What is NOT done for ST-04: branch protection on main. That is a GitHub
  settings action, owner HUMAN, and nothing here claims it. The story is not
  closeable until "direct push to main is rejected" is demonstrated.
- Reviewer non-blocking notes, deferred: template line 8 shows only `feat:` when
  fix/docs/chore titles are equally valid and fix branches carry issue ids not
  ST-nn; lines 25-28 pre-fill two commands and may be left unedited when a story
  needs tests/integration.

## Next (ordered queue, top 3 only)
1. HUMAN: `gh auth login`, then merge the three open branches in order (see
   Blockers). ST-11 and ST-12 start from main only after ST-10 lands.
2. ST-11 Workspaces create/rename/delete + legal flag (depends on ST-10).
3. ST-03 CI skeleton — gate.yml already does ruff + pytest on every PR to main,
   but its exit gate ("a deliberately failing test blocks a PR, fixing it
   unblocks") has never been demonstrated, and demonstrating it needs a PR.
   Also note the signed plan names the file `ci.yml` while the repo has
   `gate.yml` with a superset of the required checks; that naming deviation
   needs a DECISIONS row or a rename before ST-03 can be called done.

## Blockers / waiting on human
- HUMAN ACTION: run `gh auth login` in an interactive terminal. `gh` 2.96.0 is
  installed and on PATH but `gh auth status` reports no logged-in host, so no
  agent can open a PR. Until then each PR needs a human to click.
- Merge order for the three open branches, any order works since they touch
  disjoint files, but this order keeps the journal clean:
  1. feat/S1-ST-10-db (the story), 2. chore/gitignore-worktrees, 3. this branch.

## Done this week
- SETUP-000: kit configured for Sanad (uv stack), safety walls tested, two
  Windows guard gaps found AND fixed, .gitignore added, origin re-pointed.
- Phase 3 kickoff Steps 0-2: intake gate passed (pack clean), repo indexed,
  BUILD-PLAN.md approved and filed.
- ST-02: uv project skeleton (pinned stack, config, .env.example, smoke test),
  Gemini + Ollama providers; MERGED to main (PR #2, 3eb19f2).
- CI gate repaired: jscpd flags (--ignore/--exit-code), .venv excluded, gitleaks
  GITHUB_TOKEN — the verify job now passes on every PR.
- Team handbook docs/START-HERE.md added and uv setup hardened (PR #3, 442abb0).
