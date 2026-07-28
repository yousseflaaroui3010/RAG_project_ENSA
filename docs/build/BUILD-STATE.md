# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: 40e4ac0 on main (README + pipeline diagram merged, PR #5)
Updated: 2026-07-28 by Phase 3 orchestrator

## Now (the one task in flight)
- Task: chore/no-ai-attribution — drop every AI-attribution marker from the git
  workflow (no Co-Authored-By trailer, no [AI] subject marker). Docs/rules only,
  no code touched.
- Where exactly: main = 40e4ac0. ST-02 skeleton (Gemini + Ollama providers)
  merged via PR #2 (squash 3eb19f2). CI gate (gate.yml) repaired and passing
  end to end. Team handbook docs/START-HERE.md added and its uv-setup hardened
  (PR #3). Root README merged (PR #5). Repo re-indexed at 40e4ac0 (357 nodes,
  365 edges); BUILD-PLAN approved and on main.
- What is proven working: `uv sync` resolves the pinned stack; config loads;
  smoke test passes; the full CI gate (uv sync, ruff, pytest, INTENT check, dup
  gate, gitleaks) is green on PRs.
- What is NOT done yet: no data-layer code exists. ST-10 is next.

## Next (ordered queue, top 3 only)
1. ST-10 SQLite schema + data access (PRAGMA foreign_keys, cascade) — first
   real data-layer story. Cut feat/S1-ST-10-<slug> from main; owner YL.
2. ST-11 workspaces create/rename/delete + legal flag (module) — owner MB, in
   parallel (depends on ST-10).
3. ST-03 CI skeleton — gate.yml already satisfies it (ruff + pytest per PR, a
   failing test blocks); confirm and close, or extend minimally.

## Blockers / waiting on human
- None. Foundation merged; cloud provider resolved (Gemini free tier + Ollama
  local). Teammates onboard via docs/START-HERE.md.

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
- Root README.md added: three-phase Mermaid pipeline diagram (ingestion, vector
  retrieval, LLM prompt generation) sourced from Architecture 5.1/5.2/7.5 +
  ADR-04/05/07, plus quickstart and doc map. Diagram validated by rendering it
  with mermaid-cli, not by eye. MERGED (PR #5, 40e4ac0).
- AI-attribution ban written into the workflow (CLAUDE.md rule 6,
  git-discipline, b1 merge checklist). History on main left as-is by decision:
  scrubbing the 5 existing trailers would need a force-push to main.
