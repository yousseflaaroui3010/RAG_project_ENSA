#!/usr/bin/env bash
# Sanad developer setup. Run it from the repo root in Git Bash:
#
#     bash scripts/setup-dev.sh
#
# Safe to run as many times as you like. It changes nothing that is already
# correct, and it never installs anything from an untrusted source.
#
# It ends with a PASS / MISSING summary so you always know where you stand.

set -u
cd "$(dirname "$0")/.." || exit 1
ROOT="$(pwd)"

PASS=(); FAIL=(); NOTE=()
ok()   { PASS+=("$1"); echo "  OK      $1"; }
bad()  { FAIL+=("$1"); echo "  MISSING $1"; }
note() { NOTE+=("$1"); echo "  NOTE    $1"; }
step() { echo ""; echo "== $1"; }

echo "Sanad developer setup"
echo "Repo: $ROOT"

# ---------------------------------------------------------------- 1. uv
step "1. uv (installs Python 3.12 and every package for you)"
if command -v uv >/dev/null 2>&1; then
  ok "uv $(uv --version 2>&1 | awk '{print $2}')"
else
  bad "uv is not on PATH"
  echo ""
  echo "  Install it, then CLOSE AND REOPEN your terminal:"
  echo '    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
  echo "  If that is blocked, use:  python -m pip install uv"
  echo ""
  echo "  Stopping here. Nothing else works without uv."
  exit 1
fi

# ------------------------------------------------------- 2. dependencies
step "2. Project packages"
if uv sync 2>&1 | tail -3; then
  ok "packages installed and matching uv.lock"
else
  bad "uv sync failed, read the error above"
fi

# -------------------------------------------------------------- 3. gh CLI
step "3. GitHub CLI (needed to open and read pull requests)"
if command -v gh >/dev/null 2>&1; then
  ok "gh $(gh --version 2>&1 | head -1 | awk '{print $3}')"
  if gh auth status >/dev/null 2>&1; then
    ok "gh is logged in"
  else
    bad "gh is installed but NOT logged in"
    echo "    Fix:  gh auth login      (choose GitHub.com, HTTPS, browser)"
    echo "    Until you do this you cannot open a PR, and pushed work stays invisible."
  fi
else
  bad "gh is not installed"
  echo "    Fix:  winget install --id GitHub.cli    then reopen the terminal"
fi

# ------------------------------------------------- 4. branch safety hook
step "4. Branch safety hook (blocks commits straight onto main)"
HOOK_SRC="$ROOT/.claude/git-hooks/pre-commit"
HOOK_DST="$ROOT/.git/hooks/pre-commit"
if [ ! -f "$HOOK_SRC" ]; then
  bad "hook template missing at .claude/git-hooks/pre-commit"
elif [ -f "$HOOK_DST" ] && cmp -s "$HOOK_SRC" "$HOOK_DST"; then
  ok "already installed"
else
  if cp "$HOOK_SRC" "$HOOK_DST" 2>/dev/null && chmod +x "$HOOK_DST" 2>/dev/null; then
    ok "installed"
  else
    bad "could not install the hook, copy it by hand"
  fi
fi

# ------------------------------------------------------ 5. git board alias
step "5. 'git board' (one command showing who is working on what)"
if git config --global --get alias.board >/dev/null 2>&1; then
  ok "alias already set"
else
  git config --global alias.board '!git fetch --all --prune -q && echo "=== MAIN ===" && git log origin/main --oneline -3 && echo "" && echo "=== WHO IS ON WHAT ===" && git for-each-ref --sort=-committerdate --format="%(refname:short)  |  %(authorname)  |  %(committerdate:relative)" refs/remotes/origin && echo "" && echo "=== OPEN PRs ===" && gh pr list'
  ok "alias created"
fi
echo "    Use it every morning and before starting any task:  git board"

# -------------------------------------------------- 6. does the build work
step "6. Proving it actually works (not just installed)"
if uv run ruff check . >/dev/null 2>&1; then
  ok "lint clean"
else
  bad "lint failing, run: uv run ruff check ."
fi
# Judge the run by its EXIT CODE, never by the last line of output. With -q
# the last line is the progress dots, so a green run reads as a failure. This
# script shipped with that bug for exactly one test run.
TESTOUT="$(uv run pytest 2>&1)"
TESTRC=$?
SUMMARY="$(printf '%s\n' "$TESTOUT" | grep -E '[0-9]+ (passed|failed|error)' | tail -1)"
if [ "$TESTRC" -eq 0 ]; then
  ok "tests pass (${SUMMARY:-exit 0})"
else
  bad "tests failing (${SUMMARY:-exit $TESTRC}), run: uv run pytest"
fi

# --------------------------------------------------- 7. optional code graph
step "7. Code graph (OPTIONAL, not required to work on Sanad)"
if command -v codebase-memory-mcp >/dev/null 2>&1; then
  ok "codebase-memory-mcp found on PATH"
else
  note "codebase-memory-mcp is not installed on this machine"
  echo "    .mcp.json already points at it, so it starts working the moment"
  echo "    the program exists. Without it, Claude falls back to grep and find,"
  echo "    which is slower but correct."
  echo ""
  echo "    This script does NOT install it on purpose. An earlier search for"
  echo "    an install source returned a page carrying what looked like"
  echo "    prompt-injection text, and installing it was refused. Get the"
  echo "    program from a source you trust, by hand. See DECISIONS.md."
fi

# ------------------------------------------------------------- summary
echo ""
echo "======================================================"
echo " SUMMARY"
echo "======================================================"
echo " Working : ${#PASS[@]}"
echo " Missing : ${#FAIL[@]}"
echo " Notes   : ${#NOTE[@]}"
if [ "${#FAIL[@]}" -gt 0 ]; then
  echo ""
  echo " Fix these before you start:"
  for f in "${FAIL[@]}"; do echo "   - $f"; done
  echo ""
  echo " Re-run this script after fixing:  bash scripts/setup-dev.sh"
  exit 1
fi
echo ""
echo " You are ready. Your daily loop:"
echo "   git board                                  # see what changed"
echo "   git checkout main && git pull && uv sync   # get it"
echo "   git checkout -b feat/S1-ST-XX-slug         # claim your task"
echo "   git commit --allow-empty -m 'claim: ST-XX, YOURNAME'"
echo "   git push -u origin HEAD                    # plant your flag"
exit 0