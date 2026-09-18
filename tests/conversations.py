"""Test helpers for ST-53's many-conversations chat screen.

Two ways a test reaches a conversation, matching the two ways the app does:

* `conversation_id_on(page)` reads the id the chat screen's forms carry,
  exactly as a browser would send it back -- so a test that asks a
  follow-up continues the SAME conversation only because the page said
  which one, never because the server guessed.
* `live_conversation(runtime, workspace_id, user_id)` is what the chat
  screen shows for that person in that workspace with no `?c=` in the
  address: their latest conversation. When they have none it starts an
  empty one, live in memory, which is what the pre-ST-53
  `Runtime.conversation(workspace_id, user_id)` returned -- so a test can
  seed messages before the first page load.
"""

from __future__ import annotations

import html
import re

from ui.conversation import Conversation

_CONVERSATION_ID = re.compile(r'name="conversation_id" value="([^"]*)"')


def conversation_id_on(page: str) -> str:
    """The conversation id the page's composer carries ("" for an empty
    chat not yet asked anything). Every form on one page carries the same
    one, so the first match is the page's."""
    match = _CONVERSATION_ID.search(page)
    return html.unescape(match.group(1)) if match else ""


def live_conversation(runtime, workspace_id: str, user_id: str = "local") -> Conversation:
    """This person's current conversation in this workspace, started
    empty when they have none yet."""
    found = runtime.latest_conversation(user_id, workspace_id)
    if found is not None:
        return found
    return runtime.new_conversation(user_id, workspace_id)
