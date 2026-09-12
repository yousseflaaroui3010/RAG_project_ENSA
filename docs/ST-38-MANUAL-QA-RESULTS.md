# ST-38 Manual QA Results

Executed from the ST-20 checklist at commit `005a401`. A blank result is never
treated as a pass.

## Run Record

| Field | Value |
|---|---|
| Date and time | 2026-09-11 |
| Tester | OpenCode automated checks and real Chrome CDP; human hearing pass pending |
| Commit | `57187cf` (ST-39 fixes), `e9c18a3` (ST-51 API), `6da8003` (ST-05 container), stacked on `b4a11d3` |
| Branch | `fix/S3-ST-39-evaluation-failures` |
| Machine and operating system | Windows NT 10.0.19045.0 |
| Browser and version | Headless Chrome 153.0.8010.36 |
| Model mode and model | cloud / gemini-3.6-flash |
| Workspace and corpus version | evaluation workspace `14b81a1d-...`; frozen 40/20 set |
| Screen reader and version | Blocked: no actual screen-reader hearing pass recorded |

## Evidence

| ID | Evidence |
|---|---|
| FULL | `uv run pytest`: 781 passed, 2 skipped; `uv run ruff check .` passed on 2026-09-11 after API, recovery, packaging, and startup fixes |
| S1 | `tests/integration/test_s1_chat_screen.py`, `tests/unit/test_ui_conversation.py` |
| S2 | `tests/integration/test_s2_workspaces_screen.py`, `tests/unit/test_sync.py`, `tests/unit/test_ui_workspaces_screen.py` |
| S3 | `tests/integration/test_s3_reports_screen.py`, `tests/unit/test_evaluation_runner.py` |
| A11Y | `tests/unit/test_ui_contrast.py`; Chrome accessibility trees found zero unnamed interactive controls |
| B-SHELL | `docs/evidence/ST-38/st38-final-evidence/chat-ltr-final/` |
| B-SOURCE | `docs/evidence/ST-38/st38-final-evidence/source-keyboard.json` |
| B-S3 | `docs/evidence/ST-38/st38-s3-evidence/live-poll.json` |
| B-RTL | `docs/evidence/ST-38/st38-evidence/` and `docs/evidence/ST-38/st38-final-evidence/` |
| EVAL | `data/reports/14b81a1d-.../2026-09-10T21-11-27.750175+00-00.json`: G1 37/40, G2 20/20, G3 37/37 |

## Shared Shell

| ID | Result | Dated evidence or defect |
|---|---|---|
| SH-01 | Pass | 2026-09-11, B-SHELL and S1: name, selector, navigation, and theme control present |
| SH-02 | Pass | 2026-09-11, S1/S2: S2 landing, disabled `No workspace yet` selector, Chat reason |
| SH-03 | Pass | 2026-09-11, B-SHELL: Skip, Sanad Home link, selector, visual-order navigation, theme, content |
| SH-04 | Pass | 2026-09-11, S1: workspace stays visible and the moved-context notice renders |

## S1 Chat States

| ID | Result | Dated evidence or defect |
|---|---|---|
| S1-EMPTY-01 | Pass | 2026-09-11, S1 and B-SHELL: three samples and sources promise |
| S1-EMPTY-02 | Pass | 2026-09-11, S1: disabled input, visible reason, S2 link |
| S1-LOAD-01 | Blocked | Visual stages, disabled reason, and Cancel pass in S1; actual announcement hearing is part of A-03 |
| S1-ERROR-01 | Pass | 2026-09-11, S1: named error, retry, no final-looking partial answer |
| S1-NORMAL-01 | Pass | 2026-09-11, S1: user, answer, refusal, and one-question clarification variants |
| S1-NORMAL-02 | Pass | 2026-09-11, B-SOURCE: Enter opens, marked span present, focus trapped, Escape returns focus |
| S1-NORMAL-03 | Pass | 2026-09-11, S1: legal disclaimer position and non-legal absence |

## S2 Workspaces And Sync States

| ID | Result | Dated evidence or defect |
|---|---|---|
| S2-EMPTY-01 | Pass | 2026-09-11, S2: guided name, folder, and legal-flag creation |
| S2-LOAD-01 | Pass | 2026-09-11, S2: real count, usable list, Cancel-after-current-file; remaining files get visible Skipped rows |
| S2-ERROR-01 | Pass | 2026-09-11, S2: exact missing path, fix hint, no partial ingestion |
| S2-NORMAL-01 | Pass | 2026-09-11, S2: all six outcomes, five columns, required reasons |
| S2-NORMAL-02 | Blocked | Keyboard links and `aria-sort` pass; actual sort-state announcement hearing is part of A-03 |
| S2-NORMAL-03 | Pass | 2026-09-11, S2 and prior Chrome evidence: warning text, native modal trap, Escape return |

## S3 Reports States

| ID | Result | Dated evidence or defect |
|---|---|---|
| S3-EMPTY-01 | Pass | 2026-09-11, S3: evaluation command shown |
| S3-LOAD-01 | Blocked | Real Running counter and live updates pass in B-S3; periodic announcement hearing is part of A-03 |
| S3-ERROR-01 | Pass | 2026-09-11, B-S3: question 2 named; question 1 kept; Partial in list/detail |
| S3-NORMAL-01 | Pass | 2026-09-11, S3 and EVAL: date, workspace, three gates, thresholds, rows, text outcomes |
| S3-NORMAL-02 | Pass | 2026-09-11, S3: Markdown named before download; complete and Partial exports retain status |
| S3-NORMAL-03 | Blocked | Semantic table and text labels pass; cell-by-cell screen-reader keyboard navigation is part of A-03 |

## Twelve Failure Cases

| ID | Result | Dated evidence or defect |
|---|---|---|
| F-01 | Pass | 2026-09-11, S2: unsupported type is Skipped with reason |
| F-02 | Pass | 2026-09-11, `test_password_protected_file_is_failed_and_never_blocks_the_batch` |
| F-03 | Pass | 2026-09-11, `test_scanned_pdf_reports_skipped_with_a_reason`: no text layer |
| F-04 | Pass | 2026-09-11, S1 empty-workspace test |
| F-05 | Pass | 2026-09-11, S2 missing-folder test |
| F-06 | Pass | 2026-09-11, EVAL G2 20/20 and sourced-answer refusal integration test |
| F-07 | Pass | 2026-09-11, retry ceiling and focusable retry-marker tests |
| F-08 | Pass | 2026-09-11, S1 unreachable-service test; no fallback answer |
| F-09 | Descoped for V1 | 2026-09-11 ruling: V1 does not stream text; interruption keeps an explicit incomplete result, and retained partial text waits for streaming |
| F-10 | Pass | 2026-09-11, S2 soft-cap checks: measured 51-file and 1,501-page warnings name what to split |
| F-11 | Pass | 2026-09-11, S2 double-Sync test: second blocked, first row remains running |
| F-12 | Pass | 2026-09-11, S1 clarification test: exactly one question, then normal answer flow |

## Accessibility And Layout

| ID | Result | Dated evidence or defect |
|---|---|---|
| A-01 | Pass | 2026-09-11, A11Y: every signed text role clears 4.5:1 in both themes |
| A-02 | Blocked | Visible 3:1 focus and sampled keyboard paths pass; a complete both-theme walk awaits the human A-03 pass |
| A-03 | Blocked | Live-region markup and changing text are proven; no actual screen-reader hearing pass has run |
| A-04 | Pass | 2026-09-11, B-SHELL/B-RTL/B-S3: zero unnamed controls; headings and landmarks recorded |
| A-05 | Pass | 2026-09-11, reduced-motion Chrome run reports zero animated elements; stage text remains |
| A-06 | Pass | 2026-09-11, B-RTL: S1-S3 mirror; scroll width equals viewport; mono values stay LTR |
| A-07 | Pass | 2026-09-11, 900px Chrome evidence: interface remains visible and source layout stacks |

## Defects And Rulings

| ID | Severity | Status | Finding |
|---|---|---|---|
| D-ST38-01 | Sev2 | Closed 2026-09-11 | Reports list showed missing/misleading G1 and G3 values; corrected and tested |
| D-ST38-02 | Sev2 | Closed 2026-09-11 | Delete confirmation was not a modal focus trap; native dialog proven in Chrome |
| D-ST38-03 | Sev2 | Closed 2026-09-11 | Sync had no cancel path; now stops after the current file and records remaining files |
| D-ST38-04 | Sev2 | Closed 2026-09-11 | Workspace soft-cap warning was absent; signed 50-file/1,500-page limits now measured |
| D-ST38-05 | Sev2 | Closed by V1 ruling 2026-09-11 | Retained partial text waits for streaming; V1 keeps an explicit incomplete result and never presents it as final |
| D-ST38-06 | Sev2 | Closed 2026-09-11 | Reduced motion used 1ms motion instead of none; Chrome now measures zero animated elements |
| D-ST38-07 | Sev2 | Closed 2026-09-11 | Static product name was absent from signed keyboard order; it is now a normal Home link |

## Sign-Off

| Field | Value |
|---|---|
| Passed rows | 35 |
| Failed rows | 0 |
| Blocked rows | 6 |
| Sev1 defects | 0 |
| Sev2 defects | 0 open, 7 closed |
| Sev3 defects | 0 |
| Tester signature and date | Not signed: human screen-reader evidence pending |
| Release decision | BLOCKED |

ST-38 is not complete. One human hearing pass remains.
