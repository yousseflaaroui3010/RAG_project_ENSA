# Git discipline

- Branch per task: `task/T-xxx-short-slug`, cut from latest `main`.
- Commit small and often on the task branch. Subject:
  `type(scope): summary [AI]` where type is feat|fix|refactor|test|chore.
- Commit body must contain:
  `INTENT: <what this change tries to achieve>`
  `VERIFY: <exact command that passed>`
- Never commit directly on main. Never force-push. Never `--no-verify`.
- End of task: B1 squash-merges the branch into one readable commit via PR.
- Checkpoint habit: commit every time the code is green, even mid-task.
  A green commit is a save point you can always return to.
