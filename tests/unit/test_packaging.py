import re
from pathlib import Path

import yaml

from ui import access_gate

ROOT = Path(__file__).resolve().parents[2]


def test_compose_keeps_the_app_local_and_persists_product_data():
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text(encoding="utf-8"))
    app = compose["services"]["sanad"]

    assert app["image"] == "sanad-local"
    assert app["ports"] == ["127.0.0.1:8000:8000"]
    assert "sanad-data:/app/data" in app["volumes"]
    assert compose["volumes"] == {"sanad-data": None}
    assert app["environment"] == {
        "SERVER_HOST": "0.0.0.0",
        "QDRANT_STORAGE_PATH": "/app/data/qdrant",
        "PARENT_STORE_PATH": "/app/data/parents",
        "SQLITE_DB_PATH": "/app/data/sanad.db",
        "REPORTS_PATH": "/app/data/reports",
    }
    assert app["healthcheck"]["test"] == [
        "CMD",
        "python",
        "-c",
        (
            "import urllib.request; "
            "urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', "
            "timeout=2).read()"
        ),
    ]


def test_railway_waits_for_health_and_restarts_a_failed_deploy():
    """Without this file Railway swaps traffic to a container the moment it
    starts and never checks it again: a deploy that boots and immediately
    fails its own health check still becomes the live site. The path must
    be the one route the access gate leaves open, or the health check
    itself would be refused and every deploy would be rolled back."""
    import json as _json

    config = _json.loads((ROOT / "railway.json").read_text(encoding="utf-8"))

    assert config["build"]["builder"] == "DOCKERFILE"
    assert config["deploy"]["healthcheckPath"] == access_gate._HEALTH_PATH
    assert config["deploy"]["restartPolicyType"] == "ON_FAILURE"
    # Long enough for the model warm-up on a cold start; short enough that a
    # container that never answers is called a failure the same day.
    assert 60 <= config["deploy"]["healthcheckTimeout"] <= 600


def test_docker_context_excludes_secrets_state_and_host_virtualenv():
    ignored = set((ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines())

    assert {".env", ".venv/", "data/"} <= ignored


def test_dockerfile_never_reintroduces_a_railway_build_killer():
    """ST-05: every build died at "scheduling build" from 2026-09-12 until
    two Dockerfile lines were found and removed. Railway's builder rejects
    a `VOLUME` instruction outright ("use Railway Volumes" instead) and
    rejects an anonymous `--mount=type=cache` too ("missing an id
    argument"; a named one is accepted only in Railway's own
    `s/<SERVICE_ID>-<name>` format, which this repo cannot hardcode -- it
    is cloned on two machines and also builds locally). Both are guarded
    here by name so either one coming back fails the suite instead of the
    next Railway deploy."""
    lines = (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # A comment EXPLAINING why there is no cache mount (this file
            # has one) necessarily contains the string being guarded
            # against; only real instruction lines are checked.
            continue
        assert not re.match(r"^VOLUME\b", stripped), (
            f"Dockerfile has a VOLUME instruction ({stripped!r}). Railway's "
            "builder rejects this outright ('use Railway Volumes'), which is "
            "what took every build down starting 2026-09-12. Persistence is "
            "declared per target instead: compose.yaml's named volume "
            "locally, a Railway Volume attached to the service in "
            "production."
        )
        if "--mount=type=cache" in stripped:
            assert "id=" in stripped, (
                f"Dockerfile has an anonymous cache mount ({stripped!r}). "
                "Railway's builder rejects a `--mount=type=cache` with no "
                "`id=` ('missing an id argument'), and a named one is only "
                "accepted in Railway's own s/<SERVICE_ID>-<name> format, "
                "which cannot be hardcoded here -- this repo builds on two "
                "machines and locally through compose.yaml too. Drop the "
                "cache mount rather than name one."
            )


def test_the_corpus_seed_survives_two_boots_sharing_one_volume():
    """Both halves of this were caught by RUNNING two containers against
    one volume, not by reading the script, and each one corrupted the
    disk in a different way:

    * plain `mv src dst` does NOT fail when `dst` exists -- it moves `src`
      INSIDE it and exits 0. The boot that lost the race buried a second
      copy of every document at `corpus/corpus.tmp.../`, 26 files where 13
      belong, and reported success. `mv -T` refuses instead.
    * `$$` is 1 in EVERY container (the entrypoint is always pid 1), so
      two boots picked the same `corpus.tmp.1`, copied into it together,
      and one renamed it away mid-copy: the volume kept a partial corpus
      (3 of 13 files, the legal PDFs missing) and the other boot died
      cleaning up a directory that had moved. `mktemp -d` gives each boot
      a name unique by construction.

    A crash loop or a half-seeded disk on a hosting platform is debugged
    from a dashboard, with no shell, so this is guarded here."""
    entrypoint = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")
    code = [
        line
        for line in entrypoint.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    seed_moves = [line for line in code if "mv" in line and "CORPUS_DIR" in line]

    assert seed_moves, "the seeding step no longer moves anything into place"
    for line in seed_moves:
        assert "mv -T" in line, (
            f"the corpus seed uses a bare `mv` ({line.strip()!r}). With the "
            "target directory already present that moves the staging copy "
            "INSIDE it and exits 0, leaving a duplicate corpus nested one "
            "level down. Use `mv -T`, which refuses a non-empty target."
        )
    staging = [line for line in code if "seed_tmp=" in line]
    assert staging, "the seeding step no longer stages the copy before moving it"
    for line in staging:
        assert "mktemp" in line, (
            f"the staging directory is named without mktemp ({line.strip()!r}). "
            "Every container's entrypoint is pid 1, so `$$` collides between "
            "two boots sharing one volume and they corrupt each other's copy."
        )


def test_an_unreachable_corpus_source_cannot_fail_the_build():
    """PROVEN on Railway, 2026-09-12: the first corpus source (the Labour
    Code on adala.justice.gov.ma) timed out from Railway's builders while it
    downloads fine from Morocco, and `set -eu` turned that into a failed
    deploy. The seed is the least important thing the image carries (the
    live volume already has the documents, and evidence-only mode cannot
    index them anyway), so the FETCH must sit behind an `if`. The VERIFY
    stays inside that branch: a seed that is shipped must still be one
    Sanad can read."""
    code = [
        line.strip()
        for line in (ROOT / "Dockerfile").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    fetches = [line for line in code if "scripts/corpus.py fetch" in line]

    assert fetches, "the Dockerfile no longer fetches a seed corpus at all"
    for line in fetches:
        assert line.startswith("if python scripts/corpus.py fetch"), (
            f"the corpus fetch is not guarded ({line!r}). Under `set -eu` a "
            "single unreachable source -- the Ministry of Justice site times "
            "out from Railway's builders -- fails the whole deploy. Wrap it: "
            "`if python scripts/corpus.py fetch; then ... verify ...; else "
            "<warn, ship no seed>; fi`."
        )
    assert any("scripts/corpus.py verify" in line for line in code), (
        "the corpus verify step is gone: a shipped seed must still be checked"
    )
