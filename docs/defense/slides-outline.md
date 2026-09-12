# Slide deck outline (ST-43)

Status: DRAFT, 2026-09-12. Arc owned by MB, technical figures by YL.
Exit gate: covers problem, demo and limits; a 15-minute dry run fits.
Budget: 15 minutes = about 7 minutes of slides around a 7-minute demo,
plus 1 minute of slack. One idea per slide; the numbers are the story.

| # | Title | One message | Visual | Owner | Time |
|---|---|---|---|---|---|
| 1 | Sanad | Answers from your documents, with sources, or an honest "not in the documents" | Product name, one screenshot of an answer with source cards | MB | 0:20 |
| 2 | The problem | Rules live in long documents; chat assistants answer without sources and invent when unsure | One unsourced chatbot answer beside a Sanad answer | MB | 0:40 |
| 3 | Who it is for | One person, one machine, one folder of documents; no accounts by design | Persona line plus the PRD non-goals | MB | 0:30 |
| 4 | Three promises | Sources on every answer, honest refusals, a release gate | Three icons mapped to G3, G2, G1 | MB | 0:30 |
| 5 | How one question flows | Plan, hybrid search, grade, read full sections, answer or refuse | The agent graph (reuse the architecture diagram) | YL | 1:00 |
| 6 | Why these choices | Parent/child chunks, E5 plus BM25, per-workspace indexes, local-first storage | Four boxes, one reason each | YL | 0:50 |
| 7 | **Live demo** | Follow `demo-script.md` steps 1 to 10 | Switch to the browser | YL | 7:00 |
| 8 | How we measured | 60 frozen French questions: 40 answerable, 20 not; frozen before tuning | The golden-set split as a bar | MB | 0:40 |
| 9 | Results | G1 37/40 (target 36), G2 20/20, G3 37/37: release gate PASS | Three gauges with target lines | MB | 0:40 |
| 10 | Speed | Answers: median 8.3 s (target 20 s). Intake: 731.6 s per 200 pages, **misses the 600 s target** | Two bars with target lines; the miss in plain view | YL | 0:40 |
| 11 | Engineering | About 790 automated tests, protected main, every branch reviewed, crash recovery, signed API | Test count, pipeline sketch | YL | 0:30 |
| 12 | Limits, said first | Cloud model needed today; slow intake; no OCR; screen-reader pass pending; judge shares the model family | Plain list | MB | 0:40 |
| 13 | Next | Faster intake, offline mode rehearsed, PowerPoint intake, answer-trace screen | Roadmap V1.0, V1.1, V2.0 | YL | 0:20 |
| 14 | Thank you / questions | One sentence summary | Screenshot of the refusal | both | 0:10 |

Rules for the figures:

- Every number on a slide must match `docs/defense/demo-script.md`'s
  "Numbers used above" table and the frozen evaluation report. If code or
  data changes before the defense, re-run and update both, never one.
- Show the G5 miss on the same slide as the G4 pass. Hiding it invites the
  question; showing it first earns trust.
- Reuse diagrams from `docs/phase2/` (the signed architecture); do not
  redraw what is already signed.
