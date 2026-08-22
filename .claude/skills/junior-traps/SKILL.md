---
name: junior-traps
description: The mistakes that separate junior work from senior work, and the move that avoids each one. Use before starting a fix, before a refactor, before reporting something done, when a bug is confusing, or when tempted to take a shortcut.
---

# Junior traps

Every trap here has a name, a tell you can catch yourself making, and the move instead. Most of these were paid for on this machine.

## Thinking traps

**Fixing the symptom.**
Tell: the fix makes the error message go away and you cannot say why the error appeared.
Instead: name the cause in one sentence before touching anything. If you cannot, you are guessing.

**Fixing the wrong thing twice.**
Tell: your second patch to the same rule also failed.
Instead: two failed patches means the shape is wrong, not the wording. Change the shape. A path called `docs/build` kept getting blocked by a rule about build folders. Three attempts at a cleverer pattern failed. Renaming the folder took one line.

**Believing a document instead of the machine.**
Tell: "the notes say the hooks were fixed."
Instead: read the live state. A summary is a claim from the day it was written. On this machine a record said three projects were cleaned. Six were still wired wrong.

**Guessing a count.**
Tell: "that will be about four files."
Instead: count it with a command. An estimate of 4 turned out to be 152.

**Believing a sign is a wall.**
Tell: "the settings block that."
Instead: try the forbidden thing and watch. A hook wired to the wrong tool blocked nothing at all, and everyone assumed it worked because the file existed.

## Working traps

**Changing two things at once.**
Tell: it works now and you cannot say which change did it.
Instead: one change, one test, one log line. Always.

**Two files, one job.**
Tell: `thing.mjs` and `thing.mjs.bak` sitting side by side, or two files with different names doing the same work.
Instead: delete the loser or move it out of the folder. Two files, one job, is the bug that costs an hour at 1am. On this machine, two files both called `gate.mjs` ran as duplicate hooks and one was silently wrong.

**Being clever.**
Tell: the one liner you are proud of.
Instead: code gets read far more often than it gets written [1][2]. Plain and long beats short and clever.

**Building for a future that has not arrived.**
Tell: "we might need this later."
Instead: build what today needs. Complexity is allowed when the rule itself is complex, never because something might be useful [3].

**Over fixing.**
Tell: you are fixing something a different task owns.
Instead: park it. A comment naming the rule being broken and the task that closes it, plus a line in the journal. Parked and visible beats fixed silently.

**Silencing the alarm.**
Tell: raising a threshold, adding an ignore comment, deleting a test, weakening an assertion.
Instead: none of these. Ever. If the check is genuinely wrong, change it in the open with the reason written down.

**Using the side door.**
Tell: the tool refused, so you reach for a different tool that can do the same thing.
Instead: a guard you can walk around is not a guard. Change the guard in the open, or stop.

## Definition traps

**"Done" means the ticket is closed.**
Tell: you closed it when the code ran on your machine.
Instead: done means it runs where real users are, it can be watched, and it can be switched off.

**Picking the cleaner option.**
Tell: two ways to build it, you chose the prettier one.
Instead: choose the one that is easier to undo. Undo beats elegance every time a client is watching.

**Rewriting the ugly code in the way.**
Tell: the diff is three times bigger than the task.
Instead: leave it, or clean it in a separate change, so the reviewer never sees unrelated work smuggled in.

**Giving an estimate as one number.**
Tell: "about three days."
Instead: a number, what could blow it up, and what gets cut first. Estimates overrun by 30 to 40 percent on average, and a range someone is 90 percent sure about only holds 60 to 70 percent of the time. Also worth knowing: naming more risks made people **more** overconfident, not less.

## Reporting traps

**Letting the machine find your mistake.**
Tell: pushing and waiting for the build to tell you.
Instead: run the whole gate yourself first, same steps, same flags. The person you report to should never be the one who discovers it is red.

**Reading the last two lines of output.**
Tell: it looked green.
Instead: check the exit code. A failing lint run piped through `tail` showed blank lines and looked fine.

**Calling it done because it compiled.**
Tell: "typecheck passed."
Instead: run the thing. Typechecking proves shapes agree and nothing about the world.

**Rounding unverified up to working.**
Tell: "should be fine."
Instead: write the word unverified, and name the task that would settle it. An unverified claim with no owner quietly becomes a fact.

**Defending the first answer.**
Tell: arguing back when challenged.
Instead: re-examine the argument. Changing your mind fast is cheaper than being consistent [4].

## The one line version

Slow down at the start, so you do not have to at the end.

## Sources

1. Senior developers avoid these mistakes, Medium, May 2026, accessed 2026-08-06.
2. Why junior devs fail their first code review, Scoop Labs, June 2026, accessed 2026-08-06.
3. Code review tips for new junior developers, Codeworks, accessed 2026-08-06.
4. Everything not cited above comes from this machine's own `engineering-seniority.md` and `00-global.md`, written from real failures on this build.
