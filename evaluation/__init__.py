"""The evaluation package (F-08): golden set, runner, RAGAS scoring.

`evaluation/golden/` is data and belongs to MB (docs/phase2/CLAUDE.md line
26). The Python modules beside it (`golden.py`, `capture.py`, `scoring.py`,
`runner.py`) are ST-32's: the machine that runs the golden set through the
real product and writes the dated report architecture 5.3 describes.
"""

from __future__ import annotations

# `eval-judge` defines groundedness as the fraction of supported factual
# claims. Only 1.0 therefore means every claim is grounded. This is a metric
# definition, not an operator setting.
FULLY_GROUNDED_SCORE = 1.0
