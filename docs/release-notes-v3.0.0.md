Sanad v3.0.0 makes the assistant something a team can actually sign in to and
use: real accounts, documents added from the browser, answers that arrive as
they are written, and a quality dashboard.

## New
- **Formatted answers:** answers render their own bold, lists, tables and
  headings. Images, links and raw HTML from the model are switched off on
  purpose, so a model cannot paint a button or a link into an answer.
- **A truthful progress rail:** while you wait, the four real stages of the
  search are shown, driven by the server's own stage key -- not a timer
  pretending to be progress.
- **Streamed answers:** the answer appears while it is being written. The
  first characters are held until the text cannot be an honest refusal, so
  the refusal code word never flashes on screen.
- **Reports dashboard:** score meters with their pass lines, trend lines
  across runs, and a per-question map of the last run.
- **Documents from the browser:** drag and drop or choose files, download any
  document or source, and remove one after a confirmation. An upload lands in
  the workspace folder, so the folder stays the only way documents get in.
- **Real login (Keycloak):** sign in with an account, in three roles --
  administrator, curator, reader -- with access granted per workspace and a
  chat history that is yours alone. Nobody has permission by default: a
  workspace you were not granted is invisible, not merely refused.
- **Admin view:** every account with its roles and last sign-in, tick-boxes
  for who may see which workspace, "sign out everywhere", and an activity log.
- **French by default, with Arabic and English** (shipped just before this
  release, verified again here).

## Quality gate
Paid 60-question run on the frozen golden set against this code:
**G1 38/40 fully grounded (need 90%), G2 refusals 20/20, G3 sources 38/38 --
release gate PASS.** Same shape as v2.0.0's 38/40, so no regression:
`g-in-026` recovered, `g-in-014` is newly refused, `g-in-033` was refused in
both runs. Report: `docs/evals/release-v3.0.0-2026-09-14.json`.

Full suite on the merged code: 1194 passed, 2 skipped, 1 xfailed, lint clean.

## Upgrading an existing install
`AUTH_MODE` stays `none` unless you set it, so an existing install keeps
working untouched. To turn on accounts, set `AUTH_MODE=keycloak` and the
`KEYCLOAK_*` lines (README has the realm setup, including the post-logout URI
the realm must list). `UPLOAD_MAX_BYTES` caps an upload.

## Known issues
See `docs/known-issues.md`. The main ones for this release:
- Signing out shows Keycloak's own "Do you want to log out?" page: one extra
  click.
- A provider failure in the middle of a stream is not retried; you get the
  named error and a Retry button.
- Chat history lives in memory, so a restart loses the transcript. Keeping it
  is personal data under law 09-08 and needs a named owner first.
- `/api/v1` is administrators-only when accounts are on.
