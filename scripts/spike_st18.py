"""ST-18 SPIKE: measure G4 and G5 on the real corpus, and give the OR-1 verdict.

Promoted from the ST-17 session's `smoke_st17.py`, which ran the engine on
real documents outside pytest. That script proved the wiring survives real
files; it deliberately measured nothing, because the corpus it ran on was a
stand-in. ST-07 replaced the stand-in, so the same run is now a measurement.
What is new here is the measuring, the baseline, and the honesty about which
numbers are which. Two things from the original are unchanged on purpose --
the isolation check and the parent-resolution check -- because a fast wrong
answer is not a G4 pass.

    uv run python scripts/spike_st18.py index      # G5, no model calls
    uv run python scripts/spike_st18.py retrieve   # baseline, no model calls
    uv run python scripts/spike_st18.py answer     # G4, SPENDS MODEL CALLS

THE SPLIT IS DELIBERATE AND IT IS ABOUT COST. `index` and `retrieve` touch
no chat model: embeddings run locally on CPU and retrieval is arithmetic.
`answer` calls the configured provider once per grade, once per reword and
once per answer, so twenty questions is on the order of forty to eighty
calls. The core law says stop before anything that spends, so the spend is
in its own command with its own count printed before it runs, rather than
buried inside a script called `spike`.

WHAT `retrieve` IS FOR, and it is not in ST-18's exit gate. The AI-feature
discipline says build the stupidest thing that could work and measure it,
because that number is what the real system has to beat to justify itself.
Here the stupid thing is counting shared words. If hybrid retrieval cannot
beat word-counting on real French legal text, that is the OR-1 verdict and
no amount of latency measurement changes it. ST-16 said outright that it
could not prove the sparse branch helps, because both its fakes ranked by
word overlap and the dense side alone returned what the hybrid returned.
This is the first chance to find out.
"""

from __future__ import annotations

import json
import math
import re
import shutil
import statistics
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import parent_store  # noqa: E402
import sync  # noqa: E402
import vector_store  # noqa: E402
import workspaces as ws  # noqa: E402
from change_detection import compute_fingerprint  # noqa: E402
from db import repo  # noqa: E402

CORPUS = REPO_ROOT / "data" / "corpus"
RUN_DIR = REPO_ROOT / "data" / "spike-st18"
DB = RUN_DIR / "sanad.db"
QDRANT = RUN_DIR / "qdrant"
PARENTS = RUN_DIR / "parents"
RESULTS = RUN_DIR / "results.json"
TRACES = RUN_DIR / "traces.json"

# G4 and G5 as PRD section 3 states them, kept as literals next to the code
# that judges against them so nobody has to go looking for the threshold.
G4_MEDIAN_SECONDS = 20.0
G4_P95_SECONDS = 60.0
G5_SECONDS_PER_200_PAGES = 600.0


@dataclass
class Probe:
    """One retrieval question with the answer known in advance.

    `expect_file` is the corpus file that must supply the top hit, and
    `expect_marker` is a string that must appear in the retrieved text --
    an article number for the legal workspace. Both are needed: a hit from
    the right FILE can still be the wrong article in a 201-page code, and
    that is precisely the defect the citation-label fix of 2026-08-23 was
    about.
    """

    workspace: str
    question: str
    expect_file: str
    expect_marker: str = ""
    note: str = ""


# Deliberately phrased the way an HR generalist would ask, NOT the way the
# statute words it. This is the leakage guard and it is the whole reason
# these are written by hand rather than generated from the corpus: a
# question that quotes the document retrieves the document, and the run
# then measures nothing but copy-paste. "Combien de jours de conges par
# an ?" is a question; "quelle est la duree du conge annuel paye prevue a
# l'article 231" is the answer wearing a question mark.
PROBES: tuple[Probe, ...] = (
    Probe("hr", "Combien de jours de conges payes par an ?",
          "code-travail-consolide-2011-justice.pdf", "231"),
    Probe("hr", "Un salarie peut-il etre licencie sans preavis ?",
          "code-travail-consolide-2011-justice.pdf", "39"),
    Probe("hr", "Combien d'heures par semaine un salarie doit-il travailler ?",
          "code-travail-consolide-2011-justice.pdf", "184"),
    Probe("hr", "Quelle est la duree maximale de la periode d'essai ?",
          "code-travail-consolide-2011-justice.pdf", "14"),
    Probe("hr", "Une femme enceinte a droit a combien de semaines de conge ?",
          "code-travail-consolide-2011-justice.pdf", "152"),
    Probe("hr", "A partir de quel age peut-on embaucher quelqu'un ?",
          "code-travail-consolide-2011-justice.pdf", "143"),
    Probe("hr", "Qui doit etre declare a la securite sociale ?",
          "dahir-1-72-184-securite-sociale-acaps.pdf", ""),
    Probe("hr", "Comment sont calculees les cotisations sociales ?",
          "dahir-1-72-184-securite-sociale-acaps.pdf", ""),
    Probe("hr", "Qu'est-ce qui est couvert par l'assurance maladie ?",
          "cnss-regime-securite-sociale-cleiss.pdf", ""),
    Probe("hr", "A quel age part-on a la retraite ?",
          "cnss-regime-securite-sociale-cleiss.pdf", ""),
    Probe("manuals", "Comment attraper une erreur dans mon programme ?",
          "tutorial-errors.txt", ""),
    Probe("manuals", "Comment ecrire dans un fichier ?",
          "tutorial-inputoutput.txt", ""),
    Probe("manuals", "Comment creer un objet avec ses proprietes ?",
          "tutorial-classes.txt", ""),
    Probe("manuals", "Comment enregistrer ce que fait mon programme ?",
          "howto-logging.txt", ""),
    Probe("manuals", "Comment faire communiquer deux machines ?",
          "howto-sockets.txt", ""),
    # Five added after the rule-5 review pointed out that BUILD-PLAN line
    # 66 says "20-q latency" and this file had 15. The plan's number is the
    # contract; quietly measuring 15 and reporting it against a target
    # written for 20 is the kind of silent narrowing that is invisible in a
    # journal entry.
    # WAS "combien de temps de repos entre deux journees de travail ?"
    # expecting Article 217, and BOTH halves were wrong. 217 is "il est
    # interdit aux employeurs d'occuper les salaries pendant les jours de
    # fetes payes" -- public holidays. And the question itself has no clean
    # answer in this code: daily rest is regulated only for NIGHT work and
    # only for women and minors (Article 174, eleven consecutive hours), so
    # a general daily-rest question is closer to out-of-scope than in. It
    # was scored as a retrieval miss when the fault was the label, which is
    # the worst kind of bad probe: it makes the system look wrong.
    # Replaced with a question the code answers plainly, verified by
    # reading the PDF: Article 205, "un repos hebdomadaire d'au moins
    # vingt-quatre heures allant de minuit a minuit".
    Probe("hr", "Combien de temps de repos par semaine ?",
          "code-travail-consolide-2011-justice.pdf", "205"),
    Probe("hr", "Le salarie a-t-il droit a un certificat de travail ?",
          "code-travail-consolide-2011-justice.pdf", "72"),
    Probe("hr", "Que se passe-t-il si l'employeur ne declare pas un salarie ?",
          "dahir-1-72-184-securite-sociale-acaps.pdf", ""),
    Probe("manuals", "Comment organiser mon code en plusieurs fichiers ?",
          "tutorial-modules.txt", ""),
    Probe("manuals", "Comment trier une liste ?",
          "tutorial-datastructures.txt", ""),
)


@dataclass
class Timing:
    label: str
    seconds: list[float] = field(default_factory=list)

    def add(self, value: float) -> None:
        self.seconds.append(value)

    cold_start: float | None = None

    def summary(self) -> dict[str, float]:
        """Every measured sample, plus the cold start reported beside them.

        THE COLD START IS NO LONGER TAKEN FROM THE SAMPLE POOL. The first
        version held out `seconds[0]`, which the rule-5 review correctly
        called positional rather than causal: it discards a perfectly good
        sample when the process is already warm, it would miss a cold load
        that happened at position two, and with one sample it reported the
        cold figure as an n=1 warm median. Now the caller issues ONE
        UNTIMED WARM-UP query, records it in `cold_start`, and every timed
        sample after it is a real question. Nothing is discarded, and the
        sample count matches the number of probes.

        Why it is reported at all rather than ignored: the first query of a
        process pays for loading multilingual-e5-base, and that has
        measured 34.3s and 160.07s on two runs against a warm median near
        0.2s. A user asking their first question of the day really does
        wait for it. It is a different number from "what a question costs",
        not a corrupt version of the same one.
        """
        if not self.seconds:
            return {}
        ordered = sorted(self.seconds)
        # NEAREST-RANK, the standard definition: ceil(0.95 * n). The first
        # version used round(), which for n=14 returned the 13th of 14 with
        # TWO samples above it -- not a 95th percentile at all. Immaterial
        # at 0.24s, and decisive for G4, where this same function judges an
        # answer against a 60-second budget and dropping the top sample
        # flips PASS to FAIL.
        index = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
        return {
            "n": len(ordered),
            "cold_start": self.cold_start,
            "min": ordered[0],
            "median": statistics.median(ordered),
            "p95": ordered[index],
            "max": ordered[-1],
        }


def banner(text: str) -> None:
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}", flush=True)


def _fresh_run_dir() -> None:
    if RUN_DIR.exists():
        shutil.rmtree(RUN_DIR)
    RUN_DIR.mkdir(parents=True)


def _workspaces():
    hr = ws.create_workspace(
        name="HR", folder_path=str(CORPUS / "hr"), legal_flag=True, db_path=DB
    )
    manuals = ws.create_workspace(
        name="Manuals", folder_path=str(CORPUS / "manuals"), db_path=DB
    )
    return hr, manuals


def _pages(workspace_id: str) -> int:
    conn = repo.get_connection(DB)
    try:
        return sum(
            row["page_count"] or 0 for row in repo.list_documents(conn, workspace_id)
        )
    finally:
        conn.close()


def index() -> int:
    """G5, plus the sync-side costs the journal lists as unmeasured.

    Runs on a FRESH store every time. A warm store would measure the second
    sync, which is a different and much smaller number, and quoting it as
    G5 would be the most flattering possible mistake.
    """
    _fresh_run_dir()
    repo.ensure_schema(DB)
    hr, manuals = _workspaces()
    measured: dict = {"g5": {}, "notes": []}

    with vector_store.open_store(QDRANT) as client:
        banner("1. COLD SYNC -- this is the G5 number, model load included")
        # The model load is INSIDE the first number on purpose. G5 says a
        # workspace becomes questionable within ten minutes of pressing
        # Sync, and a user pressing Sync on a fresh install waits for the
        # encoder to load whether or not we find that fair to the code.
        for workspace in (hr, manuals):
            start = time.perf_counter()
            report = sync.sync_workspace(
                workspace_id=workspace.id, db_path=DB, client=client,
                parent_base_path=PARENTS,
            )
            elapsed = time.perf_counter() - start
            counts = {k.value: v for k, v in report.counts.items() if v}
            pages = _pages(workspace.id)
            files = sum(counts.values())
            per_200 = (elapsed / pages * 200) if pages else None
            print(f"  {workspace.name:<9} {elapsed:7.1f}s  {files} files, "
                  f"{pages or '-'} pages  {counts}", flush=True)
            if per_200 is not None:
                verdict = "PASS" if per_200 <= G5_SECONDS_PER_200_PAGES else "FAIL"
                print(f"            -> {per_200:.1f}s per 200 pages "
                      f"(G5 budget {G5_SECONDS_PER_200_PAGES:.0f}s) {verdict}",
                      flush=True)
            measured["g5"][workspace.name] = {
                "seconds": elapsed, "files": files, "pages": pages,
                "seconds_per_200_pages": per_200,
            }

        banner("2. WHAT LANDED")
        for workspace in (hr, manuals):
            points = client.count(vector_store.collection_name(workspace.id)).count
            folder = PARENTS / workspace.id
            parents = len(list(folder.glob("*.json"))) if folder.exists() else 0
            print(f"  {workspace.name:<9} {points:>6} children  {parents:>5} parents",
                  flush=True)
            measured["g5"][workspace.name].update(children=points, parents=parents)

        banner("3. SECOND SYNC -- everything unchanged, so this is pure overhead")
        # Journal item: the per-file registry commit cost. A sync in which
        # nothing changed does the scan, the hash and the registry work and
        # NO embedding, so this number isolates that half.
        for workspace in (hr, manuals):
            start = time.perf_counter()
            report = sync.sync_workspace(
                workspace_id=workspace.id, db_path=DB, client=client,
                parent_base_path=PARENTS,
            )
            elapsed = time.perf_counter() - start
            counts = {k.value: v for k, v in report.counts.items() if v}
            files = sum(counts.values()) or 1
            print(f"  {workspace.name:<9} {elapsed:7.2f}s  {counts}  "
                  f"-> {elapsed / files * 1000:.0f} ms per file", flush=True)
            measured["g5"][workspace.name]["unchanged_sync_seconds"] = elapsed

        banner("4. THE PER-FILE WORKSPACE-WIDE PARENT SCAN (ST-17 finding 1)")
        # `_ingest` calls delete_document before converting every changed
        # file, and `list_parent_ids` reads EVERY parent JSON in the
        # workspace to filter by source_file. Cost is files x parents. The
        # second sync above never hits it, because nothing changed -- so it
        # is forced here by touching one file's timestamp and content.
        # NAMED, not globbed. `next(glob("*.pdf"))` picked whichever file
        # the filesystem happened to return first -- a different document
        # on another machine, so a different number -- missed `.PDF` on a
        # case-sensitive filesystem, and raised StopIteration on an empty
        # folder. It is the same case bug ST-07's re-review had just fixed
        # one file away, re-introduced by reflex.
        target = CORPUS / "hr" / "dahir-1-72-184-securite-sociale-acaps.pdf"
        original = target.read_bytes()
        before = compute_fingerprint(target)
        try:
            target.write_bytes(original + b"\n%% st18 probe\n")
            start = time.perf_counter()
            report = sync.sync_workspace(
                workspace_id=hr.id, db_path=DB, client=client,
                parent_base_path=PARENTS,
            )
            elapsed = time.perf_counter() - start
            counts = {k.value: v for k, v in report.counts.items() if v}
            hr_parents = measured["g5"]["HR"]["parents"]
            print(f"  one changed file re-ingested in {elapsed:.1f}s  {counts}",
                  flush=True)
            print(f"  the deletion path read ~{hr_parents} parent JSONs to find "
                  f"one file's own", flush=True)
            measured["reingest_one_file_seconds"] = elapsed
        finally:
            # This function DELIBERATELY EDITS A CORPUS FILE, and the
            # corpus is the thing every ST-18 number is measured against.
            # Restoring the bytes is not enough on its own -- "I wrote the
            # old bytes back" is an intention. The fingerprint is checked,
            # and a mismatch shouts, because a silently corrupted corpus
            # would poison every later run with no symptom.
            target.write_bytes(original)
            after = compute_fingerprint(target)
            if after.hex_digest != before.hex_digest:
                raise RuntimeError(
                    f"RESTORE FAILED for {target.name}. The corpus is now "
                    f"different from what it was before this probe: "
                    f"{before.hex_digest[:16]} -> {after.hex_digest[:16]}. "
                    f"Run `python scripts/corpus.py fetch` after deleting it."
                )
            print(f"  restored, fingerprint unchanged "
                  f"({after.hex_digest[:16]})", flush=True)

    measured["notes"].append(
        "The cost of RE-ATTEMPTING a failed or skipped file on every sync is "
        "STILL UNMEASURED. Corpus v1 contains no scanned or corrupt file -- "
        "the ST-07 gate refuses one on purpose -- so there is nothing here "
        "that exercises that path. Measuring it needs a deliberate bad "
        "fixture, which is a different job from measuring the real corpus."
    )
    RESULTS.write_text(json.dumps(measured, indent=2), encoding="utf-8")
    print(f"\nwrote {RESULTS}", flush=True)
    return 0


_WORD = re.compile(r"\w{3,}", re.UNICODE)
_PARENT_CACHE: dict[str, list] = {}


def marker_found(marker: str, text: str) -> bool:
    """Does `text` actually cite the article `marker` names?

    A PLAIN SUBSTRING TEST WAS WRONG HERE, and it was wrong in the
    direction that flatters the result. `"14" in text` is true of "Article
    143", of "2014", of "1-72-184"; `"39" in text` is true of "article
    139". Worse, `1-72-184` is the NAME OF ANOTHER DOCUMENT in the same
    workspace (`dahir-1-72-184-securite-sociale-acaps.pdf`), so the `72`
    and `184` probes could both be satisfied by retrieving the wrong file
    entirely -- the exact failure the marker exists to detect. Four of the
    eight markers in `PROBES` are collidable that way, so the published
    right-article figure was an upper bound rather than a measurement.

    Found by a cold review of this file and reproduced before fixing.

    The rule now is the one a CITATION uses: the number must be preceded
    by the word "article" and must end where the number ends, so 143 never
    answers for 14. Accents and case are folded first because the corpus is
    real French and the probes are typed in ASCII -- the same asymmetry
    that had already rigged the keyword baseline once."""
    wanted = marker.strip()
    if not wanted:
        return False
    pattern = re.compile(
        rf"\barticles?\s+(?:\d+\s*(?:,|et|and|-|to|a)\s*)*{re.escape(wanted)}\b"
    )
    return bool(pattern.search(_fold(text)))


def _fold(text: str) -> str:
    """Lower-case AND strip accents, so `conges` matches `congés`.

    THE BASELINE WAS RIGGED WITHOUT THIS AND I DID NOT NOTICE. The probes
    below are written in unaccented ASCII, the way someone types quickly;
    the corpus is properly accented French. `casefold()` folds case and
    does NOT fold accents, so the word-counting baseline could not match
    `conges` to `congés` at all, while the dense encoder is unaffected by
    the difference. The first published comparison was therefore hybrid
    12/15 against a baseline that had been handicapped before it started.
    The rule-5 review measured the damage: folding accents alone lifts the
    baseline from 6 to 8, and dropping the word floor from 4 to 3
    characters lifts it to 9. Hybrid still wins, so the verdict survives --
    but the MARGIN was about double the real one, and a margin is what a
    reader takes away.

    The lesson is not about accents. A baseline exists to be the number the
    real system must beat, so anything that quietly weakens it flatters the
    thing under test. Build the baseline as if you wanted it to win.
    """
    decomposed = unicodedata.normalize("NFD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _all_parents(workspace_id: str) -> list:
    """Every parent in one workspace, read once and kept.

    `parent_store.list_parent_ids` cannot do this: it takes a `source_file`
    and answers "which parents came from THAT file", because it exists for
    the deletion path. Listing a whole workspace is a different question, so
    this reads the directory -- the parent id IS the file stem -- rather
    than bending a deletion helper into a lister it was not built to be.

    Cached because the baseline runs once per probe and re-reading a few
    hundred JSON files fifteen times would make the BASELINE the slow half
    of a comparison about speed.
    """
    if workspace_id not in _PARENT_CACHE:
        folder = PARENTS / workspace_id
        _PARENT_CACHE[workspace_id] = [
            parent_store.get_parent(
                workspace_id=workspace_id, parent_id=path.stem, base_path=PARENTS
            )
            for path in sorted(folder.glob("*.json"))
        ]
    return _PARENT_CACHE[workspace_id]


def _keyword_rank(question: str, parents: list) -> object | None:
    """The stupidest thing that could work: count shared words.

    No embeddings, no index, no model. This is the number hybrid retrieval
    has to beat to justify existing, per the AI-feature discipline, so it
    is built to be as strong as three lines can make it: accents folded
    (see `_fold`) and a 3-character floor, which keeps "age" and "jour"
    while still dropping "de", "la" and "un".
    """
    terms = set(_WORD.findall(_fold(question)))
    best, best_score = None, 0
    for parent in parents:
        score = len(terms & set(_WORD.findall(_fold(parent.text))))
        if score > best_score:
            best, best_score = parent, score
    return best


def retrieve() -> int:
    """Does hybrid retrieval beat counting words? No model calls.

    Requires `index` to have run: it reads the store that command built.
    """
    if not DB.exists():
        print("no indexed store -- run `index` first")
        return 2

    conn = repo.get_connection(DB)
    try:
        by_name = {row["name"]: row["id"] for row in repo.list_workspaces(conn)}
    finally:
        conn.close()
    lookup = {"hr": by_name.get("HR"), "manuals": by_name.get("Manuals")}

    hybrid_hits = keyword_hits = marker_hits = marker_total = 0
    timing = Timing("retrieval")
    rows = []

    with vector_store.open_store(QDRANT) as client:
        banner("RETRIEVAL: hybrid (the product) vs counting words (the baseline)")
        # One UNTIMED warm-up so the encoder load lands here instead of
        # inside question one. Timed separately, reported separately, and
        # never mixed into the sample -- see `Timing.summary`.
        warm_start = time.perf_counter()
        vector_store.search(
            client, workspace_id=lookup["hr"], query_text="question de rodage"
        )
        timing.cold_start = time.perf_counter() - warm_start

        for probe in PROBES:
            workspace_id = lookup[probe.workspace]
            start = time.perf_counter()
            hits = vector_store.search(
                client, workspace_id=workspace_id, query_text=probe.question
            )
            timing.add(time.perf_counter() - start)

            top = hits[0] if hits else None
            hybrid_ok = bool(top and top.source_file == probe.expect_file)
            hybrid_hits += hybrid_ok

            baseline = _keyword_rank(probe.question, _all_parents(workspace_id))
            keyword_ok = bool(baseline and baseline.source_file == probe.expect_file)
            keyword_hits += keyword_ok

            marker_ok = None
            if probe.expect_marker:
                # The denominator counts every probe that NAMES an article,
                # whether or not anything came back. Gating it on `top` --
                # as the first version did -- meant a probe that retrieved
                # nothing SHRANK the denominator instead of scoring a miss,
                # which improves the ratio by failing harder.
                marker_total += 1
                joined = " ".join(h.chunk_text for h in hits[:3])
                marker_ok = marker_found(probe.expect_marker, joined)
                marker_hits += marker_ok

            flag = "hit " if hybrid_ok else "MISS"
            base_flag = "hit " if keyword_ok else "MISS"
            mark = "" if marker_ok is None else ("  marker ok" if marker_ok
                                                 else f"  marker {probe.expect_marker} MISSING")
            print(f"  hybrid {flag}  words {base_flag}{mark}   {probe.question}",
                  flush=True)
            if top and not hybrid_ok:
                print(f"         got {top.source_file} / "
                      f"{(top.section_label or '-')[:44]}", flush=True)
            rows.append({
                "question": probe.question, "workspace": probe.workspace,
                "expect_file": probe.expect_file, "hybrid_ok": hybrid_ok,
                "keyword_ok": keyword_ok, "marker_ok": marker_ok,
                "top_file": top.source_file if top else None,
                "top_label": top.section_label if top else None,
            })

    total = len(PROBES)
    banner("BASELINE VERDICT")
    print(f"  hybrid retrieval : {hybrid_hits}/{total} top hits in the right file")
    print(f"  counting words   : {keyword_hits}/{total}")
    if marker_total:
        print(f"  right ARTICLE in the top 3 : {marker_hits}/{marker_total} "
              f"(a right-file hit can still be the wrong article)")
    summary = timing.summary()
    print(f"  retrieval time   : median {summary['median']:.3f}s  "
          f"p95 {summary['p95']:.3f}s  (n={summary['n']}, no model calls)")
    # Same `or 0.0` guard as the G4 block. Not reachable here today, since
    # this function's warm-up always sets the field -- but the two printed
    # the same value two different ways, and the unguarded one is the shape
    # that crashed `answer` after it had spent the money.
    print(f"  cold start       : {summary['cold_start'] or 0.0:.1f}s on an "
          f"untimed warm-up query -- the encoder loading, paid once per "
          f"process")
    if hybrid_hits <= keyword_hits:
        print("\n  HYBRID DOES NOT BEAT WORD-COUNTING ON THIS CORPUS.")
        print("  That is an OR-1 finding, not a bug to hide. Record it.")

    existing = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    existing["retrieval"] = {
        "hybrid_top_file": hybrid_hits, "keyword_top_file": keyword_hits,
        "total": total, "marker_in_top3": marker_hits, "marker_total": marker_total,
        "timing": summary, "rows": rows,
    }
    RESULTS.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"\nwrote {RESULTS}", flush=True)
    return 0


def answer(confirmed: bool = False) -> int:
    """G4, end to end through the real model. THIS ONE SPENDS.

    Every question costs at least one grade call and one answer call, and
    each retry adds a grade and a reword, so the ceiling is
    `1 + (retry_ceiling + 1) * 2` provider calls per question.

    THE GUARD IS `--yes` AND IT IS REAL. The first version of this
    docstring said the count was "printed and confirmed", and nothing in
    the file ever asked for confirmation -- a money guard that existed only
    in its own description, which the rule-5 review caught. Printing is not
    asking. `input()` would have been the obvious fix and it is the wrong
    one here: this script runs under an agent with no terminal, where a
    prompt either hangs forever or reads EOF and sails straight through,
    which is a guard that fails OPEN. An explicit flag cannot be supplied
    by accident and behaves identically with or without a human present.

    It also writes every answer, refusal, trace and timing to `traces.json`.
    That file is the real output. G4 is two numbers; the traces are the raw
    material ST-19's golden set gets written FROM, which is the whole reason
    this story runs before that one -- error analysis decides what evals are
    worth writing, and evals written before any error analysis test what
    their author imagined rather than what the system does.
    """
    if not DB.exists():
        print("no indexed store -- run `index` first")
        return 2

    # Imported here, not at module scope, so `index` and `retrieve` never
    # touch the chat layer: importing `agent.chat` is harmless, but keeping
    # the spend-shaped code out of the free commands means a mistake cannot
    # start a provider client in a command that promises not to.
    from agent.answering import build_write_answer  # noqa: PLC0415
    from agent.chat import build_chat_model  # noqa: PLC0415
    from agent.grading import build_grade, build_reword  # noqa: PLC0415
    from agent.graph import ask  # noqa: PLC0415
    from agent.ports import AgentPorts  # noqa: PLC0415
    from agent.retrieval import build_retrieve  # noqa: PLC0415
    from agent.stores import parent_texts  # noqa: PLC0415
    from config import get_settings  # noqa: PLC0415

    settings = get_settings()
    per_question = 1 + (settings.retry_ceiling + 1) * 2
    banner("G4: END TO END THROUGH THE REAL MODEL -- THIS SPENDS")
    print(f"  provider   : {settings.model_mode} / {settings.chat_model_cloud}")
    print(f"  questions  : {len(PROBES)}")
    print(f"  worst case : {len(PROBES) * per_question + 1} provider calls "
          f"({per_question} per question at retry ceiling "
          f"{settings.retry_ceiling}, plus 1 warm-up)", flush=True)
    if not confirmed:
        print("\n  NOTHING WAS SENT. Re-run with --yes to authorise the calls "
              "above:\n    uv run python scripts/spike_st18.py answer --yes",
              flush=True)
        return 2

    conn = repo.get_connection(DB)
    try:
        by_name = {row["name"]: row["id"] for row in repo.list_workspaces(conn)}
    finally:
        conn.close()
    lookup = {"hr": by_name.get("HR"), "manuals": by_name.get("Manuals")}

    timing = Timing("answer")
    rows: list[dict] = []
    sourced = refused = failed = 0

    with vector_store.open_store(QDRANT) as client:
        model = build_chat_model()
        ports = AgentPorts(
            # ST-22 and ST-25 are not built. Stubbed IN THE OPEN, and it
            # matters for reading the numbers: no clarification round and no
            # session summary means every timing below is a FLOOR. A real
            # ST-22 adds at least one more provider call to an ambiguous
            # question, and several of these are ambiguous.
            summarize=lambda history: "",
            clarify=lambda question, summary: None,
            rewrite=lambda question, summary: (question,),
            retrieve=build_retrieve(client),
            grade=build_grade(model),
            reword=build_reword(model),
            fetch_parents=lambda workspace, ids: parent_texts(
                workspace, ids, base_path=PARENTS
            ),
            write_answer=build_write_answer(model),
        )

        # ONE UNTIMED WARM-UP, for the same reason `retrieve` has one and
        # then some. The first fix added the warm-up to `retrieve` ONLY,
        # which left this function with no warm-up AND no holdout -- so the
        # ~35 second encoder load moved from "held out of the sample" to
        # "inside question one, in the pool", against a 20 second median
        # budget. A fix that improves one call site and silently degrades
        # its sibling is worse than the thing it replaced, and the rule-5
        # re-review caught it because nobody had ever run this branch.
        warm_start = time.perf_counter()
        try:
            vector_store.search(
                client, workspace_id=lookup["hr"], query_text="question de rodage"
            )
        finally:
            encoder_warm = time.perf_counter() - warm_start

        # AND ONE THROWAWAY PROVIDER CALL. Warming the encoder alone leaves
        # the FIRST question paying for TLS setup, credential resolution and
        # whatever metadata the client fetches on its first request -- inside
        # the pool, against a 20 second median budget. Smaller than a 35
        # second encoder load and not nothing, and the re-review flagged it
        # as an undisclosed cost rather than a measured one. It is measured
        # now. This is the 141st call, not the 141st question: the count
        # printed above is worst-case questions, and this one extra is
        # declared here rather than hidden.
        provider_start = time.perf_counter()
        try:
            model.complete(system="Reponds exactement: OK", user="rodage")
            provider_warm: float | None = time.perf_counter() - provider_start
        except Exception as exc:  # noqa: BLE001
            provider_warm = None
            print(f"  warm-up provider call FAILED: {type(exc).__name__}: {exc}",
                  flush=True)
            print("  (the real loop below will report this per question)",
                  flush=True)

        timing.cold_start = encoder_warm + (provider_warm or 0.0)
        shown = "failed" if provider_warm is None else f"{provider_warm:.1f}s"
        print(f"  warm-up (untimed): encoder {encoder_warm:.1f}s, "
              f"provider handshake {shown}\n", flush=True)

        for probe in PROBES:
            start = time.perf_counter()
            try:
                result = ask(
                    workspace_id=lookup[probe.workspace],
                    question=probe.question,
                    ports=ports,
                )
                elapsed = time.perf_counter() - start
                timing.add(elapsed)
                # `refusal` is DERIVED from the answer's kind, so it and the
                # variant the UI would render cannot disagree. Reading
                # `sources` emptiness instead would be a second opinion, and
                # `__post_init__` already makes an ANSWER without sources
                # unrepresentable -- so an empty-sources row is a refusal by
                # construction, not by this script's guess.
                is_refusal = result.refusal
                sourced += not is_refusal
                refused += is_refusal
                # KEEP THE PAIRS TOGETHER. An earlier version built
                # `files` as a sorted SET and `labels` as the original
                # LIST, then zipped them: different lengths, different
                # order, so a file was printed beside another file's
                # article and `strict=False` dropped the remainder in
                # silence. That is a citation-provenance error inside the
                # measurement OF citation provenance, and it went into
                # traces.json -- the file ST-19's golden set is written
                # from. De-duplicate the PAIR or not at all.
                cited = list(
                    dict.fromkeys(
                        (source.file_name, source.section_label)
                        for source in result.sources
                    )
                )
                files = [name for name, _label in cited]
                labels = [label for _name, label in cited]
                marker_ok = (
                    marker_found(probe.expect_marker, result.text or "")
                    if probe.expect_marker else None
                )
                print(f"  {elapsed:6.1f}s  {'REFUSED' if is_refusal else 'sourced':<8}"
                      f"  {probe.question[:52]}", flush=True)
                if files:
                    shown = ", ".join(
                        f"{name} / {(label or '-')[:34]}" for name, label in cited
                    )
                    print(f"           {shown}", flush=True)
                rows.append({
                    "question": probe.question,
                    "workspace": probe.workspace,
                    "expect_file": probe.expect_file,
                    "expect_marker": probe.expect_marker,
                    "marker_in_answer": marker_ok,
                    "seconds": elapsed,
                    "kind": str(result.kind),
                    "refused": is_refusal,
                    "retries": result.retries,
                    "searched": list(result.searched),
                    "source_files": files,
                    "section_labels": labels,
                    "answer": result.text,
                    "trace": [
                        {"kind": str(step.kind), "detail": step.detail,
                         "files": list(step.files)}
                        for step in result.trace.steps
                    ],
                })
            except Exception as exc:  # noqa: BLE001
                # A spike reports what happened. Swallowing one failure and
                # continuing is right here -- PRD F-02's own rule that one
                # bad item must not kill the batch -- but it is RECORDED,
                # never counted as a pass.
                failed += 1
                elapsed = time.perf_counter() - start
                print(f"  {elapsed:6.1f}s  ERROR     {probe.question[:52]}",
                      flush=True)
                print(f"           {type(exc).__name__}: {exc}", flush=True)
                rows.append({
                    "question": probe.question, "workspace": probe.workspace,
                    "seconds": elapsed, "error": f"{type(exc).__name__}: {exc}",
                })

    summary = timing.summary()
    banner("G4 VERDICT")
    # A PARTIAL RUN GETS NO VERDICT. The first version printed the PASS/FAIL
    # block whenever ANY question succeeded, and then printed "no G4 number
    # was produced" underneath it -- the same lie the all-error path had
    # already been fixed for, surviving one branch over because only the
    # all-error path was ever executed. A median over the questions that
    # happened to work is a measurement of the easy ones: whatever made the
    # others fail is exactly what a latency budget is meant to catch.
    if summary and not failed:
        median_ok = summary["median"] <= G4_MEDIAN_SECONDS
        p95_ok = summary["p95"] <= G4_P95_SECONDS
        print(f"  median {summary['median']:6.1f}s  (budget "
              f"{G4_MEDIAN_SECONDS:.0f}s)  {'PASS' if median_ok else 'FAIL'}")
        print(f"  p95    {summary['p95']:6.1f}s  (budget "
              f"{G4_P95_SECONDS:.0f}s)  {'PASS' if p95_ok else 'FAIL'}")
        # `or 0.0` because a missing cold start must not crash a run that
        # has already spent the money. `f"{None:.1f}"` raises TypeError,
        # and it did: this whole block only executes on a fully successful
        # G4 run, which had never happened, so the crash sat in the one
        # branch whose failure costs the most.
        print(f"  n={summary['n']}, cold start "
              f"{summary['cold_start'] or 0.0:.1f}s measured separately on "
              f"an untimed warm-up")
        print(f"  NOTE: the p95 of {summary['n']} samples is one value near "
              f"the top of the list, not a stable statistic.")
    print(f"\n  sourced answers : {sourced}/{len(PROBES)}")
    print(f"  refusals        : {refused}/{len(PROBES)}")
    print(f"  errors          : {failed}/{len(PROBES)}")

    if failed:
        # This branch exists because the first real run took it and the
        # ORIGINAL version of this block lied on the way through: with 15
        # errors and 0 answers it still printed "every row above is either
        # sourced or a refusal". It was written on the assumption that the
        # provider works, which is the assumption a spike is supposed to
        # test. An error is not a refusal -- a refusal is a claim about the
        # user's documents, an error is a fact about our plumbing -- and
        # `agent/grading.py` already settled that those two must never
        # share an outcome.
        print(f"\n  {failed} of {len(PROBES)} questions never reached the model.")
        print("  NO G4 NUMBER WAS PRODUCED. This is not a slow result, it is "
              "an absent one.")
        if summary:
            print(f"  ({summary['n']} questions did answer, median "
                  f"{summary['median']:.1f}s -- NOT a G4 figure, because it "
                  f"describes only the ones that worked.)")
        return 1

    print("\n  G3 (100% of answers carry a source) is STRUCTURAL, not measured "
          "here:\n  `Answer.__post_init__` makes an ANSWER without sources "
          "unrepresentable,\n  so every non-error row is either sourced or an "
          "F-05 refusal by construction.")

    TRACES.write_text(
        json.dumps({"timing": summary, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nwrote {TRACES}  <- ST-19 gets written from this", flush=True)
    return 0


_COMMANDS = {"index": index, "retrieve": retrieve, "answer": answer}


def main(argv: list[str]) -> int:
    args = argv[1:]
    confirmed = "--yes" in args
    positional = [a for a in args if a != "--yes"]
    if len(positional) != 1 or positional[0] not in _COMMANDS:
        print(f"usage: python scripts/spike_st18.py "
              f"{{{'|'.join(_COMMANDS)}}} [--yes]")
        print("  --yes authorises the provider calls that `answer` makes.")
        return 2
    command = positional[0]
    if command == "answer":
        return answer(confirmed=confirmed)
    return _COMMANDS[command]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
