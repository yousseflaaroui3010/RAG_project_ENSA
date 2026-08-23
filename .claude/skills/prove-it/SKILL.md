---
name: prove-it
description: Earn a green instead of trusting one. Use when a bug appears, before fixing anything, when writing or changing a test or any check, when a suite passes and you are about to believe it, and before saying a fix works. Covers enumerating every candidate root cause before touching code, breaking a check on purpose to prove it can fail, and reading what a mutation result actually means.
---

# Prove it

A passing suite is a claim, not evidence. On this project a green suite has
been insufficient **every single time**: ST-10 was graded "zero blocking
defects" and an independent re-review found a real one; ST-11 took three
rounds and each round found a defect while the tests stayed green; ST-17
killed all 12 of its mutations and self-review still found a missing line.

This skill is the work that turns a green into evidence. Three parts:
find the real cause, prove the check can fail, know what each technique is
blind to.

---

## Part 1 — Every candidate cause, before you touch anything

The junior move is to find a plausible cause and fix it. Plausible is not
the same as actual, and a fix aimed at the wrong cause makes the real one
harder to see, because the symptom moves.

**Write the list before you write the fix.** For the observed symptom,
enumerate every mechanism that could produce it — not the likely ones, all
of them. Aim for at least three; if you can only think of one, you have not
understood the system yet.

For each candidate, record three things:

| Cause | How I would rule it in or out | Cost |
|---|---|---|

Then order by **cost, not by hunch** — the thirty-second check goes first
even if it feels unlikely. Rule each one out with an observation, not with
reasoning. "That can't be it because X" is a hypothesis about X; go look at X.

Stop when exactly one survives and you can **produce the symptom on demand**
by that mechanism. If two survive, you have two bugs or one wrong model.

### Ask which side drifted

When two things disagree — a record and the artifact, a test and the code, a
doc and the behaviour — do not assume you know which one is wrong. The
cheaper explanation is usually that the record is stale. Check it anyway.

A signed schema on a past project recorded 95 check constraints and the build
had 93. It was logged as "the record is probably wrong". The record was
right; the repo's copy of the schema was a revision behind, missing a state
the code used in ten places.

### Then state the fix before you make it

One or two lines, out loud, before editing:

- **what** is wrong (the mechanism, not the symptom)
- **why** it produces this exact symptom
- **what** the minimal change is
- **why** nothing else needs to change

If you cannot write the fourth line, the blast radius is unknown. Go find it.

---

## Part 2 — Break it on purpose

**A check that has never failed is untested, not passing.**

Every new test, assertion, gate step, lint rule or guard gets proven in both
directions before it is trusted:

1. Break the thing it is supposed to catch. On purpose. One change.
2. **Watch it go red.** Read the failure message — it is what a future
   teammate will get, so it must name the real problem.
3. Restore.
4. Watch it go green.

A test written after the code, never seen failing, proves only that it does
not crash.

### Where to inject the break

Mutate the **decision site** — the line that makes the call — not a helper
whose output still compares unequal downstream. ST-12 raised a false "vacuous
test" alarm this way: the mutation was weak, not the test.

### Reading the result honestly

| What you see | What it usually means | What to do |
|---|---|---|
| Test goes red, message is clear | The check is real | Keep it |
| Test goes red, message is useless | The check works, the report does not | Fix the message |
| **Mutation survives** | Either the test is vacuous **or the code is dead** | Read the survivor before blaming the test — ST-13's survivor was a genuinely redundant guard |
| **Mutation is impossible to kill** | Likely an equivalent mutant | Prove both paths produce identical output by running them, then pin the property another way |
| **Zero survivors across the board** | Suspicious, not reassuring | ST-17 killed 12 of 12 and self-review still found a missing line |

### The mutation that restores a default

If your mutation removes a line and the system falls back to a **default**
rather than to nothing, a one-sided assertion cannot see it. Dropping
`timeout=0.5` gave sqlite3's own 5.0s default, which satisfied "it waited at
least 0.4s" — so the test stayed green while the config was ignored entirely.
Assert a **ceiling as well as a floor** whenever a default could stand in.

---

## Part 3 — Three techniques, three blind spots

Each of these finds defects the others structurally cannot. Running one is
not running the others.

**1. Mutation testing** — breaking working code to see if anything notices.
Blind to: any branch no code reaches. It cannot see a class nobody raises
(ST-13) or a line that was never written (ST-16, ST-17). It tests the tests,
not the design.

**2. Reading the diff after green** — adversarial self-review, knowing
nothing about what it was meant to do. This is what has found the real defect
on **four stories running**, and every time it was a **missing** line rather
than a wrong one. Ask: what happens to the input nobody thought about? ST-12's
three worst defects all lived in one blind spot — "what happens to a file we
cannot read".

**3. Running it for real** — on realistic input, outside the test harness.
Blind to nothing, expensive, and it has found something every time it has been
done here. ST-14's 39 green tests all agreed a citation label was fine; one
real document showed it was unreadable. ST-17 merged fully green and the first
real-PDF run produced a wrong citation on Article 235.

**Run all three before calling something done.** If you skip one, say which.

---

## Part 4 — The vacuous-test shapes seen on this project

Check every new test against this list. All six are real, all cost something.

1. **Self-referential.** The expected value is built from the same setting the
   code reads, so emptying the setting leaves every assertion passing (ST-15's
   prefix tests). Pin expected values as **literals**.
2. **Fixture too small for the property.** One child makes per-parent and
   per-document numbering indistinguishable (ST-16). One parent makes a range
   label look correct (ST-16's first real run). A blank line landing mid-piece
   by luck (ST-14). Size the fixture so the property can actually fail.
3. **Both sides carry the same error.** Comparing a report against its own
   persistence cannot see a duplicate that appears in both — PR #40, where the
   test the description credited with catching duplicate rows passes with the
   bug present.
4. **Keyed by a field that collapses duplicates.** A dict keyed on file name
   turns two rows into one. Compare ordered lists when count or order matters.
5. **One-sided bound with a default behind it.** See Part 2.
6. **Degenerate count.** `assert count == 0` passes when the fixture never
   created anything. Assert `== 1` before and `== 0` after (ST-11's cascade
   tests). Apply the mutation **after** fixture setup, never before.

---

## Part 5 — What you must be able to say at the end

Before reporting anything fixed, be able to answer all five. If you cannot,
it is not done — say so and name what is missing.

1. What was the mechanism, and how did I rule out the other candidates?
2. Can I reproduce the original symptom on demand?
3. Which assertion did I watch **fail**, and what did the message say?
4. Which of the three techniques did I run, and which did I skip?
5. What did I **not** verify, and what would settle it?

Anything unverified is labelled unverified, in the artifact and in the report,
with the task that would close it named. An unverified claim with no owner
quietly becomes a fact.

## The line that outranks the rest

Never make a check pass by weakening it. Not by raising a threshold, not by
loosening an assertion, not by an ignore comment, not by deleting the test.
That is cheating the check, not meeting it. If it is red and you cannot make
it honestly green, say so plainly and stop.