# WHAT'S LEFT: install, fill in, and by-design gaps

> AUTOMATED: paste SETUP-PROMPT.md into Claude Code first; it handles
> items 5-8 below and fills VARIABLES.md for you by asking or detecting.

## Install on your machine (once)
1. Claude Code, latest version. Node 22+ and python3 (the hooks use it;
   both ship with WSL2/macOS dev setups).
2. codebase-memory-mcp: in the repo, tell Claude Code
   "Install https://github.com/DeusData/codebase-memory-mcp and configure
   it", or run its setup script. Verify with /mcp after the restart; the kickoff
   indexes the repo by itself in its Step 1. This is the map layer; nothing else replaces it.
3. Playwright browsers, when e2e work starts:
   `npx playwright install --with-deps`.
4. Nothing to install for jscpd or gitleaks: jscpd runs via npx, gitleaks
   runs inside CI only.

## Configure once per repo (10-15 min)
5. Copy this kit in, `chmod +x .claude/hooks/*.sh`, commit.
6. Fill VARIABLES.md targets: CLAUDE.md, config.sh, gate.yml, rule globs.
7. GitHub ruleset on {{PROTECTED_BRANCH}}: block direct pushes, require
   PR, require the `gate` checks, block force push (manual UI step,
   Settings -> Rules -> Rulesets).
8. Restart Claude Code, then verify: /hooks (6 hooks), /memory (global
   rules + CLAUDE.md), /agents (11 agents), /mcp (graph server). Test a
   wall: ask for `git commit --no-verify -m test`; it must bounce.

## Per project (each new engagement)
9. Drop the signed D/S pack into docs/phase2/ (PRD, ADRs + C4, stack
   record + contracts, infra plan, test strategy, sign-off).
10. Paste PHASE3-KICKOFF-PROMPT.md. Step 0 audits the pack and stops on
    gaps before any code.

## Defer until launch (Phase 4)
11. At launch: move .claude/agents-phase4/o*.md back into .claude/agents/,
    then Langfuse or Arize Phoenix account + key (O1), eval framework (O2),
    NeMo Guardrails or equivalent (O3), Portkey gateway (O4). The O
    agents sit idle and cost nothing until invoked.

## Optional
12. E2B sandboxes: only if agents will run genuinely untrusted code;
    b4's worktree isolation covers normal test runs.
13. Serena: an alternative symbol backend. Pick ONE of Serena or
    codebase-memory-mcp, never both; every MCP server's tool list costs
    context in every session.

## Empty or thin by design (not missing)
14. prompts/ holds one README and one example: it fills when YOUR PRODUCT
    needs runtime prompts, via the prompt-registry-entry skill.
15. docs/evals/golden.jsonl has one seed row: it grows from real traffic.
16. docs/build/ templates carry placeholders: the orchestrator fills them
    in Step 2.
17. No app code ships in the kit: that is Phase 3's output, not its input.
