# Rehearsal log (ST-45, PRD G6)

G6: **at least 9 of 10 consecutive scripted rehearsals complete without
failure**, plus one recorded fallback run stored OFF the demo machine
(PRD open risk R4: single demo machine).

Rules for filling this in:

- One row per full run of `demo-script.md`, all ten steps, start to end.
- "Clean" means every step showed what the script says, with no restart and
  no switch to the video. A step that needed its "If it fails" action is
  NOT clean; write which step and why.
- Count consecutive runs. A failure resets nothing, but the ten counted
  runs must be ten in a row.
- Note the commit the app was running (`git log --oneline -1`), so a
  failure can be tied to code.

| # | Date and time | Who ran it | Commit | Mode (cloud/offline) | Clean? | Failed step and cause | Total time |
|---|---|---|---|---|---|---|---|
| 1 | | | | | | | |
| 2 | | | | | | | |
| 3 | | | | | | | |
| 4 | | | | | | | |
| 5 | | | | | | | |
| 6 | | | | | | | |
| 7 | | | | | | | |
| 8 | | | | | | | |
| 9 | | | | | | | |
| 10 | | | | | | | |

**Result:** __ clean out of 10. G6 met: yes / no.

## Recorded fallback run

| Field | Value |
|---|---|
| Recorded on (date) | |
| Commit | |
| Length | |
| Stored where (NOT the demo laptop) | |
| Checked it plays on another machine | yes / no |
