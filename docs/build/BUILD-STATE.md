# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: (setup commit on chore/setup-config)
Updated: 2026-07-20 by setup-engineer

## Now (the one task in flight)
- Task: SETUP-000 one-time kit configuration
- Branch: chore/setup-config (setup edits committed here; human merges to main)
- Where exactly: kit configured for Sanad, CI on uv, both Windows guard gaps
  fixed and re-tested, .gitignore added, origin re-pointed to the new public repo.
- What is proven working: guard now blocks Edit/Write to docs/phase2 and the
  hook scripts (config.sh excepted), and blocks the PowerShell tool too
  (verified live). dup-sentry, --no-verify block, commit-on-main block all
  refuse as designed. All kit files set to the Sanad uv stack.
- What is NOT done yet (human steps):
  1. Review and merge chore/setup-config into main, then push main.
  2. Install the git pre-commit hook (per clone): copy .claude/git-hooks/pre-commit
     to .git/hooks/pre-commit and chmod +x it.
  3. Create the branch ruleset on the new repo AFTER main is pushed
     (require PR, require the gate check, block force-push).
  4. Local TYPECHECK_CMD/TEST_CMD are DEFERRED (empty) until the first build
     story runs uv sync; restore them to "uv run ruff check ." and
     "uv run pytest -q" then.

## Next (ordered queue, top 3 only)
1. Human: merge + push main, install pre-commit hook, apply ruleset.
2. Restart Claude Code, then say "Index this project".
3. Paste PHASE3-KICKOFF-PROMPT.md to begin Step 0 (intake gate) of Sanad.

## Blockers / waiting on human
- No pyproject.toml / uv.lock yet, so uv-based hooks and CI cannot run until
  the first build story scaffolds them. CI keeps the real commands for then.

## Done this week
- SETUP-000: kit configured for Sanad (uv stack), safety walls tested, two
  Windows guard gaps found AND fixed, .gitignore added, origin re-pointed.
