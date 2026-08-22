---
name: senior-review
description: The twenty row sheet for judging whether work is senior, plus the gates that fail regardless of the rows. Use when reviewing someone's work, when writing a job description, when deciding whether a piece of work is ready, and when judging your own output against the bar.
---

# The review sheet

## Read this first

A study on performance ratings (Scullen, Mount and Goff, 2000, about 4,500 managers each rated by several people) worked out where the variation in scores came from.

**The quirks of the person doing the rating accounted for 62 percent of the variation in one group and 53 percent in the other.** The actual performance of the person being rated accounted for roughly 21 to 25 percent.

Over half of what a rating measures is the rater. Their mood, their history, where they personally set "good".

(Figures are consistent across independent write ups and the paper's own summary. The full paper sits behind a journal wall.)

That does not mean give up. It means design around it, and every rule here exists because of it.

- **Prefer pass or fail over judgement.** "Did any log line contain personal data" has one answer. "Is their code quality good" has as many answers as raters.
- **Demand evidence before a score.** A score with no artefact attached is mostly a portrait of the person scoring.
- **Two raters, separately, then compare.** Where they disagree is the interesting part, and it is usually a definition, not a fact.
- **Never turn the total into a number for pay or ranking.** The measurement cannot carry that weight.

## What this is

A shared description of what senior work looks like, used to point at specific gaps with specific evidence. Not a score out of a hundred, not a ranking, not a pay formula.

## The twenty rows

Mark each **Not yet** (does the junior version), **Sometimes** (does it when reminded), or **Usually** (does it unprompted). Every mark needs evidence written beside it.

### Everyone

| # | Row | Evidence |
| --- | --- | --- |
| 1 | Answers the four blast radius questions in writing before building | The ticket, before the first commit |
| 2 | Ships changes that can be turned off without a release | A switch, in the code |
| 3 | Adds before removing on anything touching stored data | The change split into ordered steps |
| 4 | Every bug fix arrives with a test that fails without the fix | The commit pair |
| 5 | Keeps the journal most days, checks named, blockers with a person, a date and a fallback | The journal over a month |
| 6 | Logs as fields, one id per request, no secrets or personal data | Any recent log lines |
| 7 | Small commits that each work, messages that say why | The last twenty commits |
| 8 | Says no by naming the trade off, in writing | One real instance |
| 9 | Asks for help inside an hour, with what they already tried | A message thread |
| 10 | Can name the project's three leading qualities and what it is deliberately weak at | Ask them, unprompted |

### Backend

| # | Row | Evidence |
| --- | --- | --- |
| 11 | Data changes shipped as ordered, reversible steps | The migration history |
| 12 | Time limit on every outward call, retries in one place, capped and randomised | The calling code |
| 13 | Errors returned in one consistent shape the caller can act on | The API responses |
| 14 | Handles the same request arriving twice without doing it twice | A test proving it |
| 15 | Wrote or superseded a decision record for something costly to reverse | The record |

### Frontend

| # | Row | Evidence |
| --- | --- | --- |
| 16 | Zero of the six accessibility failures on screens they built | A scan or a manual check |
| 17 | Builds empty, loading and error states without being asked | Any recent screen |
| 18 | Meets the three speed numbers on real visits at the 75th out of 100 | Field data, not a laptop test |
| 19 | Walks the screen with the keyboard before asking for review | Do it in front of them |
| 20 | Checks the data shape at the edge, so a backend change fails loudly | The code at the boundary |

## The gates

Separate from the rows. Pass or fail, and a fail is a fail regardless of how the rows look.

| Gate | Fails if |
| --- | --- |
| Personal data or secrets in logs | Any instance |
| Merged through a failing check | Any instance |
| A change that cannot be undone with no written plan for undoing it | Any instance |
| A screen shipped with any of the six accessibility failures | Any instance |
| A blocker in the journal over three days with no chase and no fallback | Any instance |
| A live agreement existing only in a call or a chat message | Any instance |

These are gates because none of them need judgement. Either it happened or it did not, which makes them the most reliable part of the sheet.

## How to run it

1. **Collect the evidence before opening the sheet.** Five recent changes, a month of journal, one incident, one handoff. Scoring first and then hunting evidence produces evidence that agrees with the score.
2. Two people mark separately.
3. Compare, and discuss only the disagreements.
4. Walk the gates. Yes or no.
5. **Pick two rows.** Not ten. The two where movement matters most, with one concrete action each.
6. Write it down, dated. The next review starts by reading the last one.

## What senior looks like

Usually on all ten shared rows, Usually on all five for the role, zero gate failures, held across two review periods rather than one good quarter, with evidence on every row. A row marked Usually with nothing to point at counts as Sometimes.

Deliberately **not** on that bar: years served, speed, framework knowledge, project size, or how confident someone sounds. A pooled study of ten experiments found industry years showed no measurable effect on code quality or output.

## Seven rules

1. No score without evidence.
2. Two raters, separately, always.
3. Never average the rows into one number. Someone strong on 19 rows and failing on "can this be undone" is not 95 percent, they are a risk.
4. Never use delivery metrics on individuals. Team level only.
5. Do not add rows without removing rows.
6. Score the last six months only.
7. Show people the sheet before using it on them. A rubric kept secret is a trap.

## What this sheet cannot tell you

It is **not validated**. Nobody has tested whether people who score well produce better outcomes. It is assembled from research on specific pieces plus widely agreed craft practice.

It cannot see judgement under pressure, because the rows describe normal conditions. It cannot see effect on others, so the person who quietly makes three others better scores the same as an equally careful loner. It rewards the visible, so work that leaves no trace is invisible to it, and some of the best senior work is a problem that never happened.

And it will drift. In a year half of it will describe how work used to be done. Review the sheet itself once a year, and when it changes, write a new version and keep the old one.
