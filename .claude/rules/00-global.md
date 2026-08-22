# Global build rules (always loaded)

## Zero duplication
Before writing any new function, class, or helper: query the codebase-memory
graph (search_graph, then trace_path or impact on candidates). If something
similar exists, extend or reuse it. CI fails PRs above 3% duplicated lines.

## State files are the memory, chat is not
- Read `docs/journal/BUILD-STATE.md` before starting anything.
- After finishing a subtask, update its `Now / Next / Blockers` sections.
- Append one line per change to `docs/journal/CHANGELOG-AI.md`:
  `YYYY-MM-DD | T-xxx | file(s) | what changed | why`
- Any real choice (library, pattern, tradeoff) gets a row in
  `docs/journal/DECISIONS.md`. If it is not written down, it did not happen.

## Definition of done for any task
1. Typecheck clean. 2. Tests green. 3. No new duplication.
4. State files updated. 5. Committed on the task branch with INTENT/VERIFY body.
6. **The whole CI gate run locally and green BEFORE any push is handed over.**

## Run the gate yourself before you hand over a push
Open `.github/workflows/gate.yml`, and run every step it runs, by hand, in
the same order with the same flags. Only then write the git sequence.

The human must never be the one who discovers the build is red. Learned
2026-07-30 in T-014: the scaffold was pushed without running `jscpd`, which
was one command away. CI failed, the human carried the red X back, and the
round trip was pure laziness. "Let the machine tell me if I am wrong" is the
junior move. Know before you ask.

Corollary, and it cost two defects in one run: **a gate step that has never
executed is untested, not passing.** A step that skips itself (no source
directory yet, no test script yet, a condition never met) proves nothing.
Treat every first execution as a likely failure and watch it.

## Fix the reason it was invisible, not just the bug
When something breaks, ask why nobody saw it sooner, and fix that too.
The jscpd step failed on a renamed flag; the real defect was that the
command was unpinned, so it resolved to whatever was newest at run time and
could break on a stranger's release schedule. Pin the tool, then fix the flag.

Do not silence the alarm. Raising a duplication threshold until the build
passes is cheating the check, not meeting it.

## Know when NOT to fix
Over-fixing is a junior failure too. If the correct fix would pre-empt a
decision another task owns, do not improvise it. Park it: a comment in the
file naming the rule being broken and the task that closes it, plus a line
in BUILD-STATE. Parked and visible beats fixed-wrong or fixed-silently.

## Say what you could not verify
Label it unverified inside the artifact, in the journal, and in the report.
An override that installs and builds but has never been exercised at runtime
is not proven. Do not let it quietly become "fine" because nothing broke yet.

## Boy-scout rule, scoped
Leave every file you edit cleaner than you found it: fix typos and messy
lines IN THE LINES YOU ALREADY TOUCH. Anything bigger (renames, moves,
restructures) becomes its own task in BUILD-PLAN so the reviewer never
sees unrelated changes smuggled into a diff.

## Absence protocol (the anti-duplication law)
Never conclude code is missing because you read files and did not see it.
Partial reads lie. "Missing" is earned three ways, all required:
1. Graph search on the symbol name plus two naming variants.
2. Project-wide grep for the name.
3. A written scope line in your report: "not found; checked graph + grep
   for X, Y, Z".
Only after all three may you create the symbol. Prefer graph queries over
reading whole folders; the graph answers structure questions for hundreds
of tokens instead of tens of thousands.

## Token discipline
- Reports back to the orchestrator stay under ~300 words. Point to
  evidence as file:line references; never paste code blocks back up.
- Structure questions ("where is X", "who calls Y", "does Z exist") go
  to the graph, never to folder-wide reads. Lockfiles, node_modules,
  and build output are never read; the deny list blocks them anyway.
- One task per session. Finish, journal, commit, /clear. A long session
  re-pays for its own history on every turn.

## Before the session ends
When I say we are done, or I say goodbye, or the work reaches a natural stop:
remind me in one line to run /coach. Do not run it yourself.
Do not remind me more than once per session.
Say only: "Worth running /coach before you close this."
