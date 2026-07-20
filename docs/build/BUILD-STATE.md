# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: ST-02 (+ Gemini provider swap) on feat/S0-ST-02-skeleton
Updated: 2026-07-20 by Phase 3 orchestrator

## Now (the one task in flight)
- Task: ST-02 project skeleton — COMPLETE (incl. Gemini provider swap), PR #2 open.
- Branch: feat/S0-ST-02-skeleton (stacked on chore/phase3-kickoff bookkeeping).
- Where exactly: pyproject.toml (pinned stack §8), uv.lock, config.py (all
  tunables), .env.example, tests/unit/test_config.py committed. Cloud provider
  set to Google Gemini (langchain-google-genai) + free local via Ollama
  (Mistral/Llama), per user choice. Exit gate GREEN: uv sync, ruff clean,
  pytest 2 passed.
- What is proven working: full stack resolves/installs; config loads; smoke test
  passes; provider swapped OpenAI -> Gemini and re-verified green.
- What is NOT done yet: CI on PR #2, then human merge.

## Next (ordered queue, top 3 only)
1. CI green on PR #2 (gate.yml: uv sync/ruff/pytest) -> human merges.
2. ST-03 CI skeleton — gate.yml likely already satisfies it; confirm/extend.
3. ST-10 SQLite schema + data access (PRAGMA foreign_keys, cascade) — first
   real data-layer story; unblocks ingestion/indexing chain.

## Blockers / waiting on human
- Human merge of PR #2 moves main. (Cloud provider now resolved: Gemini.)

## Done this week
- SETUP-000: kit configured for Sanad (uv stack), safety walls tested, two
  Windows guard gaps found AND fixed, .gitignore added, origin re-pointed.
- Phase 3 kickoff Steps 0-2: intake gate passed (pack clean), repo indexed,
  BUILD-PLAN.md approved and filed.
- ST-02: uv project skeleton complete (pinned stack, config, .env.example, smoke
  test); Gemini + Ollama providers; exit gate green; PR #2 open.
