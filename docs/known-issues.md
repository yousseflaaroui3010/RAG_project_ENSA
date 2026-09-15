# Known issues (V3.0.0)

Everything below is known, reproduced or reasoned from the code, and
deliberately not fixed before the defense. Each line says what happens, why
it waits, and what would fix it. Severity is for a live demo: none of these
breaks a signed gate (G1-G3 pass on the golden set).

## Answer quality

| Issue | Effect | Why it waits | Fix (V1.1) |
|---|---|---|---|
| The relevance grader reads ~500-character child chunks | A fact sitting just past the chunk the grader sees is refused (g-in-033, Article 66's one-month delay) | Grading on full sections changes every question and puts G2's strict 20/20 at risk days before the jury | Grade on the parent section, or the chunk plus its neighbour; keep rewording inside the documents' own legal vocabulary; re-run all 60 |
| The rewording step can import French-France terms (`CSE`) | Later search rounds look for concepts the Moroccan code does not use | Same prompt freeze as above | Add "use the documents' own terms" to prompts/query-reword with a new version and eval seeds |
| G1 passes with little margin | One unlucky run can move G1 by a row, and it does: v3.0.0's second miss is `g-in-014`, where v2.0.0's was `g-in-026` -- both classified **model variation**, not a defect (docs/evals/v1.0.1-g1-triage.md) | Three of the four v1.0.0 misses were model variation | The grader fix above |

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
| No tab icon: every page logs a 404 for `/favicon.ico` in the browser console | Cosmetic, but visible to anyone who opens developer tools during a demo |
| Below 768 px the desktop-only notice is not a main landmark | The signed layout hides the app below 768 px and shows a notice; a phone screen-reader user has no main landmark to jump to (Lighthouse landmark-one-main, both languages, docs/evidence/ST-38/lighthouse-2026-09-15.md). Desktop screens score 100 |
| The six ST-38 screen-reader rows | Open until the human Narrator pass |


## V3 features (S6: streaming, documents, login, dashboard)

| Issue | Effect | Why it waits |
|---|---|---|
| A streamed answer is held back for its first 40 characters | The bubble stays empty a beat longer than the model's first word | It is the price of never showing `NOT_COVERED` typing itself out before an honest refusal (DECISIONS 2026-09-13) |
| A stream that breaks AFTER it has started is not retried | Opening a streamed answer -- connecting, and waiting for the first reply -- IS retried by the Gemini client exactly like a normal call (google-genai sends a streamed request through the same retry wrapper, checked 2026-09-15). Only a break once text is flowing ends the answer with the named "unreachable" error and a Retry. In strict-local (Ollama) mode nothing is retried, streamed or not | A fallback to a non-streamed call was built, tested and DROPPED on 2026-09-15 after review: it repeated retries the client already makes, roughly doubled the wait before an outage is reported (about 3 minutes to about 6 on Gemini), and would start a paid call after a Cancel -- all to cover the first second or so of an answer (DECISIONS 2026-09-15) |
| The dev server crashed twice, cause unknown | On 2026-09-15 the local server died (Windows access violation, exit 139) twice, both times inside an ordinary outbound call to Keycloak (`ui/oidc.py` `_read`, opening a socket), both while a full test suite ran on the same machine with about 2 GB of 15.8 GB memory free. The whole process stops and must be restarted | Not reproduced in four later attempts, including one under the same load with 40 sign-in calls. Ruled out by isolated runs: every warm-up load (both encoders, the document readers, all together) followed by the same call, six combinations, all clean. With no reproduction there is nothing to fix yet. If it happens again, start the server with `uv run python -X faulthandler app.py` and keep the log: it names the thread and line |
| A Sync started in the first ~37 s after start-up still waits for the document readers | The server warms the search models first (~23 s), then the PDF, Word and PowerPoint readers (~14 s). A Sync started before that finishes loads them itself or waits behind the warm-up, with nothing on screen to say why | Models first is deliberate: a question is the commoner first act. Stated in `sync.warm_up_document_readers` |
| Sign-out shows Keycloak's own "Do you want to log out?" page | One extra click when signing out | Skipping it means keeping the id token, which is keeping a credential for cosmetics |
| The realm must list the post-logout URI | Otherwise Keycloak answers 400 on sign-out | It is one line in the client configuration; the README says so |
| `/api/v1` is administrators-only when `AUTH_MODE=keycloak` | A curator or reader cannot use the machine API | The signed contract has no notion of who is asking; per-route permissions are a separate change (DECISIONS 2026-09-14) |
| Chat history lives in memory, per person | Signing out or restarting loses the transcript | Persisting it is personal data under law 09-08 and needs a named owner first |
| A committed evaluation report stores every answer verbatim | Harmless today -- the corpus is published Moroccan law -- but the same command pointed at a private workspace would put that workspace's document text into git | Nobody has done it; the fix is a rule, not code. Do not commit a report from a workspace whose documents are not public. Raised by the cold review of the v3.0.0 release branch |
| Roles are read at sign-in | A role changed in Keycloak applies at the person's next sign-in | Re-reading on every request would put a network call in front of every page |
| Uploads are refused in evidence-only mode | The published demo cannot receive documents | That instance has no room for the embedding model, so an uploaded file could never be indexed anyway |
| The drop zone needs JavaScript | With scripting off there is no upload control at all | The file is sent as a raw request body; the alternative is a multipart parser this project does not carry |

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
