"""The chat-model seam (ADR-06), built by ST-23 because nothing owned it.

ADR-06 requires "a single configuration point selects the chat model",
with cloud-key mode for answer quality and strict-local mode for full
data locality and the offline demo fallback (risk R4). That interface did
not exist anywhere in the repo: checked by graph search, by a project-wide
grep for `langchain|chat_model|ChatGoogle|ChatOllama|init_chat_model`
across every `*.py` (which found only `config.py` lines 32 and 34, the
model NAMES), and by reading every row of BUILD-PLAN, where no story owns
it. ST-23 is simply the first story that needs a model, so it lands here.
Recorded as a DECISIONS row rather than absorbed quietly.

WHAT THIS SEAM IS, and why it is this narrow. One method:

    complete(system, user) -> str

Not a `BaseChatModel`, and that is the load-bearing choice. Passing the
langchain object through would let the grader use
`with_structured_output`, which is more reliable against a real cloud
model -- and it would be UNTESTABLE here, because
docs/phase2/CLAUDE.md's hard rule is "tests use the scripted fake chat
model; no API keys in tests, fixtures, or CI", and langchain's own fakes
cannot do structured output: `bind_tools` raises `NotImplementedError` on
any model that does not override it
(`langchain_core/language_models/chat_models.py:2510`). A seam the
mandated test double cannot satisfy is a seam that gets tested by
pretending. So Sanad owns a one-word verdict and parses it (see
`agent/grading.py`), and the cost -- we own the parser -- is accepted in
writing.

It is also the right floor for ADR-06's local mode: a one-word reply is
the smallest thing a 7B instruct model can be relied on to produce, and
7B is the floor ADR-06 sets.

THE TRAP THIS FILE EXISTS TO AVOID, read out of the installed package
rather than remembered: `init_chat_model("gemini-2.0-flash")` with no
provider does NOT infer Google AI Studio. It infers `google_vertexai`
(`langchain/chat_models/base.py:563`), which is a different product, a
different auth story, and a package this project does not depend on. The
one-line provider swap ADR-06 admires is real, but only with the provider
named explicitly. Here each mode names its own class, so the inference
never runs.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from config import get_settings

# ADR-06's two modes, as the config values that select them.
CLOUD = "cloud"
STRICT_LOCAL = "strict_local"


class ChatUnavailableError(Exception):
    """The configured mode cannot produce a usable model.

    Raised at BUILD time, not at call time, so a missing key is a clear
    sentence in the terminal rather than a provider's 401 three nodes into
    an answer."""


class ChatModel(Protocol):
    """What the agent needs from a model, and nothing else."""

    def complete(self, system: str, user: str) -> str:
        """One turn: a system message and a user message in, text out."""
        ...


class _LangChainChat:
    """Adapts a langchain chat model to the one method above.

    Deliberately thin. Everything langchain-specific in the answering path
    is in this class and the two builders below, so swapping the framework
    later is a file, not a search."""

    def __init__(self, model: Any) -> None:
        self._model = model

    def complete(self, system: str, user: str) -> str:
        response = self._model.invoke(
            [("system", system), ("human", user)]
        )
        text = getattr(response, "content", response)
        if isinstance(text, list):
            # Some providers return content as a list of parts. Join the
            # text ones rather than str() the list, which would send
            # Python repr syntax downstream to a parser.
            text = "".join(
                part if isinstance(part, str) else part.get("text", "")
                for part in text
            )
        if not isinstance(text, str):
            raise ChatUnavailableError(
                f"the model returned {type(text).__name__}, not text. This "
                f"seam is text in, text out (ADR-06)."
            )
        return text


def _build_cloud() -> ChatModel:
    """Google Gemini through Google AI Studio (ADR-06 cloud mode)."""
    from langchain_google_genai import ChatGoogleGenerativeAI

    settings = get_settings()
    if not settings.cloud_api_key:
        raise ChatUnavailableError(
            f"model_mode is {CLOUD!r} but CLOUD_API_KEY is empty. Put a "
            f"Google AI Studio key in .env, or set MODEL_MODE="
            f"{STRICT_LOCAL!r} to run a local model through Ollama "
            f"instead (ADR-06 keeps both doors open)."
        )
    return _LangChainChat(
        ChatGoogleGenerativeAI(
            model=settings.chat_model_cloud,
            api_key=settings.cloud_api_key,
        )
    )


def _build_strict_local() -> ChatModel:
    """A local instruct model through Ollama (ADR-06 strict-local mode).

    No key, no egress: this is the mode that makes LD-06's locality answer
    true without depending on a vendor's terms page."""
    from langchain_ollama import ChatOllama

    settings = get_settings()
    return _LangChainChat(
        ChatOllama(
            model=settings.chat_model_local,
            base_url=settings.ollama_base_url,
        )
    )


# One entry per ADR-06 mode. A third provider is a line here plus a config
# value, which is the "single configuration point" the ADR asks for.
_BUILDERS: dict[str, Callable[[], ChatModel]] = {
    CLOUD: _build_cloud,
    STRICT_LOCAL: _build_strict_local,
}


def build_chat_model() -> ChatModel:
    """The configured model, constructed now.

    Nothing calls this at import time and nothing caches it here: the
    caller that owns the model's lifetime decides, exactly as the caller
    owns the Qdrant client's lifetime (see `agent/ports.py`). A module
    that quietly held a singleton would make the mode impossible to change
    in a test without reaching into private state."""
    mode = get_settings().model_mode
    builder = _BUILDERS.get(mode)
    if builder is None:
        raise ChatUnavailableError(
            f"model_mode is {mode!r}, which is not a mode. ADR-06 defines "
            f"exactly two: {CLOUD!r} for the hosted model and "
            f"{STRICT_LOCAL!r} for a local one."
        )
    return builder()
