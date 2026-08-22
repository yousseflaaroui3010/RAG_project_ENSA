# Review checklist

Run against a finished task branch, before it goes to a human. `senior-review`
carries the twenty-row sheet for judging whether work is senior; this is the
short pass for one change.

Every line is yes, or the branch is not ready.

## Does it do what was asked

- Acceptance criteria met, each one pointing at something that was run.
- Edge cases handled: empty, one, many, huge, slow, duplicate, wrong type, two
  at the same moment.
- Nothing in the diff that nobody asked for.

## Is it safe

- Authentication and authorization both checked on every new endpoint. Owning
  the resource is a separate question from being logged in.
- No secrets, tokens, keys or personal data in code, logs, or the browser
  bundle.
- Input validated at the boundary, before business logic.

## Will it hold

- No N+1 queries. Check the ones that loop.
- Pagination on every list endpoint.
- Time limits on every call to something outside this process.
- Logs updated, with the request id carried through.

## Is it honest

- A test exists that fails without this change. Not a test that merely runs.
- No `any`, no `@ts-ignore`, no commented-out code, no stray debug output.
- No check weakened to get green: no raised threshold, no ignore comment, no
  softened assertion, no deleted test.
- Any shortcut named in writing, with the condition for removing it.

## Is it readable

- Someone else can follow it without asking questions.
- Names say what things are.
- Comments say why, never what.
- The commit message says why.

## The two questions that catch the most

Ask them out loud at the end.

What would break if this ran twice? And what happens to this code when the
thing it calls is down?
