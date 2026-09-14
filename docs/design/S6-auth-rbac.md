# S6 — Real login, roles and per-user history (design)

Status: design for the S6 wave 3 branch `feat/S6-keycloak-auth`.
Human rulings behind it (2026-09-13, recorded in DECISIONS as CR-03):
Keycloak for login, senior-level roles and permissions, per-user chat
history, an admin view and an activity log. The signed pack says the
opposite (ADR-13: "single user, no authentication"), so this is a change
request against it, never an edit of it (rule 1).

## What a reader gets

* A sign-in page instead of a browser password box. After signing in, the
  header shows who you are and a Sign out button.
* Three roles: **admin** (everything, plus the admin view and the activity
  log), **curator** (add, sync and remove documents in workspaces they are
  given, and ask questions there), **reader** (ask questions there only).
* Your chat transcript is yours: two people signed in to the same server
  never see each other's conversation.
* An activity log an admin can read: who signed in, who synced, who
  uploaded or removed a document, who deleted a workspace.

## Three modes, one setting

`AUTH_MODE` decides how the app is protected. It replaces nothing that
works today; both existing behaviours stay as one of the modes.

| `AUTH_MODE` | Who can use it | What it is |
|---|---|---|
| `none` (default) | the machine's own user | today's local-first behaviour (ADR-13, LD-07). No login, no roles, everything allowed. |
| `password` | anyone with the shared password | today's `ACCESS_PASSWORD` gate, unchanged (the Railway demo). |
| `keycloak` | named people in Keycloak | this design. |

A mode is a deliberate operator choice; there is no auto-detection. With
`keycloak` selected and its settings missing, the app refuses to start
with a sentence naming the missing setting — the same rule the model seam
already follows (`ChatUnavailableError`), because a half-configured login
that silently falls back to "no login" is the worst of the three.

## Why no new dependency

The v3 plan says no new Python auth package. Two things make that
possible:

1. **The authorization-code flow is all back-channel.** Sanad redirects to
   Keycloak, Keycloak redirects back with a `code`, and Sanad exchanges
   that code for tokens over TLS, server to server. No token ever needs a
   signature check in our process because nothing about it arrived through
   the browser.
2. **Keycloak's introspection endpoint answers the only question we have:**
   is this access token active, and what roles does it carry. It returns
   JSON. `urllib.request` from the standard library is enough for both
   calls, and `secrets`/`hashlib` cover the session token.

So: no `authlib`, no `python-jose`, no `pyjwt`. We never parse a JWT.

## The flow, step by step

1. An unauthenticated request to any page (except `/static/*`,
   `GET /api/v1/health` and the auth routes themselves) is redirected to
   `GET /auth/login`.
2. `/auth/login` mints `state` and `nonce`, stores them in a short-lived
   signed cookie, and redirects to Keycloak's authorization endpoint.
3. Keycloak sends the person back to `GET /auth/callback?code=…&state=…`.
   A mismatched or missing `state` is refused outright (that check is what
   makes a forged callback useless).
4. Sanad exchanges the code at the token endpoint using the confidential
   client secret, then calls introspection once to read `sub`,
   `preferred_username`, `email` and the realm roles.
5. Sanad writes/updates the `app_user` row, writes a `user_session` row,
   and sets `sanad_session` — `HttpOnly`, `SameSite=Lax`, `Secure` when
   the request arrived over https. The cookie carries a random token; the
   database stores only its SHA-256, so a stolen database file is not a
   set of live sessions.
6. Every later request looks the session up by that hash, checks
   `expires_at`, and attaches the user and roles to the request.
7. `POST /auth/logout` deletes the session row and clears the cookie.

`SameSite=Lax` is also the CSRF answer for every existing form: a
cross-site POST does not carry the cookie, so it arrives unauthenticated
and is refused.

## Roles and permissions

Keycloak realm roles map by name: `sanad-admin`, `sanad-curator`,
`sanad-reader` (prefix configurable). Nobody is anything by default —
someone with no Sanad role sees one page saying an administrator must
grant access. Least privilege, and it makes a misconfigured realm
obvious instead of accidentally generous.

| Action | reader | curator | admin |
|---|---|---|---|
| Ask questions in a granted workspace | yes | yes | yes |
| Download a source document | yes | yes | yes |
| Upload, remove documents, run Sync | no | yes (granted workspaces) | yes |
| Create, rename, delete a workspace | no | no | yes |
| Give feedback on an answer | yes | yes | yes |
| Read Reports | yes | yes | yes |
| Admin view (people, grants) and activity log | no | no | yes |

Per-workspace access is a grant table (`workspace_grant`): a row says
"this person may use this workspace". An admin sees every workspace
without a grant; a curator or reader sees only what they were given, and
a workspace they were not given does not appear in the selector at all —
not merely a refused action.

## Data, and the law

New tables: `app_user`, `user_session`, `workspace_grant`,
`activity_event`. All additive `CREATE TABLE IF NOT EXISTS`, the way the
registry already migrates.

Storing a person's name, email and their questions is personal data under
Morocco's law 09-08. This design keeps three things true so that is
defensible, but **a named human owner is still required** and the build
journal records it as open:

* the fields kept are the minimum to run the product (id, username,
  email, display name, roles, last sign-in);
* an admin can delete a person's sessions and history from the admin
  view, and a person can clear their own chat history;
* the activity log records what was done and by whom, never the content
  of a question.

## Scope of the first branch

In: the three modes, the flow above, the four tables, role checks on
every existing action, per-user conversations, the sign-in/sign-out UI,
the "no role yet" page, a `compose.keycloak.yaml` for a local realm, and
tests with a fake provider (no network, no Docker in CI).

Out, on purpose, and each is a follow-up: the admin view for granting
roles (Keycloak's own console does it meanwhile), the activity log
screen (the table is written from the start), and persisting chat
history across restarts.

## How it is tested without Keycloak

docs/phase2/ENGINEERING-RULES.md forbids API keys in tests, and CI has no Docker.
The provider is reached through one seam — a small module with
`authorize_url`, `exchange_code` and `introspect` — and the tests use a
scripted fake, exactly as the chat model is faked. One hand-run against a
real Keycloak in Docker is recorded in the journal; the tests prove the
rules (state mismatch refused, expired session refused, role missing
refused, a curator cannot delete a workspace, two users never share a
transcript).
