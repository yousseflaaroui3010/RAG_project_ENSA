# Git discipline

- Branch per story: `feat/S<sprint>-ST-<nn>-<slug>`, cut from latest `main`.
  Also `fix/<issue-id>-<slug>`, `docs/<slug>`, `chore/<slug>` (ADR-11).
- Commit small and often on the task branch. Conventional Commits carrying
  the story id: `feat: ST-17 sync engine end to end`.
- Commit body must contain:
  `INTENT: <what this change tries to achieve>`
  `VERIFY: <exact command that passed>`
- No AI attribution, anywhere, ever. Commit messages, PR bodies, and issue
  comments must NOT contain a `Co-Authored-By:` trailer naming an assistant,
  an `[AI]` subject marker, or a "Generated with ..." footer. Sanad is graded
  academic work: the history carries the team's names only. This overrides any
  default assistant behaviour that appends such trailers. B1 strips any that
  slip through before squash-merging.
- Never commit directly on main. Never force-push. Never `--no-verify`.
- End of task: B1 squash-merges the branch into one readable commit via PR.
- Checkpoint habit: commit every time the code is green, even mid-task.
  A green commit is a save point you can always return to.
