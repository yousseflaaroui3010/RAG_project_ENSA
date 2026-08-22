---
name: prompt-registry-entry
description: Add or update a product prompt in the prompts/ registry with id, version, owner, changelog, and eval seeds. Use whenever the product needs a new LLM prompt or a change to an existing one.
---

# Prompt Registry Entry (o4 procedure)

## Steps
1. One folder per prompt id under prompts/: `prompts/<id>/PROMPT.md`.
2. PROMPT.md frontmatter: id, version (semver), owner, model, changelog
   line. Body: the prompt, with {{DOUBLE_CURLY}} runtime variables.
3. The app loads by id and version through the single AI client module.
   Inline prompt strings in app code are defects.
4. Every new prompt or version adds at least 2 cases to
   docs/evals/golden.jsonl before it can ship.
5. A version bump requires O2's backtest to clear it; keep the previous
   version file for one-command rollback.
