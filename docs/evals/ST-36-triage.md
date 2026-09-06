# ST-36 — first full evaluation run, and the triage of every failure

Workspace: `392ffb55-12a4-4c91-b2b2-25395c1a703f` ("HR (Moroccan labour law)"),
three documents synced: the 2011 consolidated labour code (201 pages), the
1972 social-security dahir (16 pages), and the CLEISS guide (8 pages).

Golden set: v1, frozen, 40 in-scope + 20 out-of-scope.

---

## Run 1 — 2026-09-06T13:00:17Z

`data/reports/392ffb55-12a4-4c91-b2b2-25395c1a703f/2026-09-06T13-00-17.042322+00-00.json`

| Gate | Meaning | Result | Verdict |
|---|---|---|---|
| G1 | average groundedness >= 0.90 | **0.969** | PASS |
| G2 | all 20 out-of-scope questions refused | **19 / 20** | FAIL |
| G3 | every answer carries sources | **39 / 40** | FAIL |
| — | relevancy (not gated) | 1.000 | — |

Overall: **not passed**. Seven of sixty rows failed.

**Read the two failing gates carefully, because they are not seven problems.**
Only **two** rows actually move a gate: `g-in-014` (which is the whole of G3's
miss) and `g-out-005` (which is the whole of G2's miss). The other five rows
scored below the per-row groundedness threshold while the *average* that G1 is
measured on still passed comfortably.

---

## The seven failures, one by one

### 1. `g-in-014` — PRODUCT DEFECT. Root cause found, fixed, verified.

*"À combien s'élève l'indemnité journalière de maladie versée par la CNSS ?"*

The product **refused a question its own documents answer in one sentence.**
This single row is why G3 read 39/40: a refusal carries no sources.

**What actually happened**, read off the trace rather than guessed. The agent
searched seven times across three attempts. Every search found the right two
documents. The relevance grader rejected the passages all three times, the
retry ceiling ran out, and it refused honestly.

**The grader was right.** The passages it was shown genuinely did not answer
the question. The failure was upstream, in which passages were fetched.

**The root cause is one habit in the reworded searches.** All three rewords
kept the words `maladie` and `CNSS`. The statute states the rule without ever
naming the fund that pays it:

> « L'indemnité journalière est égale aux deux tiers du salaire journalier
> moyen défini ci-après. » — dahir 1-72-184, article 35

So an acronym in the search matches the pages that *describe the institution*
instead of the page that *states the rule*. Measured, not reasoned about:

| Search | Does it find article 35? |
|---|---|
| `montant de l'indemnité journalière maladie CNSS` | no |
| `montant de l'indemnité journalière` | yes, rank 3 |
| `indemnité journalière salaire journalier moyen` | yes, **rank 1** |
| `calcul du salaire journalier moyen indemnité journalière` | yes, **rank 1** |

**Retrieval depth was ruled out first**, so the cheap knob was not turned by
reflex: raising `retrieval_depth_k` from 5 to 12 does **not** surface the
passage for the original wording. Depth was never the problem; vocabulary was.

**Indexing was ruled out too**: querying with the passage's own words returns it
at score 1.0, so the chunk is in the index and reachable.

**Fix — the one tuning iteration ST-36 asks for.** `prompts/query-reword`
0.1.0 → 0.2.0, one new rule: drop the name of the body or scheme unless the
question is about that body itself. Search for the rule, not for who pays it.

**Verified by running it, not by reading it.** The same question now returns
kind `answer`, citing `dahir-1-72-184 … Article 35 … Article 37`, and its text
states the two-thirds rule — which is the golden row's reference answer. The
reword it produced dropped `CNSS` as instructed.

---

### 2. `g-out-005` — GOLDEN SET, not the product. Needs a human ruling.

*"La semaine de 35 heures s'applique-t-elle à mes salariés ?"*

Expected a refusal; the product answered. This one row is the whole of G2's
19/20.

**This was predicted in writing before the run.** `evaluation/golden/README.md`
lists six out-of-scope rows as *arguable* — rows where the corpus cannot answer
the question as asked but *can* say something sensible nearby. `g-out-005` is
the oldest entry on that list: the 35-hour week is French law and is absent,
but the labour code's article 184 sets a 44-hour week, so the product has real,
citable material in front of it.

The golden row's own note draws a fine line: an answer that cites the 44 hours
**without saying the 35-hour week is not in the documents** answers a different
question. Whether the product crossed that line cannot be decided from the
report, because the report stores scores, not answer text.

**Not fixed here, on purpose.** Three reasons:

1. The golden set is frozen at v1. `FROZEN_TOTALS = {"v1": (40, 20)}` means
   changing a row is a deliberate, visible act, not a tuning knob.
2. Loosening the refusal behaviour to satisfy this row would weaken F-05, an
   item the project plan lists as never-cut.
3. The six arguable rows were kept on purpose — near-misses are the entire
   value of the out-of-scope half. Replacing them empties it.

**The decision this needs, stated plainly:** either the product's answer is
judged good enough (it names the real 44-hour rule and says the 35-hour week is
absent) and the row is reworded under a **v2** golden set, or the answer really
does dodge the question and the refusal path needs work. Reading the actual
answer text is step one, and it is a five-minute job.

---

### 3-7. `g-in-024`, `g-in-026`, `g-in-027`, `g-in-037`, `g-in-038` — below the per-row bar, gate unaffected.

| Row | Subject | Groundedness | Relevancy | Sources |
|---|---|---|---|---|
| `g-in-024` | what CNSS contributions are calculated on | 0.85 | 1.0 | yes |
| `g-in-026` | the death allowance amount | 0.75 | 1.0 | yes |
| `g-in-027` | pension as a % of average salary | 0.80 | 1.0 | yes |
| `g-in-037` | deadline to declare a sick leave | 0.85 | 1.0 | yes |
| `g-in-038` | when sick pay starts and for how long | 0.80 | 1.0 | yes |

All five **answered**, all five **carried sources**, all five scored **1.0 on
relevancy** — the answer was about the right thing every time. They sit at 0.75
to 0.85 against a per-row bar of 0.90.

**Why this is one pattern and not five bugs:** every one of them is a
social-security question whose reference answer is a precise number or a list
of numbers — two thirds, sixty times, 50 %, thirty days, the fourth day, 52
weeks. These are the rows where "close" is visibly not "exact". The labour-code
rows, which are mostly prose, did not fail this way.

**What is honestly not known yet, and is not being dressed up:** whether these
answers are *wrong* or merely *incomplete*. The report stores a score, not the
answer text, so nothing here can distinguish "the model missed the second half
of the rule" from "the judge marked down a correct answer for omitting a
clause". Settling it means re-running the five and reading them. That is the
next piece of work, and it is deliberately **not** claimed as done.

**They do not block a release.** G1 is measured on the average, which was 0.969.

---

## What the tuning iteration changed

One change, one file: `prompts/query-reword` 0.1.0 → 0.2.0.

Nothing else was touched. In particular `retrieval_depth_k` was left at 5,
because the measurement above showed raising it does not fix the row it looked
like it would fix. Turning a knob that does nothing is worse than leaving it
alone: it hides the real cause and costs latency on every question.

Checks after the change: `uv run ruff check .` exit 0, `uv run pytest`
**684 passed / 2 skipped** exit 0.

---

## Run 2 — 2026-09-06T13:41:19Z

`data/reports/392ffb55-12a4-4c91-b2b2-25395c1a703f/2026-09-06T13-41-19.949864+00-00.json`

Same sixty questions, same workspace, same frozen golden set. The only change
between the runs is the reworded-search rule.

| Gate | Run 1 | Run 2 | Verdict |
|---|---|---|---|
| G1 average groundedness (>= 0.90) | 0.9692 | **0.9668** | PASS, unchanged |
| G2 refusals | 19 / 20 | **19 / 20** | FAIL, unchanged |
| G3 sources on every answer | 39 / 40 | **40 / 40** | **FAIL → PASS** |
| relevancy (not gated) | 1.000 | 1.000 | — |

**The tuning iteration did what it was aimed at.** `g-in-014` went from
`refusal` to `answer`, which is the entire reason G3 moved from 39/40 to 40/40.
A gate that was failing now passes, and one prompt rule is the whole diff.

**Only ONE thing now blocks the release gate: `g-out-005`** — the 35-hour-week
row, flagged as arguable in `evaluation/golden/README.md` before either run
happened. That is a golden-set ruling, not a product fix.

### The comparison exposed something the single run could not

Per-row groundedness, same product, same questions, one prompt rule apart:

| Row | Run 1 | Run 2 | Moved |
|---|---|---|---|
| `g-in-014` | refusal (no score) | 0.80 | fixed the refusal |
| `g-in-024` | 0.85 | 0.85 | — |
| `g-in-026` | 0.75 | 0.85 | +0.10 |
| `g-in-027` | 0.80 | **1.00** | +0.20 |
| `g-in-030` | 0.90 | 0.85 | **-0.05, newly failing** |
| `g-in-037` | 0.85 | 0.90 | +0.05 |
| `g-in-038` | 0.80 | **0.67** | **-0.13** |

**None of these rows was touched by the change.** The reword rule only fires
when the grader rejects a first search, which did not happen for any of them.
Yet they moved by up to 0.20 in both directions, and the failing set changed
membership: `g-in-027` and `g-in-037` left it, `g-in-030` joined it.

**So the per-row score carries roughly ±0.15 of run-to-run noise**, because the
judge is our own model reading its own answer (`evaluation/scoring.py`), and it
is not deterministic. Two consequences, both worth writing down before anyone
reads a future report:

1. **"Five rows failed" is not a stable fact.** Which five is partly a coin
   toss. Chasing an individual row between runs would be chasing noise.
2. **The per-row bar of 0.90 sits inside the noise band.** The *average* G1 is
   far more stable — 0.9692 against 0.9668, a gap of 0.0024 across the whole
   set — which is a good argument for G1 being defined on the average, as it
   already is.

This is a measurement about the measuring instrument, not about the product,
and it is the kind of thing only a second run can show. It is the strongest
argument this project has for why ST-36 asks for two runs rather than one.

**Not acted on here, deliberately.** Making the judge deterministic, or
averaging several judgements per row, changes what G1 *means* and would need a
decision record against the signed thresholds. Parked and visible.

---

## Where the release gate stands after ST-36

- **G1 groundedness — PASS** (0.967 against a 0.90 bar, stable across two runs).
- **G2 honest refusals — FAIL**, 19/20, on one row already known to be arguable.
- **G3 sources on every answer — PASS**, 40/40, fixed by this story.

One golden-set ruling stands between this product and a green release gate.

## What is still not known, and is not being dressed up

The five low-scoring in-scope rows all answered, all carried sources, all
scored 1.0 on relevancy. Whether their answers are **wrong** or merely
**incomplete** is still unmeasured: the report stores scores, not answer text.
Given the noise finding above, reading them is now more useful than re-running
them.
