# Product Prompt Registry

This folder holds the prompts YOUR PRODUCT sends to models at runtime.
It is empty until the product needs one; that emptiness is by design.
(The team's own agent prompts live in .claude/agents/, not here.)

Format: one folder per prompt id, one PROMPT.md per folder.
Rules: the app loads prompts by id and version through the single AI
client module. Inline prompt strings in app code fail review. Every new
version needs 2+ golden cases and a passing O2 backtest before release.
See .claude/skills/prompt-registry-entry/SKILL.md for the procedure.
