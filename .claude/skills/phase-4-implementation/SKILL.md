---
name: phase-4-implementation
description: Run phase 4, building the real thing, backend then frontend, one task at a time with a gate on each. Use when the project is in phase 4, when asked to implement, build, add or change a feature, and at the start and end of every building session.
---

# Phase 4: implementation

## Before anything

Read `.claude/PHASE`. If it does not hold 4, say which phase this project is in and stop. Only the human changes that file.

Then read, in this order: `docs/journal/BUILD-STATE.md`, then `constitution.md` if it exists, then `ARCHITECTURE.md`. The journal is the memory. This chat is not.

## What phase 4 produces

Phase 4 is finished when all of these are true, and not before.

1. Every feature in the plan works, proven by having been run, not by having compiled.
2. Every feature has a test that fails without it.
3. `docs/journal/BUILD-STATE.md` matches reality on the day you read it.
4. `docs/journal/CHANGELOG-AI.md` has one line per change, appended.
5. Every costly choice has a decision record.
6. Every shortcut is named, with its removal condition.
7. Nothing is in the code that nobody asked for.

Number 3 is the one that slips. A journal that describes last Tuesday is worse than no journal, because people trust it.

## The loop, one task at a time

Never two tasks in one session. Finish, journal, commit, clear.

| Step | What happens | Skill |
| --- | --- | --- |
| 1 | Write the four blast radius answers into BUILD-STATE under Doing, before any code: who is touched, the worst case, how you would find out, how to undo | `blast-radius` |
| 2 | Search before writing. Graph, then grep, then say in the report exactly what you checked | the absence rule in `00-global` |
| 3 | Decide backend or frontend, and load the crew for it | below |
| 4 | Build the smallest working version | `code-craft` |
| 5 | Make it fail loudly on bad input | `fail-loud` |
| 6 | Write the test that fails without it | `test-strategy` |
| 7 | Run the whole gate yourself. Exit codes, not the last lines | `gates` |
| 8 | Journal it. Changelog line. Decision record if it was a real choice | `work-journal`, `decision-records` |
| 9 | Commit on the task branch, message says why | `git-discipline` |

If there is no ticket system, BUILD-STATE is the ticket. Never skip step 1 because there is nowhere obvious to put it.

Step 1 is not paperwork. Half the tasks change shape once you write down what they touch, and that is cheaper on paper than in code.

## Backend first, then frontend

Backend before screens, because a screen built against a shape that later changes gets built twice.

### Backend

Load `b2-backend-dev`. Rules in `rules-scoped/03-backend.md` and `04-database.md`.

Every endpoint or job answers five questions before it is written.

| Question | Where the answer lives |
| --- | --- |
| What does it accept, and what happens to a bad value? | Validate at the door. `fail-loud` |
| What shape does it return, always, including on failure? | One consistent error shape the caller can act on |
| What happens if the same request arrives twice? | Make the second one harmless |
| What outside calls does it make, and what is the time limit on each? | `plan-for-failure` |
| Does it change stored data? | Then it ships as ordered steps. `zero-lock-migration` |

### Frontend

Load `b3-frontend-dev`. Rules in `rules-scoped/02-frontend.md`.

Mockup before building. Use the design tooling available (Claude Design, Stitch, or the `frontend-design` plugin) to settle layout and states on screen before writing components. A mockup that includes the empty and error states costs minutes. Discovering them after the client does costs a day.

Then `screen-states` governs the build. Every state exists, the six accessibility failures are checked, the keyboard walk happens before review.

Check the data shape at the edge, so a backend change fails loudly instead of quietly rendering nothing.

### Reviewing

`reviewer` after a task branch is finished. `verifier` for a cold read with no context, so it cannot be talked into agreeing with intent. `b1-lead-dev` for the merge. `architect` before anything that adds a route, a table, a service, an integration, a permission, or touches more than three files.
## References, loaded when you need them

These hold the concrete shapes and numbers. The body above holds the process.

| File | Load it when |
|---|---|
| `references/backend-contract.md` | Writing any endpoint, job, error shape, or migration |
| `references/frontend-contract.md` | Writing any component, screen, or client |
| `references/security-owasp.md` | Any auth, input, secret, dependency, or error path |
| `references/review-checklist.md` | Before a task branch goes to a human |

## The numbers this phase is held to

| Thing | Line |
| --- | --- |
| Duplicated lines | Under 3 percent |
| Complexity per function | Warn at 10, split at 15 |
| Test that proves a fix | Every single bug fix, no exception |
| Files touched in one change | Over 5 means stop and ask |
| Any user facing speed target | Written as a percentile with a window, before building |

Full detail in `quality-metrics`. The three qualities that lead this project come from `the-ilities`, and if nobody has picked them, that is a question for the human, not a guess.

## Stop and ask before

- Adding, removing or upgrading a dependency.
- A refactor touching more than five files.
- Changing anything already ruled in `constitution.md`.
- Anything that spends money, sends mail, or writes outside this machine.
- Anything that would need the phase marker changed.

Ask with numbered options and one marked Recommended, so the answer costs one tap.

## Never

- Weaken a check to get green. Not a threshold, not an ignore comment, not a deleted test, not a softened assertion.
- Route around a guard, or hand the human a command that skips one.
- Report done while a check is red.
- Claim something works without saying what you ran and what it printed. `ai-pair-discipline`.
- Silently absorb work nobody asked for.

## When reality disagrees with the plan

Phase 2 decided the shape on paper. Paper is often wrong.

When building shows a phase 2 decision was wrong, stop. Say which decision, say what you found, and write a decision record that supersedes it. Do not quietly build the better thing and leave the plan lying.

Same rule for the brief. If a feature turns out to make no sense, that is a finding for the human, not a puzzle to solve in code.

## Ending a session

Four things, every time.

1. Journal updated: done with its check named, doing, left as items, blocked with a name, a date and a fallback.
2. Changelog line appended.
3. Committed, or the reason it is not.
4. One line: "Worth running /coach before you close this."

## Leaving phase 4

Do not move the marker yourself. Tell the human phase 4 looks finished, and list the seven conditions at the top with the evidence for each. Anything unproven gets the word unverified and the task that would settle it.
