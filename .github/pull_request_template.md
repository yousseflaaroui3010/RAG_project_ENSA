<!--
Sanad PR template. The five checks below are the pull request checklist from
docs/phase2/Sanad_Architecture_v1.0.md section 12.2 (signed). Do not reword
them here; if a check is wrong, that is an escalation against the pack, not
an edit to this file.

Merges are squash-only and the PR title becomes the commit, so write the
title as a Conventional Commit: `feat: ST-nn <summary> [AI]`.
-->

## Story

<!-- One line: story id and what this branch does. -->

ST-

## INTENT

<!-- What this change tries to achieve. Must match the INTENT: line in the commit body. -->

## VERIFY

<!-- The exact commands that passed, with their output summary. -->

```
uv run ruff check .
uv run pytest -q
```

## Checklist (architecture section 12.2)

- [ ] 1. Story or feature id named, acceptance criteria listed and checked.
- [ ] 2. Tests green locally; new logic carries new tests.
- [ ] 3. Demo script still runs (reviewer executes it).
- [ ] 4. `docs/journal.md` updated when a problem was met and solved.
- [ ] 5. No secrets, no `data/` files, no generated stores in the diff.

## Acceptance criteria

<!-- Paste the story's exit gate from docs/build/BUILD-PLAN.md and check each line. -->

- [ ]

## Reviewer

<!--
Review split per section 12.2: the build owner reviews code mechanics; the
research and quality owner reviews behavior against acceptance criteria by
running the app and the demo script. Both count; the partner's approval is
the merge key either way.
-->

- Grade:
- Verdict: MERGE / SEND BACK
- Blocking defects:
- Follow-ups deferred (and where they are recorded):
