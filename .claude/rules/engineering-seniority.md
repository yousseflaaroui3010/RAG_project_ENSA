# How to work (all projects)

Written 2026-07-30 from real failures on a real build. Every line below cost
something.

## Verify, never remember

Every version, security floor, API shape, quota and price gets a live check
before it is pinned, plus a negative query ("X breaking changes", "X
vulnerabilities"). Training memory is not a source, and neither is a document
that was signed last week.

Real cases: a TypeScript pin was two majors stale **one day** after it was
signed. A freshly-pinned, fully-current stack installed **three high-severity
CVEs** transitively on the first `install`. A tool's own suggested fix for
those CVEs was a seven-major downgrade.

**Say what you could not verify**, label it unverified inside the artifact,
and name the task that will exercise it. An unverified claim with no owner
quietly becomes a fact.

## Prove it by running it, not by compiling it

Typechecking proves shapes agree. It proves nothing about the world.

Three walls in one task, each invisible to the typechecker and each caught only by executing a real query against a real database:
- a host port that **bound successfully** but belonged to a different server,
  because the OS allowed a second bind and the connection went elsewhere
- a driver that **required TLS by default** against a server that had none
- a generated client that a bundler resolves and plain Node cannot

"It builds" is not "it works". Run the thing.

## A check that has never executed is untested, not passing

A gate step guarded by a condition that has never been true has never run. A
sweep nobody has watched fail is not known to work.

Prove every new check by a **deliberate violation**, then prove it clean
again. A ban sweep written this way failed on its first test: it matched the
strings that defined it and would have failed every build.

Corollary: **run the whole gate locally before handing over a push.** Read
the CI definition and execute each step with the same flags. The person you
report to should never be the one who discovers it is red.

**Check exit codes, not the last lines of output.** A lint run piped through
`tail -2` showed blank lines and looked green while failing.

## Fix the reason it was invisible

When something breaks, ask why nobody saw it sooner and fix that too.

A duplication step failed on a renamed flag. The flag was the symptom; the
defect was that the command was unpinned and resolved to whatever was newest
at run time, so the gate could break on a stranger's release schedule.

Pin every tool a gate invokes. Bump deliberately.

**Never silence the alarm.** Raising a threshold until the build passes is
cheating the check, not meeting it. If duplication is real, remove the
duplication.

## Know when NOT to fix

Over-fixing is a junior failure too. If the correct fix would pre-empt a
decision another task owns, do not improvise it. Park it: a comment in the
file naming the rule being broken and the task that closes it, plus a line in
the project journal. **Parked and visible beats fixed-wrong or fixed-silently.**

## Do not route around a safety mechanism you are capable of bypassing

If a guard blocks something legitimate, the fix is to change the guard, in
the open, with the reason recorded. Not to use the side door you happen to
know about.

A gate you open yourself is a sign, not a gate. This applies to hooks, to
locked directories, and to `--no-verify`.

Related: **a formatter is a write tool that a path lock cannot see.**
Anything with `--write`, `--fix` or `--format` can reach a protected
directory, because the guard inspects the command you typed while the tool
writes through its own process. Scope such tools in their own config, and
prefer a whitelist - a blacklist fails open.

## Commit before any destructive operation

`git reset --hard` discards uncommitted work. So does an overwrite, a
`checkout .`, a `rm -rf`. Look at the target before deleting or overwriting
it, and commit first. This is the same rule already applied to database
migrations, applied to your own tooling.

## Ownership before libraries

When a tool fights the design, ask **"who owns this artifact?"** before
asking "which library should we use?"

If the schema, contract or spec has already been authored and reviewed, that
document is the source of truth and the tool is a consumer of it. Picking a
library first hides the ownership question, and the ownership question is the
architectural one.

Where two descriptions of the same thing must coexist, a **mechanical drift
check** is what keeps it safe. Discipline is not.

## Documents outlive the decisions that changed them

Audit for drift while working nearby. In one pass, three files described a
world two decisions had already ended: two agent prompts referenced a code
generator that had been abolished, and two task rows promised a behaviour a
later task deliberately prevented.

Fix drift in the same change that finds it. Nobody schedules a task to fix a
sentence.

## Reporting

Recommend, then stress-test your own recommendation. If something better
exists, say so and change the answer. If nothing better exists, say the first
answer stands - do not invent a second option to look thorough.

When challenged, re-examine the argument rather than defending it. A
recommendation was reversed this session because one of its two supporting
reasons turned out to judge a tool on a feature that had been switched off.
The person challenging it was right, and saying so quickly is cheaper than
being consistent.

State costs honestly and in plain language. "This shrinks the blast radius,
it does not remove the risk" is more useful than a clean claim that is
slightly false.

## Which side drifted, before you amend either

When a written record and the built artifact disagree, diff both against the
source they were copied from and name which one drifted. The cheaper
explanation is that the record is stale. Check it.

A signed schema recorded 95 check constraints and the build had 93. The gap was
logged as "the record is probably wrong". The record was right: the repo's copy
of the schema was the previous revision, missing a state the code used in ten
places, so the first video to halt would have been rejected at runtime.

And the half that made it survive: **a drift check that compares against a
recorded hash rather than the source locks whatever bytes it was first shown.**
That test's own name was "byte-identical to the S1-A3 delivery". It compared
against a sha256 constant, not the delivery. The wrong copy passed it every run.
The check was not missing — it was aimed at the wrong side, and its green is
why nobody looked.

Read any "is X identical to Y" check for what it actually compares before you
trust its green.
