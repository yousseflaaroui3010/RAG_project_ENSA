---
description: Write a decision row for something we just decided
---

Look at what we just decided in this conversation.

## Where it goes, and where it does not

This repo already has one home for decisions: the table in
`docs/journal/DECISIONS.md`. That file was authored and is reviewed. **Do not
create a `docs/decisions/` folder** — a second home for the same artifact is
drift by construction, and it is the exact failure the "who owns this artifact"
rule exists to prevent.

First, check where it belongs:

- If it changes or contradicts an existing row in `docs/journal/DECISIONS.md`,
  **stop.** Say which row, say what would have to change, and let the human
  rule on it. Do not write a row that quietly overrides one.
- If it contradicts anything in `docs/phase2/`, **stop and escalate.** The pack
  is signed and write-locked. The pack being wrong is a real possibility — it is
  at v1.2 and predates every architecture decision — but reconciling it is task
  T-007's job, not this command's.
- If it is a cross-project standard rather than a project decision, say so: it
  belongs in `~/.claude/rules/`, and the human decides.

## Then

1. Read `docs/journal/DECISIONS.md` and find the highest id. Yours is the next one.
2. Check no existing row already covers this. If one does, show it to me and
   ask whether this supersedes it.
3. Draft the row in the shape the table already uses. Keep it to the existing
   columns; do not invent new ones. The row must carry:

   - **What we chose.** One sentence, active voice. "We use X."
   - **Why.** What forced the decision.
   - **What it costs.** Required. A decision with no cost listed was not a
     decision, it was a preference.
   - **What else we considered**, and why not. One line each.
   - **Verified on**, with the date, for anything about a version, a security
     floor, an API shape, a quota or a price. If it was not checked live this
     session, label it unverified and name the task that will exercise it.

4. If the decision touches money, authentication, personal data, retention, or
   anything a regulator would care about, name the STRIDE or LINDDUN category
   in the row and say which task owns the missing control. An unowned risk
   becomes a false sense of coverage.
5. If you cannot name a cost, you have not understood the decision. Go back and
   think again before writing.
6. Show me the row and ask whether it is right **before** saving.
7. After saving, append one line to `docs/journal/CHANGELOG-AI.md` in the
   existing `YYYY-MM-DD | T-xxx | file(s) | what changed | why` format.

A row is immutable once written. If it later turns out wrong, add a new row and
mark the old one superseded. Never rewrite the reasoning of an accepted row — it
was true once, and that is the thing worth keeping.

Under 200 words in the row itself. Plain English. Someone reading it in a year
should understand it without asking me anything.
