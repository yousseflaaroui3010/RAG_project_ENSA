---
paths:
  - "api/**"
  - "db/**"
  - "agent/**"
  - "ingestion/**"
  - "indexing/**"
  - "evaluation/**"
  - "app.py"
  - "config.py"
  - "**/*.sql"
---
# Backend rules

- Contract first: routes must match the Phase 2 API contract in
  `docs/phase2/openapi.yaml`. An endpoint change and its `docs/api/openapi.yaml`
  change travel in the same branch; the contract-drift test enforces this.
- Routes in `api/` delegate to service functions only. No business logic in a
  route body. The server binds to 127.0.0.1.
- Migrations: always additive when possible, always dry-run before apply,
  never lock hot tables. Destructive migrations need explicit human approval.
- All queries go through the data layer. No inline SQL in route handlers.
- Every endpoint: input validation, standard error shape, auth check.
- No secrets in code or logs. Config comes from environment only.

## Fail loud (dev), contain the outside world (always)
- During development, crash immediately on bad input. Never catch an
  error without logging the full traceback. Keep logs free of noise so
  real bugs stand out like a spraying leak, never a slow rot.
- Every external API or network call gets a short timeout and a written
  fallback value. A slow third party must never slow your system.
