# Start here

For someone opening this repository for the first time, or coming back to it
after a while. Ten minutes, in order.

## What Sanad is

You point it at a folder of documents. It reads them, and then it answers
questions about them **with the sources attached** — or says it does not know.
It refuses rather than guesses. That refusal is a feature, not a limitation:
the product is for people who must be able to check the answer.

Everything runs on one machine. No document leaves it unless you configure a
cloud model on purpose.

## Run it once

```
uv sync
cp .env.example .env
uv run python app.py
```

Open http://127.0.0.1:8000. Make a workspace, point it at a folder, press
Sync, ask a question. That loop is the whole product; everything else serves
it.

## The four files that answer most questions

| File | What it settles |
|---|---|
| [journal/BUILD-STATE.md](journal/BUILD-STATE.md) | Where the project actually is right now. **Read this before trusting anything else**, including your own memory of it. |
| [journal/DECISIONS.md](journal/DECISIONS.md) | Every real choice and why. If something looks wrong, check here before changing it — it may be deliberate. |
| [known-issues.md](known-issues.md) | What is broken or rough, written down honestly rather than hidden. |
| [phase2/](phase2/) | The signed specification: what the product must do. **Never edit these to match the code.** If a spec is wrong, raise it. |

## How the work is done

- One story, one branch, one pull request. Never commit straight to `main`.
- A green test suite has never been enough on this project. Every branch gets
  a review pass before it merges, and those reviews keep finding real defects
  while the tests are green.
- Nothing is "done" because it should work. It is done when it was run and
  watched. If a check is red, the work is not finished — the check does not
  get weakened to make it green.

## Signing in

By default there is no login at all: it is your machine, everything is
allowed. Two other modes exist — one shared password, or named people with
roles through Keycloak. The README section "Signing in (S6)" sets up a full
Keycloak realm with demo people in one command.

## Where the code lives

Mostly flat. `app.py` is the web layer, `agent/` is the question-answering
pipeline, `db/` is storage, `ui/` is the screens, and the reading and
chunking of documents sits in `conversion.py` and its neighbours. The test
suite mirrors it under `tests/`.
