# Golden set (F-08)

The questions every release is scored against. Owned by MB (`docs/phase2/CLAUDE.md`
line 26: "`evaluation/golden/` belongs to MB. Only touch it when the story says so").

Built in three batches, because the plan builds it in three batches:

| Batch | Story | In scope | Out of scope | Running total |
|---|---|---|---|---|
| `batch1.jsonl` | ST-19 | 15 | 8 | 15 + 8 |
| batch 2 | ST-29 | +15 | +7 | 30 + 15 |
| batch 3 | ST-35 | +10 | +5 | **40 + 20, frozen** |

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

## Two honest caveats, recorded rather than smoothed over

**1. The CLEISS guide is old, and `g-in-015` inherits that.** The guide is undated
("version n2") and its contribution table is headed 1 January 2014. `g-in-015`'s
692,30 DH ceiling is what the document says, not what the CNSS pays in 2026. This
is correct for what F-08 measures — RAGAS faithfulness scores an answer against
the passages it was given, so the reference answer must match the corpus — but
nobody may quote that figure in the report as current Moroccan practice.
`data/corpus/SOURCES.md` already labels this file secondary; this is the same
warning, at the row that depends on it.

**2. `g-out-005` is the arguable one.** "Does the 35-hour week apply?" — the
corpus has *a* legal working week (44 hours, article 184) but not the one asked
about. Called out here so that if it scores badly at ST-36 the discussion is
about the question, not about the retrieval.
