# Sanad demo script (ST-30 v0, draft for ST-44 v1)

Status: DRAFT, 2026-09-12. Written from the code and the measured numbers,
not yet rehearsed. ST-30 is MB's story and ST-44 is YL's: both owners
review, then rehearse it (see `rehearsal-log.md`) before calling it v1.

Target length: **7 minutes of demo** inside a 15-minute defense. Ten steps.
Each step lists what to do, what the jury should see, what to say in one
line, and what to do if it goes wrong.

## Before the jury walks in (T-20 minutes)

These are not optional. Each one removes a failure we have already seen.

1. Close every other heavy program. Speed numbers were measured on a quiet
   machine; a busy one is visibly slower.
2. Check the model key works: the evaluation ran on `gemini-3.6-flash`
   in cloud mode. Cloud mode needs internet. **Offline (strict-local)
   mode is not used at the defense**; see "Ruling" below.
3. Start the app from the repository folder:

   ```
   uv run python app.py
   ```

   Then open `http://127.0.0.1:8000` in the browser.
4. Confirm on the Workspaces screen that both workspaces show as synced:
   **HR** (legal flag on, 3 documents, 225 pages) and **Manuals**
   (10 documents). Indexing HR from scratch takes about 7 to 9 minutes on a
   quiet laptop (422-506 s measured; 823 s under load), so it must already
   be done.
5. The app now warms up its own search models on a background thread as
   soon as it starts, ready roughly 25 s later (logged as "model warm-up
   ready"); the 23 s cold first question this step used to guard against
   should no longer happen. **Ask one warm-up question anyway** in HR (any
   sample question), belt-and-braces, and confirm it answers in seconds
   before the jury sees the screen.
6. Click **New conversation** so the screen starts clean.
7. Have the recorded fallback video open in a second window (ST-45). If a
   step fails twice, switch to the video at that step and say so plainly.

## The ten steps

| # | Do | Jury sees | Say (one line) | If it fails |
|---|---|---|---|---|
| 1 | Open **Workspaces** | Two workspaces, HR marked Legal, per-file report | "Each workspace is a folder of documents; nothing leaves this machine except the question sent to the model." | Refresh once |
| 2 | Select HR, press **Sync** | Report: 3 unchanged, in about 0.1 s | "Only new or changed files are re-read, so a second Sync is instant." | Skip; say the number |
| 3 | Go to **Chat** (HR). Ask: *Quelle est la durée de la période d'essai pour un cadre en contrat à durée indéterminée ?* | Stage hints, then an answer from Article 14, source cards, legal disclaimer line | "Every answer names its sources, and legal workspaces always carry the disclaimer." | Ask it again; then use the video |
| 4 | Press **Tab** to a source card, press **Enter** | Passage viewer with the exact excerpt marked; **Esc** closes and focus returns | "You can check the exact passage, with the keyboard only." | Click with the mouse |
| 5 | Ask: *À quel âge et avec combien de jours de cotisation peut-on obtenir une pension de vieillesse de la CNSS ?* | Answer citing Article 53 of the social-security dahir | "Different document, same promise: sources on every answer." | Skip to step 6 |
| 6 | Ask: *Quelles sont les règles applicables au télétravail ?* | Honest refusal, the searches it tried, no sources | "The documents do not cover remote work, so Sanad says so instead of inventing." | If it answers, say it is a known risk and show the Reports numbers |
| 7 | Ask: *Quel est le délai ?* | One clarifying question (which deadline?) | "An ambiguous question gets exactly one clarifying question." | Model-driven: if it answers instead, move on; do not retry twice |
| 8 | Switch the workspace selector to **Manuals**. Ask: *Comment définir une classe en Python ?* | Answer from `tutorial-classes.txt` only | "Workspaces are isolated: HR documents can never answer here." | Skip |
| 9 | Open **Reports**, then the latest run | G1 37/40, G2 20/20, G3 37/37, pass/fail per question; **Export** Markdown | "This is the release gate: 60 frozen questions, and the version only ships if all three pass." | Show `docs/evals/` export instead |
| 10 | Open `http://127.0.0.1:8000/docs` | The 9-endpoint API contract | "The same engine is available to other programs through a signed contract." | Skip |

Optional, only if time remains: add `?dir=rtl` to the Chat address to show
the right-to-left layout preview, and press **Dark theme** in the header.

## Close (30 seconds): say the limits before the jury asks

- Document intake speed depends on the machine's load: **449.4 s and 375.3 s per
  200 pages in two quiet runs (target 600 s), 731.6 s while other work ran**.
  Both runs are reported; the laptop's timings vary widely.
- Answers need the cloud model today; offline mode is designed but not
  rehearsed.
- Scanned PDFs are skipped with a reason; there is no text recognition (OCR).
- A human screen-reader pass is still pending (6 manual QA rows).

## Ruling: the defense runs in cloud mode

Decided 2026-09-12 (DECISIONS row "ST-44 ruling"): ST-44's offline
rehearsal is descoped for this window. The defense runs on the cloud model,
so the pre-jury checklist's step 2 (internet and model key) is mandatory,
and "answers need the cloud model today" is said as a limit in the close.
If the venue's network is unreliable, bring a phone hotspot and test it
during setup.

## Numbers used above, and where they come from

| Claim | Number | Source |
|---|---|---|
| Release gate (v1.0.1, golden v2) | G1 37/40, G2 20/20, G3 37/37 | `docs/evals/release-v1.0.1-2026-09-12.json` (from `data/reports/14b81a1d-.../2026-09-12T14-12-46.567306+00-00.json`), re-read by `scripts/release_gate.py` |
| Answer speed (G4) | median 8.3 s, slowest 18.1 s, 20 questions; first question 23.2 s | `data/measurements/2026-09-11-spike-st18/traces.json` |
| Intake speed (G5) | quiet laptop: 449.4 s and 375.3 s per 200 pages in two runs (PASS); under load: 823 s = 731.6 s (FAIL); unchanged re-Sync 0.09 s | `data/measurements/2026-09-12-spike-st18/results.json` and `2026-09-11-spike-st18/results.json` |
| Corpus | HR: 3 files, 225 pages; Manuals: 10 files | same |

`data/` is git-ignored: these files exist only on YL's laptop. Copy them to
the slides' source folder before the defense.
