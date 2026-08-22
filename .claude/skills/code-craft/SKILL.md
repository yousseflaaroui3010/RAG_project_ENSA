---
name: code-craft
description: The bar a change must clear before it counts as done, plus naming, duplication, comments and how to take a shortcut safely. Use before sending any change, during any code review, when tempted to merge two similar pieces of code, or when about to cut a corner.
---

# Code craft

Same bar for backend and frontend. This is the file you point at in a review.

## Why it pays

Two researchers compared 39 company codebases, 30,737 files, six to twelve months of work each. Files a tool scored as unhealthy against files it scored as healthy.

| Compared | Healthy | Unhealthy |
| --- | --- | --- |
| Reported bugs per file | 0.25 | 3.70 |
| Time to finish a change | baseline | 124 percent longer |
| Worst case time | baseline | 9 times longer |

The third row is the one that hurts a client project. Bad code does not just cost more, it costs an **unpredictable** amount more. You can plan around slow. You cannot plan around "this might take a day or it might take three weeks".

Two honest warnings. The lead author founded the company whose score was used, and every codebase belonged to that company's customers, so treat the size of the effect as their measurement. And the paper says openly it cannot tell which way the arrow points.

One more finding, worth more than it looks: how many lines a change added barely predicted how long the work took. Size is not quality. A big clean change can be easy and a tiny tangled one can eat a week.

## The bar

Ten yes or no items. Do not send the change until all ten are yes.

1. It does one thing. If the description needs the word "and", it is two changes.
2. It has a test that failed before the change and passes after.
3. Someone who did not write it can read it without asking questions.
4. The names say what things are, with no guide needed.
5. Nothing dead left behind: no unused code, no commented out blocks, no leftover debug output.
6. Nothing new left unwatched: if it can fail, it can be seen failing.
7. It can be undone. Either it reverts cleanly, or the way back is written down.
8. Old callers still work, or every caller was updated in the same change.
9. Any shortcut taken is named in writing, with the condition for removing it.
10. The message says why, not what. The what is visible in the change.

Junior asks "does it work?". Senior asks "would I be happy to be the person changing this in six months?".

## Naming

Names are the cheapest documentation there is, and the only kind that cannot go stale, because it sits on the thing it describes.

| Rule | Bad | Better |
| --- | --- | --- |
| Say what it is, not its type | `userArray`, `dataObj` | `activeUsers`, `invoice` |
| Longer names for wider reach | a global called `d` | a global called `retryDelaySeconds` |
| Booleans read as a yes or no question | `status`, `flag` | `isPaid`, `hasExpired` |
| No private abbreviations | `calcTtlAmtWTx` | `calculateTotalWithTax` |
| A name with "and" is two things | `validateAndSaveUser` | `validateUser`, `saveUser` |

If you cannot name it, you do not yet understand it. That is a signal to stop and think, not to pick a vague name and move on.

## DRY, and where it goes wrong

DRY means do not repeat yourself, and the original idea was about knowledge, not text. One rule, one place. If the tax rate lives in four files, someone will change three of them.

Juniors under apply it. Mid level engineers over apply it, and that does more damage.

The trap: two pieces of code can look identical and mean different things. Merge them and you have tied two unrelated things together, so every change to one must now be safe for the other.

```
// Two rules that look identical today
priceForCustomer = base * 1.2
priceForStaff    = base * 1.2

// Merged too early
applyMarkup(base) = base * 1.2

// Six months later staff pricing changes.
// applyMarkup needs a flag. Then another flag.
// The shared function becomes a pile of conditions.
```

The guard is the rule of three. Wait until you see the same thing three times before pulling it out. Two copies might be a coincidence. Three is a pattern.

The test before merging: **will these two always change together, for the same reason?** Yes means merge. No or unsure means leave them apart and write one line saying why.

Sometimes leave duplication on purpose and say so. Undoing a wrong merge costs more than copying a function.

## Comments

The code says what. The comment says why.

```
// Useless. Repeats the code, and goes stale the moment
// someone changes 3 to 5.
// retry three times
retry(3)

// Useful. Says what the code cannot.
// Payment provider returns a false timeout under load.
// Three attempts clears it, more than three double charges.
// Ticket PAY-4471.
retry(3)
```

Four rules follow. A comment that repeats the code is worse than none, because it drifts and then lies. The best comments record a decision, a trap or a reason. Commented out code gets deleted, since version control already remembers it. And if a block needs a paragraph, try a better name or a smaller function first.

Junior comments what the line does. Senior comments what the next person will get wrong.

## Shortcuts

You will take shortcuts. Client work guarantees it. The rule is not never. The rule is that a shortcut has three things attached, or it does not ship.

1. **A written name.** In the code and in the journal, saying what is not properly done.
2. **A removal condition.** Not "later". Something real: "when the client confirms the second currency", "before the next release".
3. **A boundary.** It lives in one place and nothing else depends on its shape.

A shortcut with all three is a decision. A shortcut with none is a trap set for a colleague. The difference is about four lines of writing.

## Junior against senior

| Moment | Junior | Senior |
| --- | --- | --- |
| Size of a change | One big change | Small changes, each working alone |
| Repeated code | Copies forever, or merges on sight | Waits for the third, asks if they change for the same reason |
| Comments | Explains what the line does | Explains why, and what breaks otherwise |
| Naming | Names it, moves on | Renames when meaning shifts, because the old name now lies |
| Old code nearby | Cleans it while passing | Leaves it, or cleans it separately so the review stays readable |
| Cleverness | Enjoys the one liner | Picks the boring version that reads at a glance |
| Errors | Catches and hides | Handles what it can, lets the rest travel up with context |
| Shortcuts | Takes them quietly | Takes them out loud, with a removal condition |
| Formatting arguments | Argues | Puts a tool in charge and stops talking about it |
| "It works" | Ships | Asks about the second call, the empty input, the slow network |
