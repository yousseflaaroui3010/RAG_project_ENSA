"""ST-07 Corpus v1: the provenance record, the fetch, and the exit gate.

WHY THIS IS CODE AND NOT A MARKDOWN TABLE. `data/` is git-ignored, by
architecture (LD-06: documents stay on operator-controlled storage) and by
`.gitignore` line 8. The corpus therefore CANNOT reach the other machine
through git, and the previous attempt at a corpus proved it: three PDFs and
ten text files sat on one laptop for six days while the journal recorded
ST-07 as blocked. A table of URLs would have had the same fate, because a
table is a thing you re-do by hand and re-doing it by hand is what nobody
does. This file is the half that IS tracked, and it rebuilds the corpus from
nothing with one command.

    uv run python scripts/corpus.py fetch     # download whatever is missing
    uv run python scripts/corpus.py verify    # the ST-07 exit gate

WHAT `verify` PROVES, and why it does not do its own PDF inspection.
ST-07's exit gate is "files open, French text selectable (not scanned),
source and date logged per file". The temptation is to re-implement that
with pymupdf here. That would be a SECOND OPINION about the corpus, and a
second opinion can disagree with the product while both look green. So the
gate runs Sanad's own conversion ladder -- `conversion.convert_file`, the
same call the sync engine makes -- and requires CONVERTED for every file.
A scanned PDF comes back SKIPPED with its reason, which is exactly the
verdict PRD F-16 binds V1 to, and the gate fails on it. The thing being
proven is therefore "Sanad can read every file in Corpus v1", which is what
ST-18 actually needs, rather than "a script agreed with itself".

NO NEW DEPENDENCY. Downloads use `urllib.request` from the standard library
rather than httpx or requests. Adding a dependency needs a human under the
core law, and a corpus fetcher is not worth one.
"""

from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from change_detection import compute_fingerprint, is_supported  # noqa: E402
from conversion import ConversionOutcome, convert_file  # noqa: E402

# WHY A DIGEST IS PRINTED AT ALL, and why nothing enforces it.
#
# Running `fetch` twice produced `howto-sockets.txt` at 23,215 bytes on
# 2026-08-23 and 22,757 on 2026-08-29: docs.python.org rebuilds the archive
# upstream, so the manuals workspace is not byte-reproducible while the
# three HR PDFs are. Pinning a hash and failing on a mismatch is the obvious
# next move and is deliberately NOT taken here -- ST-35 owns freezing the
# corpus, and a freeze invented by this script first would be the wrong
# shape. What is owed today is visibility, so `compute_fingerprint` is
# called directly at both sites. It is the project's ONE file hasher: an
# earlier version of this file hand-rolled a second one that pulled the
# whole 1.5 MB labour code into memory and raised a bare OSError, which the
# ST-07 review removed.

# A page carrying fewer than this many characters is a picture of a page.
#
# The number exists because the ST-07 review found the exit gate passing a
# scan. `config.conversion_min_text_chars` is 1, which is the right floor
# for the PRODUCT -- F-16 binds V1 to skipping a scan, and one stray
# character is enough to prove a text layer exists -- but it is far too low
# for a CORPUS gate. Reproduced before this line was written: a three-page
# PDF whose only text is the page numbers "1 2 3" converts cleanly at 12
# characters and the gate said EXIT GATE MET.
#
# 200 is chosen from the corpus itself rather than from taste. The thinnest
# real file here runs 1,783 characters per page (the labour code, which is
# dense two-column legal text laid out with wide margins); the other two
# PDFs are over 3,200. A footer-only scan lands at 4. 200 sits an order of
# magnitude below the weakest real document and an order of magnitude above
# a scan, so it discriminates without being tuned to these three files.
_MIN_CHARS_PER_PAGE = 200

# Same idea for files with no pages. The thinnest real manual is 20,074
# characters; a stub or a truncated download is far below this.
_MIN_CHARS_UNPAGED = 1_000

CORPUS_ROOT = Path(__file__).resolve().parent.parent / "data" / "corpus"

# A browser-shaped User-Agent. Two of the four sources below are government
# hosts that answer a bare urllib request with 403; this is not evasion, the
# documents are public and unauthenticated, it is only that their WAF scores
# the default `Python-urllib/3.12` as a bot.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


@dataclass(frozen=True)
class Document:
    """One corpus file and everything ST-07 must log about it.

    `authority` is the field that does real work, and it records an
    EDITORIAL JUDGEMENT, not a rule from the signed pack. The distinction
    was forced by the ST-07 review and it matters.

    An earlier version of this docstring justified deleting a private
    consulting firm's 2016 summary of Moroccan labour law by quoting PRD
    section 14: "public material (official legal texts, public manuals)".
    That is motivated reasoning. The sentence sits under **Compliance** and
    its subject is personal data -- "if real personal data ever enters a
    workspace..." -- so it is a privacy rule, not a source-authority rule.
    Worse, read as an authority rule it would also exclude the CLEISS guide
    that this corpus KEEPS, which is neither an official legal text nor a
    manual. The real distinguisher used is the publisher, and no signed
    document mentions publishers at all.

    So: deleting a dated private commentary from a corpus that will be
    quoted in a graded legal-domain report is good editorial judgement, and
    it is claimed as nothing more. This field exists so the next document
    cannot arrive with its standing unstated, and so a reader of the report
    can see which claims rest on law and which rest on a summary.

    This is the project's own recurring failure, third instance: quote the
    clause before declaring something spec-bound. The citation escalation of
    2026-08-23 was withdrawn for it, and the corpus "stand-in" blocker this
    very story removed was another.
    """

    workspace: str
    file_name: str
    url: str
    title: str
    publisher: str
    published: str
    retrieved: str
    authority: str
    note: str = ""
    # Set when the file arrives inside an archive rather than on its own.
    zip_member: str | None = None


# --------------------------------------------------------------------------
# Workspace 1: HR and Moroccan labour law. LD-02 makes this the flagship.
#
# ONE of the three entries below is backed by PRD section 17, not all three,
# and an earlier version of this comment claimed otherwise. Section 17's four
# verified findings are ALL about the labour code: that it is publicly
# downloadable as a consolidated French PDF, its article count, the ILO's
# translation edition, and a bilingual edition. The consolidated text is
# therefore section-17 backed, though even it arrives from a host section 17
# does not name (adala.justice.gov.ma rather than the Casablanca investment
# portal or Abhatoo) -- same document, same Direction de la Législation,
# different mirror. The dahir 1-72-184 and the CLEISS guide appear nowhere in
# section 17 and were chosen by this story. Their justification is the note
# on each entry, not the signed pack.
# --------------------------------------------------------------------------
_HR = "https://adala.justice.gov.ma/api/uploads/2024/04/30/code%20du%20travail-1714463246806.pdf"

MANIFEST: tuple[Document, ...] = (
    Document(
        workspace="hr",
        file_name="code-travail-consolide-2011-justice.pdf",
        url=_HR,
        title="Code du travail, loi n° 65-99, version consolidée au 26 octobre 2011",
        publisher=(
            "Royaume du Maroc, Ministère de la Justice -- portail Adala "
            "(adala.justice.gov.ma), Direction de la Législation"
        ),
        published="2011-10-26 (consolidation)",
        retrieved="2026-08-29",
        authority="primary -- official consolidated legal text",
        note=(
            "The flagship document. CONSOLIDATED, so it carries the "
            "amendments through 2011 and lists them by dahir on its own "
            "first pages. Chosen over the ILO's 2004 Bulletin Officiel "
            "edition that this corpus previously used: both are named as "
            "verified sources in PRD section 17, but the 2004 edition is "
            "the text as first promulgated, and an HR generalist answering "
            "a question in 2026 from the unamended 2004 wording is the "
            "exact failure this product exists to prevent. Only ONE edition "
            "of the code is in the corpus on purpose -- two near-identical "
            "copies would compete for the same retrieval hit and make the "
            "ST-19 golden set score noise."
        ),
    ),
    Document(
        workspace="hr",
        file_name="dahir-1-72-184-securite-sociale-acaps.pdf",
        url="https://www.acaps.ma/fr/files/dahir1-72-184pdf",
        title=(
            "Dahir portant loi n° 1-72-184 du 27 juillet 1972 relatif au "
            "régime de sécurité sociale, tel que modifié et complété"
        ),
        publisher=(
            "Autorité de Contrôle des Assurances et de la Prévoyance "
            "Sociale (ACAPS), the Moroccan state regulator"
        ),
        published="1972-07-27, as amended",
        retrieved="2026-08-29",
        authority="primary -- official legal text, regulator's own copy",
        note=(
            "The law the CNSS runs on, which is the other half of the HR "
            "generalist's daily question: the labour code says what an "
            "employee is owed, this says what is declared and contributed "
            "for them. Sourced from ACAPS rather than from a summary site "
            "because it is the regulator publishing the text it enforces."
        ),
    ),
    Document(
        workspace="hr",
        file_name="cnss-regime-securite-sociale-cleiss.pdf",
        url=(
            "https://www.univ-tlse2.fr/medias/fichier/"
            "maroc-regime-de-securite-sociale-pour-salaries-version-n2"
        ),
        title="Le régime marocain de sécurité sociale (salariés)",
        publisher=(
            "CLEISS, Centre des liaisons européennes et internationales de "
            "sécurité sociale (French public body), via Université Toulouse 2"
        ),
        published="undated edition, 'version n2'",
        retrieved="2026-08-23",
        authority="secondary -- explanatory guide from a public body",
        note=(
            "The one deliberately SECONDARY document, and it earns its "
            "place: the two texts above are law, written as law, and a "
            "corpus of nothing but statute cannot answer 'how does this "
            "work in practice'. CLEISS is a French public body, not a "
            "commercial publisher. Labelled secondary here so nobody cites "
            "it in the report as if it were Moroccan law."
        ),
    ),
)


# --------------------------------------------------------------------------
# Workspace 2: technical manuals. LD-02 says "workspace 2 = technical
# manuals" and nothing more; PRD section 14 requires "public manuals" and
# persona P2 is a junior developer who "lives inside long technical manuals".
# The French Python documentation is exactly that, and its being French is
# load-bearing rather than incidental -- see below.
# --------------------------------------------------------------------------
_PY_DOCS_ZIP = "https://docs.python.org/fr/3/archives/python-3.14-docs-text.zip"

_MANUAL_STEMS = (
    "tutorial-introduction",
    "tutorial-controlflow",
    "tutorial-datastructures",
    "tutorial-modules",
    "tutorial-inputoutput",
    "tutorial-errors",
    "tutorial-classes",
    "howto-logging",
    "howto-sockets",
    "faq-programming",
)

MANIFEST += tuple(
    Document(
        workspace="manuals",
        file_name=f"{stem}.txt",
        url=_PY_DOCS_ZIP,
        # `tutorial-classes` -> `tutorial/classes.txt` inside the archive.
        zip_member=f"python-3.14-docs-text/{stem.replace('-', '/', 1)}.txt",
        title=f"Documentation Python 3.14 en français -- {stem.replace('-', '/', 1)}",
        publisher="Python Software Foundation, docs.python.org (French translation)",
        published="Python 3.14 documentation",
        retrieved="2026-08-23",
        authority="primary -- the project's own official manual",
        note=(
            "French on purpose, and this is the reason the workspace is "
            "these files rather than any ten manuals. It shares ordinary "
            "French vocabulary with the labour code -- 'durée', "
            "'conditions', 'article', 'obligations' -- so F-01's isolation "
            "claim ('an HR question never pulls passages from the technical "
            "manuals') has to be earned on similar text. ST-16 recorded the "
            "opposite failure: its first isolation corpus was so different "
            "that isolation passed by accident. It also exercises the TXT "
            "rung of the conversion ladder while the hr workspace exercises "
            "the PDF rung, so one sync covers both."
        ),
    )
    for stem in _MANUAL_STEMS
)


def _target(doc: Document) -> Path:
    return CORPUS_ROOT / doc.workspace / doc.file_name


def _listed(workspace: str, file_name: str) -> tuple[str, str]:
    """Manifest key, case-folded on BOTH sides of every comparison.

    Windows filesystems are case-insensitive and Linux ones are not, and
    the ST-07 re-review proved that mixing the two produces a file that is
    present and missing at the same time. A corpus file stored as
    `CNSS-....PDF` satisfies `Path.exists()` on Windows -- so it converts
    and passes -- while the stray sweep compares raw names in a set, does
    not find it, and reports the SAME file as unlisted in the SAME run. On
    Linux the halves fail the other way: MISSING plus stray. One disk, two
    different wrong answers, neither of them wrong in a way that points at
    the cause.
    """
    return (workspace.casefold(), file_name.casefold())


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
        return response.read()


def fetch() -> int:
    """Download every manifest file that is not already on disk.

    Skips what is present rather than re-downloading, so it is safe to run
    repeatedly and cheap to run before `verify`.

    IT DOES NOT CHECK THAT AN EXISTING FILE IS THE RIGHT ONE. A file with a
    manifest name and the wrong contents survives `fetch` forever, because
    presence is the only test. An earlier version of this docstring said
    "`verify` is what does that", which was FALSE and was caught by the
    ST-07 review -- `verify` proves a file is readable and dense enough to
    be a real document, and it prints a digest so a swap is visible to a
    human, but nothing compares that digest to a recorded value. Nothing
    can, until ST-35 freezes the corpus and there is a recorded value to
    compare against. Stated here rather than fixed, because inventing the
    freeze in this script is exactly the wrong shape.
    """
    archives: dict[str, zipfile.ZipFile] = {}
    downloaded = 0

    for doc in MANIFEST:
        target = _target(doc)
        if target.exists():
            print(f"  have  {doc.workspace}/{doc.file_name}")
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        if doc.zip_member is None:
            target.write_bytes(_download(doc.url))
        else:
            if doc.url not in archives:
                print(f"  ...   downloading archive {doc.url}")
                archives[doc.url] = zipfile.ZipFile(io.BytesIO(_download(doc.url)))
            target.write_bytes(archives[doc.url].read(doc.zip_member))

        downloaded += 1
        print(f"  GOT   {doc.workspace}/{doc.file_name}  ({target.stat().st_size:,} bytes)")

    print(f"\n{downloaded} downloaded, {len(MANIFEST) - downloaded} already present.")
    return 0


def verify() -> int:
    """The ST-07 exit gate. Non-zero exit means Corpus v1 is not met.

    Every file must be present and must come back CONVERTED from Sanad's own
    ladder. SKIPPED is a failure here even though it is correct product
    behaviour: a scanned PDF is a legitimate thing for Sanad to skip and an
    illegitimate thing for the corpus to contain, because ST-18's numbers
    would then be measured over a file the product never read.
    """
    failures: list[str] = []
    print(f"{'file':<45} {'outcome':<10} {'pages':>6} {'chars':>9}  sha256")
    print("-" * 89)

    for doc in MANIFEST:
        target = _target(doc)
        if not target.exists():
            failures.append(f"{doc.workspace}/{doc.file_name}: MISSING -- run `fetch`")
            print(f"{doc.file_name:<45} {'MISSING':<10}")
            continue

        result = convert_file(target)
        pages = "-" if result.page_count is None else str(result.page_count)
        chars = len(result.markdown or "")
        digest = compute_fingerprint(target).hex_digest[:16]
        print(f"{doc.file_name:<45} {result.outcome:<10} {pages:>6} {chars:>9,}  {digest}")

        if result.outcome is not ConversionOutcome.CONVERTED:
            failures.append(f"{doc.workspace}/{doc.file_name}: {result.outcome} -- {result.reason}")
            continue

        # CONVERTED is necessary and not sufficient -- see _MIN_CHARS_PER_PAGE.
        if result.page_count:
            density = chars / result.page_count
            if density < _MIN_CHARS_PER_PAGE:
                failures.append(
                    f"{doc.workspace}/{doc.file_name}: converted but only "
                    f"{density:.0f} characters per page over {result.page_count} pages "
                    f"(floor {_MIN_CHARS_PER_PAGE}). This reads as a scan with a thin "
                    f"text layer, not a document Sanad can answer from."
                )
        elif chars < _MIN_CHARS_UNPAGED:
            failures.append(
                f"{doc.workspace}/{doc.file_name}: converted but only {chars:,} "
                f"characters (floor {_MIN_CHARS_UNPAGED:,}). Truncated download?"
            )

    # A file on disk that the manifest does not know about is INVISIBLE to
    # every check above and fully VISIBLE to `change_detection.scan_folder`,
    # which walks the directory rather than this list. ST-18 would therefore
    # index and time a file this gate never looked at.
    #
    # The concrete case that made this blocking rather than tidy: ST-07
    # deleted two HR documents, and a deletion happens on ONE machine. The
    # other teammate runs `fetch`, gets the three new files, and keeps the
    # two deleted ones sitting beside them -- a five-file HR workspace
    # including the superseded 2004 labour code this story removed for
    # competing with the consolidated one. The gate would have said MET.
    # `is_supported` is the filter, and it is not politeness: the sweep must
    # flag exactly what SYNC WOULD INDEX, no more. `scan_folder` skips an
    # unsupported extension, so a `Thumbs.db` or a `.DS_Store` cannot reach
    # ST-18's numbers -- and failing the gate red for an OS artifact that
    # Windows drops into any folder someone opens would train the next
    # person to ignore a red gate. Using the same predicate as sync also
    # means the two cannot drift apart about what a corpus file is.
    expected = {_listed(d.workspace, d.file_name) for d in MANIFEST}
    for workspace in sorted({d.workspace for d in MANIFEST}):
        folder = CORPUS_ROOT / workspace
        if not folder.is_dir():
            continue
        for stray in sorted(folder.iterdir()):
            if not stray.is_file() or not is_supported(stray):
                continue
            if _listed(workspace, stray.name) not in expected:
                failures.append(
                    f"{workspace}/{stray.name}: ON DISK BUT NOT IN THE MANIFEST. "
                    f"Sync indexes the folder, not this list, so ST-18 would "
                    f"measure it. Delete it, or add it to MANIFEST."
                )

    print("-" * 89)
    for workspace in ("hr", "manuals"):
        docs = [d for d in MANIFEST if d.workspace == workspace]
        print(f"{workspace:<10} {len(docs)} files")

    if failures:
        print("\nEXIT GATE NOT MET:")
        for line in failures:
            print(f"  - {line}")
        return 1

    print("\nEXIT GATE MET: every file present, and Sanad reads all of them.")
    return 0


def sources() -> int:
    """Write `data/corpus/SOURCES.md` from the manifest above.

    Generated rather than hand-written so the record and the fetcher cannot
    drift. The generated file is itself git-ignored (it lives under `data/`);
    it exists for whoever opens the corpus folder without this repo in front
    of them.
    """
    lines = [
        "# Corpus v1 (ST-07) -- provenance record",
        "",
        "GENERATED FILE. Do not edit: it is written by",
        "`uv run python scripts/corpus.py sources` from the manifest in",
        "`scripts/corpus.py`, which is the tracked source of truth. Editing",
        "this copy changes nothing and will be overwritten.",
        "",
    ]
    for workspace in ("hr", "manuals"):
        lines += [f"## Workspace: {workspace} (`data/corpus/{workspace}/`)", ""]
        for doc in (d for d in MANIFEST if d.workspace == workspace):
            lines += [
                f"### `{doc.file_name}`",
                "",
                f"- **Title:** {doc.title}",
                f"- **Publisher:** {doc.publisher}",
                f"- **Published:** {doc.published}",
                f"- **Retrieved:** {doc.retrieved}",
                f"- **Authority:** {doc.authority}",
                f"- **URL:** {doc.url}",
            ]
            target = _target(doc)
            if target.exists():
                fingerprint = compute_fingerprint(target)
                lines.append(
                    f"- **On disk:** {fingerprint.size_bytes:,} bytes, "
                    f"sha256 `{fingerprint.hex_digest[:16]}` "
                    f"(recorded, NOT pinned -- see the note at the top of "
                    f"`scripts/corpus.py`)"
                )
            if doc.zip_member:
                lines.append(f"- **Archive member:** `{doc.zip_member}`")
            if doc.note:
                lines += ["", doc.note]
            lines.append("")

    out = CORPUS_ROOT / "SOURCES.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(MANIFEST)} documents)")
    return 0


_COMMANDS = {"fetch": fetch, "verify": verify, "sources": sources}


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in _COMMANDS:
        print(f"usage: python scripts/corpus.py {{{'|'.join(_COMMANDS)}}}")
        return 2
    return _COMMANDS[argv[1]]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
