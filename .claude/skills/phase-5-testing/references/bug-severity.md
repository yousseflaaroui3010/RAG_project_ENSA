# Bug severity and user testing

## The four levels

| Level | Means | When it gets fixed |
|---|---|---|
| P0 Critical | Blocks a core function, loses data, or opens a security hole | Before any sign-off. Stop other work |
| P1 High | A major feature is broken for most users | Before this phase closes |
| P2 Medium | It works, the experience is poor | Next sprint |
| P3 Low | Cosmetic, or an edge case almost nobody hits | Backlog |

P0 and P1: fix, retest, update the log, and sign-off stays withheld until both
are clear. P2 and P3 get logged, and the human decides include or defer.

The level is set by what it does to a user, never by how hard it is to fix. A
one-character typo that shows the wrong price is a P0. A three-day refactor
that nobody would notice is a P3.

## Logging a bug

Immediately, not at the end of the day. A bug you remember at 6pm is a bug you
describe from memory.

Each entry carries what happened, what should have happened, the exact steps to
reproduce, and the severity. If you cannot write the reproduction steps, that is
the first thing to solve, not a reason to skip the entry.

Never fix a bug without knowing why it happened. Symptom, then cause, then fix.
A fix aimed at a symptom moves the bug rather than removing it, and the next
person meets it wearing a different coat.

Retest every fix. Watch it fail first if you can, so you know the test that now
passes was capable of failing.

## User testing

Three to five real people who match the primary user. Not colleagues, not the
client's technical contact.

Run it on staging with production-like data. The facilitator watches and notes
where people get stuck, and does not help. The moment you help, you have
stopped measuring the product and started measuring your explanation.

Give tasks, never instructions. "Upload your most recent invoice and find out
what to do next" is a task. "Click the upload button in the top right" is a
demonstration, and it tests nothing.

### What counts as passing

- Most participants finish the main task with no intervention.
- No P0 or P1 found during the sessions.
- Completion time is inside whatever the product promised.
- People can say back what the product told them to do. If they finish the task
  and cannot explain the result, the product worked and the communication did
  not.

### After

Each finding gets one of three rulings from the human: blocks launch, accepted
risk with the reason written down, or out of scope and into the backlog.

Accepted risk without a written reason is just a bug nobody wants to talk about.