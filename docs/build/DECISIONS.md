# DECISIONS (ADR-lite: one row per real choice)

| Date | Task | Decision | Options considered | Why | Owner |
|------|------|----------|--------------------|-----|-------|
| 2026-07-20 | SETUP-000 | TYPECHECK_CMD = `uv run ruff check .` | mypy/pyright as new dep / ruff / leave empty | pinned stack has no type checker; ruff is already pinned, no new dependency | setup |
| 2026-07-20 | SETUP-000 | Branch naming = `feat/S<sprint>-ST-<nn>-<slug>` | kit `task/T-xxx` / Phase 2 `ST-nn` | docs/phase2 is signed and ST-01..ST-52 already exist in the plan | setup |
| 2026-07-20 | SETUP-000 | CI package manager = uv (setup-uv, `uv sync --frozen`) | keep npm block / uv | Sanad is Python-only, no JS toolchain (ADR-02, ADR-10) | setup |
| 2026-07-20 | Phase3-S0 | Claude maintains BUILD-STATE/CHANGELOG/DECISIONS directly (masters editable) | immutable masters + human fold-delta / direct edit | the fold indirection created per-turn friction the user rejected | human + orchestrator |
| 2026-07-20 | Phase3-S2 | Contract of record stays frozen at docs/phase2/openapi.yaml; served copy docs/api/openapi.yaml created by ST-51 as the drift-test target | edit the phase2 copy / keep a single copy | docs/phase2 is the write-locked signed pack; ST-51 owns the served contract (ADR-13) | orchestrator |