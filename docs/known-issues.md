# Known issues (V1.0.1)

Everything below is known, reproduced or reasoned from the code, and
deliberately not fixed before the defense. Each line says what happens, why
it waits, and what would fix it. Severity is for a live demo: none of these
breaks a signed gate (G1-G3 pass on the golden set).

## Answer quality

| Issue | Effect | Why it waits | Fix (V1.1) |
|---|---|---|---|
| The relevance grader reads ~500-character child chunks | A fact sitting just past the chunk the grader sees is refused (g-in-033, Article 66's one-month delay) | Grading on full sections changes every question and puts G2's strict 20/20 at risk days before the jury | Grade on the parent section, or the chunk plus its neighbour; keep rewording inside the documents' own legal vocabulary; re-run all 60 |
| The rewording step can import French-France terms (`CSE`) | Later search rounds look for concepts the Moroccan code does not use | Same prompt freeze as above | Add "use the documents' own terms" to prompts/query-reword with a new version and eval seeds |
| G1 passes with little margin | One unlucky run can move G1 by a row | Three of the four v1.0.0 misses were model variation (docs/evals/v1.0.1-g1-triage.md) | The grader fix above |

## Models and speed

| Issue | Effect | Why it waits | Fix |
|---|---|---|---|
| Ollama's timeout is per wait for data, not per call, and it has no retry setting | A slow local model can fail at 60 s before its first word | The defense runs in cloud mode (DECISIONS 2026-09-12) | Measure strict-local mode, then set its own timeout |
| `agent/chat.py` imports httpx, declared only as a dev dependency | None today: both provider clients require httpx and it is pinned in uv.lock | Declaring it changes the dependency list (partner sign-off) | Declare httpx as a runtime dependency |
| The Docker image is about 9 GB | It bundles the CUDA build of PyTorch, unused on CPU | Not on the demo path (the defense runs `uv run python app.py`) | Port #86's CPU-only PyTorch build |
| Intake speed depends on machine load | G5 375-449 s per 200 pages quiet, 731.6 s under load | Measured and reported, as the V1.0 gate requires | Batch or smaller embedding model, re-measured against G5 |

## Data layer (from the ST-17 reviews and the data-layer follow-ups)

| Issue | Effect |
|---|---|
| `sync._ingest` discards the deletion counts it computes | Report detail only; outcomes are right |
| `last_synced_at` is not refreshed for unchanged files | A timestamp reads older than the last Sync |
| `sync_run` has no error column | A folder-level Sync error is shown live but lost on restart |
| An unreachable file may be swept as Removed (unprobed) | Needs a deliberate fixture to confirm |
| The schema script is split on `;` | Safe for today's schema; a `;` inside a string literal would break it |

## Code shape

| Issue | Why it waits | Removal condition |
|---|---|---|
| `app.create_app` (cyclomatic 31) and `api.routes.build_router` (28) | The score counts every nested route handler; splitting re-opens reviewed code for no behaviour change | The next story that adds a route splits the factory it touches (DECISIONS 2026-09-12) |

## Product

| Issue | Status |
|---|---|
| Answer traces are not persisted (issue #51) | Deferred to V1.1 with F-10 (DECISIONS 2026-09-12) |
| Sample questions show file names rather than questions | Cosmetic |
| The six ST-38 screen-reader rows | Open until the human Narrator pass |
