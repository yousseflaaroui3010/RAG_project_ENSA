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

PASS=(); FAIL=(); FIX=(); NOTE=()
ok()   { PASS+=("$1"); echo "  OK      $1"; }
# bad "what is wrong" "the command that fixes it"
# The fix is stored, not just printed, because the summary at the bottom is
# what people actually read. The first version named the problem there and
# left the cure 30 lines up the scrollback, so a reader who trusted the
# summary still did not know what to type.
bad()  { FAIL+=("$1"); FIX+=("${2:-}"); echo "  PROBLEM $1"; }
note() { NOTE+=("$1"); echo "  NOTE    $1"; }
step() { echo ""; echo "== $1"; }

# Find a program on PATH, and if it is not there, look where Windows
# installers actually put things.
#
# Why this exists: `command -v gh` only searches PATH. When it failed, the
# first version of this script said "gh is not installed" and told the reader
# to install it. On a real machine gh 2.96.0 was already sitting in the winget
# folder, just not on PATH, so following that advice would have produced a
# second copy and fixed nothing. "Not on PATH" and "not installed" are
# different problems with different fixes, and the script has to tell them
# apart before it gives advice.
#
# Prints the path if found anywhere. Exit 0 = found, 1 = genuinely absent.
locate_tool() {
  name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    command -v "$name"
    return 0
  fi
  # Env vars arrive from Windows with backslashes; normalise them.
  la="$(printf '%s' "${LOCALAPPDATA:-}" | tr '\\' '/')"
  pf="$(printf '%s' "${PROGRAMFILES:-}" | tr '\\' '/')"
  for p in \
    "$la/Microsoft/WinGet/Links/$name.exe" \
    "$la/Programs/GitHub CLI/$name.exe" \
    "$pf/GitHub CLI/$name.exe" \
    "$la/Programs/$name/$name.exe" \
    "$HOME/.local/bin/$name" \
    "$HOME/.local/bin/$name.exe" \
    "$HOME/.cargo/bin/$name.exe"
  do
    case "$p" in ""|"/"*"//"*) continue ;; esac
    if [ -x "$p" ] || [ -f "$p" ]; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

# Turn /c/Users/... back into something you can paste into a Windows PATH box.
win_dir_of() {
  d="$(dirname "$1")"
  if command -v cygpath >/dev/null 2>&1; then cygpath -w "$d" 2>/dev/null || echo "$d"
  else echo "$d"; fi
}

echo "Sanad developer setup"
echo "Repo: $ROOT"

# ---------------------------------------------------------------- 1. uv
step "1. uv (installs Python 3.12 and every package for you)"
UV_PATH="$(locate_tool uv || true)"
if command -v uv >/dev/null 2>&1; then
  ok "uv $(uv --version 2>&1 | awk '{print $2}')"
elif [ -n "$UV_PATH" ]; then
  bad "uv IS installed, but your terminal cannot see it (PATH problem)" \
      "export PATH=\"\$PATH:$(dirname "$UV_PATH")\""
  echo ""
  echo "  Found it here:  $UV_PATH"
  echo "  Do NOT install it again. Add its folder to PATH instead:"
  echo "    export PATH=\"\$PATH:$(dirname "$UV_PATH")\"     (this window only)"
  echo "  Then re-run this script."
  exit 1
else
  bad "uv is genuinely not installed"
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
  bad "uv sync failed, read the error above" "uv sync"
fi

# -------------------------------------------------------------- 3. gh CLI
step "3. GitHub CLI (needed to open and read pull requests)"
GH_PATH="$(locate_tool gh || true)"
GH_ON_PATH=no
command -v gh >/dev/null 2>&1 && GH_ON_PATH=yes

if [ "$GH_ON_PATH" = yes ]; then
  ok "gh $(gh --version 2>&1 | head -1 | awk '{print $3}')"
elif [ -n "$GH_PATH" ]; then
  bad "gh IS installed, but your terminal cannot see it (PATH problem)" \
      "export PATH=\"\$PATH:$(dirname "$GH_PATH")\""
  echo ""
  echo "    Found it here:  $GH_PATH"
  echo "    Version:        $("$GH_PATH" --version 2>&1 | head -1 | awk '{print $3}')"
  echo ""
  echo "    DO NOT install it again. You would end up with two copies and the"
  echo "    same problem. The program is fine; the terminal just does not know"
  echo "    where to look."
  echo ""
  echo "    Fix, in PowerShell (not Git Bash), then CLOSE AND REOPEN the terminal:"
  echo "      setx PATH \"\$env:PATH;$(win_dir_of "$GH_PATH")\""
  echo ""
  echo "    Or just for right now, in this Git Bash window:"
  echo "      export PATH=\"\$PATH:$(dirname "$GH_PATH")\""
else
  bad "gh is genuinely not installed (not on PATH, not in the usual folders)" \
      "winget install --id GitHub.cli"
  echo "    Fix:  winget install --id GitHub.cli    then reopen the terminal"
fi

# Only ask about login if the terminal can actually run it.
if [ "$GH_ON_PATH" = yes ]; then
  if gh auth status >/dev/null 2>&1; then
    ok "gh is logged in"
  else
    bad "gh is installed but NOT logged in" "gh auth login"
    echo "    Fix:  gh auth login      (choose GitHub.com, HTTPS, browser)"
    echo "    Until you do this you cannot open a PR, and pushed work stays invisible."
    echo "    That is exactly how three finished branches sat unseen for three days."
  fi
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
  bad "lint failing" "uv run ruff check ."
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
  bad "tests failing (${SUMMARY:-exit $TESTRC})" "uv run pytest"
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
  i=0
  while [ "$i" -lt "${#FAIL[@]}" ]; do
    echo ""
    echo "   [$((i+1))] ${FAIL[$i]}"
    if [ -n "${FIX[$i]}" ]; then
      echo "       RUN THIS:"
      printf '         %s\n' "${FIX[$i]}"
    fi
    i=$((i+1))
  done
  echo ""
  echo " Run the fix above, then run this script again:"
  echo "   bash scripts/setup-dev.sh"
  echo ""
  echo " Two notes so you do not undo your own fix:"
  echo "   - An 'export PATH=...' fix lasts only in THIS terminal window."
  echo "     Do NOT close it. Scroll up to the matching step for the"
  echo "     permanent version if you want it to stick for good."
  echo "   - An 'install' fix is the opposite: close and reopen the terminal"
  echo "     afterwards, or the new program stays invisible."
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