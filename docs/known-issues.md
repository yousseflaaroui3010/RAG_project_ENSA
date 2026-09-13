# Known issues (V2.0.0)

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
| Answer traces are shown per answer (F-10) but not persisted (issue #51) | A trace lives as long as the conversation on screen (DECISIONS 2026-09-12) |
| Sample questions show file names rather than questions | Cosmetic |
| The six ST-38 screen-reader rows | Open until the human Narrator pass |

## V1.1 and V2.0 features (F-10 to F-16)

| Issue | Effect | Why it waits |
|---|---|---|
| Workspace routing has no minimum score (F-12) | An off-topic question still gets a proposal (measured 0.769 vs 0.757) | No tuning data for a cutoff yet; nothing is answered before the user confirms |
| Arabic article numbers can be displaced in PDF text (F-14) | Arabic with an embedded digit sometimes extracts out of order; pure Arabic text and TXT/MD/DOCX are fine | No reliable trigger found; pinned as a strict xfail so the day it starts passing it turns red |
| PDFs mixing scanned and typed pages are not OCR'd (F-16) | Only a PDF with no text at all is OCR'd | Per-page detection would change the output of every typed PDF |
| OCR has no per-page timeout beyond `OCR_MAX_PAGES` (F-16) | A very slow page holds up its Sync | No other conversion rung has one either |
| Real-OCR tests skip in CI (F-16) | CI has no tessdata; the local run is the proof | The language files are an external asset, not in the repo |
| Tessdata_fast Arabic drops the space in "المادة12" (F-16) | Handled: the citation label is normalised to "المادة 12" | Upstream model quality |
| A watched folder never syncs on a deletion alone (F-13) | The removed file's chunks stay until the next Sync | A disappearance is not something the watcher can wait to "settle" |
| PowerPoint citations inside one long slide fall back to the parent range (F-11) | A window wholly inside a slide longer than ~400 characters is cited by a range that still contains the right slide | Changing chunking would also change Article labels and need a new paid evaluation |
