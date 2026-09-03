# Golden set (F-08)

The questions every release is scored against. Owned by MB (`docs/phase2/CLAUDE.md`
line 26: "`evaluation/golden/` belongs to MB. Only touch it when the story says so").

Built in three batches, because the plan builds it in three batches:

| Batch | Story | In scope | Out of scope | Running total |
|---|---|---|---|---|
| `batch1.jsonl` | ST-19 | 15 | 8 | 15 + 8 |
| `batch2.jsonl` | ST-29 | +15 | +7 | 30 + 15 |
| `batch3.jsonl` | ST-35 | +10 | +5 | **40 + 20, frozen** |

The counts live in one table in `tests/unit/test_golden_set.py`
(`EXPECTED_COUNTS`), not in a test per batch. A second test refuses any
`.jsonl` in this folder that the table does not list, because a table that
ignores what it does not know about is not a check — batch 3 could otherwise
have arrived uncounted and every count test would have gone on passing.

## THE SET IS FROZEN (ST-35, 2026-09-01, `GOLDEN_SET_VERSION = "v1"`)

40 in-scope + 20 out-of-scope, verified by both checks on that date:
`uv run pytest tests/unit/test_golden_set.py` → 13 passed, and
`uv run python scripts/golden_grounding.py` → **"OK: 60 rows grounded
(40 in scope, 20 out)"**.

Frozen means the numbers a release is graded on stop moving underneath the
grade. Two things enforce it, and it is worth knowing what each one can and
cannot see:

- the running-total test moved from `<=` to `==`. While the set was being
  built in batches, a cap was the only honest assertion — 23 rows and 45 rows
  both had to pass. Now an **under**-count is a defect too, and a cap cannot
  see one.
- `FROZEN_IDS` pins the sixty ids as a contiguous run. It catches a row added,
  dropped or renumbered. **It does not catch an edit to the wording** of a
  question or a reference answer. Pinning the bytes would have caught that and
  was deliberately not done: this file is checked out on two machines, and git
  converts its line endings on checkout — a hash would then fail for a reason
  that has nothing to do with the golden set, which is the worst kind of red.
  Wording is held by review and by git history.
- `FROZEN_TOTALS = {"v1": (40, 20)}` binds the totals to the version, and this
  is the one that makes the freeze real. **The first version of it did not.**
  It asserted `GOLDEN_SET_VERSION == "v1"` against a literal nine lines away,
  which cannot fail — so adding a 41st question meant editing
  `FINAL_TOTAL_IN_SCOPE` and one `EXPECTED_COUNTS` row, and the file went green
  with the version still reading `"v1"`. The ST-35 review did exactly that in
  an isolated copy and watched it pass 13 of 13. Now the same edit is red until
  the version is bumped and the new version gets its own row.

  What it still cannot see, stated rather than left to be found: editing the
  `"v1"` row itself. That is tampering with the frozen record under its own
  name, plainly visible in a diff, and a different thing from the quiet drift
  during a tuning session that this table exists to stop.

**To change the set after the freeze:** bump `GOLDEN_SET_VERSION`, add the new
version's totals to `FROZEN_TOTALS`, update `FINAL_TOTAL_*` and the
`EXPECTED_COUNTS` row, and write the reason in `docs/journal/DECISIONS.md`. The
friction is the feature — an evaluation set edited during a tuning session is a
set that has stopped measuring anything. This is also how PRD F-08's "at least
40" is honoured: a legitimate 41st question is not forbidden, it just costs a
version bump instead of a one-character edit.

The 40 + 20 target is PRD F-08 and architecture section 14. G2 is graded on the
out-of-scope half and demands **20 of 20** refusals, so an out-of-scope question
that is secretly answerable does not merely score wrong: it makes a release gate
fail for a reason nobody can find.

## Schema

One JSON object per line. The six signed fields come from architecture section 14
("each with id, question, reference answer, source file, source article, kind").
Three more are ours and are recorded in `docs/journal/DECISIONS.md`.

| Field | Signed? | Meaning |
|---|---|---|
| `id` | yes | `g-in-NNN` or `g-out-NNN`, unique across every batch, never reused |
| `question` | yes | French, as a user would type it |
| `reference_answer` | yes | For in-scope, the true answer. For out-of-scope, what a correct **refusal** must convey |
| `source_file` | yes | The corpus file name. **null** for out-of-scope |
| `source_article` | yes | The article or section inside it. **null** for out-of-scope |
| `kind` | yes | `in_scope` or `out_of_scope` |
| `workspace` | no | Which workspace the question is asked in. `hr` throughout batch 1 |
| `corpus_probe` | no | See below — this is what makes the file checkable |
| `notes` | no | Why the row is here, or a trap it sets. May be null |

### `corpus_probe` is the field that stops this file rotting

A golden set is a list of claims about documents, and a list of claims nobody
re-checks is a list of claims that quietly stops being true. `corpus_probe` makes
each row falsifiable by a machine, and it means the **opposite** thing on each side:

- **in-scope:** a literal string that MUST appear in `source_file`. If it stops
  appearing, either the reference answer drifted or the corpus changed.
- **out-of-scope:** a term that MUST NOT appear anywhere in the corpus. This is
  the half that matters. It is what separates "we believe the corpus cannot
  answer this" from "we checked".

Run the check with:

    uv run python scripts/golden_grounding.py

It needs the corpus on disk (`data/` is git-ignored; rebuild it with
`uv run python scripts/corpus.py fetch`). Matching folds accents and both kinds
of apostrophe, because the three PDFs do not agree on either — the CNSS dahir
uses U+02BC MODIFIER LETTER APOSTROPHE where the labour code uses a plain one.

**This bit was learned the hard way and is the reason the checker exists.** The
first pass of absence checks for this story was run with `grep -E "pr.avis"`,
where `.` matches one BYTE and `é` is two. It reported **zero** occurrences of
`préavis` in a document that contains forty. Four out-of-scope questions were
about to be written on the strength of that zero. A blind route returns the same
empty answer as a true absence.

## What batch 1 covers

Fifteen in-scope questions across all three HR documents — twelve from the labour
code, two from the CNSS dahir, one from the CLEISS guide — chosen so that a wrong
answer would cost a real HR generalist something: probation, annual leave,
seniority leave, gross misconduct, notice, severance, work certificate, minimum
working age, maternity, working hours, overtime, weekly rest, old-age pension,
sick pay, birth leave.

Eight out-of-scope questions, every one verified absent by the checker above. They
are deliberately near-misses rather than nonsense. Asking a labour-law corpus about
football scores proves nothing; asking it about **rupture conventionnelle** — when
it holds long passages on ending a contract — is where a model actually invents.

## What batch 2 adds

Fifteen more in-scope questions, deliberately rebalanced toward the two CNSS
documents: **8 labour code, 4 CNSS dahir, 3 CLEISS guide**, where batch 1 was
12/2/1. Over the 30 in-scope questions so far that is 20/6/4, which is roughly
how the three documents compare in size. A test holds the three-document rule
**per batch**, not over the whole set, so a later batch cannot drift entirely
onto the labour code on the strength of an earlier one.

Several rows are paired with a batch-1 row on purpose, because the pair is
harder than either question alone:

| Batch 2 | Pairs with | Why the pair is the test |
|---|---|---|
| `g-in-018` employer's gross misconduct (art. 40) | `g-in-004` employee's (art. 39) | consecutive articles, opposite parties — answering one with the other is a clean miss |
| `g-in-019` who qualifies for severance (art. 52) | `g-in-006` the severance scale (art. 53) | consecutive articles; the scale alone is an incomplete answer |
| `g-in-027` pension amount (dahir art. 55) | `g-in-013` pension conditions (dahir art. 53) | one says who qualifies, the other says how much |
| `g-in-025` maternity benefit, **14 weeks** (dahir art. 37) | `g-in-009` maternity leave, **14 weeks** (code art. 152) | same number, different documents, different meaning — citing the wrong file is wrong even with the right figure |
| `g-in-029` early retirement at 55 (CLEISS) | `g-in-013` normal pension at 60 (dahir) | two ages that must not merge |

**One article-number collision is in the set at batch 2, and it is
deliberate:** labour code article 53 vs CNSS dahir article 53 (severance vs
old-age pension). A citation that gets the number right and the document wrong
is still a wrong citation, and F-03 makes the source line the product's
contract with the user.

*Corrected at the ST-35 review:* this paragraph used to claim two collisions
here, counting labour code article 33 vs dahir article 33 as well. At batch 2
only the code's article 33 was a row (`g-in-017`); the dahir's arrives with
`g-in-037` in batch 3. The claim was true of the corpus and false of the set —
see the batch 3 table below, where it is now graded.

Seven more out-of-scope questions, every one verified absent: French labour
court, personal-data obligations, health emergency rules, sabbatical leave,
non-compete clauses, the thirteenth-month bonus, and profit sharing.

### One question that was dropped, and why it is worth knowing

"How many months of notice must a manager give?" is the perfect out-of-scope
question — article 43 states the obligation and hands the **duration** to a
decree the corpus does not contain, so the corpus names the topic and cannot
answer it. It is not in the set, because the schema requires an out-of-scope
row to name a term that is absent from every document, and there is no such
term here: `préavis` appears 40 times and the decree number appears in a
footnote. Rather than bend the rule that makes the out-of-scope half
falsifiable, the question was left out. `g-in-005`'s note carries the same
trap from the in-scope side instead.

## What batch 3 adds, and what it closes

Ten more in-scope questions — **6 labour code, 2 CNSS dahir, 2 CLEISS guide** —
bringing the 40 in-scope rows to 26 / 8 / 6. Five more out-of-scope, taking
the refusal half to the 20 that G2 grades.

The ten in-scope rows deliberately cover the parts of an HR job the first two
batches left out: what an employer may **not** punish (art. 36), the ladder of
sanctions for an ordinary fault (art. 37), the notice owed before an economic
layoff (art. 66), when a `règlement intérieur` becomes compulsory (art. 138),
what a sick employee owes their employer (art. 271), the family-event leave
table (art. 274), the CNSS deadline for the same sick note (dahir art. 33),
when sick pay starts and stops (dahir art. 34), who qualifies for compulsory
health insurance (CLEISS, AMO) and what remarriage does to a survivor's
pension (CLEISS).

Four traps are new — three by design, the fourth found at the review — and all
four are the kind that only a sourced-answer product can fail:

| Rows | The trap |
|---|---|
| `g-in-035` (code art. 271) + `g-in-037` (dahir art. 33) | **One event, two deadlines, two documents.** The same sick day owes the employer notice within 48 hours and the CNSS a form within 30 days. Getting the number right from the wrong file is a wrong citation. |
| `g-in-037` (dahir art. 33) + `g-in-017` (code art. 33) | The two article 33s are now **both rows**, not just a note. Until this batch the collision was described; now it is graded. |
| `g-in-039` (AMO) + `g-in-025` (dahir art. 37) + `g-in-029` (early retirement) | **"54 days of contributions" appears four times in the CLEISS guide alone, for four different benefits, across only two windows** — 6 months for AMO, 6 civil months for sick pay, 10 civil months for maternity pay, 6 months for early retirement. So the number does not identify the entitlement, and neither does the window: three of the four share one. |
| `g-in-032` (code art. 37) + `g-in-025` (dahir art. 37) | **The third article-number collision**, found at the ST-35 review rather than when the row was written: disciplinary sanctions in the labour code against maternity benefit in the dahir. Same shape as the two article 53s and the two article 33s. |

`g-in-034`'s ten-employee threshold also sits against `g-in-022`'s fifty, and
`g-in-031` is the negative of `g-in-004`: one lists what justifies a dismissal,
the other what can never justify one, and they are neighbours in the text.

### Two out-of-scope questions were written and then thrown away

Both were caught by `scripts/golden_grounding.py` or by the rule it enforces,
and both are worth more than the rows that replaced them.

**1. "Ai-je droit à une indemnité pour perte d'emploi ?" — the checker said no.**
This is the ideal-looking out-of-scope question: unemployment insurance is not
what a 1972 social-security dahir or a 2011 labour code is about. The probe
came back **present three times** — `code=2, cleiss=1`. The labour code grants
`l'indemnité de perte d'emploi` twice, and the CLEISS guide carries a whole
paragraph on the scheme *with its contribution rates* (0,38 % employer,
0,19 % employee). The question is answerable. Scored as out-of-scope it would
have failed G2 — 19 refusals out of 20 — for a reason nobody reading the
report could have found. This is the second time on this story that a claim of
absence turned out to be false, and the second time the script, not a human,
was what noticed.

**2. "Un père a-t-il droit à un congé de paternité ?" — absent as a term, and
still wrong.** The phrase `congé de paternité` appears nowhere in the corpus, so
it passes the checker. (Precisely, and it makes the point sharper: the *word*
`paternité` does appear — once, in labour code **article 269**, which is the
birth-leave article that answers the question. The phrase is absent; the topic
is one word away.) It was dropped anyway, because the corpus **does**
answer it under another name: `g-in-015` is the father's three-day
`congé de naissance`. A refusal here would be the wrong answer. Term-absence
is necessary and not sufficient — the real test is whether the corpus can
answer the question **under any name**, and only a human reading the rows can
say. Same shape as `g-out-005` below.

That judgement was applied again at the ST-35 review, and it did not come back
clean: two of the five new out-of-scope rows are arguable on exactly this
ground and are now listed with `g-out-005` in the caveats below. The rule this
section states was right; applying it once per drafting session was not enough.

## Two honest caveats, recorded rather than smoothed over

**1. The CLEISS guide is old, and `g-in-015` inherits that.** The guide is undated
("version n2") and its contribution table is headed 1 January 2014. `g-in-015`'s
692,30 DH ceiling is what the document says, not what the CNSS pays in 2026. This
is correct for what F-08 measures — RAGAS faithfulness scores an answer against
the passages it was given, so the reference answer must match the corpus — but
nobody may quote that figure in the report as current Moroccan practice.
`data/corpus/SOURCES.md` already labels this file secondary; this is the same
warning, at the row that depends on it.

**2. Three out-of-scope rows are arguable, and they are named here so that if
they score badly at ST-36 the discussion is about the question rather than
about retrieval.** All three refuse something the corpus genuinely does not
contain, while sitting close to something it does — which is what makes them
worth having and also what makes them contestable. G2 demands 20 refusals out
of 20, so a model that answers any of these *well* costs the gate a point.

| Row | Refuses | But the corpus nearby holds |
|---|---|---|
| `g-out-005` | the 35-hour week | *a* legal working week — 44 hours, article 184 |
| `g-out-019` | rules on `titres-restaurant` | dahir article 19's catch-all: "tous autres avantages en argent, les avantages en nature" (`g-in-024`), from which a sourced answer could reasonably be built |
| `g-out-020` | a hiring **quota** for disabled workers | an entire chapter of duties — labour code articles 166 to 171 — so a good answer may name those while correctly denying the quota |

`g-out-019` and `g-out-020` were added to this list at the ST-35 review, not
when they were written. Both had passed `golden_grounding.py`: the terms really
are absent. That is the limit the script has always had and the reason this
section exists — see the paternity question above.
