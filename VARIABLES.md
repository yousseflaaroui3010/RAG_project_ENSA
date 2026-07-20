# VARIABLES (fill these per project, ~5 minutes)

In markdown files ({{DOUBLE_CURLY}}):
- {{PROJECT_NAME}}, {{PROJECT_ONE_LINER}}, {{PRIMARY_STACK}}  DONE (Sanad)
- {{DEV_CMD}} {{TYPECHECK_CMD}} {{TEST_CMD}} {{LINT_CMD}} {{E2E_CMD}}  DONE (uv)
- {{PROTECTED_BRANCH}} (usually main)  DONE (main)
- Phase 4, when it starts: {{TRACING_PLATFORM}} {{EVAL_FRAMEWORK}}
  {{GUARDRAIL_FRAMEWORK}} {{GATEWAY_PROXY}} {{PROMPT_REGISTRY}}
  {{DEFAULT_SMALL_MODEL}}  (deferred to Phase 4 start)

In real config (must be working commands, no curly braces):
- .claude/hooks/config.sh: TYPECHECK_CMD, TEST_CMD, PROTECTED_BRANCHES  DONE
- .github/workflows/gate.yml: the two command lines marked TODO  DONE (uv)
- .claude/rules/backend.md + frontend.md: the paths: globs, to match
  this project's real folder names  DONE (Sanad module map)

Files that consume these: CLAUDE.md, PHASE3-KICKOFF-PROMPT.md, agent
files in .claude/agents/ (o1-o4 use the Phase 4 set).
