"""ST-13 exit gate: the fixture corpus converts, a corrupted file reports
Failed, and a scanned PDF reports Skipped with a reason.

Reference: docs/phase2/Sanad_Architecture_v1.0.md ADR-07 (the ladder:
pymupdf4llm for PDF, markitdown for DOCX, passthrough for TXT and MD),
docs/phase2/Sanad_PRD_v1.0.md F-02 (criterion 3: one failing file never
blocks the rest), F-16 (binding V1: a scanned PDF is Skipped with the
reason stated) and section 11's failure table.

Every fixture is a real file with real bytes, built here rather than
committed: a genuine multi-page PDF from pymupdf, a genuine OOXML package
from `zipfile`, a genuinely encrypted PDF, genuinely corrupted bytes. The
converters are never mocked. That is the point -- ST-13's whole risk lives
in what two third-party parsers do with hostile input, and a mocked parser
would answer that question by assuming it. The ST-11 review found a test
that passed while proving nothing; a fake PDF would be that test again.

Assertions come in pairs wherever a mutation could restore a DEFAULT
rather than remove behaviour (the ST-12 lesson recorded in BUILD-STATE):
a one-sided bound cannot see a value that falls back to something
plausible.
"""

from __future__ import annotations

import logging
import zipfile

import pymupdf
import pytest

import conversion
from config import get_settings
from conversion import ConversionOutcome

# --- fixture builders -------------------------------------------------


def _pdf_with_headings(path, pages=2):
    """A real PDF whose big text becomes markdown headings. Two pages by
    default so a page count of 1 (a plausible hardcoded default) is
    distinguishable from a page count that was actually read."""
    doc = pymupdf.open()
    for number in range(1, pages + 1):
        page = doc.new_page()
        page.insert_text((72, 100), f"Chapitre {number}", fontsize=24)
        page.insert_text((72, 140), f"Corps du texte de la page {number}.", fontsize=11)
    doc.save(path)
    doc.close()
    return path


def _scanned_pdf(path):
    """A PDF with an image and no text layer at all -- what a flatbed
    scanner produces, and the F-16 binding case."""
    doc = pymupdf.open()
    page = doc.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 200))
    pixmap.set_rect(pixmap.irect, (255, 240, 200))
    page.insert_image(pymupdf.Rect(50, 50, 250, 250), pixmap=pixmap)
    doc.save(path)
    doc.close()
    return path


def _locked_pdf(path):
    """A real AES-256 encrypted PDF. Note it OPENS without error; only
    `needs_pass` reveals it, which is exactly the trap `_read_pdf` guards."""
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), "Confidentiel", fontsize=20)
    doc.save(
        path,
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="user",
    )
    doc.close()
    return path


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml"
 ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1"
 Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
 Target="word/document.xml"/>
</Relationships>"""

_DOCUMENT_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body>
<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Titre principal</w:t></w:r></w:p>
<w:p><w:r><w:t>Un paragraphe de contenu.</w:t></w:r></w:p>
<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t>Sous titre</w:t></w:r></w:p>
</w:body>
</w:document>"""


def _docx(path, document_xml=_DOCUMENT_XML):
    """A genuine minimal OOXML package, assembled with the standard
    library. Built by hand on purpose: python-docx is not a dependency of
    this project, and adding one to write test fixtures would be a real
    dependency bought with a test's convenience."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("[Content_Types].xml", _CONTENT_TYPES)
        package.writestr("_rels/.rels", _RELS)
        package.writestr("word/document.xml", document_xml)
    return path


# --- the happy rungs --------------------------------------------------


def test_pdf_converts_and_preserves_headings(tmp_path):
    """ADR-07's entire reason for keeping PDFs off markitdown: the parent
    splitter cuts on markdown headings (architecture 7.5), so a converter
    that flattens them destroys the structure retrieval depends on.

    Both halves are asserted. Heading markup alone would still pass if the
    converter dropped the body; body text alone would still pass if it
    dropped every heading -- which is precisely the regression ADR-07 is
    written to prevent."""
    result = conversion.convert_file(_pdf_with_headings(tmp_path / "code.pdf"))

    assert result.outcome is ConversionOutcome.CONVERTED
    assert result.reason is None
    assert "# Chapitre 1" in result.markdown
    assert "# Chapitre 2" in result.markdown
    assert "Corps du texte de la page 1." in result.markdown
    assert "Corps du texte de la page 2." in result.markdown


def test_pdf_reports_its_real_page_count(tmp_path):
    """PRD F-02 criterion 1 promises each added file is reported "with its
    page count", and db/schema.sql has the column for it.

    Three page counts are checked, not one. A single assertion against a
    2-page file cannot tell a real read from a hardcoded 2, and `None` or
    `1` are both plausible defaults a mutation could restore."""
    counts = {}
    for pages in (1, 2, 5):
        result = conversion.convert_file(
            _pdf_with_headings(tmp_path / f"doc{pages}.pdf", pages=pages)
        )
        assert result.outcome is ConversionOutcome.CONVERTED
        counts[pages] = result.page_count

    assert counts == {1: 1, 2: 2, 5: 5}


def test_docx_converts_and_preserves_headings(tmp_path):
    result = conversion.convert_file(_docx(tmp_path / "note.docx"))

    assert result.outcome is ConversionOutcome.CONVERTED
    assert "# Titre principal" in result.markdown
    assert "## Sous titre" in result.markdown
    assert "Un paragraphe de contenu." in result.markdown


def test_docx_has_no_page_count(tmp_path):
    """None means "this format has no pages", not "we did not look". A
    DOCX has no fixed pagination until something renders it, so any number
    here would be invented."""
    result = conversion.convert_file(_docx(tmp_path / "note.docx"))

    assert result.outcome is ConversionOutcome.CONVERTED
    assert result.page_count is None


def test_markdown_file_passes_through_unchanged(tmp_path):
    source = "# Titre\n\nUn paragraphe avec des accents: congés payés.\n"
    path = tmp_path / "readme.md"
    path.write_text(source, encoding="utf-8")

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.CONVERTED
    assert result.markdown == source
    assert result.page_count is None


def test_txt_passes_through_unchanged(tmp_path):
    source = "Ceci est un document texte simple.\nDeuxieme ligne.\n"
    path = tmp_path / "notes.txt"
    path.write_text(source, encoding="utf-8")

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.CONVERTED
    assert result.markdown == source


def test_utf8_bom_is_stripped_from_the_first_heading(tmp_path):
    """Windows editors prepend a byte-order mark. Decoded as plain UTF-8 it
    survives as an invisible first character, so the file starts with
    '\\ufeff# Titre' and the chunker's heading match fails on a document
    that looks perfect in every editor. `text_file_encoding` is
    "utf-8-sig" for this reason.

    Asserted from both ends: the BOM is gone AND the heading is intact at
    position zero. Checking only that the BOM is absent would also pass if
    the whole first line had been eaten."""
    path = tmp_path / "bom.md"
    path.write_bytes("# Titre\n\nCorps.\n".encode("utf-8-sig"))

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.CONVERTED
    assert "﻿" not in result.markdown
    assert result.markdown.startswith("# Titre")


# --- the Failed rung (PRD F-02 criterion 3, section 11 failure table) --


def test_corrupted_pdf_reports_failed_with_a_reason(tmp_path):
    """Exit gate. The reason is user-facing (it lands in sync_item.reason
    and renders in the S2 file table), so it is asserted to be real prose,
    not merely non-None."""
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\nthis is not a pdf at all\n" + b"\x00\xff" * 50)

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.FAILED
    assert result.markdown is None
    assert "damaged" in result.reason
    assert len(result.reason.split()) > 3


def test_empty_pdf_reports_failed(tmp_path):
    """A zero-byte .pdf raises EmptyFileError, a SUBCLASS of FileDataError.
    Held here so a future narrowing of that except clause to the subclass
    list cannot silently drop the truncated-download case."""
    path = tmp_path / "empty.pdf"
    path.write_bytes(b"")

    assert conversion.convert_file(path).outcome is ConversionOutcome.FAILED


def test_password_protected_pdf_reports_failed_with_a_reason(tmp_path):
    """PRD section 11: "Corrupted or password-protected file -> Failed with
    reason". The trap this covers: pymupdf OPENS an encrypted PDF without
    complaint and even answers `page_count`; only `needs_pass` tells the
    truth. Without that check pymupdf4llm dies on an undeclared TypeError
    mid-batch.

    Asserted as FAILED *and* on the password wording, because a generic
    failure would technically satisfy the first half while telling the
    user nothing they can act on."""
    result = conversion.convert_file(_locked_pdf(tmp_path / "locked.pdf"))

    assert result.outcome is ConversionOutcome.FAILED
    assert "password" in result.reason


def test_corrupted_docx_reports_failed_and_never_returns_its_own_bytes(tmp_path):
    """The most dangerous behaviour in this module, and the reason
    `_read_docx` validates the package itself.

    markitdown 0.1.5 does not raise on a `.docx` it cannot parse as Word:
    it falls through to another converter and returns the raw bytes AS A
    SUCCESS. Verified -- this exact fixture came back as the string
    'PK\\x03\\x04garbage-not-a-zip' with no exception. Reported Added,
    those bytes would be chunked, embedded, and one day cited to a user as
    a source.

    So the second assertion is the load-bearing one: FAILED alone would
    still pass if the guard were removed and something else happened to
    reject it, but garbage can never be in `markdown` while this holds."""
    path = tmp_path / "broken.docx"
    path.write_bytes(b"PK\x03\x04garbage-not-a-zip")

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.FAILED
    assert result.markdown is None
    assert "Word" in result.reason


def test_valid_zip_that_is_not_a_word_file_reports_failed(tmp_path):
    """The half of the fallback that `zipfile.is_zipfile` alone misses: a
    real ZIP renamed .docx passes the zip check, and markitdown returns a
    directory listing of its entries as the document's text. Only the
    `word/document.xml` check catches it."""
    path = tmp_path / "archive.docx"
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("hello.txt", "hi")

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.FAILED
    assert result.markdown is None


def test_docx_with_a_corrupt_body_reports_failed(tmp_path):
    """The rung's last guard: a package that IS a Word file by structure
    but whose `word/document.xml` is not valid XML. It passes both the zip
    and the main-part checks, so only markitdown's own
    `MarkItDownException` catches it -- verified reachable, not assumed."""
    path = _docx(tmp_path / "mangled.docx", document_xml="not xml at all <<<>>>")

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.FAILED
    assert result.markdown is None
    assert "Word" in result.reason


def test_pdf_renamed_to_docx_reports_failed(tmp_path):
    """A PDF with the wrong extension must not quietly take the DOCX rung:
    markitdown converts it with its own PDF path, which ADR-07 rejects
    because it strips heading structure. The user gets one honest Failed
    row instead of a silently degraded document."""
    source = _pdf_with_headings(tmp_path / "real.pdf")
    path = tmp_path / "mislabelled.docx"
    path.write_bytes(source.read_bytes())

    assert conversion.convert_file(path).outcome is ConversionOutcome.FAILED


def test_undecodable_text_file_reports_failed(tmp_path):
    """Decoding is strict on purpose. A latin-1 fallback never raises, so
    a mis-encoded French file would be indexed as 'CongÃ©s payÃ©s' and only
    surface when an answer quoted the mojibake back."""
    path = tmp_path / "legacy.txt"
    path.write_bytes(b"Cong\xe9s pay\xe9s\xff\xfe invalid \x80\x81")

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.FAILED
    assert "UTF-8" in result.reason


@pytest.mark.parametrize("name", ["gone.pdf", "gone.docx", "gone.txt"])
def test_an_ordinary_missing_file_is_not_logged_as_an_unexpected_failure(
    tmp_path, caplog, name
):
    """.claude/rules/backend.md: "Keep logs free of noise so real bugs
    stand out like a spraying leak, never a slow rot."

    A file deleted mid-sync is routine. If it reached the last-resort
    catch it would be logged ERROR with a full traceback on every sync,
    and the one log line that means "a parser crashed in a way we have
    never seen" would be buried in false alarms. Each rung therefore
    names this case explicitly, and this test is what stops a future
    simplification from quietly merging them back.

    Asserted against the paired test below, which proves a genuinely
    undeclared crash IS logged -- silence alone would also be produced by
    a logger that never fires at all."""
    with caplog.at_level(logging.ERROR, logger="conversion"):
        result = conversion.convert_file(tmp_path / name)

    assert result.outcome is ConversionOutcome.FAILED
    assert caplog.records == []


def test_a_converter_crashing_in_an_undeclared_way_is_logged_with_a_traceback(
    monkeypatch, tmp_path, caplog
):
    """The other bound. Containing a surprise must never mean hiding it
    (.claude/rules/backend.md: "Never catch an error without logging the
    full traceback")."""

    def explode(path):
        raise RuntimeError("undeclared parser bug")

    monkeypatch.setitem(conversion._CONVERTERS, "txt", explode)
    path = tmp_path / "landmine.txt"
    path.write_text("content", encoding="utf-8")

    with caplog.at_level(logging.ERROR, logger="conversion"):
        conversion.convert_file(path)

    assert len(caplog.records) == 1
    assert caplog.records[0].exc_info is not None


def test_a_converter_crashing_in_an_undeclared_way_costs_one_file(monkeypatch, tmp_path):
    """The last-resort catch. Both parsers have already been caught
    throwing something undeclared on hostile input, and F-02 criterion 3
    says one surprise costs one file, never the batch.

    The failure is injected rather than found, because a bug we can
    reproduce on demand is one we have already fixed."""

    def explode(path):
        raise RuntimeError("undeclared parser bug")

    monkeypatch.setitem(conversion._CONVERTERS, "txt", explode)
    path = tmp_path / "landmine.txt"
    path.write_text("content", encoding="utf-8")

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.FAILED
    assert "undeclared parser bug" in result.reason


@pytest.mark.parametrize("name", ["gone.txt", "gone.md", "gone.pdf", "gone.docx"])
def test_missing_file_reports_failed_on_every_rung(tmp_path, name):
    """A file deleted between the scan and the conversion is an ordinary
    race in a sync, and every rung has to survive it identically.

    Parametrised across all four because each rung reaches it by a
    different exception: OSError for text, `pymupdf.FileNotFoundError`
    (which shadows the builtin and subclasses RuntimeError, so `except
    OSError` does NOT catch it) for PDF, and the builtin OSError for
    DOCX. The reason is asserted too -- a missing file must not be
    described as damaged, or its owner goes hunting for corruption in a
    file that simply is not there."""
    result = conversion.convert_file(tmp_path / name)

    assert result.outcome is ConversionOutcome.FAILED
    assert "could not be read" in result.reason
    assert "damaged" not in result.reason


# --- the Skipped rung (F-16 binding V1 behaviour) ---------------------


def test_scanned_pdf_reports_skipped_with_a_reason(tmp_path):
    """Exit gate, and the binding V1 behaviour under PRD F-16: a scanned
    PDF is Skipped WITH THE REASON STATED, not Failed -- nothing is
    broken and there is nothing for the user to fix.

    The wording is asserted because "with the reason stated" is the
    requirement; a bare Skipped with a null reason satisfies the enum and
    fails the promise."""
    result = conversion.convert_file(_scanned_pdf(tmp_path / "scan.pdf"))

    assert result.outcome is ConversionOutcome.SKIPPED
    assert result.markdown is None
    assert "no text layer" in result.reason
    assert "scan" in result.reason


def test_scanned_pdf_is_not_reported_as_failed(tmp_path):
    """Guards the distinction itself. Skipped and Failed are different
    promises to the user -- "nothing to index here" versus "this file is
    broken, go fix it" -- and collapsing them would send someone hunting
    for corruption in a perfectly good scan."""
    assert conversion.convert_file(_scanned_pdf(tmp_path / "scan.pdf")).outcome is not (
        ConversionOutcome.FAILED
    )


def test_empty_text_file_reports_skipped_without_the_scan_wording(tmp_path):
    """An empty .txt has nothing to index either, but telling its owner
    the file "is a scan or images only" would be nonsense. Same outcome,
    honest reason."""
    path = tmp_path / "blank.txt"
    path.write_text("   \n\n  \t\n", encoding="utf-8")

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.SKIPPED
    assert "no text" in result.reason
    assert "scan" not in result.reason


def test_docx_with_no_text_reports_skipped(tmp_path):
    """A valid Word file of empty paragraphs reaches the same shared
    emptiness gate as a scan."""
    empty_body = _DOCUMENT_XML.replace("Titre principal", "").replace(
        "Un paragraphe de contenu.", ""
    ).replace("Sous titre", "")
    path = _docx(tmp_path / "blank.docx", document_xml=empty_body)

    assert conversion.convert_file(path).outcome is ConversionOutcome.SKIPPED


def test_unsupported_extension_reports_skipped_with_the_shared_reason(tmp_path):
    """A file type outside the V1 set (PPTX is F-11 / ST-48). The reason
    is the SAME constant the folder scan uses -- asserted by identity, not
    by repeating the string here, so one reworded copy cannot drift away
    from the other and show the user two explanations for one situation."""
    path = tmp_path / "deck.pptx"
    path.write_bytes(b"anything")

    result = conversion.convert_file(path)

    assert result.outcome is ConversionOutcome.SKIPPED
    assert result.reason == conversion.UNSUPPORTED_TYPE_REASON


def test_min_text_chars_is_read_from_config_at_both_bounds(tmp_path, monkeypatch):
    """The ST-12 lesson, applied: a mutation that ignores this setting and
    hardcodes 1 restores a DEFAULT rather than removing behaviour, so a
    test run at the default value cannot see it.

    Run at a NON-default threshold, and asserted on both sides of it:
    just below must Skip, just above must Convert. Either assertion alone
    is satisfiable by a converter that always answers the same way."""
    settings = get_settings().model_copy(update={"conversion_min_text_chars": 10})
    monkeypatch.setattr(conversion, "get_settings", lambda: settings)

    below = tmp_path / "short.txt"
    below.write_text("123456789", encoding="utf-8")  # 9 chars
    above = tmp_path / "long.txt"
    above.write_text("12345678901", encoding="utf-8")  # 11 chars

    assert conversion.convert_file(below).outcome is ConversionOutcome.SKIPPED
    assert conversion.convert_file(above).outcome is ConversionOutcome.CONVERTED


# --- batch behaviour: PRD F-02 criterion 3 ----------------------------


def test_one_bad_file_never_stops_the_others(tmp_path):
    """The exit gate's headline promise, exercised on a mixed corpus with
    the failure deliberately placed FIRST, so a batch that aborts on it
    loses everything after it.

    Every outcome is asserted, not just the count of survivors: asserting
    only "4 converted" would pass if the corrupted file had quietly
    converted into garbage too."""
    corrupt = tmp_path / "1-broken.pdf"
    corrupt.write_bytes(b"%PDF-1.7 not really\x00\xff")
    scan = _scanned_pdf(tmp_path / "2-scan.pdf")
    good_pdf = _pdf_with_headings(tmp_path / "3-good.pdf")
    good_docx = _docx(tmp_path / "4-note.docx")
    good_md = tmp_path / "5-readme.md"
    good_md.write_text("# Titre\n\nCorps.\n", encoding="utf-8")
    good_txt = tmp_path / "6-notes.txt"
    good_txt.write_text("Du texte.\n", encoding="utf-8")

    results = conversion.convert_files(
        [corrupt, scan, good_pdf, good_docx, good_md, good_txt]
    )

    assert [r.outcome for r in results] == [
        ConversionOutcome.FAILED,
        ConversionOutcome.SKIPPED,
        ConversionOutcome.CONVERTED,
        ConversionOutcome.CONVERTED,
        ConversionOutcome.CONVERTED,
        ConversionOutcome.CONVERTED,
    ]
    assert [r.file_name for r in results] == [
        "1-broken.pdf",
        "2-scan.pdf",
        "3-good.pdf",
        "4-note.docx",
        "5-readme.md",
        "6-notes.txt",
    ]
    assert all(r.markdown for r in results if r.converted)


def test_results_never_carry_a_contradictory_pair(tmp_path):
    """The invariant behind the dataclass docstring: markdown is set on
    CONVERTED only, reason on the other two only. Checked across the whole
    corpus in one place so no single rung can drift out of it."""
    corrupt = tmp_path / "broken.pdf"
    corrupt.write_bytes(b"%PDF-1.7 not really\x00\xff")
    paths = [
        corrupt,
        _scanned_pdf(tmp_path / "scan.pdf"),
        _pdf_with_headings(tmp_path / "good.pdf"),
        _docx(tmp_path / "note.docx"),
    ]

    for result in conversion.convert_files(paths):
        if result.converted:
            assert result.markdown and result.reason is None
        else:
            assert result.reason and result.markdown is None


def test_every_supported_extension_has_a_rung():
    """The ladder and the V1 set are one decision in two files. Adding
    "pptx" to `supported_document_extensions` without writing its
    converter would otherwise ship a silent Skipped on every deck the
    scan hands over.

    Asserted as equality, both directions: a missing rung fails, and so
    does a rung for a type the scan never yields."""
    assert set(conversion._CONVERTERS) == set(get_settings().supported_document_extensions)


@pytest.mark.parametrize("name", ["doc.PDF", "note.DocX", "readme.MD", "notes.TXT"])
def test_extension_matching_is_case_insensitive(tmp_path, name):
    """Windows and macOS hand over `REPORT.PDF` routinely. Dispatch shares
    `change_detection.file_type` precisely so a file the scan accepted can
    never be a file the ladder refuses."""
    path = tmp_path / name
    if path.suffix.lower() == ".pdf":
        _pdf_with_headings(path)
    elif path.suffix.lower() == ".docx":
        _docx(path)
    else:
        path.write_text("# Titre\n\nCorps.\n", encoding="utf-8")

    assert conversion.convert_file(path).outcome is ConversionOutcome.CONVERTED
