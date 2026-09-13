"""S6: the answer writer streams to a listener without changing a decision.

Three promises, each with its own test group:

1. Nobody listening -> the old path: ONE `complete` call, no stream.
2. Somebody listening -> the listener sees growing prefixes of the reply,
   and the port still RETURNS (or declines with) exactly what `complete`
   would have produced.
3. A decline is never shown while it is being written, and a listener
   that raises (Cancel) closes the model's stream.
"""

from __future__ import annotations

import httpx
import pytest

from agent import streaming
from agent.answering import STREAM_HOLD_CHARS, build_write_answer
from agent.chat import ChatUnavailableError, _LangChainChat
from agent.ports import AnswerNotCoveredError
from vector_store import SearchHit

HIT = SearchHit(
    parent_id="p-1",
    source_file="code-du-travail.pdf",
    section_label="Article 13",
    chunk_text="extrait",
    score=0.9,
)
PARENTS = {"p-1": "Article 13. La periode d'essai est de trois mois pour les cadres."}
QUESTION = "Quelle est la duree de la periode d'essai ?"
LONG_ANSWER = (
    "**Article 13** fixe la periode d'essai a trois mois pour les cadres, "
    "renouvelable une seule fois."
)


class StreamingFake:
    """A model with both methods, recording which one was used, how many
    pieces the stream handed out, and whether the stream was closed."""

    def __init__(self, reply: str, piece: int = 7):
        self.reply = reply
        self.piece = piece
        self.completed = 0
        self.streamed = 0
        self.pieces_given = 0
        self.closed = False

    def complete(self, system: str, user: str) -> str:
        self.completed += 1
        return self.reply

    def stream(self, system: str, user: str):
        # Held on the fake, the way a provider client can hold its own
        # response stream. Without this, CPython closes an abandoned
        # generator by itself and a missing `close()` goes unnoticed.
        self.live = self._pieces()
        return self.live

    def _pieces(self):
        self.streamed += 1
        try:
            for start in range(0, len(self.reply), self.piece):
                self.pieces_given += 1
                yield self.reply[start : start + self.piece]
        finally:
            self.closed = True


def _write(model):
    return build_write_answer(model)(QUESTION, (HIT,), PARENTS)


def _write_listening(model):
    seen: list[str] = []
    with streaming.listening_with(seen.append):
        result = _write(model)
    return result, seen


# --- 1. nobody listening --------------------------------------------------


def test_with_no_listener_the_writer_makes_one_complete_call_and_never_streams():
    model = StreamingFake(LONG_ANSWER)

    assert _write(model) == LONG_ANSWER
    assert (model.completed, model.streamed) == (1, 0)


def test_a_model_without_stream_still_answers_when_someone_is_listening():
    class CompleteOnly:
        def complete(self, system, user):
            return LONG_ANSWER

    result, seen = _write_listening(CompleteOnly())

    assert result == LONG_ANSWER
    assert seen == []


# --- 2. somebody listening ------------------------------------------------


def test_a_listener_sees_growing_prefixes_ending_in_the_whole_answer():
    model = StreamingFake(LONG_ANSWER)

    result, seen = _write_listening(model)

    assert (model.completed, model.streamed) == (0, 1)
    assert result == LONG_ANSWER
    assert len(seen) >= 3, "a 100-character reply in 7-character pieces must arrive in steps"
    assert all(LONG_ANSWER.startswith(text) for text in seen)
    assert [len(t) for t in seen] == sorted(len(t) for t in seen)
    assert seen[-1] == LONG_ANSWER


def test_nothing_is_shown_before_the_hold_length_is_reached():
    model = StreamingFake(LONG_ANSWER)

    _, seen = _write_listening(model)

    assert min(len(text) for text in seen) >= STREAM_HOLD_CHARS


def test_a_short_one_line_answer_is_returned_whole_but_never_streamed():
    short = "Trois mois."
    result, seen = _write_listening(StreamingFake(short, piece=3))

    assert result == short
    assert seen == []


def test_an_answer_opening_with_notamment_still_streams():
    """The hold is for the decline SPELLING, not for any line starting 'Not'."""
    reply = "Notamment, l'article 13 fixe la periode d'essai a trois mois pour les cadres."

    _, seen = _write_listening(StreamingFake(reply))

    assert seen and seen[-1] == reply


# --- 3. declines and cancel -----------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "NOT_COVERED",
        "NOT_COVERED - les sections parlent des conges, pas de la periode d'essai.",
        "Reponse : NOT_COVERED, les sections ne traitent pas cette question du tout.",
        "**NOT-COVERED** rien dans ces sections ne repond a la question posee ici.",
    ],
)
def test_a_decline_is_never_shown_while_it_is_written_and_still_declines(reply):
    seen: list[str] = []
    with streaming.listening_with(seen.append), pytest.raises(AnswerNotCoveredError):
        _write(StreamingFake(reply, piece=4))

    assert seen == [], f"the reader was shown {seen[-1:]!r} before an honest refusal"


def test_a_listener_that_raises_stops_and_closes_the_stream():
    class Cancelled(Exception):
        pass

    model = StreamingFake(LONG_ANSWER * 5, piece=5)

    def cancel_on_first_text(_text):
        raise Cancelled

    with streaming.listening_with(cancel_on_first_text), pytest.raises(Cancelled):
        _write(model)

    assert model.closed
    assert model.pieces_given < len(LONG_ANSWER * 5) // 5, "the rest was still fetched"


def test_a_listener_is_invisible_outside_its_block():
    with streaming.listening_with(lambda _t: None):
        assert streaming.listening()
    assert not streaming.listening()


# --- the langchain adapter --------------------------------------------------


class _Chunk:
    def __init__(self, content):
        self.content = content


def test_the_adapter_streams_text_pieces_and_joins_list_parts():
    class Model:
        def stream(self, messages):
            self.messages = messages
            yield _Chunk("Trois ")
            yield _Chunk([{"type": "text", "text": "mois"}, " pour"])
            yield _Chunk("")
            yield _Chunk(" les cadres.")

    model = Model()
    pieces = list(_LangChainChat(model).stream("sys", "user"))

    assert pieces == ["Trois ", "mois pour", " les cadres."]
    assert model.messages == [("system", "sys"), ("human", "user")]


@pytest.mark.parametrize(
    ("error", "phrase"),
    [
        (httpx.ReadTimeout("timed out"), "did not respond in time"),
        (httpx.ConnectError("getaddrinfo failed"), "could not be reached"),
    ],
)
def test_a_provider_failure_mid_stream_is_the_same_named_error(error, phrase):
    class Model:
        def stream(self, messages):
            yield _Chunk("Trois mois")
            raise error

    with pytest.raises(ChatUnavailableError) as caught:
        list(_LangChainChat(Model()).stream("s", "u"))

    assert phrase in str(caught.value)
    assert "getaddrinfo" not in str(caught.value)
