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
