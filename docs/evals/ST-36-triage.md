# ST-36 - first full evaluation run and tuning triage

Historical workspace: `392ffb55-12a4-4c91-b2b2-25395c1a703f` ("HR (Moroccan
labour law)"). Corrected-run workspace:
`14b81a1d-5af0-4fb9-a46a-493fad3eb650` ("RH - Code du travail"). Despite the
earlier triage claim, the corrected-run workspace held only the consolidated
2011 labour code and the 1972 social-security dahir. The CLEISS guide was
missing from both the registry and the index.

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

ST-39 found a corpus setup failure behind three of the five refusals. The
tracked CLEISS URL returned 404 because its permanent suffix was missing, so
`g-in-028`, `g-in-039`, and `g-in-040` were evaluated without their named
source. The same missing guide explains why answered row `g-in-030` explicitly
said that none of its passages contained the requested child ages. The URL is
corrected and pinned by a regression test. `scripts/corpus.py fetch` downloaded
the 208,172-byte PDF, `verify` passed all three HR files, Sync added the guide,
and `scripts/golden_grounding.py` reported all 60 rows grounded. A model-backed
rerun is still required; local retrieval now ranks the guide passage first for
`g-in-028`, first for `g-in-039`, and third for `g-in-040`.

The other two refusals have a different mechanism. Free local probes already
rank the answer passage within the configured top five: third for `g-in-017`
and first for `g-in-033`. Their refusal therefore cannot be repaired by adding
the guide or merely raising retrieval depth. The saved report has no trace, so
a focused model-backed rerun must distinguish planner, grader, and writer.

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

### ST-39 focused reruns and evaluator correction

The human approved a maximum of 104 provider calls for focused diagnosis. The
three diagnostic rounds plus two experimental prompt cases used 97 calls and
produced no provider errors. Every one of the thirteen failed rows reached
groundedness 1.00 in at least one focused run:

| Focused run | Rows at 1.00 |
|---|---|
| Complete 13-row trace capture after restoring the guide | `g-in-013`, `017`, `027`, `028`, `033`, `037`, `039` |
| Six-row run during the later-rejected answer-writer experiment | `g-in-024`, `030`, `040` |
| Three-row run after preserving source labels for the judge | `g-in-025`, `026`, `038` |

The traces separated two confirmed mechanisms from one rejected experiment:

1. The missing CLEISS guide caused the guide-dependent failures described
   above. Once indexed, those rows retrieved and answered from the guide.
2. The evaluator dropped the file and section label before sending a passage
   to its judge, even though the writer had seen that label and was explicitly
   allowed to name it. This made valid claims such as "Article 34 of Dahir
   1-72-184" look unsupported. A regression was watched fail on the missing
   label. After the capture used the same labeled block as the writer,
   `g-in-025`, `g-in-026`, and the otherwise unchanged `g-in-038` answer all
   scored 1.00. The gate threshold and judge scoring rule were not changed.

The answer-writer experiment was not kept. Although its two isolated cases
passed, the first full run still made `g-in-024` add nearby caps and contribution
rates, contrary to the experiment's own expected behavior. Cold review caught
that mismatch. The prompt, its cases, its archive, and the shared loader change
were removed; `prompts/answer-writer/PROMPT.md` is byte-for-byte back at 0.1.0
with git object id `93a8a2935498fcd5a0cbd38f286455be8362c12e`.

One focused `g-in-026` attempt still refused after a nearby death-benefit
section passed the child-chunk grader but failed the full-section writer's
stricter check. A later retry found Article 44 and scored 1.00. This is useful
variation evidence, not a new official gate result.

At that point these rows had passed across focused runs, not one frozen 60-row
run. The persisted release result therefore still remained 27/40, and the
approved diagnostic budget had only seven calls left.

### Experimental full run - 2026-09-10T20:32:30Z

The human separately approved a full run capped at 360 provider calls. The
evaluator used 289 calls, produced no provider error, and persisted:

`data/reports/14b81a1d-5af0-4fb9-a46a-493fad3eb650/2026-09-10T20-32-30.708771+00-00.json`

| Gate | Result | Verdict |
|---|---|---|
| G1 fully grounded in-scope rows | **38/40 (95%)** | PASS; needs at least 36/40 |
| G2 clear out-of-scope refusals | **20/20** | PASS |
| G3 sources on actual answers | **38/38** | PASS |
| Mean groundedness of scored answers | **1.0000** | supporting metric only |
| Mean relevancy of scored answers | **1.0000** | supporting metric only |

The separate release command read this exact report and printed `RELEASE GATE:
PASS`. `g-in-026` and `g-in-033` were the two in-scope refusals. Both had
answered at 1.00 in a focused run, so they remain measured model variation, not
missing-corpus or evaluator defects. They are within the signed allowance of at
most four non-fully-grounded in-scope rows; the threshold was not changed.

This report is historical rather than current release evidence because it used
the answer-writer experiment that cold review subsequently rejected.

### Final-code full run - 2026-09-10T21:11:27Z

After restoring answer-writer 0.1.0, the human approved one final run capped at
360 calls. The official evaluator used 284 calls, produced no provider error,
and persisted:

`data/reports/14b81a1d-5af0-4fb9-a46a-493fad3eb650/2026-09-10T21-11-27.750175+00-00.json`

| Gate | Result | Verdict |
|---|---|---|
| G1 fully grounded in-scope rows | **37/40 (92.5%)** | PASS; needs at least 36/40 |
| G2 clear out-of-scope refusals | **20/20** | PASS |
| G3 sources on actual answers | **37/37** | PASS |
| Mean groundedness of scored answers | **1.0000** | supporting metric only |
| Mean relevancy of scored answers | **1.0000** | supporting metric only |

The separate release command read this exact report and printed `RELEASE GATE:
PASS`. `g-in-014`, `g-in-017`, and `g-in-033` were the three in-scope refusals.
Each has answered correctly in an earlier controlled or focused run, so the
result records model variation rather than an absent source. Three misses remain
within the signed allowance of four.

Cold review then tested the release command itself with altered copies of the
report. It had accepted partial, duplicate, relabeled, and boolean-score rows.
The gate now requires every frozen ID exactly once and in order, verifies each
row's frozen in/out category, and rejects booleans or out-of-range score values.
Each new control was watched fail before the guard. The hardened command still
prints `RELEASE GATE: PASS` for the genuine final report.

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

- Query-reword 0.2.0 passed both controlled prompt cases, but `g-in-014` remains
  variable and was one of three refusals in the final run.
- The final-code frozen run passes G1 at 37/40, G2 at 20/20, and G3 at 37/37.
- `g-in-014`, `g-in-017`, and `g-in-033` remain in-scope refusals within G1's
  signed 90% boundary; all three have also produced correct answers in earlier
  controlled or focused runs.
- The corrected evaluator, release command, and report screen pass the full
  offline gate: 743 passed and 2 skipped; lint passed. The corpus check reports
  60 rows grounded (40 in scope, 20 out).
- The release command now rejects missing, extra, duplicate, or reordered
  frozen rows before calculating the three gates. It still passes the final
  report after confirming all 60 expected IDs are present once and in order.
- ST-36's evaluation findings are closed. ST-39 as a whole still waits for
  ST-38's manual QA findings because its story gate covers both inputs.
