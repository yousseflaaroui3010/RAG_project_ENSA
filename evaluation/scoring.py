"""The groundedness/relevancy judge (G1), behind one seam (ST-32).

Mirrors `agent/chat.py`'s pattern on purpose: one `Protocol` the runner
can be built and tested against with no RAGAS import anywhere in a test,
and exactly one real builder that is allowed to fail LOUDLY at build
time -- `agent.chat.ChatUnavailableError`'s pattern, named `Scorer
UnavailableError` here.

WHY THE REAL BUILDER CURRENTLY ALWAYS RAISES, said in the open rather
than left for a report full of blank numbers to discover. Verified by
RUNNING it against the exact pinned versions in this project's lockfile,
not from memory and not from RAGAS's own docs alone (docs/phase2/
CLAUDE.md's "prove it by running it" rule, and this project's rule that a
signed brief can itself be stale -- ST-32's own survey said "no
dependency conversation needed"; running the import shows that is wrong):

1. **`import ragas` itself raises `ModuleNotFoundError`, unconditionally,
   on this project's exact pins.** `ragas==0.4.3`'s `ragas/llms/base.py`
   imports `langchain_community.chat_models.vertexai.ChatVertexAI` at
   module load time. That submodule does not exist in
   `langchain-community==0.4.2` (what this project's lockfile actually
   resolves) -- VertexAI support moved to the standalone
   `langchain-google-vertexai` package as part of langchain-community's
   documented sunset. Filed upstream and reproduced independently here:
   ragas issues #2741, #2745 and #2753 (vibrantlabsai/ragas) all report
   the identical traceback. This is a broken pin, not a local
   misconfiguration, and it blocks every use of `ragas`, not only the
   Google-specific path.
2. **Past that import, RAGAS 0.4.x's current metric API does not accept
   this project's chat model.** `ragas.metrics.collections.Faithfulness`
   / `AnswerRelevancy` take a provider-native client through
   `ragas.llms.llm_factory`, not a LangChain chat model -- `agent.chat.
   ChatModel` (this whole project's model seam, ADR-06) does not fit
   that shape. `llm_factory`'s own docstring routes Google/Gemini through
   `litellm`, which is not a dependency this project declares.
3. **`AnswerRelevancy` additionally needs an `embedding_factory` client.**
   Nothing in this project has verified that the local
   `intfloat/multilingual-e5-base` embedder (`config.embedding_model`,
   already loaded for retrieval) can be handed to it, or whether a second,
   separate embeddings client would have to be built and paid for.

None of the three is a "code around it" problem. (1) is a broken
dependency pin needing a version decision. (2) and (3) are unmade design
decisions about which adapter Sanad's own model and embedder count as to
RAGAS -- guessing at either would be a second, unreviewed implementation
of ADR-06's "one configuration point", exactly what this project's core
law says to escalate rather than improvise. See docs/journal/
BUILD-STATE.md's ST-32 entry and DECISIONS.md, 2026-09-05.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class ScorerUnavailableError(Exception):
    """The configured scorer cannot be built. Raised at BUILD time, before
    any of the golden set's questions run, so a broken dependency reads as
    one sentence in the terminal rather than sixty blank scores."""


@dataclass(frozen=True)
class ScoreResult:
    """RAGAS's two per-question numbers. Both 0.0-1.0 (architecture 7.1's
    `score` neutral type)."""

    groundedness: float
    relevancy: float


class Scorer(Protocol):
    """What the runner needs from RAGAS, and nothing else -- narrowed the
    same way `agent.chat.ChatModel` narrows the model seam, so a test
    double can satisfy it with no RAGAS import anywhere in a test file."""

    def score(
        self, *, question: str, answer_text: str, contexts: Sequence[str]
    ) -> ScoreResult:
        """`contexts` must be the section text the writer actually read
        (`evaluation.capture.Captured.contexts`), never the wider set
        retrieval found -- see that module's docstring for why scoring
        the wider set would measure a document the model never saw."""
        ...


def build_ragas_scorer() -> Scorer:
    """The real scorer. See the module docstring: this currently always
    raises. Left as the one seam whoever resolves the escalation fills in
    -- not a fake that would let a report show numbers nothing computed,
    which is the exact "stub that answers plausibly" agent/ports.py's own
    docstring calls the most dangerous object in this project."""
    raise ScorerUnavailableError(
        "ragas 0.4.3 cannot be imported against this project's pinned "
        "langchain-community (0.4.2): ragas/llms/base.py imports "
        "langchain_community.chat_models.vertexai.ChatVertexAI, a module "
        "that version no longer carries (upstream bug -- ragas issues "
        "#2741, #2745, #2753). Fixing the import still leaves two unmade "
        "design decisions: which adapter carries this project's Gemini "
        "chat model and its local e5 embedder into ragas's provider-based "
        "factories. See docs/journal/BUILD-STATE.md's ST-32 entry and "
        "DECISIONS.md, 2026-09-05, for the numbered options."
    )
