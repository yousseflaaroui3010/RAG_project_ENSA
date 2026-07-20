---
paths:
  - "prompts/**"
---
# Prompt registry rules
- One folder per prompt id; frontmatter carries id, version, owner,
  model, changelog. Runtime values use {{DOUBLE_CURLY}} variables.
- Never edit a version in place after release; bump the version.
- A new version ships only with 2+ golden cases and a cleared backtest.
