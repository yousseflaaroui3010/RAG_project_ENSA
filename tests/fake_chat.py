"""The scripted fake chat model, shared by every test that needs one.

Not a test file: pytest does not collect it. It sits beside
`tests/fake_encoders.py` for the same reason -- a double that four test
files need is one object, not four.

docs/phase2/CLAUDE.md's hard rule is "tests use the scripted fake chat
model; no API keys in tests, fixtures, or CI", and `agent/chat.py` narrowed
the whole model seam to one method so this class could be nine lines. It
satisfies `agent.chat.ChatModel` structurally: a Protocol, so nothing has
to inherit from anything.

IT RECORDS EVERY CALL, and that half is not convenience. Assertions about
what the model was SHOWN are how a prompt gets tested at all, and the call
COUNT is what catches a retry hidden inside an adapter -- something a
graph-level test structurally cannot see, because from the graph's side
one model call and three look identical.

EXTRACTED BY ST-24, which would otherwise have written the fourth and
fifth copies. Two copies remain in ST-23's own test files
(`tests/unit/test_agent_grading.py`, `tests/integration/test_ask_retry_
loop.py`) and are deliberately left there: rewriting another story's tests
inside this story's diff is the drive-by the scoped boy-scout rule keeps
out. Folding them in is a named `chore/` follow-up in BUILD-STATE.
"""

from __future__ import annotations


class ScriptedChat:
    """Answers from a script, then repeats its last answer forever.

    Repeating rather than raising at the end of the script is deliberate:
    a test about the FIRST call should not have to know how many later
    calls the graph makes, and a test that cares about the count asserts
    on `calls` directly."""

    def __init__(self, *replies: str):
        if not replies:
            raise ValueError(
                "ScriptedChat needs at least one reply. An empty script "
                "would raise IndexError inside the port under test, which "
                "reads like a bug in the code rather than in the test."
            )
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
