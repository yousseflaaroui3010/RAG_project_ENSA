# SETUP GUIDE: Phase 3 + 4 Claude Code System

> AUTOMATED: you can skip the hand-work below. Paste SETUP-PROMPT.md into
> Claude Code and it runs these steps itself, asks you the few questions
> it cannot detect, and tests the walls. This guide stays as the reference.
Plain words, short steps. Total setup time: about an hour.

## The idea in one paragraph
Words in a prompt are notes taped to the fridge. Claude reads them, then
sometimes ignores them. So this kit gives you four walls that do not
depend on Claude's mood: (1) small scoped instructions that load only
when needed, (2) local hooks that physically block or force actions,
(3) CI checks on every pull request, (4) rules on the git server itself,
which Claude cannot touch. Plus one shared memory: a code graph for the
codebase, and three small files for state, decisions, and changes.
Anthropic's own docs say it plainly: CLAUDE.md and rules are context, not
enforcement; to actually block an action, use a PreToolUse hook.

## Step 1: Copy the kit into your repo
- Copy everything in this kit into your project root (keep the folder
  structure: `.claude/`, `docs/`, `.github/`, `CLAUDE.md`, `.mcp.json`).
- Make the hook scripts executable:
  `chmod +x .claude/hooks/*.sh`
- Commit all of it. The whole team gets the same walls.
- Windows note: these hooks are bash + python3 scripts. On Windows, run
  Claude Code inside WSL2 so they work as-is.

## Step 2: Fill in the blanks (10 minutes)
- `CLAUDE.md`: replace every TODO_ with your real commands and product line.
- `.claude/hooks/config.sh`: set TYPECHECK_CMD and TEST_CMD to your real
  commands. Empty string = that check is skipped until you set it.
- `.github/workflows/gate.yml`: adjust the two TODO command lines.
- `.claude/rules/backend.md` and `frontend.md`: fix the `paths:` globs to
  match your real folder names. Keep the quotes around each glob; unquoted
  globs silently fail to parse. Keep path-scoped rules at project level
  (there is a known bug where user-level `~/.claude/rules/` ignores paths).

## Step 3: Install the code map (this fixes "Claude forgets my codebase")
This is a graph index of your whole repo: every function, class, call
chain. Claude asks the map instead of reading folders file by file.
- Tool: codebase-memory-mcp (open source, MIT, single binary, runs fully
  on your machine, no API key).
- Easiest install: open Claude Code in the repo and say
  "Install https://github.com/DeusData/codebase-memory-mcp and configure
  it for this project". Or run their setup script:
  `curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/scripts/setup.sh | bash`
- The kit's `.mcp.json` already points at the binary name; if you install
  to a custom path, put the full path in the `command` field.
- Restart Claude Code, run `/mcp`, confirm the server is listed with its
  tools. Then say "Index this project".
- Correction to your earlier notes: `npm install -g
  @modelcontextprotocol/server-memory` is a DIFFERENT tool (a generic
  note-memory server). It does not index code. Do not use it for this.
- Honest numbers: the vendor's "120x fewer tokens" is a best-case
  microbenchmark. The authors' own paper measured about 10x fewer tokens
  with a small quality dip vs full file reading, and an independent test
  saw roughly 2-3x on a real workflow. Still a big win; just set
  expectations at 2-10x, not 100x.

## Step 4: Verify the walls are up (5 minutes)
Open Claude Code in the repo and run:
- `/hooks` : you should see PreToolUse, PostToolUse, Stop, PreCompact,
  SessionStart wired.
- `/memory` : CLAUDE.md and the unscoped rules should be listed. Open a
  backend file, run `/memory` again, backend.md should appear.
- `/agents` : b1-b4 and o1-o4 should be listed.
- Test a wall: ask Claude to run `git commit --no-verify -m test`.
  The guard must block it and say why.

## Step 5: Lock the git server (the wall Claude can never touch)
On GitHub.com:
- Repo Settings -> Rules -> Rulesets -> new ruleset on `main`:
  block direct pushes, require a pull request, require the `gate` status
  checks to pass, block force pushes.
- The kit's `.github/workflows/gate.yml` provides those checks:
  typecheck, tests, INTENT commit-body check, 3% duplication gate (jscpd),
  and secret scanning.
- Precision on your notes: true `pre-receive` server hooks exist only on
  GitHub Enterprise Server (or self-hosted GitLab/Gitea). On regular
  GitHub.com, rulesets + required status checks are the equivalent wall,
  and they are enough: Claude cannot merge anything that fails CI.

## Step 6 (optional): Isolation upgrades
- Git worktrees: one worktree per task
  (`git worktree add ../proj-T-001 task/T-001-slug`) keeps agent chaos out
  of your main checkout. Cheap and local.
- E2B sandboxes: cloud microVMs for running untrusted test code. Nice to
  have; a worktree plus CI covers most solo/team setups. Add E2B later if
  agents start running risky scripts.
- Keep MCP servers to a minimum. Every connected server's tool list eats
  context in every session. The graph server (and maybe E2B) is enough.

## Step 7: Start Phase 3
Drop the signed Phase 2 pack into `docs/phase2/`, then paste
`PHASE3-KICKOFF-PROMPT.md` into Claude Code. It will audit the pack,
build the task plan, wait for your approval, then run the loop.

---

# RISK PLAYBOOK (the part most setups skip)

## Risk 1: /compact eats details mid-task
What survives a compact, by design:
- Root CLAUDE.md is re-read from disk and re-injected after compaction.
- The SessionStart hook fires again (compaction counts as a session
  source) and re-injects BUILD-STATE.md, branch, and recent commits.
- The PreCompact hook backs up the raw transcript to `.claude/backups/`
  and stamps BUILD-STATE.md so the next context knows it happened.
Your rule of thumb: if it matters, it lives in a file or a commit, never
only in chat. For long builds, prefer finishing a task, then `/clear` and
starting fresh, over trusting a compact summary.

## Risk 2: session or usage limit hits mid-task
- Tasks are sized under an hour on purpose: smaller than any limit window.
- Commit every green state. A green commit is a save point; worst case
  you lose minutes, not hours.
- Resume with `claude --continue` (or `--resume`). SessionStart re-runs
  and re-injects the state. The orchestrator's interruption protocol says:
  read BUILD-STATE, check `git status` on the task branch, continue from
  the "Where exactly" line. Never rebuild a task blind.

## Risk 3: Claude bypasses local checks
- The guard hook blocks `--no-verify`, force pushes, hook-path edits,
  HUSKY=0 / SKIP=, and edits to `.claude/hooks/` or settings.
- Assume a clever agent can still find a path around anything local.
  That is fine: the server ruleset + CI is the wall that holds. Local
  hooks exist to catch problems in seconds instead of at PR time.

## Risk 4: infinite hook loops burning tokens
- The Stop gate honors `stop_hook_active` and caps itself at 3 pushbacks
  per session (see config.sh), then lets go and logs it. Watch
  `.claude/logs/stopgate.log` if sessions feel stuck.

## Risk 5: memory drift
- Claude Code also keeps its own "auto memory" notes per project. Review
  them now and then via `/memory` and delete anything wrong; stale memory
  is worse than no memory.
- Same for BUILD-STATE.md: the orchestrator prunes Done items weekly so
  the file stays small enough to inject whole.

## Risk 6: duplicate and redundant code
Three layers catch it: agents must query the graph before writing
anything new (rule + prompt), b1 re-checks at review, and CI fails any PR
over 3% duplicated lines. If one layer sleeps, the next one catches it.

## Daily rhythm (2 minutes to read, saves hours)
- Start: open Claude Code, state auto-loads, confirm the Now task.
- Work: one task, one branch, commits at every green step.
- Handoff: b4 tests in isolation, b1 reviews and squash-merges.
- End of day: b1 squashes stragglers; you skim CHANGELOG-AI.md and
  DECISIONS.md like a site foreman reading the shift log.

---

# KIT v2 ADDITIONS (reviewer, skills, locked specs, journal gate)

- New agent `reviewer`: read-only by construction. It inherits all tools
  (including the code-graph MCP) but `disallowedTools` strips Edit and
  Write, so "do not edit files" is a fact, not a request. It grades 1-10;
  below 9 returns an exact file:line fix list to the builder.
- `b4-delivery-eng` now runs with `isolation: worktree` (its shell
  commands execute in a temporary git worktree, so test runs never dirty
  your checkout) and `memory: project` (it remembers flaky suites across
  sessions). Known bug: worktree isolation applies when b4 is spawned as
  a subagent; it is ignored if you launch it as the top-level agent with
  `claude --agent` (issue #50357).
- Two Skills in `.claude/skills/`: `zero-lock-migration` (expand,
  dual-write, backfill, contract) and `contract-types-regen`. Both are
  preloaded into b2 via its `skills:` frontmatter line.
- The guard hook now write-locks `docs/phase2/`. Builders physically
  cannot edit signed specs; they must escalate.
- The Stop gate now also checks the journal: if code changed this session
  but BUILD-STATE.md and CHANGELOG-AI.md were never touched, the session
  is pushed back to write the entry (same 3-attempt safety cap).
- Gotcha: agent files edited on disk load at session start; restart
  Claude Code (or use /agents) after changing them.
- Symbol backend: the reviewer works with the codebase-memory graph. If
  you prefer Serena's find_symbol / find_referencing_symbols (LSP-exact
  references), install it INSTEAD, not alongside; every extra MCP server
  costs context in every session.

---

# KIT v3 ADDITIONS (prompt architecture, new roles, anti-skip protocol)

- All 11 agent prompts rebuilt in XML blocks (role, context, instructions,
  constraints, output format) with reasoning discipline baked in: an
  epistemic ledger (facts vs inferences vs gaps), a no-guessing rule for
  schemas and commands, verify-before-report for code writers, and a
  fixed report contract per agent. Runtime values are {{VARIABLES}}; the
  full list lives in VARIABLES.md.
- Two new roles: tech-scout (vets every new dependency with hostile
  queries, CVEs, license, and stack fit) and docs-verifier (confirms
  external APIs against current official docs before anyone codes against
  memory, and audits internal doc drift). Both are read-only via
  disallowedTools.
- Anti-skip, anti-duplication upgrade: the absence protocol is now a
  global rule (graph + grep + written scope line before creating any
  symbol), and a new dup-sentry hook physically blocks creating a file
  whose name already exists elsewhere in the repo (common names like
  index.* are whitelisted inside the script).
- Six skills now: zero-lock-migration, contract-types-regen,
  dependency-vetting, api-doc-verification, e2e-failure-triage,
  prompt-registry-entry.
- prompts/ now ships a README, a format rule, and one example entry, so
  the registry is a template instead of an empty folder.
- REMAINING-CHECKLIST.md answers "what do I still install and fill in".

---

# KIT v5: fewer bodies, same walls (token consolidation)
- tech-scout and docs-verifier merged into one read-only `scout`; the two
  procedures stayed intact as skills that load only when the mode needs
  them.
- b2 no longer preloads its two skills; it invokes them when a task
  actually touches migrations or contracts.
- o1-o4 moved to .claude/agents-phase4/ so their descriptions stop riding
  on every Phase 3 turn; move them back at launch (README inside).
- b1 now consumes the reviewer's blast-radius map instead of rebuilding
  it, and the orchestrator handles trivial single-file tasks itself.
- Deliberately NOT merged: reviewer stays separate from builders and b1
  (read-only fresh eyes is the quality mechanism), and b2/b3 stay split
  (the generated-types contract between them is the coordination system).

---

# KIT v6: compressed prompts + five senior upgrades
- Every agent prompt, CLAUDE.md, and the kickoff rewritten telegraphic:
  same walls, roughly 40% fewer words, so every invocation and every
  main-session turn gets cheaper. Skills and hooks untouched: skills
  load only on demand, hooks cost compute not context.
- Added: plan-two-approaches beat (b2, b3), silent-requirements sweep in
  kickoff Step 0, rule of three in the duplication law and the
  reviewer's craft check, idempotent mutations (b2 + reviewer), spike
  branch before framework-level adoption (scout).

---

# KIT v8: the commit-door lock (field-tested gap, closed)
A real project proved two holes: the guard blocked pushes to main but
never commits ON main (and a repo with no remote never pushes), and the
stop-gate's 3-strike safety valve let journals slip silently. Fixed:
- guard.sh now blocks `git commit` and `git merge` while the current
  branch is protected. Agents commit on task branches or not at all.
- The stop-gate's escape now leaves a journal-debt flag instead of
  silence; SessionStart shows the debt and guard blocks ALL commits
  until BUILD-STATE and CHANGELOG are updated. Debt survives restarts.
- SessionStart warns when the code graph was never indexed, and the
  kickoff stamps a marker after indexing.
- .claude/git-hooks/pre-commit is a versioned git-level lock the HUMAN
  installs per clone (two commands in its header); it stops even human
  slips on main while letting merges through.

---

# KIT v9: package-manager-aware CI
gate.yml now carries both npm and pnpm blocks (npm active, pnpm ready,
with a cache-dependency-path note for monorepos), pinned to Node 22.
SETUP-PROMPT detects the manager from the lockfile, aligns every
workflow in .github/workflows/ to it, and treats an uncommitted or
ignored lockfile as a stop-and-report finding.
