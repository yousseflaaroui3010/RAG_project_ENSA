import re
from pathlib import Path

import yaml

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
