#!/usr/bin/env bash
# One place to set your project commands. All hooks source this file.
# Leave a variable empty ("") to skip that check until you configure it.

# Fast check that runs after every file edit (keep it under ~30s):
# DEFERRED until the first build story creates pyproject.toml + uv.lock and
# installs ruff. Target command (restore then): "uv run ruff check ."
TYPECHECK_CMD=""

# Full test suite that must pass before Claude is allowed to stop:
# DEFERRED until pytest is installed via uv sync (first build story).
# Target command (restore then): "uv run pytest -q"
TEST_CMD=""

# Branch names Claude must never push to directly:
PROTECTED_BRANCHES="main master production"

# Max times the Stop gate may push back per session (loop safety valve):
STOP_MAX_ATTEMPTS=3
