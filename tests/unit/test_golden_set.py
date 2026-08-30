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
import re
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

# Short French function words that are NOT also English words, used as the
# fallback language signal for an accent-free French question. Deliberately
# excludes look-alikes ("a", "an", "on", "par", "sans") -- a marker that an
# English sentence can contain makes the check weaker, not more generous.
FRENCH_MARKERS = frozenset(
    {
        "le", "la", "les", "un", "une", "des", "du", "au", "aux", "ce", "cette",
        "mon", "ma", "mes", "son", "sa", "ses", "quel", "quelle", "quelles", "quels",
        "combien", "comment", "est-il", "est-elle", "peut-on", "puis-je",
        "doit-il", "a-t-il", "a-t-elle", "sont", "dans", "pour", "avant", "apres",
        "salarie", "salarié", "employeur", "travail", "contrat", "conge", "congé",
    }
)

# One row per batch: the counts the owning story is graded on, taken from
# BUILD-PLAN lines 67 and 84 and project plan lines 101, 119 and 135.
#
# A TABLE RATHER THAN A TEST PER BATCH, decided when batch 2 arrived and the
# batch-1 test was about to be copy-pasted. The plan builds this set in three
# batches, so the copy-paste version ends at three near-identical tests whose
# only difference is two numbers -- and the third copy is exactly where the
# core law says abstract it or write down why not. ST-35 adds one row here.
EXPECTED_COUNTS = {
    # file name        in scope, out of scope, story
    "batch1.jsonl": (15, 8, "ST-19"),
    "batch2.jsonl": (15, 7, "ST-29"),
}

# Running totals after every batch that exists, which is the number ST-35
# freezes at and the number PRD F-08 and G2 are written against: 40 in-scope
# and 20 out-of-scope. G2 demands 20 refusals out of 20, so the out-of-scope
# total is not decoration -- it IS the denominator of a release gate.
FINAL_TOTAL_IN_SCOPE = 40
FINAL_TOTAL_OUT_OF_SCOPE = 20


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

    THIRD VERSION OF THIS CHECK, and each rewrite was forced by a real row
    rather than by taste:

    1. A hand-written list of accented letters, `éèêàùôûçîï`. Failed on its
       first run: `g-in-008` opens "À partir de quel âge" and carries neither
       the capital À nor the â. A list of characters needs maintaining.
    2. "Does NFKD decomposition change the string", which needs no list.
       Failed when batch 2 arrived: `g-out-009` is "Comment saisir le conseil
       de prud'hommes contre mon employeur ?" -- flawless French with not one
       accented character in it. The check was measuring accents and calling
       the answer "French".
    3. Accented character OR two distinct French function words. A question
       has to fail BOTH to be reported, which is what stops correct French
       being rejected while still catching English outright.
    """
    for row in rows:
        question = row["question"]
        has_accent = unicodedata.normalize("NFKD", question) != question
        words = set(re.findall(r"[\w'-]+", question.lower()))
        markers = len(words & FRENCH_MARKERS)
        assert has_accent or markers >= 2, (
            f"{row['id']} has no accent and only {markers} French marker word(s); is it French?"
        )


def test_every_batch_holds_the_counts_its_story_was_given():
    for name, (want_in, want_out, story) in EXPECTED_COUNTS.items():
        path = GOLDEN_DIR / name
        assert path.is_file(), f"{name} is missing ({story})"
        rows = _rows(path)
        got_in = sum(1 for r in rows if r["kind"] == IN_SCOPE)
        got_out = sum(1 for r in rows if r["kind"] == OUT_OF_SCOPE)
        assert got_in == want_in, f"{name} ({story}) has {got_in} in-scope, expected {want_in}"
        assert got_out == want_out, (
            f"{name} ({story}) has {got_out} out-of-scope, expected {want_out}"
        )


def test_no_batch_file_is_left_out_of_the_counts_table():
    """The table above is only a check while it lists every file.

    Without this, ST-35 could add batch 3 and forget the row, and the count
    check would go on passing while grading a set nobody counted. A table
    that silently ignores what it does not know about is not a check.
    """
    on_disk = {p.name for p in GOLDEN_DIR.glob("*.jsonl")}
    assert on_disk == EXPECTED_COUNTS.keys(), (
        f"golden files on disk {sorted(on_disk)} do not match the counts table "
        f"{sorted(EXPECTED_COUNTS)}"
    )


def test_the_running_total_never_passes_what_ST_35_freezes_at():
    """40 in-scope + 20 out-of-scope is PRD F-08, and G2 grades 20 of 20 on
    the second number. Going over it is as wrong as falling short: a 21st
    out-of-scope question makes the gate's own denominator a lie.
    """
    rows = _all_rows()
    in_scope = sum(1 for r in rows if r["kind"] == IN_SCOPE)
    out_of_scope = sum(1 for r in rows if r["kind"] == OUT_OF_SCOPE)
    assert in_scope <= FINAL_TOTAL_IN_SCOPE, f"{in_scope} in-scope questions, F-08 caps it at 40"
    assert out_of_scope <= FINAL_TOTAL_OUT_OF_SCOPE, (
        f"{out_of_scope} out-of-scope questions, G2 is written against 20"
    )


def test_every_batch_draws_on_every_document_in_the_hr_workspace():
    """Fifteen questions all pulled from the labour code would leave the two
    CNSS documents unmeasured, and retrieval could be broken for both without
    a single golden question noticing.

    This is the fixture-too-small-for-its-own-property shape that has now
    shipped five times on this project (ST-14, ST-16, ST-23, ST-24, ST-21).
    Here it would be a golden set too narrow for the corpus it grades.

    Held per BATCH rather than over the whole set on purpose: checking only
    the total would let a batch drift entirely onto the labour code as long
    as an earlier batch had covered the other two.
    """
    for name in EXPECTED_COUNTS:
        cited = {r["source_file"] for r in _rows(GOLDEN_DIR / name) if r["kind"] == IN_SCOPE}
        assert cited == {
            "code-travail-consolide-2011-justice.pdf",
            "dahir-1-72-184-securite-sociale-acaps.pdf",
            "cnss-regime-securite-sociale-cleiss.pdf",
        }, f"{name} leaves an HR document ungraded: {sorted(cited)}"
