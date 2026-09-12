"""Sanad conversion ladder (ST-13, PPTX added for F-11/ST-48).

Turns one document on disk into markdown text the chunker can cut, per
ADR-07: `pymupdf4llm` for PDF, `markitdown` for DOCX and PPTX, passthrough
for TXT and MD. Markdown, not plain text, because the parent splitter cuts on
markdown headings (architecture section 7.5) -- a converter that flattens
headings would silently destroy the structure the retrieval quality
depends on, which is exactly why ADR-07 refuses to use one converter for
everything.

This module CONVERTS, it never DECIDES and never WRITES. It reads bytes
and returns text: no registry row, no chunk, no vector, no sync_item.
ST-12 decided which files need converting; ST-17 will call this and
persist the outcome. Keeping the three apart is what lets the whole
ladder, including its two failure rungs, be tested with no database and
no vector store in existence.

The contract that matters most is PRD F-02 criterion 3: a file that
cannot be processed is reported Failed with a plain-language reason AND
every other file completes. So `convert_file` returns an outcome for a
bad document, it does not raise. It reports three outcomes, matching
`sync_item.result` in db/schema.sql:

  CONVERTED -- markdown, plus a page count for formats that have pages
  FAILED    -- damaged, password-protected, or undecodable (PRD S2 table)
  SKIPPED   -- readable but nothing to index: a scanned PDF with no text
               layer (the binding V1 behaviour under F-16), an empty
               file, or an unsupported extension

Sits beside change_detection.py: both are ingestion domain modules over
db/repo.py, and this one imports the shared "unsupported file type"
wording from there so the two never explain the same situation twice.
"""

from __future__ import annotations

import logging
import re
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import pymupdf
import pymupdf4llm
from markitdown import MarkItDown, MarkItDownException

from change_detection import UNSUPPORTED_TYPE_REASON, file_type
from config import get_settings

logger = logging.getLogger(__name__)

# The one entry inside a .docx package that makes it a Word document. A
# `.docx` that is a valid ZIP without this part is not a Word file, and
# markitdown does NOT reject it -- see `_read_docx` for what it does
# instead, and why that is the most dangerous behaviour in this module.
_DOCX_MAIN_PART = "word/document.xml"

# The equivalent guard for PPTX (F-11/ST-48): the one entry that makes a
# `.pptx` package a PowerPoint file. Verified against markitdown 0.1.5's
# PptxConverter to have the identical danger `_read_docx` already guards
# for DOCX: given a `.pptx` that is a valid ZIP but not really a
# PowerPoint package, it does not raise -- it falls through to a
# directory-listing converter and returns that AS A SUCCESS. A `.pptx`
# that is not even a ZIP comes back as its own raw bytes, also with no
# exception. See `_read_pptx`.
_PPTX_MAIN_PART = "ppt/presentation.xml"

# Named once so the dispatch table and the "no text layer" wording can never
# disagree about which extension is the scanned-document case.
_PDF = "pdf"

# Plain-language reasons. User-facing: they land in `sync_item.reason` and
# render in the S2 file table (PRD section 8), so they say what happened and
# what to do about it, never a stack frame or a library name.
_REASON_PDF_DAMAGED = (
    "the PDF is damaged or is not really a PDF file. Open it in a PDF "
    "reader to check it, then sync again"
)
_REASON_PDF_LOCKED = (
    "the PDF is password-protected. Remove the password, save a copy "
    "without it, then sync again"
)
_REASON_PDF_NO_TEXT_LAYER = (
    "this PDF has no text layer, so it is a scan or images only. Sanad "
    "cannot read text from pictures yet, so nothing was indexed"
)
_REASON_DOCX_DAMAGED = (
    "the DOCX is damaged or is not really a Word file. Open it in Word to "
    "check it, then sync again"
)
_REASON_PPTX_DAMAGED = (
    "the PPTX is damaged or is not really a PowerPoint file. Open it in "
    "PowerPoint to check it, then sync again"
)
_REASON_EMPTY = "the file has no text in it"
_REASON_UNDECODABLE = (
    "this file is not valid UTF-8 text, so it could not be read. Open it "
    "and re-save it with UTF-8 encoding, then sync again"
)
_REASON_UNREADABLE = "the file could not be read: {detail}"


class ConversionOutcome(StrEnum):
    """What the ladder concluded about one file.

    These three map straight onto `sync_item.result` values in
    db/schema.sql that describe conversion: CONVERTED becomes `added` or
    `changed` depending on what ST-12 decided about the same file, FAILED
    becomes `failed`, SKIPPED becomes `skipped`. The distinction between
    the last two is the user's: FAILED means "this file is broken, you
    can fix it", SKIPPED means "nothing here to index, and that is not
    your fault"."""

    CONVERTED = "converted"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class ConversionResult:
    """One file's conversion outcome.

    `markdown` is the converted text and is None for every outcome except
    CONVERTED. `reason` is the plain-language explanation and is None for
    CONVERTED only -- the two fields are exact opposites, which is what
    makes "converted but empty" and "failed with no reason" both
    unrepresentable rather than merely discouraged.

    `page_count` is the source document's page count, and None for
    formats that have no pages (DOCX, TXT, MD). It is not decoration:
    PRD F-02 criterion 1 promises each added file is reported "with its
    page count", and `document.page_count` in db/schema.sql is the column
    ST-17 fills from it. None means "this format has no pages", never
    "we did not bother to look"."""

    file_name: str
    outcome: ConversionOutcome
    markdown: str | None = None
    page_count: int | None = None
    reason: str | None = None

    @property
    def converted(self) -> bool:
        return self.outcome is ConversionOutcome.CONVERTED


@dataclass(frozen=True)
class _Extracted:
    """What one rung of the ladder pulled out of a file, before the shared
    emptiness check that every format is held to."""

    text: str
    page_count: int | None = None


class ConversionError(Exception):
    """Base class for conversion domain errors, so ST-17 can catch this
    rather than the pymupdf, markitdown, zipfile and OS error shapes the
    rungs translate. Carries `reason`, the plain-language text the user
    sees. Mirrors `ChangeDetectionError` in the sibling module."""

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class DocumentFailedError(ConversionError):
    """The document is broken: damaged bytes, a password we do not have,
    text in an encoding we cannot decode. Becomes FAILED, and the reason
    tells the user what to fix.

    There is deliberately no matching `DocumentSkippedError`. Every skip
    is decided in one place -- the emptiness gate in `convert_file`, plus
    the unsupported-extension guard -- and both already hold the value
    they need to return. An exception class for skipping existed in an
    earlier draft and was raised by nothing at all: a second way to
    express an outcome that no rung ever used, which self-review caught
    only because mutation testing cannot see a branch nothing reaches."""


def _read_pdf(path: Path) -> _Extracted:
    """PDF rung: pymupdf4llm, which preserves headings (ADR-07).

    The document is opened here rather than letting `to_markdown` open it
    by filename, for two reasons that are both bugs otherwise:

    1. A password-protected PDF OPENS FINE. pymupdf raises nothing, and
       `page_count` even answers. It is `needs_pass` that says the content
       is locked, and if we do not check it, `to_markdown` walks into the
       encrypted page tree and dies on `TypeError: 'NoneType' object is
       not subscriptable` -- an uncaught third-party crash, in the middle
       of a batch, over a file PRD F-02 explicitly requires be reported as
       one Failed row. Verified empirically against pymupdf 1.28.0.
    2. The page count has to be read from the same open document that
       produced the text, not a second `open()` of a file that may have
       changed in between.
    """
    try:
        doc = pymupdf.open(path)
    except pymupdf.FileNotFoundError as exc:
        # NOT the builtin: pymupdf shadows the name with its own class,
        # which subclasses RuntimeError, so `except OSError` does not catch
        # it and neither does the FileDataError clause below. A file
        # deleted between the scan and the conversion is an ordinary race
        # in a sync, not a surprise, so it is named here rather than left
        # to the last-resort catch that logs a traceback.
        raise DocumentFailedError(_REASON_UNREADABLE.format(detail=str(exc))) from exc
    except pymupdf.FileDataError as exc:
        # Covers EmptyFileError too, which subclasses it: a zero-byte .pdf
        # and a truncated one are the same story to the user.
        raise DocumentFailedError(_REASON_PDF_DAMAGED) from exc
    try:
        if doc.needs_pass:
            raise DocumentFailedError(_REASON_PDF_LOCKED)
        page_count = doc.page_count
        text = pymupdf4llm.to_markdown(doc)
    finally:
        doc.close()
    return _Extracted(text=text, page_count=page_count)


def _read_docx(path: Path) -> _Extracted:
    """DOCX rung: markitdown (ADR-07), behind a package check it does not
    do for itself.

    The check is not defensive padding, it is the fix for markitdown's
    most dangerous behaviour: given a `.docx` it cannot parse as Word, it
    does not raise, it falls through to another converter and returns
    whatever that produces AS A SUCCESS. Verified against markitdown
    0.1.5: a corrupted `.docx` came back as the literal bytes
    'PK\\x03\\x04garbage-not-a-zip', and a valid ZIP that is not a Word
    file came back as a directory listing of its entries. Either would be
    reported Added, embedded, and returned to a user as a cited source --
    a silent poisoning of the index that no exception ever announces.
    A file with no `word/document.xml` is not a Word document, full stop.

    (markitdown does raise for a zero-byte file, via BadZipFile. Only the
    non-empty malformed cases fall through, which is the harder half to
    notice.)
    """
    # One check, not two. An earlier draft called `zipfile.is_zipfile`
    # first; mutation testing proved that branch unreachable as a cause of
    # any verdict, because opening a ZipFile already raises BadZipFile on
    # exactly the inputs is_zipfile rejects. Two guards where one decides
    # is not extra safety, it is a line no test can ever hold to account.
    try:
        with zipfile.ZipFile(path) as package:
            has_main_part = _DOCX_MAIN_PART in package.namelist()
    except zipfile.BadZipFile as exc:
        raise DocumentFailedError(_REASON_DOCX_DAMAGED) from exc
    except OSError as exc:
        # Kept apart from BadZipFile: a file that is missing or locked by
        # Word is not a damaged file, and telling its owner to "open it in
        # Word to check it" would send them looking for the wrong problem.
        raise DocumentFailedError(
            _REASON_UNREADABLE.format(detail=exc.strerror or str(exc))
        ) from exc
    if not has_main_part:
        raise DocumentFailedError(_REASON_DOCX_DAMAGED)

    try:
        result = MarkItDown().convert(str(path))
    except MarkItDownException as exc:
        raise DocumentFailedError(_REASON_DOCX_DAMAGED) from exc
    # No page count: a DOCX has no fixed pagination until something
    # renders it, so claiming a number here would be inventing one.
    return _Extracted(text=result.markdown)


# markitdown's own per-slide marker, verified by converting a real deck
# (markitdown 0.1.5's PptxConverter): every slide's content is preceded by
# `\n\n<!-- Slide number: N -->\n`, an HTML comment, never a markdown
# heading. `_label_pptx_slides` turns each one into a real H1 so chunking's
# existing heading split does the rest -- no change to chunking.py at all.
_PPTX_SLIDE_MARKER = re.compile(r"<!--\s*Slide number:\s*(\d+)\s*-->")

# Any markdown heading line INSIDE one slide's own content: markitdown
# emits the slide's title as its own "# Title" heading and, when present,
# speaker notes as "### Notes:". Demoted to plain text rather than left as
# headings, because a slide is one citable unit -- letting either split off
# into its own section would either duplicate the slide as two citations or
# (for notes) cite it under a bare "Notes:" label with no slide number at
# all, which is worse than not splitting.
# The text after the hashes is optional: markitdown writes a slide whose
# title placeholder is empty as a bare "#" line, which would otherwise stay
# in the stored text as a stray "#".
_MD_HEADING_LINE = re.compile(r"^#{1,6}(?:\s+(.*))?$")


def _demote_heading_line(line: str) -> str:
    match = _MD_HEADING_LINE.match(line)
    return (match.group(1) or "") if match else line


def _label_pptx_slides(markdown: str) -> str:
    """markitdown's slide-comment markers -> one "Slide N" H1 per slide.

    PRD F-11's whole contract is "citations name the file plus slide
    number", and F-03 already cites by `section_label`. Rather than teach
    chunking.py a second, PPTX-specific notion of location, this produces
    plain markdown that chunking's existing H1-H3 split and range-merge
    logic (`_merged_label` in chunking.py) already handle correctly -- a
    parent spanning slides 1 to 3 comes out labelled "Slide 1 ... Slide 3"
    for the same reason a parent spanning articles does, with no new code
    in chunking.py at all.

    A slide that has nothing left after its heading is demoted (a
    genuinely blank slide, F-11's binding empty-slide case) contributes NO
    heading and no text: numbering is never invented for a slide with
    nothing on it, so a real slide 3 is never mislabelled 2 because slide
    2 was skipped. If every slide is like that, the result is the empty
    string, which reaches `convert_file`'s shared emptiness gate exactly
    like a scanned PDF or a blank DOCX -- Skipped, not a fabricated deck
    of empty headings."""
    parts = _PPTX_SLIDE_MARKER.split(markdown)
    sections: list[str] = []
    # `parts` alternates [preamble, slide_number, body, slide_number, body,
    # ...]. markitdown always opens with the first marker (verified), so
    # `parts[0]` is empty in practice; a non-empty preamble cannot be
    # attributed to any one slide and is dropped rather than mislabelled.
    for index in range(1, len(parts), 2):
        number = parts[index]
        body = parts[index + 1] if index + 1 < len(parts) else ""
        content = "\n".join(
            _demote_heading_line(line) for line in body.splitlines()
        ).strip()
        if not content:
            continue
        # The heading gives parents clean slide boundaries. The plain lines
        # repeat the slide number INSIDE the text, because chunking drops
        # heading lines from a section's body: without them, every child
        # of a parent merged from short slides would be cited by the
        # parent's whole range. config's `parent_citation_marker_pattern`
        # reads them. There is one at each END of the slide on purpose: a
        # child window that starts in slide 3's tail and runs into slide 4
        # then carries both numbers and is cited "Slide 3 ... Slide 4". With
        # only the opening line it would be cited "Slide 4", which is wrong
        # for the slide-3 text it holds.
        sections.append(
            f"# Slide {number}\nSlide {number}\n{content}\n(end of Slide {number})"
        )
    return "\n\n".join(sections)


def _read_pptx(path: Path) -> _Extracted:
    """PPTX rung (F-11/ST-48): markitdown (ADR-07), behind the same kind of
    package check `_read_docx` uses, for the identical reason -- verified
    empirically against markitdown 0.1.5, not assumed: a `.pptx` that is a
    valid ZIP but not really a PowerPoint package (no
    `ppt/presentation.xml`) does not raise, it falls through to a
    directory-listing converter and returns that AS A SUCCESS; a `.pptx`
    that is not even a ZIP comes back as its own raw bytes, also with no
    exception. Either would be reported Added and one day cited to a user
    as a source. A file with no `ppt/presentation.xml` is not a
    PowerPoint file, full stop -- see `_read_docx` for the DOCX twin of
    this guard.

    (A `.pptx` that IS a real package but whose `ppt/presentation.xml` is
    not valid XML is caught differently: markitdown raises
    `MarkItDownException` for that case, verified against a real fixture,
    so `_read_pptx` never reaches its own fallback risk for it.)"""
    try:
        with zipfile.ZipFile(path) as package:
            has_main_part = _PPTX_MAIN_PART in package.namelist()
    except zipfile.BadZipFile as exc:
        raise DocumentFailedError(_REASON_PPTX_DAMAGED) from exc
    except OSError as exc:
        raise DocumentFailedError(
            _REASON_UNREADABLE.format(detail=exc.strerror or str(exc))
        ) from exc
    if not has_main_part:
        raise DocumentFailedError(_REASON_PPTX_DAMAGED)

    try:
        result = MarkItDown().convert(str(path))
    except MarkItDownException as exc:
        raise DocumentFailedError(_REASON_PPTX_DAMAGED) from exc
    # No page count: a slide deck has no pagination (PRD F-11 cites by
    # slide number, not a page; `document.page_count` stays NULL for it
    # exactly as it already does for DOCX).
    return _Extracted(text=_label_pptx_slides(result.markdown))


def _read_text(path: Path) -> _Extracted:
    """TXT / MD rung: passthrough (ADR-07). A .md file is already the
    target format, and a .txt file is markdown with no markup in it.

    Decoding is strict. The tempting fallback -- retry in latin-1, which
    never raises -- would turn a mis-encoded French document into
    'CongÃ©s payÃ©s' and index it silently; the user would only find out
    when an answer quoted the mojibake back at them. Failing with a
    reason they can act on is the honest trade."""
    try:
        text = path.read_text(encoding=get_settings().text_file_encoding)
    except UnicodeDecodeError as exc:
        # The reason names UTF-8 rather than the configured codec on
        # purpose: the default is "utf-8-sig", which is UTF-8 that also
        # tolerates a byte-order mark, and no editor offers "utf-8-sig" as
        # a save option. Naming it would be precise and useless.
        raise DocumentFailedError(_REASON_UNDECODABLE) from exc
    except OSError as exc:
        raise DocumentFailedError(
            _REASON_UNREADABLE.format(detail=exc.strerror or str(exc))
        ) from exc
    return _Extracted(text=text)


# The ladder itself: one rung per supported extension. `is_supported` in
# change_detection.py gates the folder scan against config, and
# `test_every_supported_extension_has_a_rung` holds this table to the same
# config, so widening `supported_document_extensions` again without writing
# the new extension's converter turns the suite red instead of shipping a
# silent Skipped -- exactly what caught a missing rung when "pptx" joined
# the V1 set for F-11/ST-48.
_CONVERTERS: dict[str, Callable[[Path], _Extracted]] = {
    _PDF: _read_pdf,
    "docx": _read_docx,
    "pptx": _read_pptx,
    "txt": _read_text,
    "md": _read_text,
}


def _no_text_reason(extension: str) -> str:
    """Why a file that converted cleanly still has nothing to index.

    PDF gets its own wording because for a PDF this is the expected,
    common case -- a scan -- and PRD F-16 binds V1 to reporting it as
    Skipped WITH THE REASON STATED. Telling someone who scanned a
    contract that "the file has no text in it" would read as a bug in
    Sanad rather than a description of their file."""
    return _REASON_PDF_NO_TEXT_LAYER if extension == _PDF else _REASON_EMPTY


def convert_file(path: str | Path) -> ConversionResult:
    """Convert one document to markdown. Never raises for a bad document.

    That is the whole point, and it is PRD F-02 criterion 3: a corrupted
    file must produce one Failed row and let the batch finish. A caller
    that has to wrap this in a try/except to survive a scan of a real
    folder would have the criterion backwards.

    Returns CONVERTED with markdown and a page count; FAILED with a
    reason the user can act on; or SKIPPED with a reason that is nobody's
    fault. `markdown` is set on CONVERTED only and `reason` on the other
    two only, so no outcome can carry a contradictory pair.
    """
    path = Path(path)
    extension = file_type(path)
    converter = _CONVERTERS.get(extension)
    if converter is None:
        # Reached only if a caller hands over a file the scan should have
        # filtered out, so it repeats the scan's own wording rather than
        # inventing a second explanation for one situation.
        return ConversionResult(
            file_name=path.name,
            outcome=ConversionOutcome.SKIPPED,
            reason=UNSUPPORTED_TYPE_REASON,
        )

    try:
        extracted = converter(path)
    except DocumentFailedError as exc:
        return ConversionResult(
            file_name=path.name, outcome=ConversionOutcome.FAILED, reason=exc.reason
        )
    except Exception as exc:  # noqa: BLE001 - deliberate, see below
        # Last resort, and narrow in scope even though it is broad in
        # type: the only code inside `converter` that is not ours is a
        # third-party document parser being fed adversarial bytes, and
        # both of ours have already been caught throwing something
        # undeclared (pymupdf4llm's TypeError on an encrypted PDF, found
        # by probe). One such surprise must cost one file, not the whole
        # sync -- F-02 criterion 3 outranks a tidy exception list here.
        # It is logged with a full traceback, per .claude/rules/backend.md
        # ("never catch an error without logging the full traceback"), so
        # containing it never means hiding it.
        logger.exception("unexpected converter failure on %s", path.name)
        return ConversionResult(
            file_name=path.name,
            outcome=ConversionOutcome.FAILED,
            reason=_REASON_UNREADABLE.format(detail=f"{type(exc).__name__}: {exc}"),
        )

    text = extracted.text or ""
    # One emptiness gate for every rung, deliberately after conversion
    # rather than per format: "the converter ran and produced nothing" is
    # one condition, and a scanned PDF is only its most common cause. An
    # empty .txt and a DOCX of blank paragraphs reach it the same way.
    if len(text.strip()) < get_settings().conversion_min_text_chars:
        return ConversionResult(
            file_name=path.name,
            outcome=ConversionOutcome.SKIPPED,
            reason=_no_text_reason(extension),
        )
    return ConversionResult(
        file_name=path.name,
        outcome=ConversionOutcome.CONVERTED,
        markdown=text,
        page_count=extracted.page_count,
    )


def convert_files(paths: Iterable[str | Path]) -> list[ConversionResult]:
    """Convert several documents, one result each, in the order given.

    The batch demonstration of PRD F-02 criterion 3 at module level: it
    holds no state, so a failure cannot corrupt a later file, and it
    catches nothing, because `convert_file` already cannot raise for a
    bad document. If it ever needs a try/except, that is a bug in
    `convert_file`, not a gap here.

    Deliberately thin: no registry write, no sync_run row, no chunking,
    no ordering policy. Those are ST-17's, and putting them here would
    make the ladder untestable without a database."""
    return [convert_file(path) for path in paths]
