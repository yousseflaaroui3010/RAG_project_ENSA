"""Figures: the pictures, diagrams and schemas inside a document.

Text extraction (`conversion.py`) throws pictures away. This module finds
them, cuts each one out as a PNG, and records what surrounds it: the
caption, the nearest heading, the paragraph before and the paragraph after,
and the page or slide number. `sync.py` turns each figure into one
searchable card that points at the text section the figure sits in.

WHO DECIDES WHERE A FIGURE IS. Docling's layout model (IBM, MIT licence)
draws one box around each whole figure, labels included, and links its
caption. For a PDF, the PNG is then rendered by PyMuPDF from that exact
box on the original page, not taken from Docling's own page image, so the
crop is at print quality and identical to what the reader sees in the
file. Measured on a generated manual page on 2026-09-19: a vector diagram
of four boxes, two lines, a circle and six labels came out as ONE figure
with every label inside it; a logo repeated on every page and a framed
warning paragraph came out as nothing.

WHAT IS REFUSED, and why each rule exists:

* a region in the top or bottom margin band: running headers and footers
  carry logos, and a logo is repeated noise, never an answer;
* an image that repeats on several pages: the same logo placed elsewhere;
* a region Docling classifies as a logo or signature;
* a region too small to read;
* a PDF region with no drawing and no picture inside it: that is text in a
  frame, and extracting it as an image would hide words from search.

COST. Docling is slow on a laptop processor, so a PDF page is only handed
to it when PyMuPDF finds a picture or a drawing on that page. A PDF made
only of text, like a law, costs nothing here.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import uuid
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from config import get_settings

logger = logging.getLogger(__name__)

# Identifiers become file names; same allow-list as parent_store.
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+$")
_FIGURE_NAMESPACE = uuid.UUID("7a1c6f3e-2b4d-4f0a-9c1e-5d3b8a6f2e10")

# Docling picture classes that are never an answer.
_NOISE_CLASSES = frozenset({"logo", "signature", "stamp", "qr_code", "bar_code", "icon"})

_SUPPORTED = frozenset({".pdf", ".pptx", ".docx"})

# How far under a figure, in PDF points (1/72 inch), a caption may start.
# A property of page layout, about two lines of body text, not a tunable.
_CAPTION_GAP_POINTS = 40.0
# How far above a photo its label may sit: one line of small text.
_LABEL_GAP_POINTS = 20.0
# An image covering this much of a page is the page itself: a scan, or a
# full-page background. Found in review: a 4-page scanned PDF came out as
# four "figures" the size of the page, each a Gemini call for nothing.
_FULL_PAGE_FRACTION = 0.7

# A paragraph that starts like a caption, in French, English or Arabic.
_CAPTION_START = re.compile(
    r"^\s*(figure|fig\.|schéma|schema|image|illustration|photo|شكل|صورة)(\s|\d|:|$)", re.I
)


class UnsafeFigureIdError(ValueError):
    """A workspace or figure id that is not usable as a path segment."""


@dataclass(frozen=True)
class Figure:
    """One extracted figure and everything around it.

    `page` is the PDF page or PowerPoint slide number, 1-based, and None for
    a Word document, which has no fixed pages. `explanation` is written by a
    model at Sync time and is always shown to the reader as generated; it
    helps search find the figure and is never given to the answer writer."""

    id: str
    source_file: str
    index: int
    page: int | None
    caption: str
    heading: str
    context_before: str
    context_after: str
    image_sha256: str
    width_px: int
    height_px: int
    kind: str = ""
    explanation: str = ""

    def document_text(self) -> str:
        """What the document itself says about this figure: caption,
        section and the text around it. Nothing written by a model."""
        parts = [f"Figure : {self.caption}" if self.caption else "Figure"]
        if self.heading:
            parts.append(f"Section : {self.heading}")
        if self.context_before:
            parts.append(self.context_before)
        if self.context_after:
            parts.append(self.context_after)
        return "\n".join(parts)

    def card_text(self) -> str:
        """The searchable text: the document's own words, plus the
        generated description when there is one."""
        if not self.explanation:
            return self.document_text()
        return f"{self.document_text()}\nDescription générée : {self.explanation}"


@dataclass(frozen=True)
class ExtractedFigure:
    """A figure plus its PNG bytes, before it is stored."""

    figure: Figure
    png: bytes


# --- extraction ------------------------------------------------------------


def extract_figures(path: Path) -> list[ExtractedFigure]:
    """Every meaningful figure in one document, in reading order.

    Never raises for a bad or unusual document: figures are an addition to
    the text, and a figure failure must not turn a readable file into a
    failed one. Failures are logged and the file simply has no figures."""
    settings = get_settings()
    if not settings.figures_enabled or path.suffix.lower() not in _SUPPORTED:
        return []
    try:
        if path.suffix.lower() == ".pdf":
            drawn, photos, repeated = _pdf_page_plan(path)
            raws: list[_Raw] = []
            photo_only = [number for number in photos if number not in set(drawn)]
            if drawn:
                try:
                    candidates = _docling_candidates(path, drawn)
                    raws += _render_pdf_regions(path, candidates, repeated)
                except Exception:  # noqa: BLE001 -- the layout model is optional
                    # No layout model here (a host without its weights, or
                    # offline): drawn pages fall back to their photos, and
                    # the file's other pages lose nothing.
                    logger.warning(
                        "layout model unavailable for %s; keeping photos only",
                        path.name,
                        exc_info=True,
                    )
                    photo_only = photos
            if photo_only:
                raws += _photo_raws(path, photo_only, repeated)
        else:
            raws = _office_raws(path, _docling_candidates(path, None))
        found = _finish(path, raws)
    except Exception:  # noqa: BLE001 -- see docstring: never fail the file
        logger.exception("figure extraction failed for %s; indexing its text only", path.name)
        return []
    return found[: settings.figures_max_per_document]


def _pdf_pages_with_visuals(path: Path) -> tuple[list[int], frozenset[bytes]]:
    """Every page worth looking at, drawn or photographed, and the digests
    of images repeated across pages."""
    drawn, photos, repeated = _pdf_page_plan(path)
    return sorted(set(drawn) | set(photos)), repeated


def _pdf_page_plan(path: Path) -> tuple[list[int], list[int], frozenset[bytes]]:
    """Which pages hold drawn artwork, which hold photos, and which images
    are decoration.

    The cheap gate in front of the slow layout model. An image placed on
    `figure_repeat_limit` pages or more is decoration: a header logo, or a
    watermark behind the text. Found on the Moroccan Labour Code, where
    every one of 201 pages carries the same background image over 58% of
    the page; counting it would have sent the whole law to the layout
    model, about half an hour of Sync for zero figures.

    The split matters for speed and accuracy. A PHOTO is one embedded
    image whose exact frame the PDF records, so it is cut out directly. A
    DRAWING is many lines and shapes with no frame of its own, and only
    the layout model can say where it starts and ends. Found on a 32-page
    inspection report with nine photos per page: the layout model boxed
    each page's grid of nine photos as ONE picture, and took 25 seconds a
    page to do it."""
    import pymupdf

    settings = get_settings()
    per_page: list[tuple[int, list[tuple[bytes, float]], bool]] = []
    seen_on: Counter[bytes] = Counter()
    with pymupdf.open(path) as doc:
        for page in doc:
            area = page.rect.width * page.rect.height
            images = [
                (info["digest"], _rect_fraction(info["bbox"], area))
                for info in page.get_image_info(hashes=True)
            ]
            seen_on.update({digest for digest, _ in images})
            per_page.append((page.number + 1, images, _looks_drawn(page.get_drawings())))
    repeated = frozenset(d for d, n in seen_on.items() if n >= settings.figure_repeat_limit)
    drawn = [number for number, _images, looks_drawn in per_page if looks_drawn]
    photos = [
        number
        for number, images, _drawn in per_page
        if any(
            digest not in repeated
            and settings.figure_min_page_fraction <= fraction < _FULL_PAGE_FRACTION
            for digest, fraction in images
        )
    ]
    return drawn, photos, repeated


def _looks_drawn(drawings: list[dict[str, Any]]) -> bool:
    """Does this page's vector artwork look like a diagram?

    Text documents are full of vector lines that are not figures:
    underlines, heading bars, table rules. Measured on the CLEISS guide,
    whose eight text pages carry up to 481 such lines and not one real
    shape. A diagram shows itself either by several shapes with real
    width AND height (boxes, circles, arrows' heads), or by a line that is
    neither horizontal nor vertical, or by a curve: table grids have none
    of those, wiring schematics made only of lines usually have them."""
    shapes = 0
    for drawing in drawings:
        rect = drawing["rect"]
        if rect.width > 3 and rect.height > 3:
            shapes += 1
            if shapes >= get_settings().figure_min_drawings:
                return True
        for item in drawing.get("items", ()):
            if item[0] == "c":
                return True
            if item[0] == "l":
                start, end = item[1], item[2]
                if abs(start.x - end.x) > 2 and abs(start.y - end.y) > 2:
                    return True
    return False


def _rect_fraction(bbox: Any, page_area: float) -> float:
    x0, y0, x1, y1 = bbox
    return max(0.0, (x1 - x0) * (y1 - y0)) / page_area if page_area else 0.0


def _converter(fmt: str) -> Any:
    """A Docling converter for one input format, built on first use.

    Built lazily and cached because loading the layout model takes seconds,
    and a process that never syncs a document with pictures should never
    pay for it."""
    cached = _CONVERTERS.get(fmt)
    if cached is not None:
        return cached
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    if fmt == "pdf":
        options = PdfPipelineOptions()
        options.do_ocr = False
        options.do_table_structure = False
        options.generate_page_images = False
        options.generate_picture_images = False
        options.do_picture_classification = True
        converter = DocumentConverter(
            allowed_formats=[InputFormat.PDF],
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)},
        )
    else:
        converter = DocumentConverter(allowed_formats=[InputFormat.PPTX, InputFormat.DOCX])
    _CONVERTERS[fmt] = converter
    return converter


_CONVERTERS: dict[str, Any] = {}


# One figure before it is numbered: (page, top y, PNG or None, context).
_Raw = tuple[int | None, float, bytes | None, dict[str, str]]


def _docling_candidates(
    path: Path, pdf_pages: list[int] | None
) -> list[tuple[Any, Any, dict[str, str]]]:
    """Every picture the layout model finds, with its caption and context."""
    from docling_core.types.doc import PictureItem, SectionHeaderItem, TextItem

    is_pdf = pdf_pages is not None
    converter = _converter("pdf" if is_pdf else "office")
    documents = (
        [converter.convert(path, page_range=span).document for span in _spans(pdf_pages)]
        if is_pdf
        else [converter.convert(path).document]
    )

    candidates: list[tuple[Any, Any, dict[str, str]]] = []
    for doc in documents:
        items = [item for item, _level in doc.iterate_items()]
        heading = ""
        for position, item in enumerate(items):
            if isinstance(item, SectionHeaderItem) or str(getattr(item, "label", "")) == "title":
                heading = item.text.strip()
            if isinstance(item, PictureItem):
                if _classified_as_noise(item):
                    continue
                caption = item.caption_text(doc).strip()
                after = _neighbour_text(items, position, +1, TextItem, item)
                if not caption and _CAPTION_START.match(after):
                    # Word and PowerPoint do not link captions the way a PDF
                    # layout model does: the "Figure 1 : ..." line is simply
                    # the next paragraph. Take it as the caption, and the
                    # paragraph after it as the following context.
                    caption = after
                    after = _neighbour_text(items, position, +1, TextItem, item, skip=1)
                context = {
                    "caption": caption,
                    "heading": heading,
                    "before": _neighbour_text(items, position, -1, TextItem, item),
                    "after": after,
                    "kind": _top_class(item),
                }
                candidates.append((doc, item, context))
    return candidates


def _office_raws(path: Path, candidates: list[tuple[Any, Any, dict[str, str]]]) -> list[_Raw]:
    """Word and PowerPoint pictures are embedded files: take them as they are."""
    is_slides = path.suffix.lower() == ".pptx"
    return [
        (_page_of(item) if is_slides else None, float(order), _png_of(item.get_image(doc)), ctx)
        for order, (doc, item, ctx) in enumerate(candidates)
    ]


def _finish(path: Path, raws: list[_Raw]) -> list[ExtractedFigure]:
    """Reading order, size floor, numbering, ids."""
    ordered = sorted(
        (raw for raw in raws if raw[2] is not None), key=lambda raw: (raw[0] or 0, raw[1])
    )
    kept: list[ExtractedFigure] = []
    for page, _top, png, ctx in ordered:
        size = _png_size(png)
        if min(size) < get_settings().figure_min_px:
            continue
        sha = hashlib.sha256(png).hexdigest()
        kept.append(
            ExtractedFigure(
                figure=Figure(
                    id="",
                    source_file=path.name,
                    index=0,
                    page=page,
                    caption=ctx.get("caption", ""),
                    heading=ctx.get("heading", ""),
                    context_before=ctx.get("before", ""),
                    context_after=ctx.get("after", ""),
                    image_sha256=sha,
                    width_px=size[0],
                    height_px=size[1],
                    kind=ctx.get("kind", ""),
                ),
                png=png,
            )
        )
    return _drop_repeated(kept)


def _spans(pages: list[int]) -> list[tuple[int, int]]:
    """Consecutive page numbers grouped, so Docling is called once per run
    of pages rather than once per page."""
    spans: list[tuple[int, int]] = []
    for number in pages:
        if spans and number == spans[-1][1] + 1:
            spans[-1] = (spans[-1][0], number)
        else:
            spans.append((number, number))
    return spans


def _render_pdf_regions(
    path: Path, candidates: list[tuple[Any, Any, dict[str, str]]], repeated: frozenset[bytes]
) -> list[_Raw]:
    """Cut each figure out of the original page with PyMuPDF.

    A region that fails a rule in the module docstring gives nothing. A
    region that holds several separate photos is cut into one figure per
    photo: the layout model sometimes boxes a whole grid of photos as one
    picture, and one answer needs one photo, not a page of nine."""
    import pymupdf

    settings = get_settings()
    out: list[_Raw] = []
    with pymupdf.open(path) as pdf:
        for _doc, item, ctx in candidates:
            prov = item.prov[0]
            page = pdf[prov.page_no - 1]
            height = page.rect.height
            box = prov.bbox.to_top_left_origin(page_height=height)
            rect = pymupdf.Rect(box.l, box.t, box.r, box.b) & page.rect
            band = settings.figure_margin_band * height
            in_margin = rect.y1 <= band or rect.y0 >= height - band
            if rect.is_empty or in_margin or not _has_graphics(page, rect, repeated):
                continue
            inner = _photos_inside(page, rect, repeated)
            if len(inner) >= 2:
                out += [raw for bbox in inner if (raw := _photo_raw(page, bbox)) is not None]
                continue
            caption_block = _printed_caption(page, rect)
            if caption_block is not None:
                block_rect, text = caption_block
                ctx["caption"] = text
                if block_rect.y0 > rect.y0 + 0.5 * rect.height:
                    # The caption was printed inside the box the layout
                    # model drew: cut it off so the image holds only the
                    # figure and the words stay searchable as text.
                    rect = pymupdf.Rect(rect.x0, rect.y0, rect.x1, min(rect.y1, block_rect.y0))
            pixmap = page.get_pixmap(clip=rect, dpi=settings.figure_render_dpi)
            out.append((prov.page_no, rect.y0, pixmap.tobytes("png"), ctx))
    return out


def _photos_inside(page: Any, rect: Any, repeated: frozenset[bytes]) -> list[Any]:
    """The distinct, non-decorative photos lying (mostly) inside a region."""
    import pymupdf

    settings = get_settings()
    area = page.rect.width * page.rect.height
    found: list[Any] = []
    for info in page.get_image_info(hashes=True):
        if info["digest"] in repeated:
            continue
        box = pymupdf.Rect(info["bbox"])
        if not settings.figure_min_page_fraction <= _rect_fraction(box, area) < _FULL_PAGE_FRACTION:
            continue
        overlap = box & rect
        if overlap.is_empty or overlap.get_area() < 0.8 * box.get_area():
            continue
        if not any(abs(box.x0 - seen.x0) < 1 and abs(box.y0 - seen.y0) < 1 for seen in found):
            found.append(box)
    return found


def _photo_raws(path: Path, pages: list[int], repeated: frozenset[bytes]) -> list[_Raw]:
    """Every non-decorative photo on these pages, each cut out by its own
    frame. No layout model: the PDF already knows where each photo is."""
    import pymupdf

    out: list[_Raw] = []
    with pymupdf.open(path) as pdf:
        for number in pages:
            page = pdf[number - 1]
            for bbox in _photos_inside(page, page.rect, repeated):
                raw = _photo_raw(page, bbox)
                if raw is not None:
                    out.append(raw)
    return out


def _photo_raw(page: Any, bbox: Any) -> _Raw | None:
    """One photo, its label and the text around it."""
    import pymupdf

    settings = get_settings()
    height = page.rect.height
    rect = pymupdf.Rect(bbox) & page.rect
    band = settings.figure_margin_band * height
    if rect.is_empty or rect.y1 <= band or rect.y0 >= height - band:
        return None
    caption = ""
    printed = _printed_caption(page, rect)
    if printed is not None:
        caption = printed[1]
    else:
        caption = _label_above(page, rect)
    before, after = _text_around(page, rect, caption)
    pixmap = page.get_pixmap(clip=rect, dpi=settings.figure_render_dpi)
    context = {"caption": caption, "heading": "", "before": before, "after": after, "kind": "photo"}
    return (page.number + 1, rect.y0, pixmap.tobytes("png"), context)


def _label_above(page: Any, rect: Any) -> str:
    """The short line printed right above a photo, centred over it.

    Inspection reports, catalogues and photo annexes label each photo this
    way ("WALLS/FLOORS" over a picture of a floor). Only text whose centre
    lies over the photo counts, so the label of the next photo in the row
    is never borrowed."""
    words: list[str] = []
    # Margins included: the first row of photos often starts just under
    # the page's top edge, and its labels sit inside the header band.
    for line in _lines(page, skip_margins=False):
        box, text = line
        centre = (box.x0 + box.x1) / 2
        if rect.x0 <= centre <= rect.x1 and rect.y0 - _LABEL_GAP_POINTS <= box.y1 <= rect.y0 + 2:
            words.append(text)
    return " ".join(words)[:200]


def _text_around(page: Any, rect: Any, caption: str) -> tuple[str, str]:
    """The nearest text above and below a photo, caption excluded."""
    limit = get_settings().figure_context_chars
    above = [
        (box, text)
        for box, text in _lines(page)
        if box.y1 <= rect.y0 + 2 and text not in caption
    ]
    below = [
        (box, text)
        for box, text in _lines(page)
        if box.y0 >= rect.y1 - 2 and text not in caption
    ]
    before = " ".join(text for _box, text in sorted(above, key=lambda b: b[0].y1)[-3:])
    after = " ".join(text for _box, text in sorted(below, key=lambda b: b[0].y0)[:3])
    return before[-limit:], after[:limit]


def _lines(page: Any, skip_margins: bool = True) -> list[tuple[Any, str]]:
    """Every text line on a page, with its box; page furniture (header and
    footer bands) excluded unless `skip_margins` is False."""
    import pymupdf

    height = page.rect.height
    band = get_settings().figure_margin_band * height if skip_margins else -1.0
    lines: list[tuple[Any, str]] = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            text = " ".join(span["text"] for span in line["spans"]).strip()
            box = pymupdf.Rect(line["bbox"])
            if text and band < box.y0 < height - band:
                lines.append((box, " ".join(text.split())))
    return lines


def _printed_caption(page: Any, rect: Any) -> tuple[Any, str] | None:
    """A caption-shaped text block at the bottom of, or just under, a figure.

    Found on Wikipedia's PDF export, where each picture sits in a frame
    with its own caption printed under it: the layout model drew its box
    around picture AND caption, then linked the NEXT figure's caption, so
    "Figure 5" was filed as "Figure 6". The printed block is the ground
    truth when there is one; the layout model's link is the fallback."""
    import pymupdf

    below_limit = rect.y1 + _CAPTION_GAP_POINTS
    best: tuple[Any, str] | None = None
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        block = pymupdf.Rect(x0, y0, x1, y1)
        overlaps_width = min(block.x1, rect.x1) - max(block.x0, rect.x0) > 0.3 * block.width
        starts_low = rect.y0 + 0.5 * rect.height <= block.y0 <= below_limit
        clean = " ".join(text.split())
        if overlaps_width and starts_low and _CAPTION_START.match(clean):
            if best is None or block.y0 < best[0].y0:
                best = (block, clean)
    return best


def _has_graphics(page: Any, rect: Any, repeated: frozenset[bytes]) -> bool:
    """True when the region holds a picture or a vector drawing.

    The guard against the worst mistake this module can make: cutting a
    block of TEXT out as an image, which would hide those words from
    search behind a picture of them. A repeated image (watermark, logo)
    does not count, or every paragraph printed over a watermark would
    qualify. A single drawn frame around text does not count either: the
    region must hold more drawings than a border."""
    for info in page.get_image_info(hashes=True):
        if info["digest"] not in repeated and rect.intersects(info["bbox"]):
            return True
    inside = [d for d in page.get_drawings() if rect.intersects(d["rect"])]
    return len(inside) >= 2


def _neighbour_text(
    items: list[Any], start: int, step: int, text_type: type, picture: Any, skip: int = 0
) -> str:
    """The nearest body paragraph before or after a figure, not its caption.

    `skip` passes over that many body paragraphs first: 1 when the first
    one after the figure turned out to be its caption."""
    limit = get_settings().figure_context_chars
    captions = {ref.cref for ref in getattr(picture, "captions", [])}
    position = start + step
    while 0 <= position < len(items):
        item = items[position]
        label = str(getattr(item, "label", ""))
        if label in {"title", "section_header"}:
            # A new slide or section starts: its text is not this figure's.
            return ""
        if (
            isinstance(item, text_type)
            and getattr(item, "self_ref", None) not in captions
            and label not in {"caption", "page_header", "page_footer"}
            and item.text.strip()
        ):
            if skip:
                skip -= 1
                position += step
                continue
            text = " ".join(item.text.split())
            return text[:limit] if step > 0 else text[-limit:]
        position += step
    return ""


def _classified_as_noise(picture: Any) -> bool:
    return _top_class(picture) in _NOISE_CLASSES


def _top_class(picture: Any) -> str:
    """Docling's most likely class for a picture, or "" when it gave none.

    Read defensively: the classifier's output moved from `annotations` to
    `meta` between Docling releases, and a missing class must mean "keep
    the figure", never "crash the sync"."""
    meta = getattr(picture, "meta", None)
    sources = [getattr(meta, "classification", None)] if meta is not None else []
    sources += list(getattr(picture, "annotations", []) or [])
    for source in sources:
        predictions = getattr(source, "predictions", None) or getattr(
            source, "predicted_classes", None
        )
        if predictions:
            best = max(predictions, key=lambda p: getattr(p, "confidence", 0.0))
            return str(getattr(best, "class_name", "")).lower()
    return ""


def _page_of(picture: Any) -> int | None:
    prov = getattr(picture, "prov", None)
    return prov[0].page_no if prov else None


def _png_of(image: Any) -> bytes | None:
    if image is None:
        return None
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _png_size(png: bytes) -> tuple[int, int]:
    """Width and height straight from the PNG header."""
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


def _drop_repeated(figures: list[ExtractedFigure]) -> list[ExtractedFigure]:
    """Remove images that appear on several pages: logos placed in the body."""
    threshold = get_settings().figure_repeat_limit
    counts = Counter(item.figure.image_sha256 for item in figures)
    kept = [item for item in figures if counts[item.figure.image_sha256] < threshold]
    return [
        ExtractedFigure(
            figure=Figure(
                **{
                    **asdict(item.figure),
                    "index": i,
                    "id": figure_id(item.figure.source_file, i, item.figure.image_sha256),
                }
            ),
            png=item.png,
        )
        for i, item in enumerate(kept)
    ]


def figure_id(source_file: str, index: int, image_sha256: str) -> str:
    """Stable id: the same image at the same place gets the same id."""
    return uuid.uuid5(_FIGURE_NAMESPACE, f"{source_file}\x00{index}\x00{image_sha256}").hex


# --- storage ---------------------------------------------------------------
#
# One directory per workspace, like the parent store: a PNG and a JSON card
# per figure. Isolation between workspaces is a property of the filesystem.


def _check(value: str, kind: str) -> str:
    if not value or not _SAFE_IDENTIFIER.match(value):
        raise UnsafeFigureIdError(f"{kind} is not usable as a path segment: {value!r}")
    return value


def _workspace_dir(workspace_id: str, base_path: str | Path | None) -> Path:
    root = Path(base_path if base_path is not None else get_settings().figure_store_path)
    return root / _check(workspace_id, "workspace id")


def save_figures(
    *, workspace_id: str, figures: list[ExtractedFigure], base_path: str | Path | None = None
) -> int:
    if not figures:
        # Most files have no figures: create nothing on disk for them.
        return 0
    folder = _workspace_dir(workspace_id, base_path)
    folder.mkdir(parents=True, exist_ok=True)
    for item in figures:
        name = _check(item.figure.id, "figure id")
        (folder / f"{name}.png").write_bytes(item.png)
        (folder / f"{name}.json").write_text(
            json.dumps(asdict(item.figure), ensure_ascii=False), encoding="utf-8"
        )
    return len(figures)


def load_figure(
    *, workspace_id: str, figure_id: str, base_path: str | Path | None = None
) -> Figure | None:
    path = _workspace_dir(workspace_id, base_path) / f"{_check(figure_id, 'figure id')}.json"
    try:
        return Figure(**json.loads(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, ValueError, TypeError):
        return None


def figure_png_path(
    *, workspace_id: str, figure_id: str, base_path: str | Path | None = None
) -> Path | None:
    path = _workspace_dir(workspace_id, base_path) / f"{_check(figure_id, 'figure id')}.png"
    return path if path.is_file() else None


def figures_of(
    *, workspace_id: str, source_file: str, base_path: str | Path | None = None
) -> list[Figure]:
    folder = _workspace_dir(workspace_id, base_path)
    if not folder.is_dir():
        return []
    found: list[Figure] = []
    for card in folder.glob("*.json"):
        try:
            figure = Figure(**json.loads(card.read_text(encoding="utf-8")))
        except (ValueError, TypeError):
            continue
        if figure.source_file == source_file:
            found.append(figure)
    return sorted(found, key=lambda f: f.index)


def delete_figures(
    *, workspace_id: str, source_file: str, base_path: str | Path | None = None
) -> int:
    folder = _workspace_dir(workspace_id, base_path)
    removed = 0
    found = figures_of(workspace_id=workspace_id, source_file=source_file, base_path=base_path)
    for figure in found:
        for suffix in (".png", ".json"):
            (folder / f"{figure.id}{suffix}").unlink(missing_ok=True)
        removed += 1
    return removed


def delete_workspace_figures(*, workspace_id: str, base_path: str | Path | None = None) -> int:
    folder = _workspace_dir(workspace_id, base_path)
    if not folder.is_dir():
        return 0
    removed = 0
    for path in folder.iterdir():
        if path.suffix in {".png", ".json"}:
            path.unlink(missing_ok=True)
            removed += path.suffix == ".json"
    if not any(folder.iterdir()):
        folder.rmdir()
    return removed
