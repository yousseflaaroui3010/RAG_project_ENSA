"""ST-23: ADR-06's two model modes, selected by one config value.

Reference: ADR-06 ("a single configuration point selects the chat model.
Cloud-key mode uses the team's API key ... strict-local mode runs a local
model through the same interface"), and docs/phase2/ENGINEERING-RULES.md's hard rule
that no test carries an API key.

NOTHING HERE INVOKES A MODEL, and that stays true even though a cloud key
now exists on the build machine. ADR-12 forbids keys in CI outright, so a
test that called a provider would pass on one laptop and fail in the gate
-- which is worse than not testing it. Every test asserts on the object
that was BUILT (its class, and the model name it was given) and stops.

WHAT THESE TESTS PROVE: the config value selects the right provider, and
a misconfiguration fails with a sentence a human can act on.
WHAT THEY CANNOT: that the provider answers. That was proven separately,
by hand, on 2026-08-27 -- and it immediately found what no test here
could, because the fault was not in the code: the pinned model name had
been RETIRED by Google, and every call returned 404. See config.py.
"""

from __future__ import annotations

import httpx
import pytest

import agent.chat
from agent.chat import (
    CLOUD,
    STRICT_LOCAL,
    ChatUnavailableError,
    _LangChainChat,
    build_chat_model,
)
from config import get_settings


def _with_settings(monkeypatch, **overrides):
    settings = get_settings().model_copy(update=overrides)
    monkeypatch.setattr(agent.chat, "get_settings", lambda: settings)
    return settings


def test_cloud_mode_builds_a_google_ai_studio_model_not_a_vertex_one(monkeypatch):
    """The trap this module exists to avoid, pinned.

    `init_chat_model("gemini-2.0-flash")` with no provider infers
    `google_vertexai` -- a different product, a different auth story, and a
    package this project does not depend on. Asserting the concrete class
    is what stops a future "simplification" to `init_chat_model` from
    silently pointing at Vertex."""
    _with_settings(
        monkeypatch, model_mode=CLOUD, cloud_api_key="not-a-real-key",
        chat_model_cloud="gemini-3.6-flash",
    )
    from langchain_google_genai import ChatGoogleGenerativeAI

    chat = build_chat_model()

    assert isinstance(chat, _LangChainChat)
    assert isinstance(chat._model, ChatGoogleGenerativeAI)
    assert chat._model.model.endswith("gemini-3.6-flash")


def test_strict_local_mode_builds_an_ollama_model_at_the_configured_url(monkeypatch):
    """ADR-06's offline path and risk R4's fallback. Asserted at a
    NON-DEFAULT url and model, so a builder that ignored config and
    hardcoded the defaults fails here."""
    _with_settings(
        monkeypatch, model_mode=STRICT_LOCAL, chat_model_local="qwen2.5:7b",
        ollama_base_url="http://127.0.0.1:9999",
    )
    from langchain_ollama import ChatOllama

    chat = build_chat_model()

    assert isinstance(chat._model, ChatOllama)
    assert chat._model.model == "qwen2.5:7b"
    assert chat._model.base_url == "http://127.0.0.1:9999"


def test_cloud_mode_applies_the_configured_timeout_and_retry_ceiling(monkeypatch):
    """A stalled network call must not hang a question forever, and Cancel
    must have something to cancel (PRD section 11). Compared against
    LITERAL numbers set here, not the config defaults, so a builder that
    ignores config and just relies on the provider's own default (timeout
    None, max_retries 6) would still fail this."""
    _with_settings(
        monkeypatch, model_mode=CLOUD, cloud_api_key="not-a-real-key",
        model_call_timeout_seconds=12.5, model_call_max_retries=4,
    )

    chat = build_chat_model()

    assert chat._model.timeout == 12.5
    # The Gemini client's max_retries counts TOTAL attempts
    # (HttpRetryOptions(attempts=max_retries)); 4 retries means 5 tries.
    assert chat._model.max_retries == 5


def test_strict_local_mode_applies_the_configured_timeout(monkeypatch):
    """ChatOllama has no `timeout` field of its own (checked its
    model_fields directly); the value has to reach `ollama.Client` through
    `client_kwargs`, which is the mechanism this asserts."""
    _with_settings(
        monkeypatch, model_mode=STRICT_LOCAL, model_call_timeout_seconds=17.0,
    )

    chat = build_chat_model()

    assert chat._model.client_kwargs.get("timeout") == 17.0


def test_cloud_mode_without_a_key_says_so_before_any_call_is_made(monkeypatch):
    """The out-of-the-box experience, because `model_mode` defaults to
    `cloud` and a fresh clone has no key -- not an edge case, the first
    thing a new teammate hits.

    It fails at BUILD time with a sentence naming both ways out. The
    alternative is a provider's 401 arriving three nodes into an answer,
    which reads like the corpus failing rather than the setup being
    incomplete."""
    _with_settings(monkeypatch, model_mode=CLOUD, cloud_api_key="")

    with pytest.raises(ChatUnavailableError) as caught:
        build_chat_model()

    message = str(caught.value)
    assert "CLOUD_API_KEY" in message
    assert STRICT_LOCAL in message, "the error must name the other way out"


def test_a_mode_that_is_not_one_of_the_two_names_both(monkeypatch):
    """ADR-06 defines exactly two modes. A typo in `.env` should not
    silently fall back to either one -- picking a default here would mean
    a machine intended to be offline quietly reaching for a cloud key."""
    _with_settings(monkeypatch, model_mode="local")

    with pytest.raises(ChatUnavailableError) as caught:
        build_chat_model()

    message = str(caught.value)
    assert "'local'" in message
    assert CLOUD in message and STRICT_LOCAL in message


# --- the adapter -------------------------------------------------------


class _Reply:
    def __init__(self, content):
        self.content = content


class _RecordingModel:
    def __init__(self, reply):
        self.reply = reply
        self.messages = None

    def invoke(self, messages):
        self.messages = messages
        return self.reply


class _TimingOutModel:
    """Stands in for a provider whose retries are exhausted: both
    ChatGoogleGenerativeAI (reraise=True in google.genai's tenacity retry)
    and ChatOllama (no timeout handling at all in ollama._client) let this
    exact exception type escape `invoke()` unchanged."""

    def invoke(self, messages):
        raise httpx.ReadTimeout("timed out")


def test_a_provider_timeout_is_mapped_to_the_unreachable_error(monkeypatch):
    """PRD section 11: "answering service unreachable -> clear error and a
    retry action". Without a timeout wrapped here, this exception would hit
    api/routes.py's generic `except Exception` and come back as an
    unexplained 500 -- or, in the UI, print raw httpx internals verbatim
    (ui/conversation.py shows an error's own text as the offending value)."""
    with pytest.raises(ChatUnavailableError) as caught:
        _LangChainChat(_TimingOutModel()).complete("s", "u")

    message = str(caught.value)
    assert "did not respond in time" in message
    # Never the provider's own exception text (could carry request internals).
    assert "httpx" not in message and "ReadTimeout" not in message


@pytest.mark.parametrize(
    "error",
    [
        httpx.ConnectError("[Errno 11001] getaddrinfo failed"),
        ConnectionError("Failed to connect to Ollama"),
    ],
    ids=["cloud-no-network", "ollama-not-running"],
)
def test_an_unreachable_provider_is_mapped_to_the_unreachable_error(error):
    """The commonest unreachable case -- no network, or Ollama not running
    -- escaped as an unexpected 500 before (review of 7ebc552). Gemini
    re-raises httpx.ConnectError; the ollama client raises the builtin
    ConnectionError."""

    class _Unreachable:
        def invoke(self, _messages):
            raise error

    with pytest.raises(ChatUnavailableError) as caught:
        _LangChainChat(_Unreachable()).complete("s", "u")

    message = str(caught.value)
    assert "could not be reached" in message
    assert "getaddrinfo" not in message and "Failed to connect" not in message


def test_the_adapter_sends_a_system_message_and_a_human_message():
    """The seam's whole shape is (system, user) -> text. A model handed
    one merged blob follows instructions worse, and the grader's
    instructions are the reason it answers one word."""
    model = _RecordingModel(_Reply("RELEVANT"))

    text = _LangChainChat(model).complete("you judge passages", "is this relevant?")

    assert text == "RELEVANT"
    assert model.messages == [
        ("system", "you judge passages"),
        ("human", "is this relevant?"),
    ]


def test_content_returned_as_a_list_of_parts_is_joined_not_stringified():
    """Some providers return content as a list of parts. `str()` on that
    list would send Python repr syntax -- brackets, quotes, the word
    'text' -- into a parser that is looking for one word."""
    model = _RecordingModel(_Reply([{"type": "text", "text": "OFF_"}, "TOPIC"]))

    assert _LangChainChat(model).complete("s", "u") == "OFF_TOPIC"


def test_a_model_returning_something_that_is_not_text_fails_loudly():
    """Text in, text out. A provider handing back a structure means this
    seam's assumption is wrong, and that should be a named error rather
    than a repr flowing downstream."""
    model = _RecordingModel(_Reply({"unexpected": "shape"}))

    with pytest.raises(ChatUnavailableError, match="not text"):
        _LangChainChat(model).complete("s", "u")
