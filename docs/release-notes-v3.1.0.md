Sanad v3.1.0 turns the signed-in app into something each person owns: your
own workspaces from your own folders, every chat kept and reopenable, and
limits that keep an open sign-up from being abused.

## New
- **Your own workspaces:** anyone who signs in can create a workspace and
  owns it. Only you see it and change it. The workspaces that already
  existed (the demo's "RH -- Code du travail") are shared: everyone reads
  and asks, nobody changes them.
- **Create a workspace from a folder on your computer:** pick the folder;
  its supported files are uploaded and indexed. Files in subfolders and
  unsupported types are skipped and named on screen.
- **Every chat kept:** each conversation has its own address, a title taken
  from its first question, and a place in a slide-out History panel. Open,
  rename or delete any of them; "New conversation" keeps the old one.
- **A calmer screen:** the header fits on one row, the language switch
  lives in a new footer, and the history slides in from the reading side
  (the right, in Arabic).
- **Rate limits** (with accounts on): caps on sign-in attempts per address,
  and per person on questions, Syncs, new workspaces, uploads and other
  changes. Over a cap, Sanad says how many seconds to wait.

## Removed
- **Roles and the admin page.** Every signed-in person is equal; Keycloak
  only checks who they are. Grants and the activity-log screen are gone.
- **The machine API (`/api/v1`) with accounts on**, except the health check:
  it listed every workspace and could index any server folder.

## Quality gate
Paid 60-question run on the frozen golden set against this code (2026-09-19): **G1 39/40 fully grounded (need 90%), G2 refusals 20/20, G3 sources 39/39 -- release gate PASS.** Better than v3.0.0's 38/40; the one miss, `g-in-033`, was refused in both runs (known issue: the grader reads short chunks). Report: `docs/evals/release-v3.1.0-2026-09-19.json`.

Full suite on the release code: 1372 passed, 2 skipped, 1 xfailed, lint clean.

## Upgrading an existing install
Nothing to do by hand. On start-up Sanad moves old saved chats into the new
conversation table (then removes the old table) and adds a workspace-owner
column; every existing workspace becomes shared. Back up `sanad.db` first.
The login-free modes (`AUTH_MODE=none` or `password`) work as before: one
person, their own folders typed in place, no caps.

## Known limits
See `docs/known-issues.md`. Chiefly: rate limits live in one process (one
replica only); workspace names are unique across everyone; feedback left on
a shared workspace is visible to no one.
