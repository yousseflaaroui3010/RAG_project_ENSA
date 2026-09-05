"""ST-33: the release gate. Reads an ST-32 evaluation report (the exact
JSON shape `evaluation.runner.EvalReport.to_json()` writes -- nothing here
changes that shape) and decides the release process's exit code, which is
the one thing that module's own docstring says is deliberately NOT its
job: "the release gate's PROCESS EXIT CODE... BUILD-PLAN splits that to
ST-33 ... which reads this same report and ... can apply its own policy."

THE THREE THRESHOLDS, named once, read from nowhere else (PRD section 3
"Goals and success metrics" -- G1/G2/G3 -- and LD-04, both docs/phase2/,
signed and write-locked):
  G1 groundedness  >= EVAL_GROUNDEDNESS_THRESHOLD (config; 0.90 today)
  G2 refusals      refusal_pass == refusal_total, and refusal_total > 0
  G3 sources       sources_pass == sources_total, and sources_total > 0

The ">0" half of G2 and G3 matters: an eval run with zero out-of-scope
rows, or zero rows for which a source could even apply, must not pass by
vacuous truth (0 == 0). This mirrors `evaluation.runner._aggregate`'s own
`g2`/`g3` booleans exactly, so on any report actually produced by
`run_evaluation` this module's verdict and the report's own `passed` field
agree.

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

from dataclasses import dataclass
from typing import Any

from config import get_settings

# G2 wants 20 of 20; G3 wants every answer sourced. Both are fixed PRD
# fractions, not configurable the way G1's threshold is (architecture
# never gives G2/G3 a settings field), so they are named constants here
# rather than a second settings entry for numbers that never move.
REQUIRED_REFUSAL_RATE = 1.0
REQUIRED_SOURCE_RATE = 1.0


@dataclass(frozen=True)
class GateVerdict:
    """One evaluation report's release-gate outcome. `*_failing` name the
    golden-set question ids that missed THAT specific gate; a row can
    appear under more than one (an in-scope question that got refused
    misses both G1 and G3 at once, since it was never scored and never
    carried a source)."""

    passed: bool
    g1_passed: bool
    g2_passed: bool
    g3_passed: bool
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


def evaluate_report(report: dict[str, Any]) -> GateVerdict:
    """Apply the three PRD thresholds to one parsed report dict (the
    output of `json.loads` on a file `evaluation.runner.run_evaluation`
    wrote, or an equivalent hand-built fixture in a test).

    Raises `KeyError` if the report is missing a required field -- a
    malformed report must stop the gate loudly, never be read as a
    silent pass."""
    threshold = get_settings().eval_groundedness_threshold
    groundedness = report.get("groundedness")
    refusal_pass = report["refusal_pass"]
    refusal_total = report["refusal_total"]
    sources_pass = report["sources_pass"]
    sources_total = report["sources_total"]
    results = report.get("results", [])

    g1_passed = groundedness is not None and groundedness >= threshold
    g2_passed = refusal_total > 0 and (refusal_pass / refusal_total) >= REQUIRED_REFUSAL_RATE
    g3_passed = sources_total > 0 and (sources_pass / sources_total) >= REQUIRED_SOURCE_RATE

    g1_failing = tuple(
        r["question_id"]
        for r in results
        if r.get("kind") == "in_scope" and not r.get("passed")
    )
    g2_failing = tuple(
        r["question_id"]
        for r in results
        if r.get("kind") == "out_of_scope" and not r.get("passed")
    )
    g3_failing = tuple(
        r["question_id"] for r in results if r.get("sources_present") is False
    )

    return GateVerdict(
        passed=g1_passed and g2_passed and g3_passed,
        g1_passed=g1_passed,
        g2_passed=g2_passed,
        g3_passed=g3_passed,
        g1_failing=g1_failing,
        g2_failing=g2_failing,
        g3_failing=g3_failing,
    )
