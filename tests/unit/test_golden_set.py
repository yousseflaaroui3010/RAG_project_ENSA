"""ST-19's exit gate says "schema respected". This is the machine that says it.

The gate has three words in it and only one of them was ever going to be
checked by a human reading a diff. A golden set is 23 near-identical JSON
lines today and 60 at ST-35, and the failure mode is not a malformed file --
it is one row out of sixty with a null where a file name should be, or a
duplicate id, or an out-of-scope question that quietly carries a source. Any
of those scores wrong at ST-36 and the report blames the product.

WHAT THIS FILE DELIBERATELY DOES NOT DO: load the corpus. `data/` is
git-ignored, so a test that reads the PDFs would pass on MB's machine, skip
on CI, and prove nothing anywhere. A test that skips itself is untested, not
passing. The corpus half lives in `scripts/golden_grounding.py`, which is run
by hand, and its result is quoted in the journal with a date.

So the split is: this file checks the SHAPE of the claims, that script checks
whether the claims are TRUE.
"""

import json
import unicodedata
from pathlib import Path

import pytest

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "evaluation" / "golden"

# The six field names are architecture section 14, quoted: "each with id,
# question, reference answer, source file, source article, kind". The last
# three are ours (DECISIONS row, 2026-08-30). Both groups are listed here so
# that adding a field is a deliberate edit to this list rather than a silent
# widening of the schema.
SIGNED_FIELDS = frozenset(
    {"id", "question", "reference_answer", "source_file", "source_article", "kind"}
)
LOCAL_FIELDS = frozenset({"workspace", "corpus_probe", "notes"})
ALL_FIELDS = SIGNED_FIELDS | LOCAL_FIELDS

IN_SCOPE = "in_scope"
OUT_OF_SCOPE = "out_of_scope"

# ST-19's own numbers, from BUILD-PLAN line 67 and project plan line 101.
# ST-29 and ST-35 raise these; the counts are asserted rather than merely
# eyeballed because "15 in-scope" is the thing the story is graded on.
BATCH1_IN_SCOPE = 15
BATCH1_OUT_OF_SCOPE = 8


def _rows(path: Path) -> list[dict]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:  # pragma: no cover - only on a bad edit
            raise AssertionError(f"{path.name} line {number} is not valid JSON: {exc}") from exc
    return rows


def _all_rows() -> list[dict]:
    files = sorted(GOLDEN_DIR.glob("*.jsonl"))
    assert files, f"no golden-set files in {GOLDEN_DIR}"
    return [row for path in files for row in _rows(path)]


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    return _all_rows()


def test_the_golden_file_is_utf8_without_a_byte_order_mark():
    """A BOM would ride into the first row's `id` and make it unmatchable.

    Not hypothetical on this project: `~/.claude/rules/git-discipline.md`
    carries exactly that BOM, and ST-24 found one sitting inside a regex
    character class. On Windows a single `>` redirect puts it there.
    """
    for path in sorted(GOLDEN_DIR.glob("*.jsonl")):
        assert not path.read_bytes().startswith(b"\xef\xbb\xbf"), f"{path.name} starts with a BOM"


def test_every_row_carries_exactly_the_agreed_fields(rows):
    for row in rows:
        missing = ALL_FIELDS - row.keys()
        extra = row.keys() - ALL_FIELDS
        assert not missing, f"{row.get('id')} is missing {sorted(missing)}"
        assert not extra, f"{row.get('id')} has unagreed fields {sorted(extra)}"


def test_ids_are_unique_and_say_which_half_they_belong_to(rows):
    """An id is how ST-32's report names a question, so a duplicate is a
    report that silently overwrites one row with another."""
    ids = [row["id"] for row in rows]
    assert len(ids) == len(set(ids)), "duplicate id in the golden set"
    for row in rows:
        prefix = "g-in-" if row["kind"] == IN_SCOPE else "g-out-"
        assert row["id"].startswith(prefix), f"{row['id']} does not match its kind {row['kind']}"


def test_kind_is_one_of_the_two_values_and_nothing_else(rows):
    for row in rows:
        assert row["kind"] in {IN_SCOPE, OUT_OF_SCOPE}, f"{row['id']} has kind {row['kind']!r}"


def test_an_in_scope_row_names_the_document_it_came_from(rows):
    """F-03 says every answer carries its sources. A golden row that claims
    an answer exists without naming where it lives cannot grade that."""
    for row in (r for r in rows if r["kind"] == IN_SCOPE):
        assert row["source_file"], f"{row['id']} is in scope with no source_file"
        assert row["source_article"], f"{row['id']} is in scope with no source_article"
        assert row["source_file"].endswith((".pdf", ".docx", ".txt", ".md")), row["source_file"]


def test_an_out_of_scope_row_carries_no_source_at_all(rows):
    """This is the assertion that protects G2. An out-of-scope row with a
    source in it is a row somebody believed was answerable, and 20 of 20
    refusals is not a threshold that survives one of those."""
    for row in (r for r in rows if r["kind"] == OUT_OF_SCOPE):
        assert row["source_file"] is None, f"{row['id']} is out of scope but names a source file"
        assert row["source_article"] is None, f"{row['id']} is out of scope but names an article"


def test_every_row_has_a_question_a_reference_answer_and_a_probe(rows):
    for row in rows:
        for field in ("question", "reference_answer", "corpus_probe", "workspace"):
            value = row[field]
            assert isinstance(value, str) and value.strip(), f"{row['id']}.{field} is empty"
        assert row["question"].endswith("?"), f"{row['id']} is not phrased as a question"
        assert row["notes"] is None or row["notes"].strip(), f"{row['id']}.notes is blank not null"


def test_the_questions_are_in_french(rows):
    """LD-02 puts the flagship corpus in French and F-08 grades against it.
    An English golden question measures the wrong system.

    Checked by accents rather than by a language model: every question in a
    French set of this size carries at least one, and the cheap check is the
    one that will still be run at ST-35.

    The accent test is "does NFKD decomposition change the string", NOT a
    hand-written list of accented letters. The first version WAS such a list
    and it failed on its first run: `g-in-008` opens "À partir de quel âge",
    and neither the capital À nor the â was in the list. A list of characters
    is a list somebody has to remember to extend.
    """
    for row in rows:
        question = row["question"]
        assert unicodedata.normalize("NFKD", question) != question, (
            f"{row['id']} has no accented character in its question; is it French?"
        )


def test_batch_one_holds_the_counts_the_story_was_given():
    rows = _rows(GOLDEN_DIR / "batch1.jsonl")
    in_scope = sum(1 for r in rows if r["kind"] == IN_SCOPE)
    out_of_scope = sum(1 for r in rows if r["kind"] == OUT_OF_SCOPE)
    assert in_scope == BATCH1_IN_SCOPE, f"batch 1 has {in_scope} in-scope, expected 15"
    assert out_of_scope == BATCH1_OUT_OF_SCOPE, (
        f"batch 1 has {out_of_scope} out-of-scope, expected 8"
    )


def test_batch_one_draws_on_every_document_in_the_hr_workspace():
    """Fifteen questions all pulled from the labour code would leave the two
    CNSS documents unmeasured, and retrieval could be broken for both without
    a single golden question noticing.

    This is the fixture-too-small-for-its-own-property shape that has now
    shipped five times on this project (ST-14, ST-16, ST-23, ST-24, ST-21).
    Here it would be a golden set too narrow for the corpus it grades.
    """
    rows = _rows(GOLDEN_DIR / "batch1.jsonl")
    cited = {r["source_file"] for r in rows if r["kind"] == IN_SCOPE}
    assert cited == {
        "code-travail-consolide-2011-justice.pdf",
        "dahir-1-72-184-securite-sociale-acaps.pdf",
        "cnss-regime-securite-sociale-cleiss.pdf",
    }, f"batch 1 leaves an HR document ungraded: {sorted(cited)}"
