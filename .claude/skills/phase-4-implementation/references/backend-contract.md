# Backend contract

Concrete shapes and numbers. The process that governs when to apply them is in
the phase-4 skill body. `rules-scoped/03-backend.md` and `04-database.md` bind
above this file.

## Endpoints

Plural noun resources (`/users`). The OpenAPI spec is the source of truth. A
breaking change goes to `/v2/...`; never break an active endpoint.

Pagination is mandatory on every list. Default 20, maximum 100. No fetch-all.

Validate at the boundary before any business logic: type, length, format,
range. Never trust the client.

Every mutating endpoint is idempotent, by key or by natural uniqueness. That is
what stops a retry or a double-click becoming a double charge.

Handle `SIGTERM`: drain requests, close the database, exit.

Target p95 under 200ms. Written as a percentile with a window, per
`quality-metrics`.

## Error shape

One shape, always, including on failure:

```json
{ "error": { "code": "...", "message": "...", "status": 400, "requestId": "..." } }
```

Layered: route returns the HTTP status, service throws typed exceptions, data
layer catches and wraps.

| Status | Means |
|---|---|
| 400 | Bad input |
| 401 | Not authenticated |
| 403 | Authenticated, not allowed |
| 404 | Not found |
| 409 | Conflict |
| 422 | Validation failed |
| 500 | Server fault |

Never return `200` with `{ success: false }`. A caller that has to read the body
to know it failed will eventually forget to.

Cases that must be handled, not assumed away: nulls, wrong types, duplicates,
concurrent edits, expired sessions, network failure mid-action, empty and
maximum states.

## Database

Every table carries `id`, `created_at`, `updated_at`, all UTC. Convert to local
time in the frontend only.

Never `SELECT *`. Name the columns.

Migrations are reversible and non-locking. Never modify a deployed migration.
See `zero-lock-migration` for the expand-contract procedure.

Index foreign keys and any column in a WHERE clause. Run `EXPLAIN` on new
queries.

Transactions for multi-step operations. Constraints at the database level, not
only in application code.

Soft deletes preserve relational integrity. Hard delete only for a GDPR or CCPA
erasure request.