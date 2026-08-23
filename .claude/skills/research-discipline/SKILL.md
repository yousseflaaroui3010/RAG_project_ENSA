---
name: research-discipline
description: How to tell whether a check actually checked. Use when a gate passes but the thing may still be broken, when two observers disagree on a result, before trusting a passing test or linter, after running any tool that scaffolds or installs, and before claiming a fix works.
---
# Evidence discipline

Written 2026-08-03, from real failures in one long session. This file covers
one narrow problem: **a check passed and the thing was still broken.** Every
line below cost a round.

Companion skill in this repo: `prove-it`, which covers enumerating root
causes and proving a check can fail. (On import to Sanad this paragraph
pointed at a machine-local `engineering-seniority.md` that is not in this
repo; the pointer was repaired rather than left to dead-end.)

## Match the width of the claim to the width of the evidence

I tested one field at the top level of a request body, got "extra inputs are not
permitted", and wrote down "X is not a field". That is a statement about a whole
schema built on evidence about one object. Someone else found the field nested
one level down. It was real the entire time.

**"Not here" is never "nowhere".** Before writing an absence claim, say out loud
which container you actually looked in, and put that in the claim: not "X does
not exist" but "X is not accepted at the top level of this endpoint, tested with
a wrong value and a valid one".

An absence claim without its scope cannot be falsified, so it survives long
after it stops being true.

## Green from one vantage point is not green

An automated gate reported a test failing. I ran the same test eight times, saw
eight passes, and reported it fixed. It failed again immediately.

The failure was deterministic. It depended on a lowercase Windows drive letter
in the working directory. My shell normalised the letter, the gate passed it
through unchanged, so every run I made passed and every run it made failed. Same
repo, same command, same second.

**When another observer disagrees with your result, the disagreement is the
finding.** Do not average it out and do not re-run until it agrees with you. Ask
what is different about how they invoked it: cwd, shell, env, path spelling,
concurrency, TTY. A check whose result depends on who called it is not a check.

Eight passes from one vantage point are one sample, not a proof.

## Run the control with the same harness

Chasing that bug, all my passing runs came from Bash and all my failing runs
came from `cmd.exe`. I concluded "it is the drive-letter casing" and started
fixing. Two variables had moved and I had attributed the effect to one.

The conclusion turned out to be right, which is worse than being wrong, because
nothing forced me to notice the method was luck.

**Change one thing. Then run the control through the identical harness.** If the
only way you can produce the failure is a different launcher, the launcher is a
suspect.

## Validation runs in stages, so probe in stages

An API rejected a numeric value for a field with a type error. I concluded the
field was usable and spent a round finding out the engine refuses it outright.

Type validation, semantic validation and resource lookup are usually three
separate stages. A type error only proves stage one knows the name.

**Probe every field twice: once with a deliberately wrong value to learn whether
it is known, once with a legal value to learn whether it is accepted.** The
first tells you the schema. Only the second tells you the world.

Generalises past APIs: a config key the parser accepts is not a config key the
program honours.

## A checker verifies what you pointed it at

An accessibility checker reported 7 of 7 text elements passing WCAG AA. A caption
was invisible on screen. It had measured the text against the card's own dark
background, and what was actually behind the text was a white wall in the video.

The number was true. The question was wrong.

**Before trusting a passing check, say what it compared and confirm that is what
matters.** Then look at the output with your own eyes once. One frame caught what
a hundred assertions missed.

## Rejected work is usually free, so interrogate before you buy

A metered API bills completed jobs and not rejected requests. So a request that
is guaranteed invalid on one axis costs nothing while still running the whole
validator.

I mapped an entire undocumented schema with about 120 deliberately broken
requests for zero money: 44 candidate field names refuted, four confirmed, one
enum discovered from its own error message.

**Ask the machine what it accepts before paying it to show you.** Poison one
required field so nothing can succeed, then vary the field under test. Cheaper
than reading docs, and it cannot be out of date.

Two guards make it safe. Poison an axis the validator checks LAST, so earlier
stages still run. And put a kill switch in the script that cancels anything
accepted by mistake, then report the spend as non-zero if it fires.

## Measure the artifact, do not read its number off a document

A document recorded a render as 27 seconds and priced it accordingly. The file
was 20.8 seconds. Nobody had opened it; the number came from a character-count
estimate and then hardened into a fact through repetition.

**Anything you can measure, measure.** Duration, byte count, row count, hash.
And when you correct a number, write down where the old one came from, or the
next person re-derives the estimate and believes it again.

## Do not assert a count you are also rendering

Two signed documents said "fifteen states" and then listed fourteen. My UI
copy repeated the fifteen while the page rendered fourteen items from the same
array.

**Render the length. Never type the number.** A sentence that counts its own
list cannot drift from it. Where the number must stay prose, cite the source and
flag the mismatch rather than picking a side quietly.

## Build tools write files you did not ask them to write

Two cases in one session. A framework plugin added a dependency to
`package.json` during a test run, with a caret range in a file of exact pins,
and nobody decided it. A CLI staged a third-party minified bundle into a
directory the linter walks, producing 199 errors in code we did not write.

This is the same shape as "a formatter is a write tool a path lock cannot see",
extended: **build plugins edit manifests, and scaffolders drop vendored code
into your check paths.**

After running any tool that scaffolds, stages or installs, diff the files you
did not touch. Especially the manifest and the lockfile.

## Adding a config file can silently rebind an existing command

I added `vite.config.ts` for a web app. The test runner had no config of its
own, so it adopted that one, and from that moment a suite that only hashed files
was booting the entire framework build pipeline. Running the unit tests
regenerated the app's build directory as a side effect.

**A tool that falls back to a shared config will pick up whatever you add
next.** When you introduce a config file, check which other commands resolve it,
and give anything that should not inherit it its own.

The tell is cheap to find: delete a generated directory, run the unrelated
command, and see whether it comes back.

## Prove a fix the same way you proved the defect

The routine that worked, every time, in this order:

1. Reproduce deterministically and record the counts, not the impression
2. Fix at the layer that holds for every caller, not just the one that
   complained
3. Re-run the exact reproduction and show it passing
4. Break it on purpose and watch it fail, so you know the check can still say no
5. Restore, and confirm clean through the original caller's own invocation

Step 4 is the one under pressure you will want to skip. It is the only step that
distinguishes "the check passes" from "the check works". A suite that ran zero
tests and reported failure was one wrapper away from running zero tests and
reporting success.

## When a fix does not work, correct the comment you already wrote

I added a config option believing it fixed the bug, wrote a long comment saying
so, then found it failed 4 out of 4 and fixed it elsewhere. The comment was now
a trap pointing the next reader at the wrong line.

**A wrong explanation left in place costs more than no explanation.** When the
cause moves, edit every note that named the old one, in the same change.