# BUILD-PLAN (Sanad, Phase 3)

Derived from the signed pack: PRD v1.0 (features F-01..F-16), Architecture
v1.1 (ADR-01..ADR-13, module map §4, flows §5, data §7, stack §8, QA §14),
Project Plan v1.1 (stories ST-01..ST-52, checkpoints C1-C3, descope ladder).
This plan does not invent stories; it re-expresses the 52 signed stories as a
build queue with **Phase-2 refs, dependencies, and exit gate** per row.

Authority order: PRD > Architecture > Project Plan > openapi.yaml. A story that
seems to need breaking an ADR is an escalation, not a workaround.

## Ordering law (kickoff)
Contracts and the data layer land before the UI that consumes them. Concretely:
db (ST-10) and the service functions precede screens (ST-27/28); the API
contract already exists frozen at `docs/phase2/openapi.yaml` and is implemented
by ST-51, with its working copy seeded to `docs/api/openapi.yaml` (drift test
target). Data layer = Sprint 1; agent + UI = Sprint 2; eval + hardening =
Sprint 3; defense = Sprint 4.

## Legend
- **Own:** YL (build), MB (research/quality), BOTH, HUMAN (click-only, cannot be automated).
- **Refs:** PRD feature (F-xx) / Architecture (ADR-xx, §x) / contract (openapi.yaml).
- **Exit gate:** the story's acceptance criteria from the plan = the S4 gate. Must be green to close.
- One story = one branch `feat/S<sprint>-ST-<nn>-<slug>` (also fix/docs/chore), cut from latest main.

## Epic index (plan §3.1)
| Epic | Name | Owner | Sprint | Release |
|---|---|---|---|---|
| E1 | Foundation and study | YL (+MB onboarding) | 0 | Sprint-0 baseline |
| E2 | Ingestion and indexing | YL | 1 | V1.0 |
| E3 | Agent and chat | YL | 2 | V1.0 |
| E4 | Workspaces screen | YL | 2 | V1.0 |
| E5 | Evaluation and reports | YL (build), MB (golden) | 3 | V1.0 |
| E6 | Hardening and measurements | MB (QA), YL (fixes) | 3 | V1.0 |
| E7 | Defense package | MB (materials), YL (demo) | 4 | Defense |
| E8 | Comfort stretch F-10..F-12 | YL | 4 (conditional) | V1.1 |

---

## Sprint 0 — E1 Foundation and study (Jul 20-22)
| ID | Title | Own | Phase-2 refs | Depends on | Exit gate |
|---|---|---|---|---|---|
| ST-01 | Create private repo `sanad`, add MB, both clone | YL/HUMAN | ADR-11; plan §4 | — | Both machines push a test commit to a branch; MB's push succeeds (origin already re-pointed per BUILD-STATE) |
| ST-02 | Skeleton: `pyproject.toml`, uv lock, `config.py`, `.env.example` | YL | ADR-10; §8 stack; §11 layout | ST-01 | `uv sync` green both machines; every config var documented in `.env.example` |
| ST-03 | CI skeleton `ci.yml`: ruff + pytest per PR | YL | ADR-12; §12.3 | ST-02 | A deliberately failing test blocks a PR; fixing it unblocks |
| ST-04 | Branch protection on `main` + PR template | HUMAN | ADR-11; §12.2 | ST-01 | Direct push to main rejected; template shows the 5-point checklist |
| ST-05 | Dockerfile + compose with `data/` volume | YL | ADR-10; §12.1 | ST-02 | `docker compose up` serves a UI stub in the browser |
| ST-06 | Study day: LangGraph tutorial + reference walkthrough | BOTH | ADR-03; bib [1][2] | — | Two journal entries; MB explains sync + agent loop, YL explains parent/child trade-off |
| ST-07 | Corpus v1: labor code PDF + 2 HR/CNSS guides + manuals ws2 | MB | PRD §17; LD-02 | — | Files open, French text selectable (not scanned), source+date logged per file |
| ST-08 | Project board, all stories imported, WIP limits | MB/HUMAN | plan §1 | ST-01 | Every story visible with owner + priority |
| ST-09 | Journal + rehearsal-log templates in `docs/` | MB | §11; §13.2 | ST-01 | `journal.md` + `rehearsal_log.md` exist with headers, first entry written |

Sprint-0 baseline exit: all Highest sprint-0 stories Done (target 2026-07-22).

## Sprint 1 — E2 Ingestion and indexing (Jul 23-29). YL build; MB eval prep.
| ID | Title | Own | Phase-2 refs | Depends on | Exit gate |
|---|---|---|---|---|---|
| ST-10 | SQLite schema + data access, `PRAGMA foreign_keys`, cascade | YL | ADR-08; §7.3/7.4; F-01/F-02/F-08 | ST-02 | Unit tests: cascade delete, all six statuses, unique file-per-workspace |
| ST-11 | Workspaces create/rename/delete + legal flag (module) | YL | F-01; §7.1 | ST-10 | F-01 criteria pass at module level, incl. derived-data-only delete |
| ST-12 | Content hashing + change-detection state machine | YL | F-02; §5.1 | ST-10 | new/changed/unchanged/removed unit-tested, incl. size+hash collision guard |
| ST-13 | Conversion ladder PDF/DOCX/TXT/MD; Skipped/Failed reasons | YL | ADR-07; F-02; F-16 skip; LD-03 | ST-02 | Fixture corpus converts; corrupted→Failed; scanned PDF→Skipped with reason |
| ST-14 | Parent/child chunking per §7.5 | YL | §7.5; supports F-03 | ST-13 | Boundary tests at 2,000 and 4,000 chars; 100-char overlap verified |
| ST-15 | Embeddings module + mandatory `passage:`/`query:` prefixes + prefix test | YL | ADR-05; §14; bib [4][5] | ST-14 | Test fails if any embedded text lacks its prefix; model downloads once + caches |
| ST-16 | Vector store (per-workspace collections) + parent JSON store | YL | ADR-04; §7.5; F-01 | ST-14, ST-15 | Isolation test: HR query never returns manuals chunks; parents resolve by id |
| ST-17 | Sync engine end to end + per-file report rows | YL | F-02; §5.1 | ST-12, ST-13, ST-16 | F-02 criteria pass on fixtures; six statuses correct; double-sync blocked |
| ST-18 | SPIKE: index labor corpus, measure G4/G5 + 20-q latency, OR-1 verdict | YL | §9; OR-1; G4/G5 | ST-17, ST-07 | Numbers in journal vs G4/G5; verdict: on-track / tune / change-request |
| ST-19 | Golden set batch 1: 15 in-scope + 8 out-of-scope (FR) | MB | F-08; §13.1 | ST-07 | Files in `evaluation/golden/`, schema respected, PR reviewed by YL |
| ST-20 | Manual QA checklist from failure table + screen states | MB | PRD §8, §11 | — | One checklist covering all 12 failure rows + all S1-S3 states |

**Checkpoint C1 (Jul 29):** spike verdict acceptable and velocity >=80%? If no, apply descope ladder step 1 and re-plan Sprint 2.

## Sprint 2 — E3 Agent + E4 Workspaces screen + CR-01 API (Jul 30-Aug 5)
| ID | Title | Own | Phase-2 refs | Depends on | Exit gate |
|---|---|---|---|---|---|
| ST-21 | Agent graph skeleton + trace collector wired | YL | ADR-03/09; §5.2 | ST-16 | Graph runs end-to-end on a stub; every answer object carries its trace |
| ST-22 | Rewrite-and-split node + clarification path (F-06) | YL | F-06; §5.2 | ST-21 | Ambiguous fixture triggers exactly one clarifying question; resumes after reply |
| ST-23 | Hybrid retrieval + relevance grader + reword retry ceiling (F-04) | YL | F-04; ADR-05; §5.2 | ST-21, ST-16 | Retry count never exceeds config; off-topic fixture triggers exactly one reword |
| ST-24 | Answer node w/ source contract + honest refusal (F-03, F-05) | YL | F-03/F-05; openapi Answer invariant | ST-23 | F-03/F-05 pass on fixtures; answer without sources cannot render as final |
| ST-25 | Session memory summary node (F-07) | YL | F-07; §5.2 | ST-21 | Follow-up reference resolves; new conversation starts clean |
| ST-26 | Legal disclaimer wiring (F-09) | YL | F-09 | ST-24, ST-11 | Flagged workspace shows the line on every answer; unflagged shows none |
| ST-27 | Chat screen S1: variants, source cards, passage viewer, states | YL | ADR-02; S1 §8 | ST-24 | Every S1 state (empty/loading/error) from PRD §8 demonstrated live |
| ST-28 | Workspaces screen S2: list, detail, sync progress, report, double-sync block | YL | ADR-02; S2 §8; F-02 | ST-17 | Every S2 state demonstrated; failed file never blocks the batch in UI |
| ST-51 | CR-01 thin API: FastAPI host, `/api/v1` delegate-only, Gradio at `/`, live `/docs` | YL | ADR-13; openapi.yaml; §12.3 | ST-24, ST-27, ST-28 | Every endpoint in openapi.yaml responds on 127.0.0.1; UI unchanged when mounted; `/docs` renders |
| ST-29 | Golden set batch 2: +15 in-scope, +7 out-of-scope | MB | F-08 | ST-19 | Totals 30 in / 15 out; same schema + review path |
| ST-30 | Demo script v0 (10 steps), used in MB behavioral reviews | MB | §12.2; §13.2 | ST-07 | Script committed; one PR review references a step |
| ST-31 | Report skeleton + chapters 1-2 (problem, PRD summary) | MB | PRD | — | Chapters drafted in `docs/`, sourced from signed PRD, assumptions tagged |

**Checkpoint C2 (Aug 5):** end-to-end sourced answer to a real labor-law question on YL's machine. If no, descope steps 1-2; V1.1 dies. CR-01 note: if C1 velocity is under plan, ST-51 slides to Sprint 3 first (ladder step 3).

## Sprint 3 — E5 Evaluation/reports + E6 Hardening (Aug 6-12). Ends with V1.0 gate.
| ID | Title | Own | Phase-2 refs | Depends on | Exit gate |
|---|---|---|---|---|---|
| ST-32 | Evaluation runner: RAGAS faithfulness + relevancy + refusal checker | YL | F-08; ADR-12; §13.1; bib [8] | ST-24 | One command → dated report with per-question + overall scores |
| ST-33 | Gate script (PRD thresholds) + `eval.yml` manual-dispatch, repo secret | YL | F-08; ADR-12; G1-G3 | ST-32 | Gate exits non-zero on any miss + lists failing questions; dispatch manual only |
| ST-34 | Reports screen S3: list, detail, pass/fail, export | YL | ADR-02; S3 §8 | ST-32 | Every S3 state demonstrated; export usable in report annex |
| ST-52 | CR-01 contract tests: drift check + happy/error paths (fake model) | YL | ADR-13; §13.1; openapi.yaml | ST-51 | CI fails on schema drift; 404/409/503 of ask + sync-job asserted |
| ST-35 | Golden set complete + frozen: 40 in + 20 out, v1 tag | MB | F-08; LD-04 | ST-29 | Counts verified; freeze notice in journal; later edits need a new version |
| ST-36 | First full evaluation run + one tuning iteration | BOTH | F-08; OR-1/OR-3 | ST-32, ST-35 | Report exists; every failing question triaged; second run recorded |
| ST-37 | G4 latency measurement + tuning against targets | YL | G4; §9 | ST-17, ST-24 | 20 timed questions on reference machine; numbers vs G4 in journal |
| ST-38 | Manual QA: 12 failure rows, all states, keyboard, contrast, RTL preview | MB | PRD §8/§11; §13.1; WCAG 2.2 AA | ST-27, ST-28, ST-34 | Checklist signed with dates; every defect filed with severity |
| ST-39 | Bugfix buffer (capacity for ST-36/ST-38 findings) | YL | §14 | ST-36, ST-38 | Sev1/sev2 closed or descoped by C3 with a written ruling |
| ST-40 | Report chapters 3-4 (architecture summary, method/scrum) | MB | Architecture; plan | — | Chapters drafted, sourced from signed architecture + plan |
| ST-41 | V1.0 release: gate green, tag `v1.0.0`, code freeze | YL | §12.2; PRD §12; G1-G3 | ST-33, ST-36, ST-39 | Gate exit 0 on frozen golden set; annotated tag pushed |

**Checkpoint C3 (Aug 12):** gate green + tag pushed, or ladder steps 3-4 with written change requests; narrative becomes "V1.0 minus documented cuts".

## Sprint 4 — E7 Defense package + E8 stretch (Aug 13-19)
| ID | Title | Own | Phase-2 refs | Depends on | Exit gate |
|---|---|---|---|---|---|
| ST-42 | Report ch 5-6: results, issue-journal digest, limits/future work | MB | PRD non-goals + risks | ST-41 | Numbers match frozen eval; every limit maps to a non-goal or open risk |
| ST-43 | Slide deck: arc (MB) + technical figures (YL), reused diagrams | BOTH | signed docs | ST-41 | Covers problem→demo→limits; 15-min dry-run fits |
| ST-44 | Demo script final + one full offline strict-local rehearsal | YL | ADR-06; R4; §13.2 | ST-41 | Script v1 committed; offline run completes with network disabled |
| ST-45 | Rehearsal protocol: 10 scripted runs logged, 1 recorded fallback | BOTH | G6; §13.2 | ST-44 | G6 met (9/10 clean); recording stored off the demo machine |
| ST-46 | Q&A drill: 30 jury questions with owned one-minute answers | BOTH | all | ST-43 | Each question owned + answered; one mock defense held |
| ST-47 | STRETCH F-10 answer trace view | YL | F-10; ADR-09; contract v1.1 | ST-41 + Aug-15 gate | F-10 criterion passes; only if every Highest Done by Aug 15 |
| ST-48 | STRETCH F-11 PPTX ingestion | YL | F-11; ADR-07 | ST-13 + Aug-15 gate | F-11 criterion passes; same start condition |
| ST-49 | STRETCH F-12 workspace routing proposal | YL | F-12 | ST-24 + Aug-15 gate | F-12 criterion passes; same start condition |
| ST-50 | User interviews (R1): 3 interviews, assumptions updated | MB | R1; PRD §16 | — | Anonymized notes in `docs/`; PRD tags updated in the report (not the signed PRD) |

## Critical path (V1.0)
ST-02 → ST-10 → {ST-12, ST-13→ST-14→ST-15→ST-16} → ST-17 → ST-21 → ST-23 →
ST-24 → {ST-27, ST-51} ; eval branch ST-32 → ST-33 → ST-36 → ST-41. MB's golden
stream (ST-19→ST-29→ST-35) runs parallel and gates ST-36. Never-cut set
(ladder step 6): F-03 sources, F-05 refusals, F-08 gate, F-09 disclaimer.

## Descope ladder (plan §9.2, pre-agreed order)
1. Drop stretch ST-47..ST-49. 2. Drop ST-50. 3. Shrink CR-01: ST-52 first,
then ST-51 to ask+sync only, then defer to V1.1 (each a recorded CR vs arch v1.1).
4. Golden set 30+15 (CR vs F-08). 5. Thin F-07/F-06 (CR vs PRD). 6. Never cut
F-03/F-05/F-08/F-09.

## First story in flight
ST-01 completion then **ST-02 (project skeleton)** is the first build story, blocked
only on the pending human steps in BUILD-STATE (merge chore/setup-config, push
main, install pre-commit, apply ruleset). Nothing downstream can start until a
`pyproject.toml`/`uv.lock` exists (ST-02).
