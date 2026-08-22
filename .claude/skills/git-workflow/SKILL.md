---
name: git-workflow
description: Branch, commit, push, and PR discipline for shared repos. Use whenever creating a branch, committing, pushing, opening a PR, syncing with a teammate's work, or when the user asks how to avoid merge conflicts.
---

# Git workflow — the shared-repo playbook

The user may not read code. Every git action you propose follows the
training-wheels format: the exact command, what output to expect, and a
table of what other outcomes mean. Never say "just rebase". Show it.

## The one rule that prevents most conflicts
**Start every work session by syncing.** Conflicts come from two people
editing on top of different pasts. The longer a branch lives unsynced,
the worse the merge.

    git fetch origin
    git status

If behind: pull BEFORE touching anything. Never start work on a stale main.

## Branch rules
- Never commit directly to main. All work happens on a branch.
- One branch = one task. A branch that does two things gets two PRs' worth
  of conflicts and half a review.
- Short-lived. A branch older than a few days is a merge problem growing
  interest.

## Branch naming
    <type>/<short-kebab-description>
Types: feat, fix, chore, docs, refactor, test
Good: feat/password-reset   fix/duplicate-invoice-rows
Bad: my-branch, test2, youssef-work

## Commit rules
- Small and green. Every commit passes the checks. A green commit is a
  save point you can always return to.
- Message shape: <type>: <what changed, present tense>
  Good: fix: reject expired reset tokens
  Bad: updates, wip, asdf
- Never bundle a format-only change with a logic change. Two commits.

## Before every push
1. Sync first: git fetch origin, then rebase your branch on origin/main
   if it moved. Resolve conflicts LOCALLY, where it is cheap.
2. Run the checks. Push red code and the conflict becomes public.
3. Push the branch, never main: git push -u origin <branch-name>

## Pull requests
- Open a PR for every branch. Even solo — the PR is the reviewable,
  revertable unit and the training record.
- PR description answers three things: what changed, why, how it was
  verified (name the command and the result).
- Small PRs get reviewed. Big PRs get skimmed. Aim under ~400 changed lines.
- After merge: delete the branch. Dead branches are clutter that gets
  branched from by accident.

## When a conflict happens anyway
1. Do not panic-force anything. Force-push is denied here for a reason.
2. git status names the conflicted files. Open each; the <<<< ==== >>>>
   markers show both versions.
3. Resolve, run the checks, commit. If unsure which side is right,
   STOP and ask the user — a wrong resolution silently deletes a
   teammate's work.

## Never
- Never push to main directly, even when allowed by permissions.
- Never rebase or amend commits that are already pushed and shared.
- Never resolve a conflict by picking a side you do not understand.
- Never use --force or --no-verify. Both are denied; do not request them.

## Per-repo, once (tell the user, they click it)
GitHub → repo → Settings → Branches → Add rule for main:
require a pull request before merging, require status checks.
This is the server-side lock. Everything above is discipline;
this is the wall.