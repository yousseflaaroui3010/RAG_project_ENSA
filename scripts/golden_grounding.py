"""Check the golden set's claims against the real corpus (ST-19).

    uv run python scripts/golden_grounding.py

`tests/unit/test_golden_set.py` checks the SHAPE of the golden set. This
checks whether it is TRUE. The two are separate because `data/` is
git-ignored: a pytest that reads the corpus would skip on CI and prove
nothing, and a check that skips itself is untested, not passing.

Two opposite questions, one per half of the file:

- **in scope:** does `corpus_probe` appear in the document the row cites?
  If not, either the reference answer drifted from the text or the corpus
  was refetched into a different edition.
- **out of scope:** does `corpus_probe` appear ANYWHERE in the workspace?
  If it does, the question is answerable and calling it out-of-scope will
  cost a release gate: PRD G2 demands 20 refusals out of 20.

WHY THIS SCRIPT EXISTS AT ALL, and it is not tidiness. The first pass of
absence checks for ST-19 was run with `grep -E "pr.avis"`. In a non-UTF-8
locale `.` matches one BYTE and `é` is two, so the pattern cannot match
`préavis` -- and grep reported ZERO occurrences in a document that holds
forty. Four out-of-scope questions were about to be written on that zero.
A route that cannot see returns exactly what a true absence returns, so
absence is only worth believing from a route that has been shown to find
something. Hence `--self-test` below, which is not optional decoration:
it fails the run if the matcher cannot find a string known to be present.

Exit code 0 only when every row checks out, so this can be pasted into a
gate later without rewriting it.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import conversion  # noqa: E402

GOLDEN_DIR = REPO_ROOT / "evaluation" / "golden"
CORPUS = REPO_ROOT / "data" / "corpus"

# A string every one of the three HR documents contains, used to prove the
# matcher can see before any of its "not found" answers are believed. It
# carries an accent on purpose: the accent is what the broken route missed.
CONTROL_PROBE = "salarié"


def fold(text: str) -> str:
    """Strip accents and normalise both apostrophes, on BOTH sides of every
    comparison.

    The three PDFs do not agree with each other: the CNSS dahir renders the
    apostrophe as U+02BC MODIFIER LETTER APOSTROPHE, the labour code as a
    plain one, and the CLEISS guide uses U+2019. A probe typed by a human
    will match none of the three reliably unless they are folded together.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return stripped.replace("ʼ", "'").replace("’", "'").lower()


def load_corpus(workspace: str) -> dict[str, str]:
    """Convert every file of one workspace through the real ladder.

    Deliberately the SAME converter the product uses (`conversion.py`,
    ST-13) rather than a second PDF reader written here. A check that reads
    the documents differently from the way the product reads them can pass
    while the product sees something else entirely.
    """
    folder = CORPUS / workspace
    if not folder.is_dir():
        raise SystemExit(
            f"no corpus at {folder}.\n"
            "data/ is git-ignored. Rebuild it with:\n"
            "    uv run python scripts/corpus.py fetch"
        )
    texts: dict[str, str] = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file():
            continue
        result = conversion.convert_file(path)
        if not result.converted or result.markdown is None:
            print(f"  ! {path.name}: {result.outcome} -- {result.reason}")
            continue
        texts[path.name] = fold(result.markdown)
    return texts


def self_test(texts: dict[str, str]) -> list[str]:
    """Prove the matcher can find something before trusting it not to."""
    failures = []
    probe = fold(CONTROL_PROBE)
    for name, body in texts.items():
        if probe not in body:
            failures.append(
                f"CONTROL PROBE FAILED: {CONTROL_PROBE!r} not found in {name}. "
                "The matcher is blind; every 'absent' result below is meaningless."
            )
    return failures


def check(rows: list[dict], texts: dict[str, str]) -> list[str]:
    failures = []
    for row in rows:
        probe = fold(row["corpus_probe"])
        if row["kind"] == "in_scope":
            source = row["source_file"]
            body = texts.get(source)
            if body is None:
                failures.append(f"{row['id']}: cites {source}, which is not in the workspace")
            elif probe not in body:
                failures.append(
                    f"{row['id']}: {row['corpus_probe']!r} is NOT in {source} "
                    f"({row['source_article']}). The reference answer may have drifted."
                )
            else:
                print(f"  ok  {row['id']}  grounded in {source} / {row['source_article']}")
        else:
            hits = {name: body.count(probe) for name, body in texts.items()}
            total = sum(hits.values())
            if total:
                where = ", ".join(f"{n}={c}" for n, c in hits.items() if c)
                failures.append(
                    f"{row['id']}: {row['corpus_probe']!r} IS in the corpus ({where}). "
                    "This question is answerable and must not be scored as out-of-scope."
                )
            else:
                print(f"  ok  {row['id']}  {row['corpus_probe']!r} absent from all "
                      f"{len(texts)} files")
    return failures


def main() -> int:
    rows = [
        json.loads(line)
        for path in sorted(GOLDEN_DIR.glob("*.jsonl"))
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    workspaces = sorted({row["workspace"] for row in rows})
    failures: list[str] = []

    for workspace in workspaces:
        print(f"\nworkspace {workspace!r}")
        texts = load_corpus(workspace)
        print(f"  {len(texts)} files converted")

        control = self_test(texts)
        if control:
            failures.extend(control)
            continue
        print(f"  control probe {CONTROL_PROBE!r} found in all {len(texts)} files")

        failures.extend(check([r for r in rows if r["workspace"] == workspace], texts))

    print()
    if failures:
        print(f"FAILED: {len(failures)} of {len(rows)} rows")
        for line in failures:
            print(f"  - {line}")
        return 1
    in_scope = sum(1 for r in rows if r["kind"] == "in_scope")
    print(f"OK: {len(rows)} rows grounded ({in_scope} in scope, {len(rows) - in_scope} out)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
