# Core law

No `paths` frontmatter, so this loads every session. It is short on purpose —
every line here competes for attention with everything else in the window.
Everything in it is either enforced by a machine elsewhere, or genuinely needs
saying every single time.

## Stop and ask before
- Adding, removing or upgrading any dependency
- Changing anything in `constitution.md` — a decision there is closed until a
  human re-opens it in writing
- A refactor touching more than five files
- Anything that spends money, sends mail, or writes to something outside this
  machine

## Done means done
Never report a task complete while a check is red. If you cannot make it green,
say so plainly and stop. Never disable a check, weaken an assertion, add an
ignore comment, raise a threshold, or delete a test to get green. That is
cheating the check, not meeting it.
<!-- enforced by: .claude/hooks/gate.mjs (Stop). Delete this section if that
     hook is ever removed, not before. -->

## Read before you write
Before changing an exported function, read the files that import it.
If you did not read a file, do not claim what is in it.

## Prove it by running it
Typechecking proves shapes agree. It proves nothing about the world. A check
that has never executed is untested, not passing. Prove a new check by making
it fail on purpose, watching it fail, then watching it pass clean.

## Say what you could not verify
Label it unverified, in the artifact, and name the task that would settle it.
An unverified claim with no owner quietly becomes a fact.

## Duplication
Two copies is fine. On the third, either abstract it or write one line in a
decision record saying why not. A wrong abstraction costs more than a duplicate.

## Simplicity
Build what today's task needs. Complexity is allowed when the business rule is
genuinely complex — not because something might be useful later.

## Never
- Hand the human a `!` prefixed command, or any route that runs outside the tools, to get past a guard. Hook checks do not run on those, so suggesting one is handing over a bypass. The only sanctioned routes are the human editing the file in an editor, or changing the guard in the open with the reason recorded
- `git push --force`, `--no-verify`, or any flag that skips a hook. If a guard
  blocks something legitimate, change the guard in the open, with the reason
  recorded. A gate you can open yourself is a sign, not a gate
- A secret, key or connection string in a file that gets committed
- String-concatenated SQL, or any query built by pasting user input into text
- `===` / `!==` on a cryptographic value. Use a constant-time comparison, and
  guard the length first
- Parsing a webhook body before verifying its signature. Raw bytes first
- Logging a password, token, secret, or a full request body
