"""Loads golden-set rows for the evaluation runner (ST-32, F-08).

`evaluation/golden/README.md` owns the schema and `evaluation/golden/`
belongs to MB (docs/phase2/CLAUDE.md line 26: "only touch it when the
story says so"). This module only READS what is on disk there -- it does
not police freeze rules, running totals, ids, or the French-language
check. Those all already exist in `tests/unit/test_golden_set.py`, which
is the schema's own gate and runs on every PR. Duplicating any of that
logic here would be a second place it could drift from the first (core
law: two copies is fine, three needs a written reason), and this module
does not need to re-police a set another test already polices -- it needs
to run whatever the folder currently holds.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

IN_SCOPE = "in_scope"
OUT_OF_SCOPE = "out_of_scope"

# Same folder `tests/unit/test_golden_set.py::GOLDEN_DIR` points at.
DEFAULT_GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


@dataclass(frozen=True)
class GoldenRow:
    """One line of one `evaluation/golden/*.jsonl` file.

    The six signed fields (architecture section 14) plus the three local
    ones the README records (DECISIONS 2026-08-30): `workspace`,
    `corpus_probe`, `notes`. `corpus_probe` is loaded but unused here --
    it is `scripts/golden_grounding.py`'s field, not the runner's."""

    id: str
    question: str
    reference_answer: str
    source_file: str | None
    source_article: str | None
    kind: str
    workspace: str
    corpus_probe: str
    notes: str | None = None

    @property
    def is_in_scope(self) -> bool:
        return self.kind == IN_SCOPE


def _row_from_json(data: dict) -> GoldenRow:
    return GoldenRow(
        id=data["id"],
        question=data["question"],
        reference_answer=data["reference_answer"],
        source_file=data["source_file"],
        source_article=data["source_article"],
        kind=data["kind"],
        workspace=data["workspace"],
        corpus_probe=data["corpus_probe"],
        notes=data.get("notes"),
    )


def load_golden_set(golden_dir: Path | None = None) -> tuple[GoldenRow, ...]:
    """Every row of every `*.jsonl` file in `golden_dir`, in file-name then
    file-order -- the same traversal `test_golden_set.py::_all_rows` uses,
    so "every row in the folder" means one thing in both places.

    Deliberately does not validate schema, counts, or the freeze: a
    malformed row is caught by `tests/unit/test_golden_set.py` in the
    gate, before this ever runs against a real model. Raises if the
    folder holds no rows at all, since a report over zero questions is
    not a report anything can gate a release on."""
    directory = golden_dir if golden_dir is not None else DEFAULT_GOLDEN_DIR
    rows: list[GoldenRow] = []
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rows.append(_row_from_json(json.loads(line)))
    if not rows:
        raise ValueError(f"no golden-set rows found in {directory}")
    return tuple(rows)
