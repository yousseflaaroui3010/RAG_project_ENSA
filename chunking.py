"""Sanad parent/child chunking (ST-14).

Implements the chunking half of architecture section 7.5: markdown becomes
PARENTS (whole sections, split on H1-H3 headings, merged below
`parent_merge_below_chars`, split above `parent_split_above_chars`) and
CHILDREN (fixed windows of `chunk_child_size_chars` with
`chunk_child_overlap_chars` of overlap).

The two exist for different jobs, which is the whole point of the pattern:
children are small enough to embed precisely and stay far under the E5
512-token input ceiling, so retrieval finds the right spot; parents are
whole sections, so the answering model reads enough context to actually
answer. Search the small thing, read the big thing.

This module SPLITS, it never EMBEDS and never WRITES. No vector, no JSON
file, no registry row: section 7.5's parent store is ST-16 and the
embeddings are ST-15. Note in particular that child text here is RAW --
the mandatory `passage: ` prefix (CLAUDE.md hard rule, unit-test enforced)
belongs to ST-15 and must be added exactly once, there.

Sits beside conversion.py in the flat layout: ST-13 produces the markdown
this module consumes.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from config import get_settings

# H1-H3 only, per section 7.5. `####` and deeper deliberately do NOT split:
# they are subsections of the section they sit in, and promoting them to
# parents would shred a document into fragments too small to answer from.
# The `\s+` after the hashes is what excludes `####` (and `#hashtag`, which
# is not a heading at all and appears constantly in real text).
_HEADING = re.compile(r"^(#{1,3})\s+(.*\S)\s*$")

# A fenced code block. Lines inside one are never headings, no matter how
# many `#` they start with -- a Python comment (`# TODO: fix this`) inside
# a fence is the common case, and treating it as an H1 would split a
# document at a line that is not a section at all.
#
# An UNCLOSED fence (a stray ``` from a converted PDF table) therefore
# swallows every heading after it, and the document becomes one long
# section split by size instead. That is the deliberate direction to fail
# in: a missed split only makes sections coarser and loses no text, while
# a false split attaches the wrong heading to real content and produces a
# wrong citation, which PRD F-03 cannot afford.
_FENCE = re.compile(r"^\s*(```|~~~)")

# Joins the first and last labels of a merged parent, e.g.
# "Article 1 ... Article 3". Deliberately NOT " - ": real headings contain
# dashes ("Article 2 - Duree"), and joining two of those with a dash gives
# "Article 2 - Duree - Article 4 - Rupture", where the reader cannot tell
# the range separator from the heading's own punctuation. Found by running
# a realistic document, not by a test -- every test heading had been a
# tidy "Article 1".
_LABEL_RANGE_SEPARATOR = " ... "

# Inline markup stripped out of a heading before it becomes a section label.
#
# A label is not markdown, it is the citation text shown to a user on a
# source card (UX spec 6.2 / PRD F-03). Real converted PDFs put emphasis in
# their headings constantly -- pymupdf4llm turned a heading of the Moroccan
# labour-law summary into
#   `**G-** **<u>Securite sociale et charges sociales</u>**`
# which is what the user would have been shown as the source of the answer.
# Found by running real documents through the ladder, not by a test: every
# fixture heading in this suite is a tidy "Article 1".
#
# Order matters: bold before italic, or `**x**` loses one pair of asterisks
# and leaves `*x*`.
#
# The underscore form is matched only at a word BOUNDARY, which is what
# separates emphasis from an identifier. `_Formalites exigees_` is italic
# and its markers go; `max_length` is a name and survives untouched.
# Stripping every underscore was the first version of this and it damaged
# real headings, which is worse than leaving one marker in.
_LABEL_HTML = re.compile(r"<[^>]+>")
_LABEL_BOLD = re.compile(r"(\*\*|__)(.+?)\1", re.S)
_LABEL_ITALIC = re.compile(r"\*(.+?)\*", re.S)
_LABEL_ITALIC_US = re.compile(r"(?<!\w)_(.+?)_(?!\w)", re.S)
_LABEL_CODE = re.compile(r"`+")

# Paragraph boundary used when an oversized section has to be split. Splitting
# there rather than mid-sentence keeps each parent readable as context.
_PARAGRAPH_BREAK = "\n\n"

# Namespace for deriving parent ids. Derived rather than pasted as a magic
# literal so the value is reproducible from something a reader can check.
_PARENT_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "parents.sanad.local")

# Separator inside the name a parent id is derived from. NUL cannot appear in
# a filename on any filesystem Sanad runs on, so no real file name can be
# crafted to collide with another file's index.
_PARENT_ID_SEPARATOR = "\x00"


class ChunkingError(Exception):
    """Base class for chunking domain errors, so callers catch this rather
    than a ValueError from deep inside a windowing loop."""


class InvalidChunkSettingsError(ChunkingError):
    """Raised when the configured sizes cannot produce a correct split.

    Checked up front, and loudly, because every one of these failure modes
    is SILENT otherwise -- there is no crash to follow back to a cause:
      - overlap >= size, or a non-positive split limit: an infinite loop
        that hangs Sync forever while growing memory;
      - a non-positive child size: every parent produces zero children, so
        whole documents are indexed as unsearchable;
      - a negative overlap: the windows leave GAPS, so a passage sits in
        the parent but is never embedded, and the only symptom is the
        assistant answering "not covered here" about text it holds."""


@dataclass(frozen=True)
class Parent:
    """One section of a document: the unit the answering model READS.

    `section_label` is the heading this text sat under, or None for text
    that appeared before any heading (a preamble, or a whole TXT file that
    has no headings at all). It is not decoration: PRD F-03 puts it in
    every citation next to the file name, so a wrong label is a wrong
    citation -- see `_merged_label` for why merged parents carry a range
    rather than only their first heading.

    `id` is DERIVED, not random: the same document chunked twice produces
    the same ids, so re-ingestion overwrites in place instead of orphaning
    the old parent files. See `_parent_id`."""

    id: str
    text: str
    source_file: str
    section_label: str | None = None


@dataclass(frozen=True)
class Child:
    """One embedding-sized window of a parent: the unit that gets SEARCHED.

    Carries `parent_id` so a hit can be traded for the full section at
    answer time, and repeats `source_file` / `section_label` because
    architecture section 7.5 defines exactly those fields in the Qdrant
    point payload -- the search result has to be citable without a second
    lookup."""

    text: str
    parent_id: str
    source_file: str
    section_label: str | None = None


@dataclass(frozen=True)
class ChunkedDocument:
    """Everything one document became. Parents and children are returned
    together because they are only meaningful as a pair: every child's
    `parent_id` refers to a parent in the same result."""

    parents: list[Parent]
    children: list[Child]


@dataclass(frozen=True)
class _Section:
    """A run of text under one heading, before any merging or splitting."""

    label: str | None
    text: str


def _parent_id(source_file: str, index: int) -> str:
    """A parent's identity, derived from where it lives rather than drawn at
    random, so chunking the same document twice produces the SAME ids.

    This is the difference between re-ingestion being self-healing and
    re-ingestion leaving litter. Architecture §7.5 keys the parent store on
    this value (`data/parents/<workspace_id>/<parent_id>.json`) and puts it
    in the Qdrant payload. With random ids, re-syncing a CHANGED file minted
    a whole new set: every old JSON orphaned on disk, and any vector that
    survived the rewrite pointed at a parent file that no longer existed --
    a search hit that resolves to nothing, which is the one thing a sourced
    answer cannot survive. With derived ids the same file simply overwrites
    itself in place.

    A `uuid5` rather than a bare digest so the value is still a UUID, the
    same shape as every other id in the system (§7.4).

    Scope note: the name deliberately does NOT include the workspace. §7.5
    already namespaces both stores per workspace -- a directory per
    workspace, a collection per workspace -- so two workspaces holding a
    file of the same name never meet. If a future store ever flattens that,
    this is the single line that has to take a workspace id.

    Shrinking documents still leave a tail: a file that drops from ten
    parents to six leaves ids 6..9 behind. That residue is now DETERMINISTIC,
    so ST-17 can compute exactly which ids to delete instead of guessing."""
    name = f"{source_file}{_PARENT_ID_SEPARATOR}{index}"
    return str(uuid.uuid5(_PARENT_ID_NAMESPACE, name))


def _validate_settings(settings) -> None:
    """Refuse a configuration that cannot split correctly, before any of it
    runs.

    All four checks guard SILENT failures, which is why they are worth the
    lines: two of them hang Sync with no error, and two of them produce a
    perfectly normal-looking index that has quietly lost text. Found by
    self-review after the suite was green -- `_windows` had guarded its own
    infinite loop from the start, and `_split_oversized` had the identical
    loop with no guard at all."""
    size = settings.chunk_child_size_chars
    overlap = settings.chunk_child_overlap_chars
    split_above = settings.parent_split_above_chars

    if size <= 0:
        raise InvalidChunkSettingsError(
            f"chunk_child_size_chars must be positive, got {size}; at or "
            f"below zero every parent yields no children at all and the "
            f"document is indexed as unsearchable"
        )
    if overlap < 0:
        raise InvalidChunkSettingsError(
            f"chunk_child_overlap_chars must not be negative, got {overlap}; "
            f"a negative overlap leaves gaps between windows, so text sits "
            f"in the parent and is never embedded"
        )
    if overlap >= size:
        raise InvalidChunkSettingsError(
            f"chunk_child_overlap_chars ({overlap}) must be smaller than "
            f"chunk_child_size_chars ({size}); otherwise each window starts "
            f"at or before the previous one and the split never ends"
        )
    if split_above <= 0:
        raise InvalidChunkSettingsError(
            f"parent_split_above_chars must be positive, got {split_above}; "
            f"at or below zero an oversized section is cut into empty "
            f"pieces forever"
        )


def _split_on_headings(markdown: str) -> list[_Section]:
    """Cut the document at every H1-H3 heading.

    Text before the first heading becomes a section with no label rather
    than being dropped. That case is not an edge case at all: a converted
    TXT file has no headings whatsoever, so this path carries the entire
    document."""
    sections: list[_Section] = []
    label: str | None = None
    body: list[str] = []
    in_fence = False

    def flush() -> None:
        text = "\n".join(body).strip()
        if text:
            sections.append(_Section(label=label, text=text))

    for line in markdown.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            body.append(line)
            continue
        heading = None if in_fence else _HEADING.match(line)
        if heading is None:
            body.append(line)
            continue
        flush()
        label = _clean_label(heading.group(2))
        body = []
    flush()
    return sections


def _clean_label(heading_text: str) -> str | None:
    """Turn a raw heading into the text a user should see as a citation.

    Returns None for a heading that was nothing but markup, so it is
    treated as unlabelled rather than cited as an empty string -- PRD F-03
    allows "no section label" (a plain TXT file has none) but an empty
    label rendered on a source card is a broken citation, not an absent
    one."""
    text = _LABEL_BOLD.sub(r"\2", heading_text)
    text = _LABEL_ITALIC.sub(r"\1", text)
    text = _LABEL_ITALIC_US.sub(r"\1", text)
    text = _LABEL_CODE.sub("", text)
    text = _LABEL_HTML.sub("", text)
    return " ".join(text.split()) or None


def _merged_label(sections: list[_Section]) -> str | None:
    """The label for a parent built from several sections.

    A range ("Article 1 - Article 3"), not just the first heading, and the
    reason is PRD F-03: the label is shown to the user as the source of the
    passage. Labelling a parent that spans Articles 1 to 3 as "Article 1"
    would cite a sentence from Article 3 under the wrong heading -- a
    quietly wrong citation in a product whose core promise is honest
    sourcing.

    Unlabelled sections are skipped rather than turning the whole range
    into None, which leaves one deliberate imprecision: a preamble too
    short to stand alone merges forward and is cited under the heading
    that follows it. The alternative is a parent of a few dozen
    characters, which gives the answering model nothing to answer from.
    It is bounded -- a document has at most ONE unlabelled preamble, so at
    most one parent per file can be affected."""
    labels = [section.label for section in sections if section.label]
    if not labels:
        return None
    if labels[0] == labels[-1]:
        return labels[0]
    return f"{labels[0]}{_LABEL_RANGE_SEPARATOR}{labels[-1]}"


def _merge_small_sections(sections: list[_Section], merge_below: int) -> list[_Section]:
    """Glue consecutive sections together until they reach `merge_below`.

    A document of forty one-line articles would otherwise produce forty
    parents so short that retrieving one tells the model almost nothing.

    The trailing leftover (a final run that never reached the threshold)
    is appended to the previous group rather than left standing, because a
    parent under the threshold is exactly what this step exists to
    prevent. When there is no previous group the document is simply
    shorter than `merge_below`, and one small parent is the correct and
    only answer."""
    groups: list[list[_Section]] = []
    buffer: list[_Section] = []
    buffered_chars = 0

    for section in sections:
        buffer.append(section)
        buffered_chars += len(section.text)
        if buffered_chars >= merge_below:
            groups.append(buffer)
            buffer = []
            buffered_chars = 0
    if buffer:
        if groups:
            groups[-1].extend(buffer)
        else:
            groups.append(buffer)

    return [
        _Section(
            label=_merged_label(group),
            text=_PARAGRAPH_BREAK.join(section.text for section in group),
        )
        for group in groups
    ]


def _split_oversized(text: str, split_above: int) -> list[str]:
    """Break a section longer than `split_above` into pieces.

    Splits at paragraph breaks in preference to mid-sentence: a parent is
    what the answering model reads, and a section cut through the middle
    of a sentence loses that sentence from BOTH pieces -- neither half
    says anything complete. A single paragraph that is itself longer than
    the limit (a wall-of-text PDF page with no blank lines) still has to
    be cut, and is cut on the character limit as a last resort."""
    if len(text) <= split_above:
        return [text]

    pieces: list[str] = []
    current = ""
    for paragraph in text.split(_PARAGRAPH_BREAK):
        candidate = f"{current}{_PARAGRAPH_BREAK}{paragraph}" if current else paragraph
        if len(candidate) <= split_above:
            current = candidate
            continue
        if current:
            pieces.append(current)
            current = ""
        # The paragraph alone still does not fit: hard-cut it, then carry
        # the remainder forward so it can pack with what follows.
        while len(paragraph) > split_above:
            pieces.append(paragraph[:split_above])
            paragraph = paragraph[split_above:]
        current = paragraph
    if current:
        pieces.append(current)
    return pieces


def _windows(text: str, size: int, overlap: int) -> list[str]:
    """Fixed-size sliding windows over one parent, `overlap` chars shared
    between neighbours.

    Deliberately a character window and not a sentence splitter: the
    story's exit criterion is a VERIFIABLE 100-character overlap, and it
    is the character count that guarantees every embedded input stays
    under the E5 512-token ceiling (architecture section 7.5). A
    smarter boundary would trade a provable guarantee for a prettier one.

    The final short window is emitted, never dropped -- the tail of a
    document is as answerable as its middle.

    Trusts `_validate_settings`, which has already refused every size and
    overlap pair that could hang this loop or leave gaps in it. A second
    guard here would be a branch no test could ever reach."""
    stride = size - overlap
    chunks: list[str] = []
    start = 0
    while True:
        window = text[start : start + size]
        if window:
            chunks.append(window)
        if start + size >= len(text):
            # The window just emitted reached the end. Stopping here is what
            # stops a text whose length is an exact multiple of the size from
            # emitting a final window made entirely of already-covered
            # overlap -- a duplicate chunk, embedded and searchable twice.
            break
        start += stride
    return chunks


def chunk_document(markdown: str, *, source_file: str) -> ChunkedDocument:
    """Split one converted document into parents and children.

    Takes markdown text rather than a ConversionResult so the splitter can
    be tested, and reasoned about, without a converter: ST-17 is what
    joins ST-13's output to this input.

    Empty or whitespace-only input yields no parents and no children
    rather than raising. Conversion already reports such a file as Skipped
    (ST-13's emptiness gate), so reaching here with nothing in hand means
    the caller skipped that check, and inventing an empty parent would put
    a citable source with no content into the index."""
    settings = get_settings()
    _validate_settings(settings)
    sections = _split_on_headings(markdown)

    parents: list[Parent] = []
    children: list[Child] = []
    for section in _merge_small_sections(sections, settings.parent_merge_below_chars):
        for piece in _split_oversized(section.text, settings.parent_split_above_chars):
            parent = Parent(
                # `len(parents)` is this parent's position in the document,
                # counted across sections, which is what makes the id stable
                # for the same input.
                id=_parent_id(source_file, len(parents)),
                text=piece,
                source_file=source_file,
                section_label=section.label,
            )
            parents.append(parent)
            children.extend(
                Child(
                    text=window,
                    parent_id=parent.id,
                    source_file=source_file,
                    section_label=section.label,
                )
                for window in _windows(
                    piece,
                    settings.chunk_child_size_chars,
                    settings.chunk_child_overlap_chars,
                )
            )
    return ChunkedDocument(parents=parents, children=children)
