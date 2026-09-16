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
| The six ST-38 screen-reader rows | Open until the human Narrator pass |


## V3 features (S6: streaming, documents, login, dashboard)

| Issue | Effect | Why it waits |
|---|---|---|
| A streamed answer is held back for its first 40 characters | The bubble stays empty a beat longer than the model's first word | It is the price of never showing `NOT_COVERED` typing itself out before an honest refusal (DECISIONS 2026-09-13) |
| A stream that fails after the server starts replying is not retried | Opening a streamed answer IS retried by the Gemini client like a normal call, up to the moment the server starts its reply (the response headers): google-genai sends the streamed request through the same retry wrapper, with Sanad's `model_call_max_retries` (checked 2026-09-15 in google-genai 2.12.1 and langchain-google-genai 4.2.7). Anything after that is not retried: the model's thinking time before its first words, an error sent inside the stream, or a dropped connection. A timeout or failed connection shows the named "unreachable" sentence and a Retry; any other failure there (a reset connection, an in-stream API error) shows the generic error panel with the error's name, also with a Retry. In strict-local (Ollama) mode nothing is retried, streamed or not | A fallback to one non-streamed call was built, tested and DROPPED on 2026-09-15 after review: it repeated retries the client already makes, roughly doubled the wait before an outage is reported (about 3 minutes to about 6 on Gemini), and would start a paid call after a Cancel, to cover only the gap between the server replying and the first 40 characters of text (DECISIONS 2026-09-15) |
| The dev server crashed twice, cause unknown | On 2026-09-15 the local server died twice with a Windows access violation: exit 139 in Git Bash, which PowerShell and cmd show as -1073741819 (0xC0000005). The second crash was captured with `-X faulthandler`: the crashing thread was in an ordinary outbound call to Keycloak (`ui/oidc.py` `_read`, urllib, opening a socket). Both happened while a full test suite ran on the same machine with about 2 GB of 15.8 GB memory free. The whole process stops and must be restarted | Tried four times and did not reproduce, including once under the same load with 40 sign-in calls, and six isolated runs of every warm-up load followed by the same call, all clean. Clean runs rule nothing out when the original never reproduced, so the cause is open. If it happens again, start the server from Git Bash as `uv run python -X faulthandler app.py 2> sanad-crash.log` so the report is saved (faulthandler writes to the error stream; in PowerShell 5.1 a `2>` redirect writes UTF-16, which other tools misread) |
| From #129: a Sync started in the first ~37 s after start-up still waits for the document readers | #129 warms the search models first (~23 s), then the PDF, Word and PowerPoint readers (~14 s). A Sync started before that finishes loads them itself or waits behind the warm-up, with nothing on screen to say why. Before #129 is merged, EVERY first Sync after start-up pays the readers' ~14 s | Models first is deliberate: a question is the commoner first act. Stated in `sync.warm_up_document_readers` (added by #129) |
| Sign-out shows Keycloak's own "Do you want to log out?" page | One extra click when signing out | Skipping it means keeping the id token, which is keeping a credential for cosmetics |
| The realm must list the post-logout URI | Otherwise Keycloak answers 400 on sign-out | The committed realm (`keycloak/realm-sanad.json`) lists it for 127.0.0.1, localhost and `KEYCLOAK_PUBLIC_APP_URL`; a hand-made realm still has to |
| Anyone on the internet can create an account on the published demo (live since 2026-09-16) | Accounts pile up in Keycloak; each new person is a reader who sees no workspace until an administrator grants one | Sign-up was asked for (YL, 2026-09-15). There is no CAPTCHA and no email check: both need an outside service (reCAPTCHA keys, a mail server), and sending mail is a stop-and-ask action. Brute-force protection and a 10-character password rule are on; an account can be disabled in Keycloak's console |
| Deleting or disabling a person in Keycloak does not sign them out of Sanad | Their session keeps working until it expires (`SESSION_TTL_HOURS`, 12 by default). Seen on the live demo: an account deleted in Keycloak was still signed in, still named in the header | Sanad holds its own session and reads roles at sign-in; re-checking with Keycloak on every request would put a network call in front of every page. The cure is in the product: Administration, "Déconnecter partout" on that person, which deletes their sessions and their saved chat |
| A person must sign in once before an administrator can grant them a workspace | The Administration page lists only accounts Sanad has seen. A brand-new Keycloak account is invisible there until its first sign-in | Sanad learns a person from the claims their sign-in carries; inventing a row from Keycloak's list would mean a second source of truth about who exists |
| Recreating the realm while keeping Sanad's data lists a person twice | Keycloak gives the same username a new internal id, and Sanad keys people by that id, so the Administration page shows the old row and the new one (seen locally, 2026-09-15) | Only happens when Keycloak's database is wiped but Sanad's is not; a new deployment starts both empty |
| The published demo signs in with four demo people whose passwords the team holds | Anyone given a demo login can use the public site with that role until the password is changed in Keycloak | They exist so the jury can see each role; the admin one has its own password (`KEYCLOAK_ADMIN_SEED_PASSWORD`), and a person can be disabled in Keycloak's console in one click |
| The demo's Keycloak is not linked to GitHub and has a redeploy trap | Changing a variable on the Railway `keycloak` service without `--skip-deploys` redeploys the plain published image, which only prints help and stops; a merge to `main` never updates it | It was uploaded with `railway up` from `deploy/keycloak/`; linking a second service to the repo needs the Railway dashboard. Upload again after any change (see the top of `deploy/keycloak/Dockerfile`) |
| The demo's Keycloak runs at the edge of the trial plan's memory | Defaults got it killed; a 128m code-memory cap crashed on a real sign-in. It now starts with a 256m heap | Values are in `deploy/keycloak/Dockerfile`; a bigger plan removes the edge |
| `/api/v1` is administrators-only when `AUTH_MODE=keycloak` | A curator or reader cannot use the machine API | The signed contract has no notion of who is asking; per-route permissions are a separate change (DECISIONS 2026-09-14) |
| A pending clarifying question does not survive a restart (S6 saved chat history) | Chat history now IS persisted per person, per workspace, across a restart (law 09-08, owner YL, DECISIONS 2026-09-15) -- `messages`, `summary`, `turns` and `session_id`, kept `chat_history_retention_days` days (default 30; 0 = nothing survives a restart at all, checked on load and swept at start-up). What is not carried over is in-flight state: `run` and any pending clarifying question, so a restart mid-clarification starts the next message as a fresh question rather than resuming it | Out of this feature's scope, which persists the settled transcript, not in-flight state |
| In `none` or `password` mode, every visitor is the single "local" person (S6 saved chat history) | There is no login in those two modes, so `Runtime.conversation` keys every transcript to the literal user id `"local"` -- anyone behind the shared password reads and can delete the SAME saved history, for every workspace, for the whole retention window. This is unchanged from every other per-person control in those modes (grants, the activity log) but is now also true of a DISK-PERSISTED transcript rather than only an in-memory one | `AUTH_MODE=keycloak` is the only mode with real per-person identity; the published demo (`password` mode) accepts this the same way it already accepts one shared set of workspaces |
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
