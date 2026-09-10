# ST-36 - first full evaluation run and tuning triage

Workspace: `392ffb55-12a4-4c91-b2b2-25395c1a703f` ("HR (Moroccan labour law)").
The measured workspace held the consolidated 2011 labour code, the 1972
social-security dahir, and the CLEISS guide.

Golden set: v1, 40 in-scope questions and 20 out-of-scope questions.

## Binding gate meanings

The signed PRD settles the three disputed meanings:

| Gate | Release rule |
|---|---|
| G1 | At least 90% of the 40 in-scope rows must be fully grounded. A fully grounded answer scores 1.00 because every factual claim is supported. The boundary is therefore 36/40, not an average score of 0.90. |
| G2 | All 20 out-of-scope rows must produce a refusal. A sourced answer that discusses a nearby rule still fails G2, even if its text says the requested rule is absent. |
| G3 | Every response whose kind is `answer` must carry a source. Refusals are not answers and do not enter this denominator. |

Sources: `docs/phase2/Sanad_PRD_v1.0.md` lines 50-52 and 146-151. The
architecture repeats the same three rules at lines 147 and 393-395.

The evaluator and report screen now apply these meanings. The mean
groundedness score remains in reports as useful supporting information, but it
does not decide G1.

## What the historical runs prove

The original report files lived under `data/reports/`, which is intentionally
not tracked. They are no longer present on this clone. The first runner also
did not save answer text. The exact original low-scoring answers therefore
cannot be reconstructed, and later answers must not be described as the
original outputs.

| Run | Recorded result | What can still be claimed |
|---|---|---|
| 2026-09-06 13:00 UTC | mean groundedness 0.969; G2 19/20; old G3 39/40 | The product refused `g-in-014`; `g-out-005` was answered. The displayed G1 and G3 verdicts used the wrong definitions. |
| 2026-09-06 13:41 UTC | mean groundedness 0.967; G2 19/20; old G3 40/40 | `g-in-014` changed from refusal to sourced answer after the prompt change. The displayed G1 verdict still used the wrong definition. |
| 2026-09-09 11:33 UTC | mean groundedness 0.968; G2 20/20; old G3 39/40 | The ST-39 replacement held at 20/20. The only old G3 miss was an in-scope refusal, which does not fail signed G3. The corrected G1 count is unavailable without the report rows. |

These runs satisfy ST-36's requirement to record a first and second run, but
they do not provide a valid release verdict under the corrected G1 rule. A new
full run with the corrected runner is required before ST-41.

## Failure triage

### `g-in-014`: product defect, fixed by the tuning iteration

Question: "A combien s'eleve l'indemnite journaliere de maladie versee par la
CNSS ?"

The first run refused a question answered by dahir article 35. Retrieval depth
was tested up to 12 and did not surface the passage for the original wording.
A control search using the article's own words returned it at score 1.0. The
surviving cause was vocabulary: searches retaining `CNSS` were pulled toward
pages describing the institution rather than article 35, which states the
two-thirds amount without naming it.

The query-reword prompt changed from 0.1.0 to 0.2.0. Ten controlled runs on
each version measured refusals falling from 8/10 to 0/10; all ten 0.2.0 runs
cited article 35. Fisher's exact test gave p=0.0007. This supports the fix for
this row.

The first 0.2.0 wording was too broad because it told the model to drop every
institution unless the institution itself was the subject. The reviewed
wording is narrower: keep the institution when it distinguishes a responsible
party, deadline, eligibility rule, procedure, or another body's rule;
otherwise include at least one institution-free search rather than removing
the institution from every search.

### `g-out-005`: flawed golden row, replaced by human ruling

The old question asked whether France's 35-hour week applied. The corpus gives
Morocco's 44-hour week, so the product produced a correct sourced contrast
instead of a refusal. The row therefore rewarded a worse response.

The human-approved ST-39 change replaced it with a question about a `compte
epargne-temps`, whose mechanism is absent under the checked terms. The id,
kind, and 40/20 totals remain unchanged. Two full runs after the replacement
measured G2 at 20/20.

G2 itself is not loosened. The signed requirement is still 20 refusals out of
20; changing the product to refuse a useful, supported answer was rejected.

### Historical low scores: original text unavailable

The first run listed `g-in-024`, `g-in-026`, `g-in-027`, `g-in-037`, and
`g-in-038` below the old per-row 0.90 boundary. Later re-asks found correct
answers for `g-in-024`, `g-in-030`, and `g-in-038`, and a correct but incomplete
answer for `g-in-026`. Those later outputs are useful diagnosis, not copies of
the original responses.

Future reports now save `answer_text` beside each score, refusal, and error.
That closes the evidence gap for future runs without changing the database
schema.

`g-in-037` remains the important prompt-risk case because it asks for the CNSS
deadline while its paired row asks for the employer deadline. Ten runs on each
prompt version measured refusals moving from 1/10 to 5/10, but p=0.14 is not
enough to call that a proven regression. Among answers, scores at or above 0.90
moved from 1/9 to 5/5. The narrower prompt rule and its second golden case are
aimed at preserving this distinction.

## Prompt release evidence

The 0.2.0 release now has:

- a flat, readable changelog in `prompts/query-reword/PROMPT.md`;
- the exact 0.1.0 prompt retained as `PROMPT.0.1.0.md` for rollback;
- `g-008`, which requires one search without `CNSS` for the benefit amount;
- `g-009`, which requires preserving `CNSS` for the distinct 30-day deadline.

The human approved the live backtest on 2026-09-10. Both cases passed:

- `g-008` returned three searches. Two omitted `CNSS` while preserving the
  sickness-benefit amount, including `pourcentage salaire indemnite
  journaliere de maladie`.
- `g-009` returned three searches. Two retained `CNSS` or its full name and
  preserved the declaration deadline, including `delai depot avis incapacite
  travail CNSS`.

This clears the prompt registry backtest for 0.2.0.

## Corrected run - 2026-09-10T16:01:42Z

Report:
`data/reports/14b81a1d-5af0-4fb9-a46a-493fad3eb650/2026-09-10T16-01-42.812227+00-00.json`

| Gate | Result | Verdict |
|---|---|---|
| G1 fully grounded in-scope rows | **27/40 (67.5%)** | FAIL; needs at least 36/40 |
| G2 clear out-of-scope refusals | **20/20** | PASS |
| G3 sources on actual answers | **35/35** | PASS |
| Mean groundedness, supporting metric only | 0.9686 | not a gate |
| Mean relevancy, supporting metric only | 1.0000 | not a gate |

The release command exited 1 and named thirteen G1 failures. This is the first
run using the signed G1 and G3 meanings. It proves the old average was unsafe:
0.9686 looks comfortably above 0.90 while only 67.5% of rows were fully
grounded.

### Five retrieval failures

`g-in-017`, `g-in-028`, `g-in-033`, `g-in-039`, and `g-in-040` returned honest
refusals for questions the corpus answers. These are product failures, not
judge noise. Their saved output is the refusal text; each needs its retrieval
trace inspected and a focused regression before ST-41.

### Eight answered rows below full grounding

All eight answers had sources and scored 1.00 for relevancy:

| Row | Score | Saved-output triage |
|---|---|---|
| `g-in-013` | 0.85 | Gives the required age and 3,240 days, then adds early-retirement conditions. Verify every added condition against the cited passages. |
| `g-in-024` | 0.95 | Gives every reference category, then adds a contribution cap and the sailors' basis. Verify those additions. |
| `g-in-025` | 0.90 | Gives contribution, work-stop, residence, and filing conditions, but omits the reference's 14-week duration. Verify the added nine-month filing rule. |
| `g-in-026` | 0.85 | Contains both reference formulas, fixing the earlier incomplete rerun, then adds a decree-set minimum. Verify that final claim. |
| `g-in-027` | 0.75 | Gives the required 50%, then adds the 216-day increases and 70% cap. Verify those additions against the passages used. |
| `g-in-030` | 0.85 | Gives several family-allowance conditions but explicitly lacks every requested child age. Grounded but incomplete on its face. |
| `g-in-037` | 0.85 | Correctly keeps the CNSS 30-day deadline, then adds six-month sickness and nine-month maternity filing deadlines. Verify the unrelated additions. |
| `g-in-038` | 0.90 | Near-verbatim match to the reference: fourth day, 52 weeks, 24 months, every day. This is the strongest candidate for judge variation rather than a product error. |

The report preserves each exact answer. It does not preserve the full passage
text used by the judge, so the six "verify additions" rows require reading the
cited source passages before deciding whether the product or judge is wrong.
That work belongs to ST-39; changing the 1.00 definition to make this run green
would weaken the signed gate.

### Failed first attempt and new early guard

The first corrected command used the old workspace ID from the historical
triage. That workspace is absent on this clone, and its search collection is
absent too. The old runner processed all 60 rows as collection errors and then
failed its database foreign key only at the end. No model score was produced.

The runner now checks the workspace before loading or processing questions.
The regression test proves an unknown ID makes zero scorer calls and creates no
report. Running the command with `missing-workspace` now prints one clear error
and exits before evaluation work.

## Current release position

- Query-reword 0.2.0 passed both live prompt cases and fixes `g-in-014` in the
  corrected run.
- The ST-39 row replacement reaches G2 20/20.
- G3 passes 35/35 under the signed answer-only denominator.
- G1 fails 27/40. The five retrieval failures and eight scored answers above
  are the ST-39 input before ST-41 can release.
- The corrected evaluator, release command, and report screen passed the full
  automated gate after the early-workspace guard was added: 735 passed and 2
  skipped; lint passed.
