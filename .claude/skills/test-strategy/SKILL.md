---
name: test-strategy
description: What to test, what not to test, and which number to ignore. Use when writing tests, when a bug is found, when deciding how much testing is enough, when a test gets in the way of a change, or when a test fails intermittently.
---

# Tests

A test is not proof the code is right. It is a trap set for a specific mistake.

That changes how you write them. Do not ask "have I tested this function". Ask "what mistake would I like to be told about loudly, at three in the afternoon, rather than at midnight from a client".

The fastest way to know a test works: make it fail on purpose before you make it pass. A test that has never failed has never been tested itself.

## The four levels

| Level | Checks | Speed | Catches | Misses |
| --- | --- | --- | --- | --- |
| Unit | One piece alone | Milliseconds | Wrong logic, bad edges | How pieces fit |
| Integration | A few pieces plus a real data store | Seconds | Wrong queries, wrong assumptions between parts | The outside world |
| Contract | The shape passed between front and back | Fast | One side changing the shape without telling the other | Whether the feature makes sense |
| End to end | A real user path through everything | Slow | Broken wiring, broken screens | Nearly all detail, and it will be flaky |

Two rules about the mix, neither a law.

Most tests belong at the level where they run fast and point straight at the problem. Fast tests get run. Slow tests get skipped, then deleted.

Keep a small number of end to end tests on the paths that must not break. Two or three for a client project: sign in, the main action, the payment. Not fifty.

The old advice is a pyramid, wide at the unit level. Frontend people argue for more integration level tests instead. Both are craft opinion, not measured fact, so pick one, write it down, and stop arguing about it in reviews.

## What to test

- Logic with branches. Anything with an `if` in it deserves a trap.
- The edges: empty, one, many, huge, zero, negative, wrong type, missing.
- Things that happen twice. The double submit, the retried request.
- Anything that has broken before. Every bug fix ships with the test that would have caught it.
- Money, permissions, and anything that deletes.

## What not to test

- Code that only passes values along. You are testing the language.
- The framework. Its authors already did.
- Exact wording on screen, unless the wording is the point. It changes weekly and fails for no reason.
- The internal steps of a function. Test what goes in and what comes out, so you can rewrite the middle without rewriting the test.

That last one is the difference between tests that help you change code and tests that stop you changing it. A test tied to how the code works instead of what it does will fight every improvement you attempt.

## Coverage is the number that lies

Researchers took five large Java projects, each already carrying more than a thousand tests, and built 31,000 different test suites from them. They measured coverage against how good each suite was at catching faults.

Once you account for how many tests are in the suite, the link between coverage and catching faults is only **low to moderate**. The fancier coverage measures did no better than the simple one. Their own recommendation, in plain words: use coverage to spot code nobody tests at all, and do not use it as a quality target.

Two caveats. The faults were introduced by a tool, not real bugs. And the projects were all Java. So the direction is solid and the exact strength is approximate.

What did correlate better was simply **how many tests there are**, and a follow up found the **number of checks inside the tests** correlated strongly too.

So: use coverage to find files with no tests at all, never set a target, and ask of any test **does it check something?** A test that runs a function and asserts nothing is theatre.

## Flaky tests disable the gate

A flaky test passes and fails on the same code with nothing changed.

The widely quoted numbers come from Google: about 1.5 percent of test runs came back flaky, about 16 percent of tests showed some flakiness, and roughly 84 percent of pass to fail transitions were flakiness rather than a real bug.

Worth knowing how those travel. Dozens of articles quote them and they all trace back to one Google blog post from 2016. That is one source repeated, not many agreeing, and it is old. Separate studies point the same way, so the direction holds even if the figures have one origin.

Why it matters more than it sounds: a gate only works if people believe it. Once a red build usually means nothing, everyone learns to press re run, and a real failure sails through behind the habit.

What to do:

- Treat a flaky test as a bug with a ticket, not as weather.
- Fix the cause, which is nearly always waiting on time instead of waiting on a condition, or two tests sharing state.
- Take a persistently flaky test out of the blocking set with a deadline, and delete it if the deadline passes. A test nobody trusts and nobody fixes is worse than no test.

## Junior against senior

| Moment | Junior | Senior |
| --- | --- | --- |
| Writing a test | After the code, for the path that already works | Before the fix, so it fails first and proves it can |
| A bug is found | Fixes it | Writes the failing test, then fixes it |
| Coverage | Chases the percentage | Uses it to find untested files, ignores the number |
| A test with no checks | Counts it | Deletes it |
| A flaky test | Presses re run | Files it as a bug and takes it out of the blocking set with a deadline |
| End to end tests | Wants one for everything | Wants three, for the paths that would embarrass you |
| A test in the way of a rewrite | Rewrites the test to match | Notices the test was tied to internals, and fixes the test's design |

## The one team number worth watching

**How many bugs reached a client that a test could have caught.** Small, honest, and hard to game. Coverage is none of those things.