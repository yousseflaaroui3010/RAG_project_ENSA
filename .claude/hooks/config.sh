#!/usr/bin/env bash
# One place to set your project commands. All hooks source this file.
# Leave a variable empty ("") to skip that check until you configure it.

# Fast check that runs after every file edit (keep it under ~30s):
TYPECHECK_CMD="npx tsc --noEmit"        # e.g. "npx tsc --noEmit" or "cargo check"

# Full test suite that must pass before Claude is allowed to stop:
TEST_CMD="npm test --silent"            # e.g. "npm test --silent" or "pytest -q"

# Branch names Claude must never push to directly:
PROTECTED_BRANCHES="main master production"

# Max times the Stop gate may push back per session (loop safety valve):
STOP_MAX_ATTEMPTS=3
