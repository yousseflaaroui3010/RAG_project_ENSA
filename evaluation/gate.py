"""ST-33: the release gate. Reads an ST-32 evaluation report (the exact
JSON shape `evaluation.runner.EvalReport.to_json()` writes -- nothing here
changes that shape) and decides the release process's exit code, which is
the one thing that module's own docstring says is deliberately NOT its
job: "the release gate's PROCESS EXIT CODE... BUILD-PLAN splits that to
ST-33 ... which reads this same report and ... can apply its own policy."

THE THREE THRESHOLDS, named once, read from nowhere else (PRD section 3
"Goals and success metrics" -- G1/G2/G3 -- and LD-04, both docs/phase2/,
signed and write-locked):
  G1 fully grounded answers / in-scope rows >= threshold (config; 0.90 today)
  G2 refusals      refusal_pass == refusal_total, and refusal_total > 0
  G3 sources       every row whose answer_kind is "answer" has a source

The ">0" half of G2 matters: an eval run with zero out-of-scope rows must
not pass by vacuous truth. G3 applies only to answers; a run with no answers
already fails G1, while refusals are not source failures. This mirrors
`evaluation.runner._aggregate` exactly.

WHY THIS RECOMPUTES RATHER THAN JUST TRUSTING `report["passed"]`: that
field already applies these same thresholds, so the two only differ on a
report that was hand-built, corrupted, or edited after the fact -- exactly
the case a release gate exists to catch on its own rather than take the
file's word for it. Recomputing also lets this module name WHICH gate
missed and WHICH questions, which a single flat `passed` bit cannot: F-08
says "the release is blocked and the failing questions are listed", and
"failing questions" has to mean something more precise than "some question
somewhere failed something".
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from config import get_settings
from evaluation import FULLY_GROUNDED_SCORE
from evaluation.golden import load_golden_set


class InvalidReportError(ValueError):
    """The report is not one result for every frozen golden question."""


@dataclass(frozen=True)
class GateVerdict:
    """One evaluation report's release-gate outcome. `*_failing` name the
    golden-set question ids that missed THAT specific gate."""

    passed: bool
    g1_passed: bool
    g2_passed: bool
    g3_passed: bool
    grounded_pass: int
    grounded_total: int
    refusal_pass: int
    refusal_total: int
    sources_pass: int
    sources_total: int
    g1_failing: tuple[str, ...]
    g2_failing: tuple[str, ...]
    g3_failing: tuple[str, ...]

    @property
    def failing_question_ids(self) -> tuple[str, ...]:
        """Every id that missed at least one gate, de-duplicated, order
        preserved from first appearance -- G1 rows, then G2, then G3."""
        seen: list[str] = []
        for question_id in (*self.g1_failing, *self.g2_failing, *self.g3_failing):
            if question_id not in seen:
                seen.append(question_id)
        return tuple(seen)


def evaluate_report(
    report: dict[str, Any],
    *,
    expected_question_ids: Sequence[str] | None = None,
    expected_question_kinds: Mapping[str, str] | None = None,
) -> GateVerdict:
    """Apply the three PRD thresholds to one parsed report dict (the
    output of `json.loads` on a file `evaluation.runner.run_evaluation`
    wrote, or an equivalent hand-built fixture in a test).

    Raises `KeyError` if the report is missing a required field, or
    `InvalidReportError` if rows are missing, extra, duplicated, or reordered.
    A partial report must stop loudly rather than pass as 1/1."""
    threshold = get_settings().eval_groundedness_threshold
    results = report["results"]
    golden_rows = load_golden_set() if (
        expected_question_ids is None or expected_question_kinds is None
    ) else ()
    expected = (
        tuple(expected_question_ids)
        if expected_question_ids is not None
        else tuple(row.id for row in golden_rows)
    )
    expected_kinds = (
        dict(expected_question_kinds)
        if expected_question_kinds is not None
        else {row.id: row.kind for row in golden_rows}
    )
    observed = tuple(row["question_id"] for row in results)
    if observed != expected:
        counts = Counter(observed)
        expected_set = set(expected)
        observed_set = set(observed)
        missing = tuple(question_id for question_id in expected if question_id not in observed_set)
        extra = tuple(question_id for question_id in observed if question_id not in expected_set)
        duplicates = tuple(
            question_id for question_id, count in counts.items() if count > 1
        )
        problems: list[str] = []
        if missing:
            problems.append(f"missing {', '.join(missing)}")
        if extra:
            problems.append(f"extra {', '.join(dict.fromkeys(extra))}")
        if duplicates:
            problems.append(f"duplicate {', '.join(duplicates)}")
        if not problems:
            problems.append("rows are out of frozen-set order")
        raise InvalidReportError(
            "report rows do not match the frozen golden set: " + "; ".join(problems)
        )

    wrong_kinds = tuple(
        f"{row['question_id']} expected {expected_kinds[row['question_id']]} "
        f"but got {row.get('kind')!r}"
        for row in results
        if row.get("kind") != expected_kinds[row["question_id"]]
    )
    if wrong_kinds:
        raise InvalidReportError(
            "report row kind does not match the frozen golden set: "
            + "; ".join(wrong_kinds)
        )

    for row in results:
        for field in ("groundedness", "relevancy"):
            value = row.get(field)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0.0 <= value <= 1.0
            ):
                raise InvalidReportError(
                    f"report row {row['question_id']} has invalid {field} "
                    f"score {value!r}; expected null or a number from 0.0 to 1.0"
                )

    in_scope = [r for r in results if r.get("kind") == "in_scope"]
    g1_failing = tuple(
        r["question_id"]
        for r in in_scope
        if r.get("answer_kind") != "answer"
        or r.get("groundedness") != FULLY_GROUNDED_SCORE
    )
    grounded_pass = len(in_scope) - len(g1_failing)
    g1_passed = bool(in_scope) and grounded_pass / len(in_scope) >= threshold
    out_of_scope = [r for r in results if r.get("kind") == "out_of_scope"]
    g2_failing = tuple(
        r["question_id"]
        for r in out_of_scope
        if r.get("answer_kind") != "refusal"
    )
    g2_passed = bool(out_of_scope) and not g2_failing
    answer_rows = [r for r in results if r.get("answer_kind") == "answer"]
    g3_failing = tuple(
        r["question_id"] for r in answer_rows if r.get("sources_present") is not True
    )
    g3_passed = not g3_failing
    refusal_pass = len(out_of_scope) - len(g2_failing)
    sources_pass = len(answer_rows) - len(g3_failing)

    return GateVerdict(
        passed=g1_passed and g2_passed and g3_passed,
        g1_passed=g1_passed,
        g2_passed=g2_passed,
        g3_passed=g3_passed,
        grounded_pass=grounded_pass,
        grounded_total=len(in_scope),
        refusal_pass=refusal_pass,
        refusal_total=len(out_of_scope),
        sources_pass=sources_pass,
        sources_total=len(answer_rows),
        g1_failing=g1_failing,
        g2_failing=g2_failing,
        g3_failing=g3_failing,
    )
