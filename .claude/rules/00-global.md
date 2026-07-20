# Global build rules (always loaded)

## Zero duplication
Before writing any new function, class, or helper: query the codebase-memory
graph (search_graph, then trace_path or impact on candidates). If something
similar exists, extend or reuse it. CI fails PRs above 3% duplicated lines.

## State files are the memory, chat is not
- Read `docs/build/BUILD-STATE.md` before starting anything.
- After finishing a subtask, update its `Now / Next / Blockers` sections.
- Append one line per change to `docs/build/CHANGELOG-AI.md`:
  `YYYY-MM-DD | T-xxx | file(s) | what changed | why`
- Any real choice (library, pattern, tradeoff) gets a row in
  `docs/build/DECISIONS.md`. If it is not written down, it did not happen.

## Definition of done for any task
1. Typecheck clean. 2. Tests green. 3. No new duplication.
4. State files updated. 5. Committed on the task branch with INTENT/VERIFY body.

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
