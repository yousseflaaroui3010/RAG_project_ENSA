"""Describe a figure from its image and its surroundings, at Sync time.

The description is for SEARCH and for DISPLAY, never for answering. It is
added to the figure's searchable card, so a question about "the cooling
circuit" can find a diagram whose caption only says "Figure 3", and it is
shown next to the image with a "generated automatically" label. The answer
writer never reads it: answers are written from the document's own text
(see `agent/answering.py::section_blocks`), so a misread measurement on a
plan cannot become a confident answer.

Which model sees the image follows `model_mode`, like every other call:

* cloud: the configured Gemini model. The image leaves the machine.
* strict-local: `vision_model_local` through Ollama. Empty means no
  description, because the default local model reads text only.

`figure_explanations = "off"` turns descriptions off in both modes.
A failed call returns "" and never fails the Sync: the figure is kept,
still findable by its caption and context.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

from agent.chat import CLOUD, STRICT_LOCAL
from agent.prompts import load_prompt
from config import get_settings

logger = logging.getLogger(__name__)

EXPLAINER_PROMPT_ID = "figure-explainer"


def describe_figure(png: bytes, *, workspace: str, document: str, figure: Any) -> str:
    """Two to four sentences about one figure, or "" when not available."""
    model = _vision_model()
    if model is None:
        return ""
    prompt = load_prompt(EXPLAINER_PROMPT_ID)
    user = prompt.render(
        workspace=workspace or "-",
        document=document,
        page=str(figure.page) if figure.page else "-",
        heading=figure.heading or "-",
        caption=figure.caption or "-",
        before=figure.context_before or "-",
        after=figure.context_after or "-",
    )
    try:
        return _ask(model, prompt.system, user, png).strip()
    except Exception:  # noqa: BLE001 -- a description is optional; see module docstring
        logger.warning("figure description failed for %s", document, exc_info=True)
        return ""


def _ask(model: Any, system: str, user: str, png: bytes) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    image = base64.b64encode(png).decode("ascii")
    reply = model.invoke(
        [
            SystemMessage(content=system),
            HumanMessage(
                content=[
                    {"type": "text", "text": user},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}},
                ]
            ),
        ]
    )
    content = getattr(reply, "content", reply)
    if isinstance(content, list):
        return " ".join(
            part.get("text", "") if isinstance(part, dict) else str(part) for part in content
        )
    return str(content)


def _vision_model() -> Any | None:
    """The model that reads images in the current mode, or None."""
    settings = get_settings()
    if settings.figure_explanations != "model":
        return None
    if settings.model_mode == CLOUD:
        if not settings.cloud_api_key:
            return None
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            model=settings.chat_model_cloud,
            api_key=settings.cloud_api_key,
            timeout=settings.model_call_timeout_seconds,
            max_retries=settings.model_call_max_retries + 1,
        )
    if settings.model_mode == STRICT_LOCAL and settings.vision_model_local:
        from langchain_ollama import ChatOllama

        return ChatOllama(
            model=settings.vision_model_local,
            base_url=settings.ollama_base_url,
            client_kwargs={"timeout": settings.model_call_timeout_seconds},
        )
    return None
