---
paths:
  - "package.json"
  - "tsconfig.json"
  - "*.config.*"
  - ".github/**/*"
  - "**/Dockerfile*"
  - "**/docker-compose*"
  - "**/*.tf"
---

<!-- BOOTSTRAP: name the actual package manager and the actual commands. Delete
     any section this project does not have. -->

# Tooling and environment

## Package manager
<BOOTSTRAP: name it, and name the lockfile.> One package manager per repo.
The lockfile is committed, always. In any automated context use the
frozen-lockfile install, never the loose one — a build that resolves a
different tree from the one you tested is not the thing you tested.

## Config changes stop for review
Any change to CI, container, or deploy config gets shown to a human before it
runs. These are the files where a small mistake is expensive and invisible.

## Secrets
Environment variables and a secret manager. Never a literal value in a file.
Where a record points at a secret, it holds the **name** of the variable, never
the value — so the value never enters the database, never enters a backup, and
never appears in a dump somebody emails themselves.

## Pin the tools your gates invoke
A gate that shells out to an unpinned tool resolves to whatever is newest at
run time, which means your build can break on a stranger's release schedule.
Pin it. Bump it deliberately.

## Never
- Commit `.env`, or any file holding a key
- Take an automatic security "fix" without reading what it changed. They
  routinely downgrade a package several majors to satisfy an advisory
- Remove an override or a resolution without checking what it was covering
- Add a dependency without asking. A dependency is a decision, not a chore
- Silence a warning to make output tidy

## Formatters are write tools
Anything with `--write`, `--fix` or `--format` can reach a protected directory,
because a permission rule inspects the command you typed while the tool writes
through its own process. Scope those tools in their own config, and prefer a
whitelist — a blacklist fails open.