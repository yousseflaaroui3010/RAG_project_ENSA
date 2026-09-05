# BUILD-STATE (the flight recorder: trust this file over chat memory)

Last verified commit: **fd2e6fa on main**, 2026-09-03. One PR landed since
the previous header: #79, the ST-21 and ST-23 reviews -- ST-21 clean, ST-23's
prompt-template leak fixed and its fusion gap parked. See the review section
in Now.

MEASURED ON MAIN AT fd2e6fa, by hand, in gate.yml order, AFTER the merge
rather than only on the branch: `uv sync --frozen` clean (170 packages),
`uv run ruff check .` exit 0, `uv run pytest` **625 passed / 2 skipped**
in 131.85s -- up from 623, which is exactly the two tests the prompt fix
adds. Exit codes read from `$?`: `SYNC_EXIT=0`, `RUFF_EXIT=0`,
`PYTEST_EXIT=0`.

**THE `.env` BLOCKER IS HALF CLOSED, AND THE OTHER HALF IS WORSE THAN THE
FIRST. THIS IS THE ENTRY TO READ.** The retired model name is fixed:
`CHAT_MODEL_CLOUD` on this clone now reads `gemini-3.6-flash`, and the
byte-order mark that was sitting at the top of `.env` was stripped at the
same time (harmless only because line 1 is a comment that absorbed it --
reorder that file so a real setting sits first and that setting silently
stops working, which is the pydantic-settings failure PR #64 recorded).

**But ONE LIVE CALL then proved THE KEY ITSELF IS INVALID.** Google answered
`400 INVALID_ARGUMENT / API_KEY_INVALID`, "API key not valid. Please pass a
valid API key." The key is present and 56 characters long, so nothing about
its SHAPE says it is wrong; only using it does. Owner: whoever holds this
clone -- a new Google AI Studio key in `.env`, which is git-ignored and holds
a secret, so no merge and no agent can do it.

**WHY THAT ONE CALL WAS WORTH THE CREDITS IT SPENT, spelled out because the
project's own law says stop and ask before spending money and the human was
asked:** the config was CORRECT and the product still could not answer. Every
check available offline was green -- the setting loads, the model name is the
one ST-24 proved live, the key is present and plausible -- and all of it was
consistent with a product that cannot talk to a model at all. Without the
call this would have surfaced at ST-36, in the middle of the first evaluation
run, as sixty failures nobody could attribute. "It builds" is not "it works",
and this is the cheapest instance of that lesson this project will get.

Plus the golden set's own corpus check, which is not in gate.yml because
`data/` is git-ignored: `uv run python scripts/golden_grounding.py` ->
**"OK: 60 rows grounded (40 in scope, 20 out)"**, exit 0 (measured at
5e49246; #79 touched no golden file).

WHY THIS HEADER MOVED AGAIN THE SAME DAY, since the count is unchanged and a
reader could mistake this for churn: #76 and #77 landed ABOVE the journal
commit that recorded 617c972, and this file's own rule says the only commit
allowed above the measured one is that journal commit. By that rule the
previous header was stale the moment #76 merged. Re-measured rather than
patched -- **the pass count is identical (623) and the point is that it was
RE-RUN, not that it changed.** A header whose number happens to still be
right, sitting above two commits nobody re-measured, is the exact shape this
file has recorded going wrong six times.

**STEP 4, GITLEAKS, WAS NOT RUN LOCALLY FOR THIS STAMP.** This header was
written on MB's clone, where gitleaks is absent -- re-checked three ways on
2026-09-03: not on PATH, `~/AppData/Local/Microsoft/WinGet/Links/` does not
exist, and `gitleaks version` returns "command not found". It IS covered for
this commit: CI `verify` ran all four steps green on #79's final push (run
33827305641, every step "success", secret scan included), and on #74, #76 and
#77 before it. So: steps 1-3 verified locally on main after the merges, step 4
verified on CI against the same trees. Do not compress that into "the whole
gate ran locally".

**WHAT ST-35's REVIEW COST, and it is the entry to read: THE FREEZE THIS
STORY EXISTS TO DELIVER COULD NOT FAIL.** `assert GOLDEN_SET_VERSION ==
"v1"` compared a constant to a literal nine lines above it in the same
module, and `FROZEN_IDS` was derived from `FINAL_TOTAL_*` rather than being
an independent record. Adding a 41st question took two number edits and
passed 13 of 13 with the version untouched -- run, not reasoned about. Three
artifacts claimed otherwise, including a DECISIONS row saying "frozen at v1
by two mechanisms". Fixed by `FROZEN_TOTALS = {"v1": (40, 20)}` and proven
by deliberate violation, red before green. **That makes eight stories running
where a post-green pass found what the suite could not**, and the second time
on this project that a mutation battery reported every mutation killed while
missing the one edit that mattered: a battery is only as wide as the list you
write for it.

**AND THE TWO REVIEW PASSES DISAGREED, which is the argument for running
both.** The cold pass called `g-out-020` a mislabelled refusal; the briefed
pass read the disability chapter (labour code articles 166-171) and showed
the refusal was correct -- there is no hiring quota under any wording. Had
only the cold pass run, a good row would have been deleted. Had only the
briefed pass run, the arguable-row risk would not have been written down.

ONE QUALIFICATION ON THAT REVIEW, recorded rather than absorbed: it ran on
**MB's own clone**, and ST-35 is MB's story. Rule 5 is about the PARTNER's
eyes, so this satisfies it in form and not necessarily in substance. The
human was told this before merging and chose to proceed, which is a decision
and not an oversight. **The unpaid-review list is unchanged: ST-21, ST-23,
ST-19, ST-29.**

Previous header, kept because its gate evidence still stands for ST-27:
Last verified commit: **c70c654 on main**, 2026-08-31. Two PRs landed
since the previous header and both are merged: #71 (MB's re-stamp at
9da0c56 after ST-19 and ST-29) and #72 (ST-27, the S1 chat screen).

MEASURED ON MAIN AT c70c654, by hand, in gate.yml order, AFTER both
merges rather than before: `uv sync --frozen` clean (170 packages),
`uv run ruff check .` exit 0, `uv run pytest` **621 passed / 2 skipped**
in 375.52s. Every exit code was read from `$?`, not inferred from the
last line of output -- `ruff_exit=0` and `PYTEST_EXIT=0`.

**ALL FOUR GATE STEPS RAN LOCALLY THIS TIME, and the fourth one is the
news.** `gitleaks` IS installed on YL's machine, so the secret scan is no
longer CI-only: `gitleaks detect --no-git` over the whole tracked tree at
c70c654 -- 112 files, 2.65 MB -- reports **"no leaks found", exit 0**.

SCOPE OF THAT SCAN, stated precisely because the previous three headers
were vaguer than the command they quoted: it covers every TRACKED FILE AS
IT STANDS at c70c654. It does NOT walk the git history, and a full-history
`gitleaks detect` timed out twice at nine minutes on this machine. History
is covered by CI's `gitleaks-action`, which passed on #72's `verify` run.
So: current tree verified locally, history verified on CI. Do not compress
that into "gitleaks clean" without the two halves.

Also still true and inherited from MB's stamp: gitleaks is NOT installed
on HER machine (PATH and `~/AppData/Local/Microsoft/WinGet/Links/` both
empty), so a header she writes cannot make this claim. Whoever installs
it there closes the gap for good.

Plus the golden set's own corpus check, which is not in gate.yml because
`data/` is git-ignored: `uv run python scripts/golden_grounding.py` ->
"OK: 45 rows grounded (30 in scope, 15 out)", per MB's stamp.

**ST-27 PAID BOTH REVIEW PASSES AND THAT IS THE HEADLINE, not the
screen.** A cold verifier read and the rule-5 reviewer pass ran on the
branch before merge and found **NINE defects, five of them blocking, on a
tree whose whole gate was green.** Seven stories running now. The two
worst were live thread races that ruff, 609 passing tests and several
by-hand runs of the real server had all passed over. The full list is in
the ST-27 review section below; read it before deciding the four unpaid
reviews can be written off.

**THE UNPAID-REVIEW LIST IS STILL ST-21, ST-23, ST-19 AND ST-29** --
unchanged by today, because ST-27 paid its own. MB's stamp recorded that
#67 and #70 merged without a rule-5 pass at the human's explicit
instruction, with the concern raised first and not withdrawn; that entry
stands and is not softened here.

WHY THIS HEADER MOVED: at merge time, which is what its own rule demands.
The only commit above the one named here should be the journal commit
recording this measurement. There is still no gate on this file's
freshness.

**SANAD CAN NOW BE LAUNCHED AND LOOKED AT.** `uv run python app.py`
serves S1, the chat screen (ST-27, CR-02: Jinja templates, hand-written
CSS, no JS toolchain). The engine has answered since ST-24; as of c70c654
a human can watch it do so, with its sources, its honest refusals and the
passage behind every citation. The sentence three headers carried until
today -- "there is still no UI and no app.py, so it cannot be LAUNCHED"
-- is the one ST-27 existed to falsify.

WHAT IS STILL NOT WIRED, so the sentence above is not read as more than
it says: F-07 session memory does nothing (ST-25's `summarize` stub), the
clarification variant cannot appear live (ST-22's `clarify` stub), there
is no rewrite-and-split, and S2 and S3 do not exist (ST-28, ST-34).

WHAT ST-24 COST, worth reading before the next agent story: the answer
itself was the easy half. The decline parser -- the one word that lets
the model say "these sections do not answer it" -- took THREE versions
and TWO review passes, and the first two versions were both wrong in the
direction that DISCARDS A CORRECT ANSWER. Neither was visible by reading
the code. Both lived in the interaction between the code and a sentence
the prompt itself instructs the model to write. 31 mutations were injected
across the story and all 31 were killed, and the mutation battery did not
find either defect: a battery is only as wide as the list you write for
it, and neither defect was on the list.

Previous header, kept because its own rule is the one this header obeys:
Last verified commit c7c2085 on main, 2026-08-27, with five PRs merged
(#49 ST-21, #52 journal re-stamp, #53 ST-23, #54 the design reference,
#55 the retired cloud model name), `uv run pytest` **451 passed / 2
skipped** in 351s and gitleaks clean over 2.98 MB.

HOW TO READ THIS HEADER, because the re-stamp rule chases its own tail
otherwise: the commit named above is the one the GATE WAS MEASURED ON.
The only commit that can come after it is the journal commit recording
that measurement, which changes no code. If you find any OTHER commit on
main above it, this header is stale -- re-measure, do not patch the
number.

ONE NUMBER TO DISTRUST IN THIS FILE, stated so nobody quotes it as a
performance figure: the suite's WALL TIME swings wildly on this machine --
90s, 181s, 260s, 308s and 504s were all observed for the same 451 tests
in one day. That is machine load, not the code. The pass count is the
signal; the seconds are noise.

A LIVE MODEL CALL NOW WORKS from this machine (Gemini, cloud mode) and
finding that out immediately exposed a dead pinned model name -- see the
blockers section, which is the most important entry in this update.

This is the first time this header has obeyed its own rule end to end.
The rule, restated because it was written five staleness incidents ago:
re-read and re-stamp immediately before merging, and take the number at
the last possible moment. What that produced here: the branch's own gate
run said 404 passed, CI `verify` on the PR said the same, and then the
whole gate was run a THIRD time on main after the squash landed -- because
a green branch and a green main are not the same claim.

Previous header, kept because it was accurate for the branch it described:
Last verified commit bbaca48 on `feat/S2-ST-21-agent-graph`, not merged;
main was at da81143 (PR #48).

THE WHOLE GATE WAS RUN BY HAND ON THE BRANCH, in gate.yml order, all four
steps, and then RE-RUN ON MAIN AFTER THE MERGE at 24479ba: `uv sync
--frozen` clean (170 packages audited), `uv run ruff check .` exit 0,
`uv run pytest` **404 passed / 2 skipped** (338 / 2 at the branch point),
and -- FOR THE FIRST TIME ON THIS MACHINE -- `gitleaks detect` exit 0,
"no leaks found", 2.77 MB scanned. CI `verify` was also green on PR #49,
all four steps, 1m23s. Earlier runs in this session showed 379 and then
396; both were true when taken, and neither is the number that counts.
66 of the 404 are ST-21's own (46 graph + 7 state + 7 trace + 6 stores).

GITLEAKS IS NOW INSTALLED HERE, so blocker item 5 below is CLOSED and the
standing caveat "CI is the only place step 4 executes" is no longer true.
`gitleaks version` reports 8.30.1 at
`~/AppData/Local/Microsoft/WinGet/Links/gitleaks`. Every earlier header
in this file that says gitleaks was NOT run locally was accurate the day
it was written; from this session on, the local gate is complete.

Previous header, kept because its own new rule is the reason this one
exists: Last verified commit: 249724a on main. Updated: 2026-08-24,
re-stamped at
merge time rather than at writing time -- see the rule below, which is the
whole reason this header moved. `uv run ruff check .` exit 0 and
`uv run pytest` 338 passed / 2 skipped, measured on the merged tree BEFORE
PR #41 was merged, and CI `verify` green on that same tree. gitleaks
(step 4) NOT run locally: still not installed on this machine; CI remains
the only place that step executes.

THE RULE THIS HEADER NOW OBEYS, and it is new: **re-read and re-stamp this
header immediately before merging, not when the PR is written.** PR #41
was accurate the day it was authored and stale the moment it landed,
because main moved five commits (PRs #42-#45) and the suite went 336 ->
338 while the PR sat open. That would have been the FIFTH instance of this
file describing a state that no longer existed, and the first time the
cause was not carelessness but latency. "Do not copy the number" was never
enough; the number has to be taken at the last possible moment.

Previous header, kept because its own correction is still the useful part:
it recorded e1e4098 / 336 passed, verified by the ST-17 RULE-5 REVIEW PASS
session which independently ran gate.yml steps 1-3 on main before touching
anything -- `uv sync --frozen` clean (170 packages), ruff exit 0, 336
passed / 2 skipped, corroborating the count rather than copying it.

WHAT LANDED ON MAIN 2026-08-23/24, none of which the sections below know
about. All six are docs and control-plane only; no source file changed
except in #40:
- #40 `900f58d` fix(change-detection): a present-but-unsupported file is
  NOT Removed. The REMOVED sweep excluded only `scan.unreadable`, never
  `scan.unsupported`, so a file that fell outside
  `supported_document_extensions` after already having a document row was
  reported Skipped AND Removed in the same run -- two rows for one file,
  with the Removed branch deleting the passages of a file the user never
  touched. Reviewed before merge; both new tests proven to fail with the
  fix reverted. This is the defect the #41 review pass found.
- #42 `ee143a3` the `report-brief` skill and a CLAUDE.md reporting rule.
- #43 `3bf742c` the `prove-it` skill: enumerate every candidate root cause
  before touching code, break every check on purpose, and read a mutation
  result honestly. Carries the six vacuous-test shapes this project has
  actually shipped.
- #44 `b248c7b` `test-strategy` and `research-discipline`, imported from
  user level so BOTH machines have them.
- #45 `12f4e0c` the core law folded into CLAUDE.md, plus the `reviewer`
  and `verifier` agents. Four of nine user-level rule files were REJECTED
  on content, not convenience -- `git-discipline.md` mandates `task/T-xxx`
  branches and an `[AI]` marker, which CLAUDE.md rules 2 and 4 forbid.
- #41 `249724a` this file's own ST-17 review pass.

STILL NOT TRACKED, and it is the one thing keeping the above at documents
rather than enforcement: `.claude/settings.json`. The two hooks
(UserPromptSubmit for the reply rule, PostToolUse for the prove-it
trigger) are written, tested and INSTALLED on YL's machine -- verified
live, the injected text appears in the session -- but the file is
deny-listed for Edit, so no agent can place or update it. MB has no hooks
at all. PR #46 is held open for exactly this reason: its tracked copy is
an older version missing the `give-steps` rule, and merging it would hand
MB a wrong hook rather than no hook.

The previous header said 0210408 / 318 tests, which was four commits
stale (PRs #36-#39 landed after it). That is the FOURTH time this file
has described a state that no longer existed, and the first three were
all the same shape. Noted rather than quietly corrected.

Earlier header, kept because its gate evidence still stands for ST-17
itself: Last verified commit 0210408 on main (ST-17, PR #35, squash).
The gate was run by hand in gate.yml
order on the branch AND re-run ON MAIN after the merge, not only on the
branch: `uv sync --frozen` clean, `uv run ruff check .` exit 0, `uv run
pytest` exit 0 with 318 passed / 2 skipped (272 / 2 at the branch point).
CI `verify` green on PR #35 with all four gate.yml steps succeeding,
including the gitleaks scan. gitleaks step 4 was NOT run locally --
re-checked this session against PATH, `Program Files` and `~/go/bin`, all
negative. Still not installed on this machine; CI remains the only place
that step executes.

RESOLVED this session, and it had been open since 2026-08-22: the CBM MCP
tools DO attach. `list_projects` answered on the first call and the repo is
indexed at 892 nodes / 3,228 edges with zero skipped files and one
parse_partial line (DECISIONS.md:59, a markdown table row, harmless). The
blocker below marked "UNVERIFIED: the CBM MCP tools attaching" is closed.

Earlier header, kept because its caveat still governs ST-14 and ST-15:
Updated: 2026-08-23 by the ST-16 session, which
independently ran the whole of gate.yml at that commit plus its own
branch: `uv sync --frozen` clean, `uv run ruff check .` clean,
`uv run pytest -q` 272 passed / 2 skipped on the branch (191 / 1 at the
branch point). gate.yml step 4, gitleaks, was NOT run -- re-checked this
session against PATH, three install locations and `winget list`, all
negative. It is still not installed on this machine and CI remains the
only place that step executes.

Earlier header, kept because its caveat still governs ST-14 and ST-15:
Updated: 2026-08-18 by Phase 3 orchestrator, catching up three merges of
journal drift: ST-14, ST-15 and the harness migration all landed on main
without a BUILD-STATE update. Verification claims below for those three
are drawn from the commit bodies of 711f7e0, 8e5a734 and 275886f (each
records ruff/pytest output at merge time); this session did not
independently re-run ST-14/ST-15's suites AT their merge commits. It did
independently re-run `uv run ruff check .` and `uv run pytest -q` on a
branch cut from 275886f (chore/separate-harness-payload, after moving the
harness payload out): ruff clean, 191 passed / 1 skipped -- matching what
275886f's own commit body claims, so the count is corroborated, not just
copied.

## Now

**UPDATE 2026-09-05: RAGAS DROPPED, BY HUMAN DECISION, NOT AN ESCALATION
ANSWER.** G1/relevancy now run on `evaluation.scoring.LLMJudgeScorer`, our
own model judging its own answer through `prompts/eval-judge`, not RAGAS.
`ragas` is removed from `pyproject.toml`; `uv lock` dropped 29 packages.
Full change-request row (what the signed doc said, why it can't hold, what
replaces it, what is lost): DECISIONS.md, 2026-09-05. G2/G3 stay
deterministic, no model involved. Gate: `uv run ruff check .` exit 0,
`uv run pytest` **635 passed / 2 skipped** on this branch.

**ST-32 EVALUATION RUNNER BUILT, 2026-09-05, ON BRANCH
`feat/S3-ST-32-evaluation-runner` (NOT MERGED).** `evaluation/{golden,capture,
scoring,runner}.py` + `scripts/run_evaluation.py`: loads the golden set, runs
each question through the real product via `ui.ports` (the decided
composition root), captures the sections the writer actually read by reusing
`ui.runs.Run.observed`, judges G2/G3 directly, writes the dated JSON report
plus `eval_run`/`eval_result` rows in one call. Proven on a fake `Scorer`
and, for the judge itself, on `tests.fake_chat.ScriptedChat` -- 10 tests,
happy + failure paths (`tests/unit/test_evaluation_runner.py`).

**[SUPERSEDED by the update at the top of this section, 2026-09-05: the
human decided to drop RAGAS rather than wait on it. The paragraph below is
kept for the evidence it recorded, not as the current state.]**

RAGAS 0.4.3 CANNOT BE IMPORTED, escalated rather than coded around.
Verified by running it, not from docs: `import ragas` raises
`ModuleNotFoundError` against this project's pinned `langchain-community`
(0.4.2) -- `ragas/llms/base.py` imports `langchain_community.chat_models.
vertexai.ChatVertexAI`, which that version no longer has (upstream bug,
ragas issues #2741/#2745/#2753). Past that, ragas 0.4.x's current metric API
wants a provider-native client (`litellm` for Gemini, undeclared) rather than
`agent.chat.ChatModel`, and `AnswerRelevancy` needs an embeddings client
nothing has verified against the local e5 embedder. `build_ragas_scorer()`
raises `ScorerUnavailableError` naming all three, mirroring `ChatUnavailable
Error`'s pattern -- see `evaluation/scoring.py` and DECISIONS.md 2026-09-05
for the numbered options -- **this is the paragraph the update above
supersedes; RAGAS is now removed rather than waited on, see there.**

ALSO FOUND, mid-session: `feat/S2-ST-28-workspaces-screen` was being built
concurrently in the SAME working directory, uncommitted, and briefly moved
this branch's own checkout out from under this story. No work was lost
(git worktree used to finish this branch in isolation) and nothing of
ST-28's was touched, staged, or reverted. ST-28 has since finished and
committed on its own branch.

Gate on this branch, final: `uv run ruff check .` exit 0; `uv run pytest`
**635 passed / 2 skipped**, up from 625 on main -- 10 new tests. `ragas`
removed from `pyproject.toml`, `uv lock` dropped 29 packages, `uv sync
--frozen` reinstalls clean without it. `.env.example` updated for the one
new setting (`EVAL_GROUNDEDNESS_THRESHOLD`); `test_every_setting_is_
documented_in_env_example` was red before that fix and green after.

**Note on ownership:** BUILD-PLAN lists ST-32 as YL's row; this session
built it on MB's clone at the orchestrator's explicit direction. Recorded
per the team rule that the recorded owner and actual author can drift.

**THE ST-21 AND ST-23 REVIEWS ARE PAID, 2026-09-03. ST-21 CAME BACK CLEAN;
ST-23 DID NOT.** That is two of the four unpaid reviews closed, and the
remaining list is now **ST-19 and ST-29's in-scope halves** (see the entry
below -- their out-of-scope rows are done).

**ST-21: NO DEFECTS FOUND, and the negative is worth recording rather than
left as silence.** What was read: `graph.py`, `nodes.py`, `state.py`,
`trace.py`, `ports.py`. Its risky parts hold up under a hostile read -- the
F-04 ceiling is read from config on EVERY decision and compared against the
trace's own reword count, so the number that stops the loop and the number
on the bubble are one number, never two; `route_after_parents` floors at zero
readable sections and routes to a refusal rather than citing documents
nothing read; `_queries` caps the WIDTH of a split, which the retry ceiling
does not cover; `ask` validates question length in-process, because ADR-13
means the openapi bound would otherwise hold for HTTP callers only. Much of
this was already hardened by ST-24's two passes, which is the honest reason
the story reads clean now and might not have in August.

**ST-23 FINDING 1, FIXED: USER INPUT WAS REACHING THE PROMPT TEMPLATE.**
`Prompt.render` substituted one variable at a time with `str.replace`, so
each result was rescanned by the next substitution -- and `question` is
filled before `passages`. A user typing the literal text `{{PASSAGES}}` into
the chat box had the WHOLE PASSAGE BLOCK expanded into their own question
slot. Proven against the REAL relevance-grader prompt rather than a fixture:
the canary appeared twice. The function also promised "every variable filled
and none left", which was false in both directions and checked nowhere.

Note what kind of miss this was: `agent/prompts.py` opens with "TWO GUARDS,
and both exist because the failure they catch is silent". Both guards run
BEFORE substitution and compare NAMES only. This was a third silent failure
in the one module written to be paranoid about silent failures.

FIXED with a single-pass `_VARIABLE.sub` and a FUNCTION replacement -- a
function rather than a string because `re.sub` processes backslashes in a
string replacement, and corpus text is full of things a template engine must
never interpret. Proven the way this project requires: **the test was written
first and watched failing on the real prompt (exit 1), then watched passing.**

**ST-23 FINDING 2, PARKED AND VISIBLE: A JOB ASSIGNED TO ST-23 WAS NEVER
DONE.** `nodes.py:_merge_hits` says in writing that honest multi-query fusion
"is retrieval work and belongs to ST-23". ST-23 shipped `retrieval.py` as a
thin wrapper with no fusion and closed without doing it OR re-parking it.
Invisible today only because `ui/ports.py` stubs `rewrite` to one query, so
query order IS score order. **The day ST-22 lands, three things start at
once:** passages arrive in arbitrary query order, nothing trims the list, and
the writer receives up to (queries x `retrieval_depth_k`) sections uncapped.
ST-32 then scores retrieval against that. Not improvised here -- picking a
fusion rule is retrieval design and belongs with whoever implements the
split. Parked as a comment in `_merge_hits` naming the rule and the story, so
whoever lands ST-22 reads it first.

TWO SMALLER NOTES, recorded and not fixed: the grader's `_DECORATION` pattern
does not fold zero-width characters, though ST-24's near-identical decline
parser was explicitly hardened for exactly that after a BOM-marked reply was
misread -- here it fails LOUDLY, which is the safe direction, so it is an
inconsistency rather than a danger. And `ChatUnavailableError`'s docstring
says "raised at BUILD time, not at call time" while `_LangChainChat.complete`
raises it at call time for a non-text response; `app.py:412` catches it around
the build path with a comment saying "the model could not even be built". Same
shape as the hyphen comment ST-23 itself recorded: a docstring describing
behaviour the code does not have.

SCOPE, STATED PRECISELY: this read the SOURCE of both stories -- `graph.py`,
`nodes.py`, `state.py`, `trace.py`, `ports.py`, `prompts.py`, `grading.py`,
`retrieval.py`, `chat.py` -- and NOT their test files, of which ST-21 alone
ships 1,099 lines. A test suite can be wrong in ways source review cannot see
(this project has shipped six fixtures too small for their own property), so
that half is still owed by anyone who wants to call these reviews complete.

ON RULE 5's "PARTNER'S EYES", and the honest version rather than the
convenient one: ST-21 and ST-23 are YL's rows in BUILD-PLAN, and this ran on
MB's clone (git identity `meriem-mb`). **If the human driving was MB, this is
a genuine partner review** -- the first this session, since the golden-set
work was MB reviewing MB. If YL was sitting at this machine, it is not. That
cannot be settled from inside the session, so it is written as a condition
rather than claimed as a fact.

**THE ST-19 / ST-29 OUT-OF-SCOPE REVIEW IS PAID, 2026-09-03, AND IT FOUND A
FALSE REFUSAL IN THE FROZEN SET.** This file's own instruction for those two
unpaid reviews was "the rows to read are the fifteen out-of-scope questions,
because those are what G2 is graded on". That is exactly what was read, and
**that is exactly the scope of this entry** -- see the honesty note at the end
of it before writing either story off.

**`g-out-008` WAS A FALSE REFUSAL, not a borderline one.** It asked "Combien de
temps dure le conge parental apres le conge de maternite ?" and was graded as a
question the product must REFUSE. Labour code **article 156 answers it under
another name, with durations**: the mother may extend the contract suspension
to ninety days at most, then take, in agreement with her employer, **one year of
unpaid leave to raise her child**. The row's old reference answer asserted the
opposite in words -- "aucun conge parental ; la notion n'y figure pas" -- and
its own note called it "le plus dur du lot", so the risk was FELT AT THE TIME
AND NOT RESOLVED. Scored as written it would have cost G2 a point for a CORRECT
answer, which is precisely the failure the `perte d'emploi` candidate was
dropped to avoid three days earlier.

REPLACED with "Un salarie peut-il prendre un conge pour creer son entreprise ?",
which keeps the slot's purpose -- a leave that does not exist, surrounded by
leaves that do. Absence established BY READING, not by the probe: the corpus's
leaves are enumerated (annual, maternity + art. 156, birth 269, family events
274, job-search 48-49, council 277, union 419) and none is discretionary, and
`convenance personnelle`, `conge exceptionnel` and `conge sans traitement` are
absent from all three files.

**THE FREEZE DID NOT NEED A VERSION BUMP FOR THIS, and that is the mechanism
working rather than a hole in it.** `FROZEN_IDS` and `FROZEN_TOTALS` pin the ids
and the counts; both are unchanged, because one question's WORDING changed. The
README has said from the start that wording is held by review and git history,
and this is that review. Anyone reading the freeze as "the set cannot change"
should read the test's docstring, which says the narrower true thing.

THREE MORE ROWS ARE ARGUABLE and are now listed in the README beside
`g-out-005`, `g-out-019` and `g-out-020`, taking that table to **six of the
twenty**:
- `g-out-006` (CMR for civil servants): dahir **article 3 names them
  explicitly**, as excluded -- "ne sont pas assujettis au present regime : les
  fonctionnaires titulaires de l'Etat". A sourced answer saying so is right.
- `g-out-009` (`prud'hommes`): the institution is French and absent, but the
  code has 24 mentions of `tribunal` and a whole dispute chapter, so the corpus
  can say where a dispute DOES go.
- `g-out-004` (auto-entrepreneur): weaker, but dahir articles 2 and 3 list who
  is and is not subject, so an answer can be reasoned from the lists.

Six of twenty is a lot and it is written down rather than averaged away. G2
wants 20 of 20, so if several are answered WELL the gate fails on questions
rather than on the product. Replacing them was rejected: near-misses are the
whole value of the out-of-scope half and the same argument repeated would empty
it. What the list buys is that ST-36 starts from evidence instead of surprise.

CLEAN, AND CHECKED RATHER THAN ASSUMED -- worth recording because a review that
only reports faults teaches nobody where the bar is: `g-out-003` (no
mutual-termination device; the `d'un commun accord` hits are about absences,
art. 50, and arbitration, art. 568), `g-out-013` (all 8 `concurrence` hits mean
economic competitiveness or "a concurrence de", i.e. "up to the amount of"),
plus `g-out-001`, `002`, `010`, `011`, `012`, `014`, `015`. Every probe ran
through `conversion.convert_file` with a control probe found first.

**THE HONESTY NOTE, so neither story gets written off on this entry: ST-19 AND
ST-29 ARE ONLY PARTLY REVIEWED.** What was read is the fifteen out-of-scope
rows. What was NOT read is their thirty in-scope rows, their reference answers,
or `tests/unit/test_golden_set.py` as those two stories left it. **They stay on
the unpaid-review list**, with the highest-value part now done. And the same
qualification as ST-35's review applies: this ran on MB's clone, on MB's
artifact, so rule 5 is met in form and not in substance.

**ST-35 GOLDEN SET COMPLETE AND FROZEN, MERGED as `617c972` (PR #74, squash),
2026-09-03, branch deleted on merge. REVIEWED first -- both passes, findings
fixed before the merge (see the review section below, and note that the freeze
described in this paragraph did not work as written until that pass fixed
it).** Batch 3
adds 10 in-scope and 5 out-of-scope rows, taking the set to **40 + 20**,
which is PRD F-08 exactly and the denominator G2 is written against.
`uv run python scripts/golden_grounding.py` -> **"OK: 60 rows grounded
(40 in scope, 20 out)"**, exit 0, control probe found in all three files
first. 19 mutations injected one at a time, all 19 killed.

GATE STEPS 1-3 BY HAND ON THE BRANCH, in gate.yml order, exit codes read
from `$?` rather than inferred from the last line: `uv sync --frozen` clean
(170 packages), `uv run ruff check .` **exit 0**, `uv run pytest` **622
passed / 2 skipped** in 230.55s, up from 621 on main -- which is exactly the
one test this story adds. **STEP 4, GITLEAKS, WAS NOT RUN.** It is still not
installed on THIS machine, re-checked today against PATH and
`~/AppData/Local/Microsoft/WinGet/Links/`, which does not exist here. CI
remains the only place that step executes for MB. Do not write "all four
steps"; YL's machine can make that claim and this one cannot.

THE TEN IN-SCOPE ROWS ARE 6 LABOUR CODE / 2 CNSS DAHIR / 2 CLEISS, putting
the 40 at 26 / 8 / 6. Every reference answer was written from article text
pulled through the product's own `conversion.convert_file`, which is the
ST-19 rule and the reason a golden row measures the corpus the product
actually sees rather than a second PDF reader's version of it.

**THE ENTRY TO READ IF YOU READ ONE: A QUESTION THAT LOOKED PERFECT WAS
ANSWERABLE, AND THE SCRIPT IS WHAT SAID SO.** "Ai-je droit a une indemnite
pour perte d'emploi ?" is the ideal-shaped refusal -- unemployment insurance
is not what a 1972 dahir or a 2011 labour code is about. The probe came back
**present three times** (`code=2, cleiss=1`): the labour code grants
`l'indemnite de perte d'emploi` twice, and the CLEISS guide carries a whole
paragraph on the scheme WITH ITS CONTRIBUTION RATES. Scored as out-of-scope
it would have made G2 read 19 refusals out of 20 -- a release gate failing
for a reason nobody reading the report could have found. The candidates were
probed BEFORE any row was drafted, which is why it cost ten minutes rather
than a review round.

**AND THE HARDER HALF, WHICH THE SCRIPT PASSED AND A HUMAN STILL HAD TO
CATCH.** "Un pere a-t-il droit a un conge de paternite ?" -- the term appears
in NONE of the three documents, so the checker says out-of-scope and is
correct about the term. Dropped anyway: the corpus answers it under another
name, since `g-in-015` is the father's three-day `conge de naissance`, so a
refusal would have been the wrong answer. **Term-absence is necessary and not
sufficient.** The checker sees only the string it was handed; whether the
corpus can answer a question under ANY name is a judgement no probe can make.
Mechanising it was considered and dropped -- it amounts to asking whether the
corpus answers a question, which is the product, so the check would be graded
by the thing it exists to grade. It is a recorded REVIEW step instead, in
`evaluation/golden/README.md` beside the rows.

THE FREEZE IS TWO MECHANISMS AND ONE HONEST GAP:
- the running total moved from `<=` to `==`. A cap was the only honest
  assertion while the set was being BUILT -- 23 rows and 45 rows both had to
  pass -- and it is the wrong one now, because it passes just as happily on
  39 in-scope rows as on 40.
- `FROZEN_IDS` pins the sixty ids as a CONTIGUOUS run, gated on a new
  `GOLDEN_SET_VERSION`, so a row added, dropped or renumbered fails loudly.
  **[CORRECTED 2026-09-03: the "gated on" half of that sentence was FALSE. The
  gate was `assert GOLDEN_SET_VERSION == "v1"`, a constant compared to a
  literal in the same file, and adding a 41st row passed 13 of 13 with the
  version untouched. `FROZEN_TOTALS` replaces it. Left standing rather than
  rewritten, because a claim this file made and the review disproved is worth
  more visible than tidy.]**
- **IT DOES NOT PIN THE WORDING**, and the test's own docstring says so
  rather than letting a green be read as more than it is. A byte hash would
  have covered wording and was refused on evidence: this repo is checked out
  on two machines and git rewrites line endings on checkout -- the commit
  adding `batch3.jsonl` printed "LF will be replaced by CRLF" -- so a hash
  would go red on one clone for a reason having nothing to do with the golden
  set, and a check that cries wolf gets deleted. A normalised hash was
  refused too, for the reason already recorded on this project: a drift check
  that compares against a stored constant locks whatever bytes it was first
  shown, and its green then says nothing about whether it is aimed at the
  right side.

THREE NEW TRAPS, all of a kind only a SOURCED-answer product can fail:
- `g-in-035` + `g-in-037`: one sick day owes the EMPLOYER notice within 48
  hours (code art. 271) and the CNSS a form within 30 days (dahir art. 33).
  One event, two deadlines, two documents; the right number from the wrong
  file is still a wrong citation.
- the two article 33s are now BOTH rows rather than a note on one. Until this
  batch the collision was described; now it is graded.
- "54 jours de cotisation" appears three times with three different windows
  -- 6 months for AMO, 10 for maternity benefit, 6 for early retirement --
  for three different benefits, so the number alone does not identify the
  entitlement.

**THE RULE-5 REVIEW PASS IS PAID, 2026-09-03, AND IT FOUND THE FREEZE DID NOT
FREEZE.** Both passes ran on the branch -- a COLD verifier read and the briefed
rule-5 pass -- and between them they returned 2 blocking findings, 6 worth
fixing and 4 notes on a tree whose whole gate was green. Eight stories running
now where a post-green pass found something the suite could not. All are fixed
on this branch.

ONE HONEST QUALIFICATION ON THE WORD "PAID", because rule 5 is about WHOSE eyes
and this file has recorded that deviation three times already: the pass ran on
**MB's clone** (git identity `meriem-mb`; gitleaks absent, which the header
says is MB's machine and not YL's). ST-35 is MB's own story. So the review
found real defects and fixed them, but if YL did not run it, this satisfies
rule 5 in FORM and not in SUBSTANCE -- the partner's eyes are the whole point,
and a story reviewed on the author's own machine is not that. Recorded this way
rather than written up as a clean pass, and whoever merges should decide
whether it still wants YL's read. The unpaid-review list above (ST-21, ST-23,
ST-19, ST-29) is unchanged by today either way.

**THE ONE TO READ: THE FREEZE THIS STORY EXISTS TO DELIVER COULD NOT FAIL.**
`assert GOLDEN_SET_VERSION == "v1"` compared a constant to a literal nine lines
above it in the same module, and `FROZEN_IDS` was DERIVED from
`FINAL_TOTAL_*`, so it was not an independent record either. The whole escape
hatch was two number edits: `FINAL_TOTAL_IN_SCOPE` to 41, the `batch3.jsonl`
row in `EXPECTED_COUNTS` to `(11, 5)`, add the row. The review did not reason
about this, it RAN it in an isolated copy and watched **13 of 13 pass with the
version still reading "v1"**. Three artifacts said otherwise -- the test's own
comment ("the two are checked against each other so neither can move alone"),
the README, and a DECISIONS row claiming "frozen at v1 by two mechanisms".
The exit gate "later edits need a new version" was being reported as met by a
check that could never go red.

Note what this means about the 19 mutations this story reported killed: the
list was drawn up by the person who wrote the code, and the one realistic
post-freeze edit was not on it. A mutation battery is only as wide as the list
you write for it -- the same sentence ST-24 wrote here after 31 killed
mutations missed two real defects. That is now twice.

FIXED: `FROZEN_TOTALS = {"v1": (40, 20)}`, a literal the live totals are
checked against. **Proven by deliberate violation, in that order:** the 41st-row
edit now fails on `test_the_totals_still_match_the_version_they_were_frozen_under`
(exit 1), and the tree returns to green once restored (14 passed, exit 0). The
residual limit is written into the docstring and the README rather than left to
be discovered -- editing the `"v1"` row itself is still possible, but that is
tampering visible in any diff, not the tuning-session drift the table stops.

**THE SECOND BLOCKING FINDING WAS OVERTURNED, and how it was overturned is the
part worth keeping.** The cold pass called `g-out-020` (the disability hiring
quota) a mislabelled refusal, because the labour code carries a whole chapter
on disabled workers. The briefed pass disagreed, having read that chapter:
articles 166 to 171 impose real duties, and there is still **no hiring quota
under any wording** -- `quota` 0 hits, `obligation d'emploi` 0, `tenu
d'employer` 0, no effectif proportion. Re-verified here independently through
`conversion.convert_file` before anything was edited. So the refusal STANDS and
what was wrong was the row's reasoning: it rested on one missing word, which is
the exact error that got "conge de paternite" dropped. Reference answer and
note rewritten; the row is now listed as arguable instead of replaced.

TWO PASSES DISAGREED AND THE DISAGREEMENT WAS THE VALUE. Had only the cold pass
run, a correct row would have been thrown away. Had only the briefed pass run,
the freeze defect would still have been caught but the arguable-row risk would
not have been written down. Neither pass alone was sufficient, which is the
first hard evidence on this project for running both rather than one.

ALSO FIXED, all re-counted against the corpus on 2026-09-03 rather than taken
from the reviews:
- "54 jours de cotisation appears three times with three different windows
  (6/10/6)" was wrong twice: **four** occurrences in the CLEISS guide alone, on
  **two** distinct windows (6, 6, 10, 6). It had already been copied into the
  README, this file and CHANGELOG-AI.
- `g-in-036`'s "huit durees" in labour code article 274 is **six**.
- `g-out-016` claimed the pension at 60 and the retraite anticipee BOTH require
  "cessation de toute activite salariee". The corpus says that only for the
  pension at 60; the anticipee paragraph asks for the employer's agreement,
  3 240 days and 54 days over 6 months, with no cessation clause.
- the README claimed two article-number collisions at batch 2 counting the two
  article 33s, while the batch-3 section announced the same collision as new.
  Both could not be true: at batch 2 only the code's article 33 was a row.
- an undocumented **third** collision, which nobody had noticed: `g-in-032` is
  labour code article 37, `g-in-025` is dahir article 37.
- `g-out-019` (titres-restaurant) joins `g-out-005` and `g-out-020` in a
  three-row arguable-rows table. The README had said `g-out-005` was "the set's
  one arguable row" and that "a second one would have been a choice, not an
  accident"; batch 3 shipped two more.
- the paternity write-up said `conge de paternite` appears nowhere. True of the
  phrase; the WORD `paternite` appears once, in article 269 -- the very article
  that answers the question.

GATE STEPS 1-3 RE-RUN BY HAND AFTER EVERY FIX, in gate.yml order, exit codes
read from `$?`: `uv sync --frozen` clean (170 packages), `uv run ruff check .`
**exit 0**, `uv run pytest` **623 passed / 2 skipped** in 179.20s -- up from 622
on the branch, which is exactly the one test the freeze fix adds. Plus
`uv run python scripts/golden_grounding.py` -> **"OK: 60 rows grounded (40 in
scope, 20 out)"**, exit 0, control probe found first.

**STEP 4, GITLEAKS, WAS NOT RUN.** Re-checked today by three routes on this
machine: not on PATH, `~/AppData/Local/Microsoft/WinGet/Links/` does not exist,
and `gitleaks version` is "command not found". CI remains the only place that
step executes for this clone. Do not write "all four steps".

STILL OWED before merge: nothing on review. Re-stamp this file's header at
merge time, not now -- the header still names c70c654 on main and this branch
is not merged.

Previous:
**ST-19 GOLDEN SET BATCH 1 IS MERGED as `7c28d6b` (PR #67, squash),
2026-08-30, and ST-29 BATCH 2 IS ALSO MERGED, as `9da0c56` (PR #70).**
[CORRECTED 2026-09-03 by the ST-35 review: this block previously read
"Previous, and still the state of main" above a paragraph saying batch 2 was
NOT MERGED. It merged before this branch existed -- `batch2.jsonl` is on main
-- so the stamp was stale in the one file the project tells everyone to read
first.] Running total at that point **30 in-scope + 15 out-of-scope**, which is
ST-29's exit gate exactly. `uv run python scripts/golden_grounding.py` ->
"OK: 45 rows grounded (30 in scope, 15 out)". 6 new mutations, all 6 killed.

**MERGED WITHOUT THE RULE-5 PARTNER REVIEW, at the human's explicit
instruction ("push all changes to github and merge them").** Same shape as
the ST-17 deviation of 2026-08-23 and the ST-21 one of 2026-08-26, and it
creates the same debt, so it is recorded here rather than absorbed. What
#67 DID have before merging: gate steps 1-3 by hand on the branch and again
after main was merged into it, CI `verify` green with all four steps
including the secret scan this machine cannot run, 14 mutations all killed,
and the grounding script re-run on the real corpus. What it did NOT have is
YL's eyes on the eight out-of-scope questions, which are the rows that
decide whether G2 measures anything. **ST-19 and ST-29 now join ST-21 and
ST-23 on the unpaid-review list.**

**THE BRANCH DEVIATION, recorded rather than absorbed:** ST-29's branch was
cut from ST-19's branch, not from latest main, because batch 2 is meaningless
without the schema and tests that existed only there. That breaks CLAUDE.md
rule 2. It cost a three-file conflict when main moved underneath it (YL's
#68 and #69 landed while #67 sat open), resolved by merging main INTO the
branch per the 2026-07-28 decision, never by rebasing.

**WHAT LANDED FROM YL WHILE THIS WORK WAS OPEN, and one line of it points
straight at the golden set:** #68 fixed the ST-18 spike's article matcher,
which was a bare substring test -- "14" hit "Article 143", and both "72" and
"184" hit "dahir n 1-72-184", the NAME OF ANOTHER DOCUMENT. Its journal line
calls `traces.json` "the file ST-19's golden set is meant to be built from".
**It was not.** Every reference answer in batches 1 and 2 was written from
the article text pulled out of the PDF through `conversion.convert_file`,
and `scripts/golden_grounding.py` re-reads the documents rather than trusting
any intermediate file. That was luck as much as design, and the safer route
is now the recorded one.

**AND YL'S ROOT-CAUSE FINDING APPLIES TO THIS WORK TOO, so it is repeated
here rather than left in his section:** `testpaths = ["tests"]` in
pyproject.toml puts `scripts/` outside every check. `scripts/golden_grounding.py`
is 1 more file in that blind spot -- it has been RUN and its output quoted
with a date, but nothing asserts it, so a change to it would break silently.
Its control probe is the only thing standing in for a test. Owner MB,
alongside the ST-07/ST-18 script findings.

WHAT BATCH 2 IS FOR, beyond the count. Batch 1 was 12 labour code / 2 dahir /
1 CLEISS, which would have left both CNSS documents nearly ungraded. Batch 2
is 8 / 4 / 3, putting the 30 in-scope rows at 20 / 6 / 4 -- roughly how the
three documents compare in size. The three-document rule is now held PER
BATCH rather than over the whole set, because a total would let batch 3 drift
entirely onto the labour code on the strength of batch 1.

FIVE ROWS ARE PAIRED WITH A BATCH-1 ROW, and the pair is the test: employer's
gross misconduct (art. 40) against the employee's (art. 39), consecutive
articles and opposite parties; the severance SCALE (art. 53) against WHO
QUALIFIES for it (art. 52); the pension AMOUNT (dahir 55) against the pension
CONDITIONS (dahir 53); and the two different fourteen-week rules -- code art.
152 is the LENGTH OF LEAVE, dahir art. 37 is the LENGTH OF PAYMENT, same
number, different documents.

TWO ARTICLE-NUMBER COLLISIONS ARE NOW DELIBERATE: code art. 53 vs dahir art.
53, and code art. 33 vs dahir art. 33. A citation that gets the number right
and the document wrong is still wrong, and F-03 makes the source line the
product's contract with the user.

ONE QUESTION WAS DROPPED AND THE REASON IS WORTH KEEPING. "How many months of
notice must a manager give?" is the ideal out-of-scope question -- article 43
states the obligation and hands the DURATION to a decree the corpus does not
hold, so the corpus names the topic and cannot answer it. It is not in the
set, because an out-of-scope row must name a term absent from every document
and there is none here: `préavis` appears 40 times. Bending that rule would
cost the out-of-scope half the only thing that makes it falsifiable. Recorded
in the README instead.

THE COUNT CHECK IS NOW A TABLE, NOT A TEST PER BATCH, plus a companion test
that refuses any golden file the table does not list. **ST-35 adds one row.**
The companion is the half that matters and it was written by asking what the
table cannot see: without it, batch 3 could arrive unlisted and every count
test would go on passing while grading a set nobody counted. There is also a
cap at 40 + 20 -- G2 grades "20 refusals out of 20", so a 21st out-of-scope
question makes the gate's own denominator a lie.

**THE FRENCH-LANGUAGE CHECK HAS NOW FAILED TWICE, ON TWO DESIGNS, AND WAS
RIGHT BOTH TIMES.** Version 1 was a hand-written list of accented letters and
missed "À partir de quel âge" (ST-19). Version 2 was "does NFKD decomposition
change the string" and rejected `g-out-009`, "Comment saisir le conseil de
prud'hommes contre mon employeur ?" -- flawless French with not one accented
character in it. Version 3 is an accent OR two distinct French function
words, failing only when both miss. The lesson is not about accents: both
earlier versions were PROXIES that held on the rows written so far and broke
the moment a row arrived that was correct in a way the proxy had not
imagined. The marker list deliberately excludes English look-alikes, because
a marker an English sentence can contain makes the check weaker rather than
more generous.

Previous, describing #67 while it was still open. Kept because its evidence
is unchanged by the merge:
**ST-19 GOLDEN SET BATCH 1 WAS BUILT on branch
`feat/S1-ST-19-golden-set-batch-1`, then NOT MERGED and NOT REVIEWED.** 15
in-scope + 8 out-of-scope French questions in `evaluation/golden/batch1.jsonl`.
Gate steps 1-3 run by hand on the branch in gate.yml order: `uv sync
--frozen` clean (170 packages), `uv run ruff check .` exit 0, `uv run
pytest` **539 passed / 2 skipped** in 150.80s, up from 529 on main. Step 4,
gitleaks, NOT RUN -- still not installed on this machine, re-checked today
against PATH and the WinGet Links folder, both empty. CI remains the only
place that step executes. Do not write "all four steps".

THIS IS THE FIRST ARTIFACT OF THE EVALUATION HALF. Nothing in
`evaluation/` existed before it. The only golden-set-shaped file in the
repo was `docs/evals/golden.jsonl`, which holds ONE placeholder row reading
`<representative user input>` -- it is the prompt-registry skill's seed
file, nothing references it, and it is NOT this. Left alone; a story that
owns it can decide.

WHAT MAKES THE 15 IN-SCOPE ROWS WORTH ANYTHING: every reference answer was
written from the article text pulled out of the real PDF through the
product's OWN `conversion.convert_file`, not from memory and not from a
second PDF reader. Using a different reader here would let the check pass
on text the product never sees. Twelve rows on the labour code (articles
14, 39, 43, 53, 72, 143, 152, 184, 201, 205, 231, 232), two on the CNSS
dahir (35, 53), one on the CLEISS guide. A test asserts all three HR
documents are cited, because fifteen questions all drawn from the labour
code would leave both CNSS documents ungraded and retrieval could be broken
for both without one golden question noticing -- the fixture-too-small-for-
its-own-property shape, now on its sixth appearance in this project.

**THE ONE TO READ IF YOU READ NOTHING ELSE: A BYTE-WISE GREP CALLED A WORD
ABSENT THAT APPEARS FORTY TIMES.** The first sweep for out-of-scope topics
ran `grep -E "pr.avis"`. Outside a UTF-8 locale `.` matches one BYTE and
`é` is two, so the pattern cannot match `préavis`, and grep reported ZERO
in a 358 KB document containing FORTY. Four of the eight out-of-scope
questions were being drafted on that zero. Caught because the number looked
wrong, not by any check.

THE FIX IS NOT BETTER GREP FLAGS. `scripts/golden_grounding.py` now refuses
to report ANY absence until a control probe it knows is present comes back
found -- proven by pointing the control at a string in no document and
watching all three files report "the matcher is blind; every absent result
below is meaningless". This project's absence protocol says a blocked route
is UNVERIFIED, never a negative finding; a route that cannot SEE returns
exactly what a true absence returns, and that case was not covered. All 8
out-of-scope terms were then re-verified through the folding route, which
also folds the three DIFFERENT apostrophes the three PDFs use (U+02BC in
the dahir, U+2019 in the CLEISS guide, plain in the labour code).

TWO CHECKS, SPLIT ON PURPOSE, and the split is about `data/` being
git-ignored:
- `tests/unit/test_golden_set.py` checks the SHAPE (10 tests, no corpus,
  runs in the gate). A corpus-reading pytest would pass here, SKIP on CI
  and prove nothing anywhere, and a check that skips itself is untested.
- `scripts/golden_grounding.py` checks whether the claims are TRUE, run by
  hand: **"OK: 23 rows grounded (15 in scope, 8 out)"**, 2026-08-30.

14 MUTATIONS INJECTED ONE AT A TIME, ALL 14 KILLED, on a committed green
checkpoint first -- the rule ST-21 wrote down and ST-24 then repeated
anyway. Sharpest three: an out-of-scope row given a source file (the
assertion that protects G2); an out-of-scope probe pointed at `préavis`,
which failed with "IS in the corpus (...=40)" and is the exact defect the
byte-grep hid; and the control probe itself made blind.

ONE TEST FAILED ON ITS FIRST RUN AND WAS RIGHT TO. The French-language
check listed accented letters `éèêàùôûçîï`; `g-in-008` opens "À partir de
quel âge" and carries neither. Replaced with "does NFKD decomposition
change the string", which needs no list to maintain.

TWO THINGS RECORDED RATHER THAN SMOOTHED OVER, both in
`evaluation/golden/README.md` beside the rows they affect:
- `g-in-015` cites the CLEISS guide's 692,30 DH birth-leave ceiling. The
  guide is undated and its contribution table is headed 1 January 2014. The
  reference answer is what the CORPUS says, which is correct for what F-08
  measures -- RAGAS faithfulness scores an answer against the passages it
  was given -- but nobody may quote that figure in the report as current
  Moroccan practice.
- `g-out-005` ("does the 35-hour week apply?") is the arguable one: the
  corpus has A legal working week, 44 hours, just not the one asked about.
  Flagged now so that if it scores badly at ST-36 the argument is about the
  question, not about retrieval.

STILL OWED before merge, and this story has no exemption: the rule-5 review
pass. Re-stamp this file's header at merge time, not now.

Previous, and still the state of main:
**THE ST-12 REVIEW DEBT IS PAID. MERGED as `1ae78c1` (PR #65, squash),
2026-08-30**, and `f4cf208` (PR #64) landed on top of it the same morning.
Both branches were deleted on merge. Gate re-run on main after BOTH:
`uv run ruff check .` exit 0, `uv run pytest` **529 passed / 2 skipped**.
PR #64 was rebuilt on the new main and re-verified BEFORE it merged rather
than trusting a green earned against an older base -- its CI ran a second
time (1m29s) on the updated branch.

WHAT PR #65 ACTUALLY FIXED, because the title understates it: **the report
was lying about the product.** An operator narrows
`supported_document_extensions`; a file already ingested under the old list
falls outside it but keeps its document row, its live vectors and its
parent files. Sync wrote a `Skipped` report row and did nothing else -- so
answers kept citing a file the report called Skipped. PR #40 had stopped
that file being reported Removed *as well as* Skipped; it never stopped it
ANSWERING. The new `_skip_unsupported` deletes both derived stores and
writes the row, deletion first, mirroring `_remove` for the same reason.

WHAT PR #64 CLOSED: ST-02's own exit criterion, "every config var
documented in `.env.example`", which nothing had ever enforced because
`.env.example` is a text file no code reads. It had drifted to TEN
undocumented settings. Three checks now hold it in BOTH directions, and
the second direction is the one that rots quietly -- pydantic-settings
IGNORES an unknown environment variable, so a stale key is something you
can fill in, restart, and watch do nothing with no error anywhere. A
fourth check refuses a byte-order mark in the template, which was already
on main and harmless only by luck.

WHAT NEITHER OF THEM TOUCHED, so it is not quietly assumed closed: the
`.env` blocker below. Both PRs fix the TRACKED end. A `.env` is git-ignored
and holds a secret, so no merge can reach it, and MB's machine still holds
an invalid key and a retired model name.

Previous, and still the state of the product:
ST-24 ANSWER NODE + SOURCE CONTRACT + HONEST REFUSAL **MERGED as c511bc8**
(PR #57, squash), 2026-08-28, followed by `2ebb74d` (PR #59, the decline
parser's case rule). The whole gate was run by hand in gate.yml order on
the branch AND RE-RUN ON MAIN after each merge: `uv sync --frozen` clean
(170 packages), `uv run ruff check .` exit 0, `uv run pytest` **522 passed
/ 2 skipped** on main (451 at the branch point), `gitleaks detect` exit 0
"no leaks found". CI `verify` green on both PRs. 31 mutations injected one
at a time, all 31 killed.

IT HAD BOTH REVIEW PASSES BEFORE MERGE, which no story on this project had
managed before: a COLD verifier read and the RULE-5 pass. The rule-5 pass
said DO NOT APPROVE, its blocking finding was fixed, and it then approved
on re-review. ST-21 and ST-23 are still owed theirs. **ST-12's was PAID on
2026-08-30 (PR #65)** and it found three real defects, so the debt was not
bookkeeping -- see the top of this section.

TWO REVIEW PASSES RAN, and the second one is the entry worth keeping.

THE RULE-5 PASS SAID **DO NOT APPROVE**, and it was right: its blocking
finding was the COLD PASS'S DEFECT SURVIVING ONE ROUND OF FIXING. The
first fix said the prose spelling of the decline must be the whole first
LINE. Still too weak -- a model that names the gap on line one and answers
on line two passes a first-line test and loses its answer:

    Not covered.
    Article 13 sets the trial period at three months.

THE LESSON, which is bigger than the bug: two rounds of review on one
regex, and each version looked obviously right until someone RAN it on a
reply nobody had thought of. Neither defect was visible in the code. Both
lived in the INTERACTION between the code and a sentence the prompt itself
instructs the model to write. That is the argument for cold reading as a
practice rather than a formality, and it is why the parser was finally
rewritten on ONE PRINCIPLE instead of patched a fourth time: an underscore
or a hyphen between the two words never occurs in prose, so those are
verdicts and may carry a trailing note; a SPACE makes it ordinary English,
and ordinary English must be the entire reply. Dropping the token side's
stop list closed three further misses in the same change.

THE DECLINE BRANCH NOW LOGS the discarded reply's first line, and that is
the half to keep even if the parser changes again. It is the branch where
a mistake is PERMANENTLY INVISIBLE: an answer read as a decline is thrown
away, the user is told their documents do not cover the question, and
nothing records what was lost. Two parser versions did exactly that and
BOTH were found by a person reading code, never by the running product.

RECORDED, NOT FIXED, with its own test so it stays deliberate:
`NOT COVERED - rien ici` -- the SPACED spelling with a trailing note -- is
read as an ANSWER. It cannot be told apart from `Not covered: overtime
rates. Article 13 sets the trial period at three months.`, a correct
answer on one line, and losing that is the worse error.

THE COLD VERIFIER PASS, which ran first, found 2 blocking, 4 worth fixing
and 6 notes; all six of the first two categories are closed. Its first
blocking finding is the one the rule-5 pass then had to finish:

**A CORRECT ANSWER WAS BEING THROWN AWAY, and the branch's own prompt is
what caused it.** The prompt instructs the model: "if they answer part of
the question, answer that part and state plainly which part they do not
cover." A model obeying that in English, naming the gap FIRST, opens with
the words "Not covered" -- and the decline parser read every one of these
as a refusal and discarded the answer:

    Not covered: overtime rates. Article 13 sets the trial period at
    three months.
    Not covered, but Article 13 sets it at three months.
    Not covered - the sections list only the trial period.

So the user's documents held the answer, the model wrote it, and the
product replied that nothing was found and suggested they add the missing
document. The text was kept nowhere and nothing was logged. Note what kind
of defect this is: reading the parser in isolation could never surface it,
because the bug only exists in the INTERACTION between the parser and a
sentence the prompt itself asks for. Fixed by splitting the spellings --
`NOT_COVERED` and `NOT-COVERED` are TOKENS (no sentence produces that
underscore or hyphen by accident) and may carry a trailing note; "not
covered" with a space is prose and must be the whole first line.

**THE F-03 INTEGRATION TEST COULD NOT FAIL.** It asserted that the cited
files were a subset of the files consulted -- in a workspace holding ONE
document, where that is true whatever the code does. Its companion
assertion, "every section label contains 'Article'", was true because
every heading in that one document starts with the word. A second document
is now indexed into the same workspace with a different file name and
headings carrying no article number, and the test runs a CONTROL PROBE in
both directions: the labour question must not cite the CNSS guide, AND the
CNSS question must cite it -- without the second half, the first is
equally true of an index that never worked. Fifth shipped instance of a
fixture too small for its own property, and the first one caught by
somebody other than the author.

Also closed, all reproduced before being fixed:
- a section that loads as BLANK counted as read. `parent_store` only
  checks the `text` field is PRESENT, so a blank one was a successful
  read: the trace said "loaded 2 of 2", the router saw a full mapping, the
  model got a headed block with nothing under it, and the document was
  still printed as a source card. Fixed in `agent/stores.py`, where
  "loaded" is defined, so the trace, the router and the citation cannot
  disagree.
- an empty model completion raised `_spoken`'s "the write_answer port
  returned a blank string" -- accurate about the shape, wrong about the
  culprit, and it sent whoever read it into ST-24's module for a
  provider's safety filter. Now `EmptyAnswerError`, and deliberately NOT a
  decline: a refusal is a claim about the user's documents.
- a literal byte-order mark sat inside a regex character class, invisible
  in an editor and one reformat from being silently deleted.
- the module docstring described the parser two revisions earlier and its
  UNVERIFIED paragraph contradicted the live probe.
- the decline drift check tied the CONSTANT to the prompt file while the
  regex spelled the token a third time; it now also runs the real parser.

FOUR DECORATED DECLINES WERE BEING READ AS ANSWERS, and this is the entry
to keep: found by RUNNING the parser over hand-built edge cases, not by
reading it and not by any test. `NOT_COVERED —` with an em dash, a
bulleted `- NOT_COVERED`, a heading `# NOT_COVERED`, and a byte-order-
marked one all came back as prose. Every one fails in the SAME direction
and it is the dangerous one: the model declined, the graph read an answer,
and the user gets a bubble saying "NOT_COVERED" with source cards under it
and `refusal` false -- which F-08's out-of-scope half scores as a
non-refusal. An em dash is what a model writing fluent prose actually
reaches for, so that row is tolerance the parser needs rather than
padding. Sixth story running where the post-green pass found what the
suite could not.

AND ST-21'S OWN RECORDED LESSON WAS REPEATED INSIDE THIS STORY, written
down rather than quietly fixed. The mutation harness restores with `git
checkout --`, and it was run while that parser fix was still UNCOMMITTED,
so the restore discarded it. ST-21 wrote the rule into this file in almost
these words -- "commit the green checkpoint FIRST, then mutate; `git
checkout --` is then the restore" -- and it was still repeated one story
later. It was cheap only by luck: the test file sat outside the harness's
restore list, so the suite went loudly red instead of quietly green. THE
REAL FIX IS NOT MORE CARE: the harness should refuse to run against a
dirty tree. That guard does not exist. Owner YL, with the `chore/` branch
that also folds ST-23's fake-chat copies.

**SANAD ANSWERS A REAL QUESTION END TO END FOR THE FIRST TIME.** Five of
the eight ports in `agent/ports.py` are now real, and every port on the
ANSWER path is: `retrieve`, `grade`, `reword`, `fetch_parents` and
`write_answer`. The three that remain stubbed -- `summarize`, `clarify`,
`rewrite` -- are ST-25 and ST-22 and are not on the critical path.
`tests/integration/test_ask_sourced_answer.py` is the first test in the
project where nothing on the answer path is a stub: real embedded Qdrant,
real chunking, real parent JSON on disk, real hybrid search, real
answering. Only the two encoders and the chat model are faked, both for
reasons already written down.

THE TWO DECISIONS THAT SHAPE THIS STORY, both in DECISIONS:

1. **ONE TUPLE DOES BOTH JOBS.** `make_answer` builds `cited` -- the
   passages whose section box P could actually load -- and uses it BOTH as
   what the writer is shown AND as what the source list is built from.
   The previous arrangement showed the writer the loaded sections while
   citing every passage, which was right whenever box P loaded everything
   and wrong the moment it did not: "loaded 4 of 5" answered from four
   sections and printed FIVE source cards, so one card pointed at a
   document whose text nothing had read. That is the same defect the floor
   at zero refuses, surviving in the partial case, and F-03 calls the
   source line the product's contract with the user. Deliberately NOT
   fixed by filtering in two places: two filters agreeing is a convention,
   one tuple is a fact.
2. **THE WRITER MAY DECLINE.** The grader (ST-23) judges 500-character
   CHILD chunks; the writer reads the FULL sections. A grader that was
   generous once leaves the writer exactly two moves -- decline, or invent
   -- and inventing is the failure this product exists to demonstrate the
   absence of. So the prompt licenses one word, `NOT_COVERED`, and
   `AnswerNotCoveredError` routes it to the honest refusal. It is an
   EXCEPTION rather than a `str | None` return, and that is the load-
   bearing half: a port that forgets a `return` yields None, so under the
   other design a plain coding mistake becomes a fluent, honest-LOOKING
   refusal that lists the searches it ran. Raising cannot happen by
   omission.

PROVEN AGAINST THE REAL MODEL, which is the half no test in this repo can
reach, and it is the reason to keep doing this. Five cases through the
real `build_write_answer` and `build_grade` on live `gemini-3.6-flash`:
French covered, English covered, two not-covered, one partly covered. **0
unexpected outcomes.** Both not-covered cases came back `NOT_COVERED`,
including a genuine near-miss -- "conge annuel paye" appears inside
Article 52's anciennete counting rule, so a sloppy model had material to
invent from. The English question was answered in English and the French
ones in French. The partly-covered case answered the covered half and
named the uncovered half in prose WITHOUT tripping the decline parser,
which is the interaction no unit test covers. No bracketed reference
numbers anywhere. The probe lives in the session scratchpad and is NOT
committed: docs/phase2/CLAUDE.md forbids keys in tests, fixtures and CI.

TWO TESTS WRITTEN BECAUSE THE MUTATION LIST WAS DRAWN UP BEFORE IT WAS
RUN, and both rules were enforced by nothing until then:
- **"only the FIRST line decides a decline"** had no test. Every decline
  case put the token on line one, so a parser scanning every line passed
  all of them -- while destroying exactly the partial answer the prompt
  asks for, whose second line naturally opens "Not covered: ...". The
  live probe produced that shape on its fifth case, so it is not
  hypothetical.
- **REFUSAL_TEXT's own content** had no test. The refusal tests compare
  `answer.text` to `REFUSAL_TEXT`: both sides read the same constant, so
  they pin WHICH constant was used and nothing about what it says, and a
  copy edit dropping F-05's next step left every one of them green. That
  is the self-referential shape from the prove-it skill, written by
  someone who had just quoted that skill. The new test pins the three
  next steps F-05 names, not the bytes, so the wording stays editable.

ST-21 LEFT REFUSAL_TEXT'S FINAL WORDING TO THIS STORY and it is now
settled. It says "and I will not guess", because UX spec 6.2 asks for the
refusal to be "styled as a legitimate outcome, not a failure" and copy
that only apologises undercuts a design that does not. The searches stay
OFF the prose and on the answer object as `searched`; 6.2 gives the
refusal variant its own design that states what was searched, and the same
facts in two places are two places free to disagree. Interface copy is
English (PRD section 5) even though the documents and the question are
usually French -- the ANSWER follows the question's language, which is the
prompt's rule and was verified live in both directions.

A THIRD REFUSAL REASON EXISTS NOW and deliberately shares its words with
the first: "the sections were read and none of them answers the question"
renders as `REFUSAL_TEXT`, because the user's next step is identical.
Only the trace detail separates them (ADR-09, F-10). Contrast the
UNREADABLE-sections refusal, which keeps its own words because its next
step genuinely differs: run a Sync.

PARKED by this story, visible rather than fixed:
- `tests/fake_chat.py` was extracted so ST-24 did not write the fourth and
  fifth copies of the scripted fake. **ST-23's two copies are NOT
  migrated** (`tests/unit/test_agent_grading.py`,
  `tests/integration/test_ask_retry_loop.py`) -- rewriting another story's
  tests inside this diff is the drive-by the scoped boy-scout rule keeps
  out. Same shape as ST-23's own fake-encoders row, settled the same way.
  Owner YL, its own one-file `chore/` branch.
- `_index` and the two-workspace corpus fixture are now a second copy
  across the two integration files. Second copy, allowed; a third earns a
  `tests/integration/conftest.py`.
- ~~`.env.example` still names the DEAD model~~ **CLOSED, PR #58.** It
  named `gemini-2.0-flash`, which PR #55 fixed in `config.py` and missed
  here -- and because `.env` is read by pydantic-settings, a teammate
  copying the example would have OVERRIDDEN the corrected default, so the
  file whose job is to help someone start was the one thing that could
  break them. Landed on its own one-line `fix/` branch rather than inside
  ST-24's squash.
- ~~No composition root builds the real `AgentPorts` yet.~~ **CLOSED BY
  ST-27, and this entry was left standing stale until the ST-32 survey on
  2026-09-03 went looking for it.** `ui/ports.py` now builds all eight:
  `build_ports(client, model, *, parents_path=None)` and
  `build_default_ports(client)`. The prediction here was half right -- it
  could not be honest until ST-22 and ST-25 land -- and ST-27 solved that
  the way this file asks for, by WRITING THE THREE STUBS OUT LOUD, each
  naming its owning story and what it costs today, rather than faking them.
  ST-32 imports this one rather than writing a second (DECISIONS,
  2026-09-03). Note the shape of the mistake for next time: the entry was
  accurate when written and nothing re-read it, which is the same staleness
  this file has now recorded six times.

Previous: THE ANSWERING HALF IS BUILT EXCEPT FOR ONE SEAM. ST-21 and ST-23
are both MERGED (24479ba and af14c4e). Of the eight ports
`agent/ports.py` defines,
four are filled and real: `retrieve`, `grade`, `reword` (ST-23) and
`fetch_parents` (ST-21). Four remain stubbed, and only ONE of them stands
between this project and an end-to-end sourced answer: `write_answer`,
which is ST-24. The other three -- `summarize`, `clarify`, `rewrite` --
are ST-22 and ST-25 and are not on the critical path.

THE UI DESIGN ARRIVED 2026-08-27, as `designrag-main/` -- a generated
React + Vite + Tailwind prototype of all three screens. It is GITIGNORED
(PR #54) and is a picture of the UI, not the UI: CR-02 puts the interface
on server-rendered Jinja templates and ADR-10 rules out a JS toolchain, so
nothing under its `src/` is ever copied. ST-27 and ST-28 read it the way
you would read a Figma file. Reviewed against the signed UX spec; findings
in their own section below.

Previous: ST-23 HYBRID RETRIEVAL + RELEVANCE GRADER + REWORD, on branch
`feat/S2-ST-23-hybrid-retrieval-grader`, gate green by hand, NOT merged
and NOT reviewed. 451 passed / 2 skipped, up from 404. 15 mutations, all
15 killed.

It fills the three seams ST-21 named for it -- `retrieve`, `grade`,
`reword` -- and builds one thing nobody owned.

THE PLAN GAP THIS STORY FOUND: **no BUILD-PLAN row owns the ADR-06
chat-model interface.** Checked three ways before writing a line (graph
search; a project-wide grep across every `*.py` for
`langchain|chat_model|ChatGoogle|ChatOllama|init_chat_model`, which found
only `config.py` lines 32 and 34 -- the model NAMES; and reading every
plan row). ST-23 is the first story whose gate needs a model to exist, so
`agent/chat.py` lands here. Recorded so ST-24 does not rediscover it.

THE TWO DECISIONS THAT SHAPE EVERYTHING ELSE:
1. The seam is Sanad's own `complete(system, user) -> str`, NOT
   langchain's `BaseChatModel`. Passing the framework object through
   would allow `with_structured_output` for the verdict, which is more
   reliable against a real cloud model AND untestable under this
   project's own rule -- docs/phase2/CLAUDE.md requires a scripted fake
   with no API keys, and langchain's fakes cannot serve structured
   output (`bind_tools` raises `NotImplementedError` at
   `langchain_core/language_models/chat_models.py:2510`, read from the
   installed package). A seam the mandated test double cannot satisfy is
   a seam that gets tested by pretending.
2. AN UNPARSEABLE GRADER REPLY RAISES. It is never counted as off-topic.
   Those two outcomes are one keystroke apart in code and a world apart
   for the reader: off-topic tells the user their documents do not cover
   the question, and a model that answered gibberish has made no such
   claim. The retry ceiling multiplies it -- three unparseable replies
   would produce a refusal listing three searches, as if the corpus had
   been examined three times.

TWO DEFECTS FOUND BY RUNNING IT, neither visible to any test:
- `OFF-TOPIC` with a hyphen raised, while the comment beside the pattern
  claimed hyphens folded. A docstring describing behaviour the code does
  not have is worse than none: it is the reason nobody re-reads the line.
- THE INTEGRATION FIXTURE WAS TOO SMALL FOR ITS OWN PROPERTY. The HR
  document produced ONE child chunk, so a search depth of 1 and a depth
  of 3 both returned one hit and the test proving the operator's setting
  governs proved nothing. Third time this project has shipped that exact
  shape (ST-14, ST-16, here). The fixture is now a realistic three-article
  extract and the fixture itself asserts it produces >= 3 children, so it
  cannot silently shrink back.

WHAT THIS STORY DOES NOT PROVE, and it is the honest limit: that a real
language model grades French legal passages correctly. Nothing on this
machine can -- no cloud key, no Ollama, see the blocker below. Everything
under the agent IS real in the integration test: real embedded Qdrant,
real chunking, real parent JSON, real hybrid search, the real three
ports. Only the encoders and the chat model are faked, both for reasons
already written down.

Previous: ST-21 AGENT GRAPH SKELETON **MERGED as 24479ba** (PR #49, squash),
2026-08-26, and re-verified on main after the merge rather than only on
the branch.

ONE DEVIATION, recorded rather than absorbed: MERGED WITHOUT THE RULE-5
PARTNER REVIEW, at the human's explicit instruction ("just merge #49 for
now"). Same shape as the ST-17 deviation of 2026-08-23, and the same debt
it created. What ST-21 did have before merging, which is more than ST-17
had: the whole gate by hand plus CI, 38 mutations all killed, one COLD
verifier pass whose blocking finding was fixed, and one human read that
found the two structural gaps. What it did NOT have is the partner's
eyes. On this project a post-green pass has found a real defect on five
stories running, so the debt is real even when the evidence looks strong.
ST-12's review is still owed too; that makes two. [SUPERSEDED 2026-08-30: ST-12's was paid, PR #65.] This is the first module of the answering half: everything before
it put documents INTO the stores, and nothing has ever taken a question.

WHAT IT IS, and just as importantly what it is not. Architecture 5.2 is
wired as a LangGraph graph (ADR-03): summarize -> rewrite -> (clarify) or
(retrieve -> grade -> fetch_parents -> answer / reword-and-retry /
refuse). Nine nodes, two branches, and NO THINKING AT ALL. Every place
the flow needs a model or a store is one callable on `agent/ports.py`,
and seven of the eight belong to a story that has not started: summarize
(ST-25), clarify and rewrite (ST-22), retrieve, grade and reword (ST-23),
write_answer (ST-24).

TWO STRUCTURAL GAPS FOUND BY THE HUMAN'S REVIEW of the first version,
both now closed, and both worth recording because the first version's
journal entry defended one of them as a deliberate choice:
1. THE PARENT FETCH WAS MISSING. 5.2 draws `P[Fetch parent sections for
   context]` between grading and answering, and 7.5 is why: the searched
   unit is a 500-character child, the READ unit is the section it came
   out of. The first version left it out, arguing ADR-03's node list does
   not name it and it changes no route -- and that argument was wrong on
   a fact, not on taste. It cannot be folded into a neighbouring port:
   `parent_store.get_parent` needs a workspace id and `write_answer`'s
   signature has none. It is now its own node, its own port, and its own
   state field. The model was answering from chunks while the docstrings
   claimed it read sections.
2. "REWRITE AND SPLIT" COULD NOT SPLIT. The rewrite port returned ONE
   string, with a comment saying "V1 returns one query" that had no
   signed basis anywhere -- 5.2 says "Rewrite and split query", ADR-03
   keeps the reference implementation's sub-queries, and BUILD-PLAN
   line 76 names ST-22 "Rewrite-and-split node". `rewrite` and `reword`
   now return a SEQUENCE, `retrieve` runs once per query with one trace
   step each, and hits are merged on (parent_id, chunk_text). One query
   is a one-element tuple, so nothing about the ordinary case changed.

`agent/stores.py` is the one port with a REAL implementation, and that is
deliberate rather than an exception being made: the other seven need a
model, this one is a read against `parent_store`, which ST-16 already
built. Deferring it would have deferred the only part of box P that could
exist. A section the store cannot find is OMITTED and counted in the
trace ("loaded 1 of 2"); a CORRUPT one raises, because a file that exists
and does not say what it should may be a section pretending to be another
section. Tested against a real store on disk written by ST-16's own
`save_parents`, including the F-01 case: asking workspace A for a parent
id that exists only in workspace B comes back empty, not with B's text.

The ports have NO DEFAULTS, deliberately. A stub that answers plausibly
is the most dangerous object in a sourced-answer product: as a default it
ships the day someone forgets to pass real ports, and Sanad invents an
answer instead of failing. The stub the exit gate names lives in the test
file, written out loud.

Exit gate, both halves:
- "the graph runs end to end on a stub" -- all three outcomes do, and the
  route is asserted as an ORDERED LIST of trace steps rather than a count,
  because "it answered" is true of a great many broken graphs.
- "every answer object carries its trace" -- true BY CONSTRUCTION, not by
  eight nodes remembering. Nodes write a draft into the state; `ask` is
  the only place an `Answer` is built and the only place a trace is
  attached.

Two more properties worth not losing:
- THE TRACE IS THE RETRY COUNTER. `retries` and `searched` are counted
  from recorded steps, never stored. F-04's ceiling is enforced against
  that count and UX spec 6.2 renders the same number on the bubble, so "the
  loop ran three times and the marker says two" is unrepresentable.
- AN ANSWER WITH NO SOURCES CANNOT EXIST. The rule is written in three
  signed documents (openapi's G3 note, docs/phase2/CLAUDE.md, PRD F-03)
  and was checked in none; `Answer.__post_init__` now raises.

32 mutations injected one at a time: 20 against the first version (all
killed) and 12 against the redesign, of which TWO SURVIVED and both were
real test defects rather than dead code:
- the split-query de-duplication test asserted on `answer.sources`, which
  `_sources_for` de-duplicates a SECOND time on (file, label) -- so the
  duplicate passage collapsed before the assertion could see it and the
  test passed with the merge broken. That is the "keyed so duplicates
  collapse" shape the prove-it skill lists, written into a test whose own
  docstring warns about vacuity. It now asserts on the passages the
  ANSWER WRITER received, which is where a duplicate actually costs
  something: the model reads the same passage twice.
- the empty-query-list guard was never tested. No port in any test
  returned `()`, so deleting the check changed nothing. Two tests added.
Both re-run after the fix and both now die. Sharpest kills across the
whole battery: a ceiling read as `<=` instead of `<`, a ceiling hardcoded
to its own default of 2 (tests run at 0, 1, 2, 5 and 20), and dropping
the workspace id when reading a parent section.
Honest caveat: the battery ran across four passes rather than one clean
sweep, because an interrupted run left one mutation on disk -- see the
lesson below.

TWO DEFECTS FOUND BY RUNNING IT, neither visible to any test in the story
and neither of a kind a mutation could find, because both were a MISSING
check rather than a wrong line. That is now the fifth story running where
the post-green pass found what the suite could not:
1. A `clarify` port returning "" was read as "the question is clear", so
   the agent SKIPPED THE CLARIFYING QUESTION AND ANSWERED -- precisely
   the guessing F-06 exists to prevent, done in silence.
2. A blank `rewrite` or `reword` sent the empty string to the store as a
   search, and the honest refusal then disclosed `('',)` to the user as
   what it had looked for (F-05).
Both now fail at the seam that produced them, naming the port, via one
shared `_spoken` guard. Four tests, one per port.

AND ONE ASSUMPTION THAT WAS WRONG, caught the same way: the first draft
computed its own LangGraph recursion limit, because the documented
default is 25 super-steps and this graph is 5 + 3R nodes long. The pinned
langgraph 1.2.9 actually defaults to 10007
(`langgraph/_internal/_config.py:32`); a ceiling of 50 -- 155 nodes --
ran untouched. The hand-computed limit was therefore a SECOND, LOWER
bound whose only possible effect was to cut a legitimate run short the
day someone adds a node. Deleted. `test_a_high_retry_ceiling_runs_to_
completion` needs 65 nodes and pins the framework's default instead.

A COLD VERIFIER PASS THEN RAN on the branch as redesigned, and it earned
its place: 1 blocking, 7 worth fixing, 6 notes. All of the blocking and
worth-fixing items are now closed except two, which are parked below.

THE BLOCKING ONE WAS A VACUOUS TEST THE MUTATION BATTERY HAD MISSED, and
that is the part to keep. `test_the_same_id_twice_is_read_once` asked for
one section three times and asserted on the returned mapping -- but
writing one text into one dictionary key three times produces exactly the
dictionary that writing it once produces, so the assertion could not see
whether the de-duplication happened at all. The verifier did not argue
it: it deleted `dict.fromkeys` and watched the assertion pass. The test
now counts the actual reads through `parent_store.get_parent`. Two
lessons, and the second is the uncomfortable one: 32 mutations had not
touched `agent/stores.py`, so a battery is only as wide as the list you
wrote for it; and this is the SEVENTH shipped example of the shape the
prove-it skill exists to catch, written by someone who had just quoted
that skill in the same file's docstring.

Also found and fixed, worst first:
- NO FLOOR AT ZERO READABLE SECTIONS. "loaded 0 of 5" answered anyway,
  handing the model an empty context while the answer still carried five
  source citations built from chunk metadata -- a citation to documents
  whose text nothing had read, against F-03. It now refuses, with its own
  wording: the passages were found, the sections could not be read, and
  the next step is a Sync, not a rephrase. Partial still answers.
- `question` WAS NEVER CHECKED against openapi's 1..2000 bounds. ADR-13
  puts the UI on the in-process path, so the route's validation is not in
  it. A blank question did fail, three nodes later, with "the rewrite port
  returned a blank string" -- pointing whoever read it at ST-22's code for
  a fault the caller committed.
- NO WIDTH LIMIT ON THE SPLIT. The ceiling bounds how many rounds run;
  nothing bounded how wide a round was, so a rewrite returning forty
  phrases cost (ceiling + 1) x 40 real searches, all forty read back to
  the user in the refusal. Now `config.max_sub_queries`.
- `_merge_hits` CLAIMED "best-ranked first" AND NOTHING SORTED. False the
  moment there are two queries: found earlier is not ranked higher. Left
  unsorted deliberately -- RRF scores are computed within one query and
  are not comparable across two, so sorting by them would be a second
  quiet wrongness -- and the docstring now says so and hands the fusion
  question to ST-23.
- `agent` IMPORTED `db.repo` for two uuid4 calls, making the answering
  module unimportable without SQLite for a call that is one stdlib line.
- Six miscounted docstring claims ("Five files" over a table of six,
  "eight boxes" over nine nodes, "two of eight fields" over three), all in
  files whose entire argument is that the docstrings are load-bearing.

WHAT THE VERIFIER CHECKED AND FOUND CLEAN, which is half the value of
having run it: every spec citation in the branch is true. It read
architecture 5.2/7.5, ADR-03, ADR-09, openapi lines 223/480-483/512,
docs/phase2/CLAUDE.md lines 33-34, PRD F-03 to F-10 and section 11, UX
spec 6.2, BUILD-PLAN line 76, and langgraph's own `_config.py:32`, and
found no fabricated reference. The previous pass of this branch had
eight wrong ones.

PARKED, all five visible rather than fixed. THE TWO THAT HAD NO OWNER NOW
HAVE ONE, a date and a fallback, because this file has carried ownerless
debt before and it rots into abandoned work rather than blocked work:
- **ISSUE #50, owner MB, fallback 2026-09-12.** A FILE BRIEFLY LOCKED
  READS AS A CORRUPT ONE and takes the whole question down.
  `parent_store.py:176` turns ANY `OSError` into `CorruptParentError`, so
  antivirus or OneDrive sync holding a parent file for a moment is
  indistinguishable from genuine corruption -- and this repo lives under
  OneDrive. A transient lock is retryable and corruption is not; they
  should not share an outcome. The fix is inside ST-16's module, so it is
  not ST-21's to make.
- **ISSUE #51, owner YL, fallback 2026-09-12.** ADR-09 SAYS V1 PERSISTS
  THE TRACE and there is nowhere to put it: `db/schema.sql` has no answer
  table and no trace table, while openapi calls `trace_id` a "stored
  trace reference". Nothing is broken today, because nothing reads a
  trace back until F-10 (V1.1) -- but the `trace_id` served now
  identifies nothing on disk, so no story may claim a trace survives a
  restart until this is settled. It is a spec decision (amend ADR-09, or
  a change request adding the tables), not a code edit.
- SEVEN COPIES of the "de-duplicate, keep first-seen order" one-liner
  across the new package. The core law says the third copy needs an
  abstraction or a DECISIONS row; there is now a row.
- `disclaimer` is always False. F-09 is ST-26's and no test here claims
  otherwise -- a default nobody has exercised is not a feature.
- `REFUSAL_TEXT` in agent/nodes.py is the honest minimum, not product
  copy. ST-24 owns the wording.
- Nothing persists a trace: see the ADR-09 escalation row in DECISIONS.

LESSON PAID FOR IN THIS SESSION, and it is the one worth carrying: a
mutation harness must never run against uncommitted work. An interrupted
run left `rewords_in` counting SEARCH instead of REWORD on disk, with no
commit to restore from -- it was recoverable only because it was one line
and the suite went loudly red. Commit the green checkpoint FIRST, then
mutate; `git checkout --` is then the restore.

Previous: ST-17 MERGED as 0210408 (PR #35, squash), and re-verified ON main after
the merge rather than only on the branch: `uv sync --frozen` clean, ruff
exit 0, 318 passed / 2 skipped. CI `verify` green on the PR with all four
gate.yml steps. This is the story that makes Sanad ingest anything:
`sync.py` is the first caller of ST-12, ST-13, ST-14, ST-15 and ST-16,
all five of which were individually green and collectively untested until
now.

TWO DEVIATIONS, both recorded as DECISIONS rows rather than absorbed:
- ownership: BUILD-PLAN line 65 assigns ST-17 to YL and this machine
  commits as `meriem-mb` (MB). Same shape as the ST-12 deviation of
  2026-07-28. The plan row is left as signed; a human decides.
- MERGED WITHOUT THE RULE-5 REVIEW PASS on 2026-08-23, at the human's
  explicit instruction. THAT DEBT IS NOW PAID -- see the review-pass
  section below. Kept in full because the reason it mattered is the
  point: CLAUDE.md rule 5 exists because a green suite has never once
  been sufficient on this project (ST-10 shipped a defect an independent
  re-review caught, ST-11 took three rounds each finding a real defect
  while the suite was green, and ST-12 merged without a review and is
  STILL owed one). ST-17 is the largest single diff in the project so
  far (+2,189 lines) and carried the same debt for five commits. The
  review found one defect that DELETES USER DATA, which is the fifth
  story running where a post-green pass found something.

What is proven, and how:
- PRD F-02's four criteria on real fixtures, not mocks: real SQLite, real
  embedded Qdrant under tmp_path, real files, the real conversion ladder
  including a genuinely AES-256 encrypted PDF. Only the two encoders are
  faked, because they download 1.1GB.
- all six `sync_item.result` values in ONE run (added, changed,
  unchanged, failed, removed, skipped), asserted as a whole-report
  equality rather than six separate greens.
- double-sync blocked, and the test attempts the second Sync from INSIDE
  the first via the converter, at the one moment it is genuinely mid-run.
  Hand-writing a half-finished row would have proved the query works and
  nothing about the guard.
- 12 mutations injected one at a time, all 12 killed. NO survivors, which
  is a first on this project and is itself worth distrusting slightly --
  see the self-review finding below, which no mutation could have found.

Self-review after green found the defect the mutation battery could not,
for the fourth story running, and it is again a MISSING line rather than
a wrong one: `vector_store.upsert_children` returns early for an empty
child list and so never reaches its own `ensure_collection`. A sync in
which every file was Skipped or Failed therefore left no collection at
all, and `vector_store.search` then told the user the workspace had NEVER
BEEN SYNCED, seconds after a sync -- the exact confusion that error's own
docstring says it exists to prevent. `sync_workspace` now ensures the
collection once per run, after the scan succeeds. Reproduced by deleting
the line and watching two tests fail with that message.

Three things ST-16 left for ST-17, all now closed:
- (a) workspace deletion across both derived stores: `sync.delete_workspace`,
  which lives in sync.py because sync owns the Qdrant client (ADR-04).
  Derived stores first, registry second.
- (b) `delete_document` is now called on every re-ingest, unconditionally,
  before conversion. Shrink residue is pinned by a test.
- (c) `StoreDeletion.unreadable_parent_files` lands in the report row's
  reason with the next step named, rather than being escalated.

CROSS-MODULE CHANGE a reviewer should look at first, because it is the
one thing in this diff that is not ST-17's own file:
`change_detection._STATUS_WITHOUT_DERIVED_DATA` was one set answering two
different questions, and one answer was wrong. A `failed` row with
unchanged bytes classified UNCHANGED forever, so a corrupted file was
reported Failed on its first sync and then dropped out of every later
report while still being unanswerable, and a file the user repaired was
never picked up. F-02 criterion 3 held for exactly one run. Split into
`_STATUS_WITHOUT_DERIVED_DATA` (removed+failed+skipped) and
`_STATUS_ALREADY_REPORTED_REMOVED` (removed only) -- because simply
widening the one set would have stopped a deleted `failed` file from ever
clearing out of the registry. ST-12's existing suite never caught this:
it is the module that READS these statuses, and ST-17 is the first that
writes them.

NOT DONE, and it is not a judgement call: ST-18. It depends on ST-07's
corpus, which does not exist -- `data/` on this machine holds only a
stray `parents/` test artifact, no labour-code PDF and no HR/CNSS guides.
ST-07 is MB's and unstarted. Numbers measured on fixtures would be
numbers about fixtures, which is worse than no numbers because they would
be quoted later. See Next.

Blast radius for ST-16, written before any code was touched and left
here because the second bullet is what the story turned out to be about:
- WHO IS TOUCHED: nothing in production. Grepped for importers of
  `embeddings`, `chunking`, `parent_store`, `vector_store` across
  `*.py`: the only non-test importer in the repo is
  `parent_store.py -> chunking.Parent`. So extending `embeddings.py`
  with the sparse pair cannot break a caller, because there are none.
  ST-17 is the first caller of any of it.
- WORST CASE: not a crash. Two silent failures. (1) sparse BM25 encoded
  with the document function on the query side, which returns different
  values with no error and quietly degrades retrieval -- the exact shape
  ADR-05's `passage:`/`query:` rule exists to prevent. (2) a workspace
  filter that leaks, so an HR question cites a manuals passage.
- HOW YOU WOULD FIND OUT: neither is visible to a typechecker or to a
  green suite, so both get a test that fails on the mutation --
  the asymmetry pinned on literals, and the isolation pinned in both
  directions.
- HOW TO UNDO: revert the branch. `data/qdrant/` and `data/parents/` are
  git-ignored derived stores with no migration: delete them and re-sync.
- Previous: ST-13 Conversion ladder MERGED as b75b584 (PR #18). The
  earlier claim in this file that it was "on branch, NOT reviewed, NOT
  merged" was stale; it was reviewed and merged. Third time this file has
  described a state that no longer existed.
- Superseded detail, kept because the library traps are still true:
  `conversion.py`: PDF via pymupdf4llm, DOCX via markitdown, TXT/MD
  passthrough, returning CONVERTED / FAILED / SKIPPED with a
  plain-language reason per PRD F-02 and section 11.
  26 mutations injected one at a time, every one turned the suite red.
  Three findings worth carrying forward, all from probing the libraries
  rather than trusting their docs:
  (a) a password-protected PDF OPENS fine in pymupdf and even answers
      `page_count`; only `needs_pass` tells the truth, and without that
      check pymupdf4llm dies on an undeclared TypeError mid-batch;
  (b) markitdown does NOT raise on a .docx it cannot parse as Word -- it
      falls through to another converter and returns the result as a
      SUCCESS. A corrupted .docx came back as its own raw bytes. That is
      the worst failure mode in the module, because nothing announces it,
      and it is why the DOCX rung validates the OOXML package itself;
  (c) `pymupdf.FileNotFoundError` SHADOWS the builtin and subclasses
      RuntimeError, so `except OSError` never catches a missing PDF.
  And two the mutation/self-review split is worth remembering for:
  (d) mutation testing found a redundant `is_zipfile` pre-check by
      SURVIVING -- a mutation nothing catches can mean dead code, not a
      vacuous test. Read the survivor before blaming the test;
  (e) self-review after green found a `DocumentSkippedError` class that
      nothing raised. Mutation testing structurally cannot see a branch
      no code reaches; only reading the diff finds those.
- Previous: ST-12 MERGED as 1862a58 (PR #14, squash).
- CORRECTION, and the reason this file was stale: an earlier entry here said
  ST-12 was "NOT reviewed, NOT merged" while 1862a58 was already on main. It
  shipped WITHOUT the reviewer pass the Next queue was explicitly waiting on.
  That matters because ST-10 and ST-11 each had a later review find real
  defects while the suite was green, and ST-12's own self-review found three
  more after CI passed. A post-hoc reviewer pass on 1862a58 is owed.
- What is proven working on main right now: `uv sync` resolves the pinned
  stack; config loads; the SQLite registry creates, cascades and rolls back
  under test; workspaces create, rename, delete, list, get and toggle their
  legal flag, with names normalized and the F-01 criteria demonstrated at
  module level. `uv run ruff check .` clean, `uv run pytest -q` 51 passed
  (2 config + 17 db + 32 workspaces -- the previous entry's per-file split,
  "15 db + 34 workspaces", was miscounted; the 51 total was right).
- Whole suite on main: ruff clean, 130 passed (2 config + 19 db + 32
  workspaces + 40 change detection + 37 conversion). CI `verify` green on
  PRs #14, #15 and #18. On this ST-14 branch: 173 passed.
- CR-02 Part B landed on main (PR #13, fea733c) while ST-13 was in flight:
  the UI dependency is now `jinja2` server-rendered templates, NOT gradio,
  and a new signed spec `docs/phase2/Sanad_UX_Spec_v1.0.md` joined the
  write-locked pack. It touches no ingestion code -- ST-13 verified clean
  against it (`grep -rn gradio` over conversion.py, change_detection.py and
  config.py finds nothing) -- but every UI story is now built on a
  different base than the original BUILD-PLAN assumed. Read docs/journal/CR-02.md
  before starting one.
- STALE AS WRITTEN, corrected 2026-08-27 rather than deleted, because the
  correction is the useful part: this bullet claimed "what does NOT exist
  yet: any UI, any retrieval, any vector store, any sync engine". Three
  of those four are now false. The vector store landed with ST-16
  (52ee47b), the sync engine with ST-17 (0210408), and retrieval with
  ST-23 (af14c4e). Only the UI is still absent, and `app.py` still does
  not exist, so Sanad still cannot be launched -- that is ST-27, ST-28
  and ST-51.
  A "what does not exist" list is the fastest-rotting sentence a journal
  can contain, because every story is an attempt to falsify one of its
  entries. If another one is written, date it and expect to revisit it.
  The original text, kept because its REASON still explains the design:
  "Four ingestion/indexing stages now exist and NONE of them are wired to
  each other: ST-12 decides what needs ingesting, ST-13 converts it,
  ST-14 splits it, ST-15 embeds the children -- and nothing calls any of
  them until ST-17. That is deliberate and is what has kept each one
  unit-testable with no database, no vector store in existence."
- FIXED 2026-08-09, was the sharpest thing the rubric review found:
  `chunk_document` was NOT idempotent. Parent ids came from
  `repo.new_id()`, so the same document chunked twice yielded a disjoint
  id set (proven by running it, not suspected). §7.5 keys the parent store
  on that id (`data/parents/<workspace_id>/<parent_id>.json`) and Qdrant
  payloads carry it, so re-ingesting a CHANGED file minted all-new ids:
  every previous parent JSON orphaned, and any vector surviving the
  rewrite pointed at a parent file that no longer existed -- a search hit
  that resolves to nothing, which a sourced answer cannot survive.
  Ids are now DERIVED: `uuid5(namespace, "<source_file>\x00<index>")`.
  Three tests pin it. Removing the random id also removed chunking.py's
  only `db.repo` import, so the splitter no longer depends on the data
  layer at all.
  STILL TRUE FOR ST-16/ST-17, so do not lose it: a document that SHRINKS
  from ten parents to six leaves ids 6..9 behind. That residue is now
  deterministic, so ST-17 can compute exactly which ids to delete instead
  of guessing -- but something still has to delete them, and the parent
  JSON and its vectors must go as ONE unit or the mismatch returns.

## Numbers (this project had none until 2026-08-09)
The rubric row is "a number with no threshold is trivia, a threshold with
no owner is a wish".

ST-18 PART ONE MEASURED 2026-08-29 on Corpus v1, MB's laptop, CPU only.
`scripts/spike_st18.py index` and `... retrieve`. NO model calls in any
number below -- these are the free half of the spike. G4 is NOT here yet.

OWNERSHIP DEVIATION, recorded rather than absorbed, same shape as the
ST-17 row of 2026-08-23: BUILD-PLAN line 66 assigns ST-18 to YL, and this
machine commits as `meriem-mb` (MB). The plan row is left as signed; a
human decides. Flagged by the rule-5 review, which noticed the ST-17
deviation had been recorded and this one had not.

REFERENCE MACHINE IS STILL UNNAMED, and every number below inherits that.
PRD G4 and G5 both say "on the reference machine" and no document names
one. These were taken on MB's laptop, CPU only, no GPU. A different
machine moves all of them, and G5's 109 seconds of headroom is not enough
to absorb much. ST-37 owns naming it.

```
Name:       G5, cold Sync of a 200-page workspace
Measures:   Wall time from pressing Sync to the workspace being questionable
Rule:       Whole `sync_workspace` call on an EMPTY store, encoder load
            included, normalised to 200 pages. Cold on purpose: a user on a
            fresh install waits for the model whether or not that is fair
Population: HR workspace, Corpus v1, 3 files / 225 pages / 1,121 children
Window:     Point measurement, re-run per release
Good:       Under 600s per 200 pages (PRD G5: 10 minutes)
Act at:     Over 600s, or under 120s of headroom
Owner:      YL (ST-37 owns the tuning if it moves)
Measured:   552.4s for 225 pages -> 491.0s per 200 pages.
            PASS ON BUDGET, ACT-AT TRIPPED. Headroom is 109.0s and this
            row's own trigger is 120s. Routed to ST-37.
```
CORRECTED BY THE RULE-5 REVIEW, and the correction is the point: the first
version of this row wrote "PASS" and left it there, while the row's OWN
act-at threshold had fired. 600 - 491 = 109, and the trigger is 120. That
is the "do not silence the alarm" rule failing in the quietest possible
way -- not by moving a threshold, but by writing a threshold, watching it
trip, and reporting the other number. A row that judges itself is worth
nothing if the verdict line ignores it.

READ THIS ONE HONESTLY: it clears the budget by 18%. That is not
comfortable, it is close. The whole cost is
embedding -- the same workspace re-syncs in 0.23s when nothing changed, so
scanning, hashing and the registry are 0.04% of it. Two consequences
nobody has written down before:
- at 2.45 seconds per page, the V1 capacity PRD section 11 advertises
  (1,500 pages per workspace) would take about SIXTY-ONE MINUTES to sync.
  That is not a G5 failure, because G5 only promises 200 pages -- but the
  capacity line and the speed line have never been read against each other,
  and a jury can multiply.
- the headroom is a CPU-and-machine number. A slower laptop fails G5 on
  the same corpus, and "reference machine" (PRD G4/G5) has never been
  named. ST-37 needs to name it.

```
Name:       Retrieval quality against a word-counting baseline
Measures:   Share of questions whose TOP hit comes from the right file
Rule:       20 hand-written questions phrased as a user would ask, never
            in the corpus's own words. Hybrid = `vector_store.search`.
            Baseline = count shared words 3+ chars, ACCENT-FOLDED, over
            every parent
Population: Corpus v1, both workspaces
Window:     Point measurement, re-run when retrieval changes
Good:       Hybrid must beat the baseline, or hybrid is not earning itself
Act at:     Hybrid <= baseline -> OR-1 change-request
Owner:      YL
Measured:   hybrid 16/20, counting words 11/20. Hybrid earns itself.
```
**THE FIRST VERSION OF THIS ROW REPORTED A RIGGED COMPARISON** and it is
the most useful mistake in the spike. It said hybrid 12/15 against a
baseline of 6/15 -- apparently double. The rule-5 review found why: every
question here is typed in unaccented ASCII ("conges") and the corpus is
properly accented French ("congés"), and `casefold()` folds case but NOT
accents. The word-counting baseline therefore could not match a large
share of its own vocabulary, while the dense encoder is untroubled by the
difference. Fixed by folding accents and lowering the word floor from 4
characters to 3, and re-run: 16/20 against 11/20.
The verdict SURVIVES -- hybrid still wins, so ADR-05 needs no change
request -- but the margin was roughly double the real one, and the margin
is what a reader remembers. A baseline exists to be the number the real
system must beat, so anything that quietly weakens it flatters the thing
under test. Build the baseline as if you wanted it to win.
```
Name:       Right ARTICLE, not just the right file
Measures:   Share of legal questions whose top 3 hits contain the article
            that actually answers them
Rule:       8 of the 20 above name a specific article of the labour code.
            WHO CHECKED WHICH, because the first version of this row
            claimed a verification that had not happened:
              - 231 conge annuel, 39 fautes graves, 184 44h/semaine,
                14 periode d'essai, 152 quatorze semaines, 143 quinze ans
                -- all six read out of the PDF by the rule-5 review;
              - 72 certificat de travail, 205 repos hebdomadaire -- both
                read out of the PDF in the fix round, text quoted in
                CHANGELOG-AI. These two did not exist when the review ran.
Population: HR workspace, Corpus v1
Window:     Point measurement
Good:       Not yet set. See below -- setting it is ST-19's job
Act at:     Not yet set
Owner:      YL, and it is the most important open number on this project
Measured:   **WITHDRAWN 2026-08-30 -- DO NOT QUOTE THIS NUMBER.** It read
            5/8, and the matcher that produced it was a plain substring
            test, so 5 is an UPPER BOUND and not a measurement. See the
            block below. The reading it replaced (4/8 with the bad probe,
            and 3/6 earlier) is withdrawn for the same reason.
```
**THE RIGHT-ARTICLE FIGURE IS WITHDRAWN, and the number it guarded was the
one this file calls the most important open number on the project.**

Found 2026-08-30 by a cold review of `scripts/spike_st18.py`, which no
test had ever exercised, and reproduced before being fixed. The check was
`probe.expect_marker in joined` -- a bare substring test against markers
that are bare numbers (231, 39, 184, 14, 152, 143, 205, 72). So:

    "14"  is satisfied by "Article 143 interdit d'employer des mineurs"
    "39"  is satisfied by "l'article 139 du present code"
    "205" is satisfied by "le decret 2-05-734"
    "72" AND "184" are both satisfied by "dahir n 1-72-184"

That last one is the one to understand: `1-72-184` is the NAME OF ANOTHER
DOCUMENT in the same workspace. A probe expecting an article of the labour
code could therefore score a hit by retrieving a completely different
file, which is precisely the failure the marker was added to detect. Four
of the eight markers collide that way.

FIXED IN THE CODE, NOT IN THE NUMBER. `marker_found` now matches the way a
citation does -- the number must follow the word "article" and end where
the number ends -- and `tests/unit/test_spike_st18_marker.py` pins both
directions, including a mutation back to the original substring test,
which turns exactly the five collision rows red. But **the figure itself
cannot be recomputed until the spike is re-run on a machine that has the
corpus**: `data/` does not exist on YL's machine and `corpus.py fetch`
fails there with CERTIFICATE_VERIFY_FAILED (TLS interception on that
network), which is not something to disable to get a number.

WHY THIS MATTERS BEYOND ONE FIGURE, and it is the lesson rather than the
bug: measurement code that is wrong does not crash and does not fail a
gate. It reports a BETTER number than the truth and the number gets
quoted. Over 1,300 lines of `scripts/` had no tests at all, which is how
this survived a rule-5 review, a re-review, and a green suite. The same
review also found the answer path stapling each source file to another
source's article label -- inside the measurement OF citation quality, and
written into `traces.json`, which is the file ST-19's golden set is meant
to be built from. Both are fixed; ST-19 must not be written from any
traces file produced before this fix.
**A FALSE VERIFICATION WAS WRITTEN INTO THIS FILE AND THE RE-REVIEW CAUGHT
IT.** The row above used to say all eight article numbers "were CHECKED
against the PDF by the rule-5 review, not assumed". The review checked
SIX. The other two probes did not exist when it ran -- they were added in
response to it. And one of those two was WRONG: Article 217 is "il est
interdit aux employeurs d'occuper les salaries pendant les jours de fetes
payes", public holidays, not rest between working days.

That is the exact failure this journal exists to prevent, committed in the
journal itself: an unverified claim wearing someone else's authority. It
is worse than an unchecked number, because "the reviewer checked it" is
the sentence that stops the next reader checking.

THE BAD PROBE IS GONE, and replacing it taught something: the question
"combien de temps de repos entre deux journees de travail" has NO clean
answer in this code. Daily rest is regulated only for NIGHT work and only
for women and minors (Article 174, eleven consecutive hours). So it was
scored as a RETRIEVAL MISS when the fault was entirely the label -- a bad
probe does not just waste a slot, it makes the system look wrong. It is
replaced by "combien de temps de repos par semaine", which Article 205
answers plainly, verified by reading the PDF rather than by remembering.
**THIS IS THE FINDING OF THE SPIKE, and it is not a speed problem.**
Retrieval finds the right DOCUMENT 16 times in 20 and the right ARTICLE
~~5 times in 8~~ **-- that second figure is WITHDRAWN as of 2026-08-30,
see the withdrawal block above: the matcher counted digits appearing
anywhere, not articles, so 5 is an upper bound. The DOCUMENT figure of
16/20 is unaffected -- it compares file names, not numbers.**

THE SHAPE OF THE FINDING SURVIVES THE WITHDRAWAL, and this is why the
entry is amended rather than deleted: the gap between finding the right
file and finding the right article can only be WIDER than was published,
never narrower, because every collision scored a hit that was not one. So
For this product that gap is close to the whole point: F-03
puts file name AND section label in every citation, and the user story is
an HR generalist forwarding "Article 231" to settle a dispute. A citation
that says "the right 201-page PDF, somewhere" does not survive that
forwarding. It is the same defect family as the citation-label escalation
of 2026-08-23, which was fixed for LABELLING and is now showing up in
RANKING.
Two honest caveats, because this number will be quoted:
- 20 questions is a small sample and 8 is smaller. Treat 5/8 as "about
  three in five", never as 62.5%. It read 3/6 and then 4/8 on earlier
  question sets, and the 4/8 included a probe whose expected article was
  simply wrong.
- I WROTE BOTH THE QUESTIONS AND THE EXPECTED ANSWERS, so this is
  self-graded. ALL FOUR whole-file misses are arguable rather than plainly
  wrong: "comment attraper une erreur" and "comment trier une liste"
  returned the FAQ instead of the tutorials, "a quel age part-on a la
  retraite" returned the dahir's pension articles instead of the CLEISS
  guide, and "comment sont calculees les cotisations" returned CLEISS
  instead of the dahir -- and those last two are the same pair of
  documents disagreeing about which of them owns contributions, which
  both plainly cover. An earlier version of this paragraph said "two of
  the three", which understated it. An independently written golden set is
  exactly what ST-19 is for, and that is the argument for writing it AFTER
  this run rather than before.

```
Name:       Warm retrieval latency
Measures:   One `vector_store.search` call, no model, no answer written
Rule:       Median and 95th (nearest-rank) of all 20 calls. The cold start
            is measured on a SEPARATE untimed warm-up query, not held out
            of the sample
Population: Corpus v1, both workspaces, MB's laptop
Window:     Point measurement
Good:       Must be a small fraction of G4's 20s median budget
Act at:     Over 2s
Owner:      YL
Measured:   median 0.240s, p95 0.298s over 20. Cold start 31.2s.
            Two runs of the same 20 questions gave medians of 0.207s and
            0.240s and cold starts of 37.6s and 31.2s. Machine load, not
            code -- quote the shape (a fifth of a second), not the digits.
```
TWO CORRECTIONS HERE, both from the rule-5 review, both about not letting
a statistic be an accident:
- the cold start used to be `seconds[0]`, held out of the pool. That is
  POSITIONAL, not causal: it throws away a good sample when the process is
  already warm, would miss a cold load that happened at position two, and
  with one sample it reported the cold figure as an n=1 warm median. There
  is now one untimed warm-up query before the loop, so every timed sample
  is a real question and nothing is discarded.
- the p95 used `round(0.95 * n) - 1`, which for n=14 returned the 13th of
  14 with TWO samples above it. That is not a 95th percentile. It is
  nearest-rank now, `ceil(0.95 * n) - 1`. Immaterial at 0.2s and decisive
  for G4, where the same function judges an answer against 60 seconds and
  dropping the top sample flips PASS to FAIL.
The cold start is still reported, because a user asking their first
question of the day really does wait for the encoder. It is a different
number from "what a question costs", not a corrupt version of it.

## ST-18 VERDICT: **TUNE**
BUILD-PLAN line 66 requires one of three words -- on-track, tune, or
change-request -- and the first version of this section gave numbers and
no verdict, which is the exit gate unmet. The word is **TUNE**, and it is
PROVISIONAL on G4, which is blocked (see Blockers).

Not on-track, because two things are already outside where they should be:
G5 clears its budget but trips its own act-at threshold (109s of headroom
against a 120s trigger), and the right-article rate is about three in
five, on a product whose citations name a section.
Not change-request, because nothing signed is wrong. ADR-05's hybrid
retrieval earns itself against a fair baseline (16/20 vs 11/20), the
conversion ladder handled every real document, and no PRD criterion has
been shown to be unachievable. What is needed is tuning inside the design
that exists -- which is ST-23's retrieval and ST-37's latency work -- not
a change to the design.
The one thing that could still turn this into a change-request is G4. If a
real answer takes longer than 60 seconds at the 95th percentile on this
corpus, that is a product-shape problem and not a tuning problem, and
nobody knows yet.

TWO JOURNAL ITEMS CLOSED BY THIS RUN, both smaller than feared:
- the per-file registry commit cost (open since ST-17): 0.23s for a
  3-file workspace and 0.32s for a 10-file one when nothing changed, so
  32-77 ms per file. Invisible next to embedding.
- ST-17 self-review finding 1, the per-file workspace-wide parent scan:
  re-ingesting ONE changed file took 33.2s and the deletion path read all
  128 of the workspace's parent JSONs to find that file's own. At this
  size it is noise inside a 33s embed. The extrapolation in that finding
  (~75,000 reads for a G5-sized workspace) still stands as arithmetic and
  is still unmeasured at that size.

ONE ITEM STILL OPEN and it cannot be closed with this corpus: the cost of
RE-ATTEMPTING a failed or skipped file on every sync. Corpus v1 contains
no scanned or corrupt file -- the ST-07 gate refuses one on purpose -- so
there is nothing here that exercises the path. It needs a deliberate bad
fixture, which is a different job from measuring the real corpus.

The pre-ST-18 number below is kept because it is still true and it is now
in context: chunking was never the G5 factor, embedding always was.

```
Name:       Chunking time for the G5 corpus
Measures:   Wall time for chunk_document over ~200 pages of markdown
Rule:       1,275,492 chars, 600 H1 sections, single call, warm process
Population: Developer machine (MB's laptop), not a user-facing path
Window:     Point measurement, re-run per release
Good:       Under 5s
Act at:     Over 30s -> chunking has become a G5 factor and needs profiling
Owner:      YL (ST-18 spike owns the real end-to-end numbers)
Measured:   0.03s on 2026-08-09 -> 600 parents, 3,600 children
```
Read honestly: this says chunking is nowhere near the G5 budget of 10
minutes for 200 pages. It says NOTHING about the budget itself, because
embeddings (ST-15) are the expensive stage and have not been written.
- CLOSED by ST-15 (8e5a734). Child text from `chunking.py` is RAW; the
  mandatory `passage: `/`query: ` prefixes now live behind `embeddings.py`'s
  one private encoder seam, added exactly once. See ST-15's Done entry
  for the review finding this almost slipped through anyway: a version of
  the prefix tests that passed even with the config prefix emptied out.

## CLOSED ESCALATION: citations named the wrong part of a long document
Raised AND WITHDRAWN 2026-08-23. Kept in full, including the mistaken
framing, because the mistake is the useful part.

WHAT WAS WRONG WITH THE ESCALATION: it claimed the good fix required a
change request against signed architecture 7.5. Re-reading 7.5 shows it
constrains where parents are SPLIT ("markdown headings H1-H3, merged
below 2,000, split above 4,000") and names `section_label` as a field --
and says NOTHING about how that label is computed. The precise fix was
therefore available all along with zero deviation, and asking a human to
arbitrate a spec change was wasted. Lesson: quote the clause before
declaring something spec-bound. "It is in the signed pack" is not the
same as "the signed pack decides it".

FIXED on `fix/S1-citation-marker-labels`: a parent and a child are
labelled by the citable markers inside their OWN text (config
`parent_citation_marker_pattern`, default `Article\s+\d+`), falling back
to the enclosing heading when there is none. Measured on the real corpus:
distinct parent labels 10 -> 82, child labels 584 distinct across 800
children, 0 mislabelled, 0 children still cited by a heading, and the
CNSS guide plus the technical manuals unchanged because they have no
numbered unit. 7 mutations, 7 killed. DECISIONS row supersedes the
escalation row rather than editing it.

The original text follows, unedited.

Raised 2026-08-23 by the ST-17 real-document run. Needs a HUMAN decision
because the good fix deviates from a signed spec (CLAUDE.md rule 1).

MEASURED, not suspected, on the real Moroccan labour code:
  313,255 chars | 119 pages | 588 distinct "Article N" | 22 markdown headings
  -> 84 parents carrying 10 distinct labels
So a passage from Article 235 is cited as "Titre II : Definitions". That
is not merely vague: it points the reader at the wrong part of the file.
F-03 ("every answer cites file name and section label") is in the
never-cut set, so this is not cosmetic.

The rule being broken is chunking's OWN, stated in `_merged_label`:
"Labelling a parent that spans Articles 1 to 3 as 'Article 1' would cite
a sentence from Article 3 under the wrong heading -- a quietly wrong
citation." ST-14 applied that to the MERGE path. The SPLIT path
(`chunk_document` -> `_split_oversized`) gives every piece of one
oversized section the same label, which is the same defect.

Three options, and the choice is a product decision:
  (a) label split parents "Titre II : Definitions (2 of 9)". Stays inside
      7.5, honest, still does not say "Article 235".
  (b) also split on a configurable citation pattern (`^Article \d+`).
      Precise and what a legal corpus actually needs. DEVIATES from
      architecture 7.5 ("parents split on markdown headings H1-H3"), so
      it needs a change request against the signed pack, not a code edit.
  (c) accept it and let ST-24/ST-27 present the label as approximate.
Recommendation: (b) via a change request, with (a) as the interim. Not
started -- no story owns it. DECISIONS row filed.

SEPARATE and already fixed on `fix/S1-citation-label-markup`: heading
markup was leaking into the label itself (`**G-** **<u>Securite sociale
et charges sociales</u>**`). That one needed no spec change.

## ST-17 RULE-5 REVIEW PASS -- DONE 2026-08-23 (the debt above, paid)
Post-hoc, against 0210408 as merged, read on main at e1e4098. The two
things the review was told to start with BOTH HELD, and saying so is
half the value of having run it.

VERIFIED, not accepted: the cross-module `change_detection` split.
`_STATUS_WITHOUT_DERIVED_DATA` (removed+failed+skipped) and
`_STATUS_ALREADY_REPORTED_REMOVED` (removed only) genuinely answer two
different questions, and the SECOND one is the half nobody would think
to check -- widening it would strand a `failed` row whose file the user
then deleted, forever. Both directions are pinned by tests, including
one asserting an `active` row with identical bytes is still UNCHANGED so
the fix cannot degenerate into "re-ingest everything every sync".
A property the ST-17 entry did not claim and which the review adds: this
split is ALSO what makes crash residue self-heal. A crash between
`save_parents` and `upsert_children` writes status `failed`; the widened
set turns that into NEW on the next run, so `_ingest`'s unconditional
delete sweeps the orphan parents. Before the split it would have been
UNCHANGED forever with zero passages and stranded parent files.

VERIFIED BY RUNNING IT, which is the only way this claim was ever going
to be worth anything: the parents-before-vectors write order in
`_ingest`. The two calls were SWAPPED and the suite re-run --
`test_an_interrupted_write_never_leaves_a_vector_without_its_parent`
goes red with `ParentNotFoundError` from parent_store.py:171. So the
module docstring's ordering claim is test-enforced, not merely asserted.
Worth knowing about that test: under the CORRECT order its assertion
loop runs over an EMPTY list, so its green means nothing on its own and
its entire value is in the mutant. That is the shape ST-16 flagged; it
is fine here BECAUSE the mutation was actually run.

DEFECT FOUND AND FIXED on `fix/S1-ST-17-unsupported-double-row` (PR #40):
ONE FILE COULD PRODUCE TWO REPORT ROWS, and the second one deleted data.
The REMOVED sweep in `detect_changes` excluded only `scan.unreadable`
from its "gone from disk" test, never `scan.unsupported` -- although both
are present on disk and both produce no fingerprint. A file already
carrying a document row that later falls outside
`supported_document_extensions` therefore landed in the unsupported list
AND the REMOVED sweep. Reproduced before the fix:
```
REPORT ITEMS: [('code.md', 'skipped'), ('code.md', 'removed')]
PERSISTED   : [('code.md', 'skipped'), ('code.md', 'removed')]
COUNTS      : {'removed': 1, 'skipped': 1}
```
That breaks rule 1 of sync.py's own docstring, and the Removed branch
deleted the file's vectors and parent files while the Skipped row told
the user nothing had happened to it. The module's own comment already
stated the rule that forbids it ("Removed means gone from disk, not 'we
had trouble with it'"); it was applied to half the cases. Reachable via
a config narrowing, which is an operator setting -- config.py notes PPTX
moving the other way for ST-48, so the list is not frozen. Product call
made by the human: ONE Skipped row and the passages KEEP answering.

AND THE REASON IT WAS INVISIBLE, fixed in the same change: every helper
in test_sync.py keys by file name -- `_results()` at line 205, and
`test_every_report_row_is_persisted_as_a_sync_item` on BOTH sides of its
comparison. A dict collapses two rows for one file into one, so NO test
in that file could see a file reported twice, including the
"all six result values in one run" test the ST-17 entry singles out as a
whole-report equality. That test now compares ordered lists.

## ST-17 review-pass findings NOT fixed (found 2026-08-23, no owner)
Three more, left alone because sync.py was not otherwise being edited
and the scoped boy-scout rule says an unrelated drive-by belongs in its
own change. All three were REPRODUCED, not reasoned about.

1. `_ingest` THROWS AWAY `unreadable_parent_files`. `_remove` surfaces it
   in the report row via `UNREADABLE_PARENTS_NOTE`; `_ingest` discards
   the whole `StoreDeletion` return value. Proven: a corrupt parent JSON
   planted in the workspace survived a re-ingest with the report row's
   reason `None`. Worse, that litter can NEVER be deleted --
   `list_parent_ids` cannot read its `source_file`, so no
   `delete_document` will ever name it, and only
   `delete_workspace_parents` clears it. ST-16's `StoreDeletion`
   docstring says the counts exist precisely so the two stores drifting
   apart becomes visible; ST-17 discards them on the hot path.
2. `last_synced_at` is NEVER updated for an UNCHANGED file. The UNCHANGED
   branch in `_run` writes no document row at all. Proven: two syncs,
   byte-identical timestamp. The column says "last synced" and the value
   means "last ingested". Needs a product call, not a code fix, and it
   belongs with whoever renders the S2 file table (ST-28).
3. A FOLDER-LEVEL FAILURE persists as a FINISHED run with six zeros,
   indistinguishable from a clean sync of an empty folder. `sync_workspace`
   finishes the run row in its `finally` (correct -- it is what stops a
   dead sync blocking the workspace forever) but `sync_run` has no error
   column (db/schema.sql lines 41-49) and openapi derives `state` from
   `finished_at` alone. The exception does reach the caller, so the live
   screen is fine; it is the persisted HISTORY that lies. ESCALATION-
   SHAPED, not a bug: the schema is signed, so closing it needs a change
   request, not a code edit. Nobody owns it.

UNVERIFIED, and it stays unverified until someone runs it: a file that
becomes unreachable rather than deleted (a dangling symlink, an offline
network target) fails `entry.is_file()` in `scan_folder`, so it misses
BOTH `unsupported` and `unreadable` and falls through to the REMOVED
sweep -- which would delete its chunks. That is the "unplugged drive"
failure `FolderNotFoundError` exists to prevent, at per-file scale, and
ST-17 is the story that made it destructive rather than merely a
classification. THE PROBE COULD NOT RUN: Windows refused the symlink
with `WinError 1314, a required privilege is not held by the client`.
Not a finding. Settled by one elevated shell or one POSIX machine.

## ST-17 self-review findings NOT fixed (found 2026-08-23, no owner)
Found by reading sync.py adversarially after it was merged. Neither is a
correctness bug, both are recorded so they do not become facts by
silence. Neither was fixed, because sync.py was not otherwise being
edited and the scoped boy-scout rule says an unrelated drive-by belongs
in its own change.

1. `delete_document` is now on the HOT PATH, and this is a finding
   against ST-17's own design rather than against ST-16.
   `_ingest` calls `vector_store.delete_document` unconditionally before
   converting every NEW or CHANGED file. That was a deliberate choice and
   it is still right for correctness -- it is what cleans crash residue
   and shrink residue. But `parent_store.list_parent_ids` reads EVERY
   parent JSON in the WORKSPACE to filter by source_file, and its
   docstring accepts that cost explicitly "which is why this is a
   deletion-path function and not something an answer ever calls". ST-17
   turned it into a per-file, per-sync function, which ST-16 never
   anticipated.
   Cost is files x parents_in_workspace JSON reads per sync. MEASURED on
   the smoke corpus: 3 files x 99 parents = ~297 reads for HR, 10 x 100
   = ~1,000 for the manuals -- invisible at that size. EXTRAPOLATED, and
   labelled as such because it has NOT been measured: a G5-sized
   workspace of ~50 files and ~1,500 parents is ~75,000 JSON reads per
   sync. Against a 10-minute budget that may still be fine; nobody knows.
   ST-18 owns finding out, and this is now a named thing for it to
   measure rather than a surprise. Cheap fix if it bites: one pass over
   the workspace directory per sync, grouped by source_file, instead of
   one pass per file.
2. Two sources of truth for one workspace's folder. `sync_workspace`
   reads the workspace row and passes `folder` down to `_run`, while
   `detect_changes` independently re-reads the same row and returns
   `report.folder_path`. `change_detection`'s own docstring says the
   folder "comes from the workspace row, never from a caller argument"
   precisely so one workspace's registry cannot be diffed against
   another's files -- and passing `folder` separately re-opens that door
   by hand. Harmless today (same row, same process, one read apart). Fix
   is two lines: drop the parameter and use `report.folder_path`.

## HANDOFF -- read this first, then stop reading (2026-08-27)
This file is long and most of it is history. Everything a new session
needs to START is in this section; the rest is evidence for claims made
here, to be consulted when a specific claim matters.

WHERE THE BUILD IS, updated 2026-08-30. Ingestion is finished and merged:
change detection, conversion, chunking, embeddings, both derived stores,
and the sync engine that wires them (ST-12 through ST-17). The answering
half is complete on the critical path and MERGED: the agent graph and its
trace (ST-21), hybrid retrieval with the grader and the reword (ST-23),
and the answer node with its source contract and honest refusal (ST-24).

**SANAD CAN NOW BE LAUNCHED AND LOOKED AT.** ST-27 is green on
`feat/S2-ST-27-chat-screen` and NOT yet merged: `app.py` plus a `ui/`
package give S1, the chat screen, server-rendered off the FastAPI host.
`uv run python app.py` starts it. The sentence this paragraph carried
until today -- "there is still NO UI and NO app.py, so Sanad cannot be
LAUNCHED" -- is the one ST-27 exists to falsify, and it is left visible
above in the correction below rather than quietly deleted.

THE SEAMS. `agent/ports.py` defines eight callables. FIVE are real --
`retrieve`, `grade`, `reword`, `fetch_parents`, `write_answer` -- and
every one of them is on the answer path. Three are stubbed and NONE is on
the critical path: `clarify` and `rewrite` (ST-22) and `summarize`
(ST-25). Read `agent/ports.py` before anything else; it names each seam's
owner and contract, and it is the file that says why there are no
defaults.

CORRECTION TO THIS SECTION'S OWN PREVIOUS TEXT, kept rather than
overwritten because the shape repeats: it said "four are real ... only ONE
is on the critical path", which was true on 2026-08-27 and false the next
day. A handoff section is the fastest-rotting prose in this file, because
every story exists to falsify one of its sentences. Date any count written
here and expect to revisit it.

WHAT IS TRUE ABOUT MODELS, as of 2026-08-27. Cloud mode WORKS: a Gemini
key is in a local `.env` and `gemini-3.6-flash` answers. Strict-local
does NOT: `ollama` is not installed and nothing listens on 11434. So a
story can now be proven against a real model -- and should be, by hand,
because that is exactly what found the retired model name that no test
could see.

## ST-27, THE CHAT SCREEN (2026-08-30, YL) -- on a branch, not merged

WHAT LANDS: `app.py` (FastAPI host, template routes) and a `ui/` package
-- `ports.py` composes the real agent, `runs.py` holds one question in
flight, `conversation.py` decides what renders, `screen.py` decides which
state the screen is in, plus `ui/templates/` and `ui/static/`. Jinja and
hand-written CSS per CR-02; ADR-10 intact, nothing vendored, no npm.

MEASURED, in gate.yml order, on the branch: `uv sync --frozen` clean (170
packages), `uv run ruff check .` exit 0, `uv run pytest` **598 passed / 2
skipped**, exit code 0. Secret scan: `gitleaks detect --no-git` over the 20
files this branch touches, **"no leaks found", exit 0** -- SCOPE STATED,
that is this branch's files, not the whole history; a full-history
`gitleaks detect` timed out twice at nine minutes on this machine.

**ST-51 IS NOT A DEPENDENCY AND THAT IS ADR-13 PAYING OFF.** The UI calls
`agent.graph.ask` IN-PROCESS, so the screen holds the real `Answer`
object. There is no JSON round trip and no second copy of the openapi
contract to keep in step. ST-51 mounts `/api/v1` on this same host later;
its exit gate is "UI unchanged when mounted", which is why every screen
route here sits under `/chat` and nothing answers on `/api`.

THE ONE DESIGN PROBLEM WORTH READING, because it is the only part that
was not obvious: **the loading stage hints.** UX spec 6.3 wants
"Searching the workspace", then "Checking the answer", then "Writing";
principle 3 says "Never fake progress ... say what is actually
happening"; and a synchronous form POST can say nothing at all. The
answer was to run `ask` on a worker thread and read the stage AT THE PORT
SEAM -- entering `retrieve` IS searching, entering `grade` IS checking,
entering `write_answer` IS writing. Nothing is timed and nothing is
estimated. The wrapper is one `dataclasses.replace`, so `agent/` is
untouched.

That decision paid for two more things it was not chosen for: **Cancel**
became real (the flag is checked at the next seam, which is literally
6.3's "stops after the current stage"), and **the passage viewer** got
its sections, because `write_answer`'s own arguments ARE what the answer
was written from.

A DEFECT CAUGHT BEFORE IT SHIPPED, and it is this project's recurring
shape: the first draft recorded the passages at `fetch_parents` and then
re-derived which of them were cited. That is two filters agreeing --
exactly what `agent/nodes.py:418` says it built ONE tuple to prevent.
Moved to the `write_answer` seam, where the arguments are that same
tuple. A source card and the passage it opens are now two views of one
list rather than two lists that happen to match.

A DEFECT CAUGHT BY RUNNING IT, which no amount of reading would have
found: on a machine with no `data/sanad.db`, `GET /` raised
`RegistryNotFoundError` and served a stack trace instead of criterion 1's
"No workspace yet" -- **the first screen a new operator ever sees.** Found
while seeding the demo workspace, not by a test. `app.py` now calls
`repo.ensure_schema` in its lifespan, and the test that pins it
deliberately does NOT create the database first.

## THE LIVE RUN, 2026-08-30 -- real corpus, real model, real browser route

The exit gate says "demonstrated live", so it was, against the REAL
things rather than fixtures. A workspace was created over
`data/corpus/hr` with the legal flag set, and Sanad's own Sync indexed
it: **2 documents active, 217 pages (201 + 16), 118 parent sections,
1,255 seconds.** The server was `uv run python app.py` on 127.0.0.1:8000
and every figure below was read off an HTTP response from it.

| S1 state | How it was demonstrated |
|---|---|
| Empty, with documents | LIVE. Sample questions naming both real files, plus the sources line |
| Loading, three stage hints | LIVE, sampled once a second: t=1 "Searching the workspace", t=3 "Checking the answer", t=4 "Writing" |
| Error | LIVE. Server restarted with `MODEL_MODE=banana`; the panel named the exact failing value |
| User variant | LIVE |
| Answer variant | LIVE. 5 source cards, disclaimer line present (legal workspace) |
| Refusal variant | LIVE. 7 searches disclosed, 0 source cards, no disclaimer |
| Clarification variant | TEST ONLY -- ST-22's stub means the running app cannot produce one |
| Source cards + passage viewer | LIVE. Article 14's whole section, 3,811 chars, with the 512-char retrieved chunk marked |
| Interrupted (cancel) | LIVE. "Incomplete -- not an answer", no sources, input re-enabled |
| No workspace / no documents | TEST ONLY -- the live machine has both |

THE ANSWER IT ACTUALLY GAVE, because a screenshot of a state is not the
same as a correct product. Asked "Quelle est la duree de la periode
d'essai pour un cadre ?", `gemini-3.6-flash` answered from **Article 14**
-- three months for cadres, renewable once, with the fixed-term rules
beside it -- and cited Articles 14, 13, 80-82 and 502-503 of the
consolidated code. The retry marker read 0 for that one. The refusal run
("Comment cuisiner un tajine aux pruneaux ?") disclosed 7 searches and
its marker read "Reworded 2 time(s)", which is exactly
`config.retry_ceiling = 2`: the number shown IS the number the loop ran.

ENCODING CHECKED RATHER THAN ASSUMED, because a French corpus in a
Windows terminal is where mojibake hides: the served page decodes as
UTF-8 with **zero replacement characters**, and the accented bytes are
real codepoints (0xe9 for é, 0xe0 for à). The console this was read in
cannot display them; the page is fine.

**A COLD PROCESS IS UNRESPONSIVE ON ITS FIRST SEARCH, and it is parked,
not fixed.** The first `retrieve` in a fresh server loads the real
encoders (sentence-transformers + the fastembed BM25 model), and while
that happens the server served no other request for minutes -- the stage
hint sat on "Searching the workspace" and even `GET /chat/messages`
never reached the log. OBSERVED, and the GIL is the likely cause rather
than a proven one; nobody has profiled it. It is a warm-up cost, not a
defect in the screen: the second question in the same process answered in
seconds. Two things follow. For the defense, ASK ONE QUESTION BEFORE THE
JURY WALKS IN (ST-30's demo script should say so). For a future story,
the fix is a startup warm-up in `app.py`, which trades a slow boot for a
fast first question -- deliberately NOT improvised here, because it makes
`uv run python app.py` take half a minute before it serves anything and
that is a call for whoever owns the demo.

## ST-27's TWO REVIEW PASSES, 2026-08-31, and what they cost

Both ran on the branch before merge, per rule 5. **Seven stories running
now** on the claim that a post-green review finds a real defect: this one
found nine, five of them blocking, on a branch whose whole gate was green.

THE TWO BLOCKING FINDINGS BOTH PASSES AGREED ON, and neither was visible
in any test, any lint or any live run:

1. **TWO LIVE RACES, and the screen produces them by itself.** Starlette
   runs a plain `def` route on a threadpool, and this page polls every
   700ms while it is open. So `settle` -- read the run, check it is done,
   clear it -- had two threads pass the check and append ONE answer
   TWICE, into the transcript and into `turns`, which then fed a
   duplicated exchange back as F-07 memory. And `_start` read `busy`,
   then assigned `conversation.run` on a later line, so a double-clicked
   Send started TWO paid model runs and silently discarded the first.
   Both are now one locked step (`Conversation.begin`, `Conversation.
   settle`).
   AND THE FIRST VERSION OF THEIR TESTS WAS VACUOUS -- caught by running
   the mutation rather than by reading. Releasing 16 threads off a
   `threading.Barrier` and asserting the outcome PASSED with both locks
   removed, because CPython does not switch threads inside a check that
   does no I/O and allocates nothing. That is hoping for an unlucky
   interleaving. The `done` read now sleeps 20ms, so without the lock
   every thread sleeps at once and acts on the same stale answer: red at
   `assert 3 == 1`, twice, and green with the locks back. A barrier
   INSIDE the critical section is not the fix -- the correct code would
   deadlock on it.
   THE DOCSTRING WAS THE TELL: it said "no second reader to race with".
   One user is not one thread.
2. **CANCEL DID NOTHING DURING "WRITING".** The checkpoint only fired when
   the NEXT port was entered, and `write_answer` is the last one -- so the
   flag set during the one stage a user actually waits through was never
   read again. The button was decoration on the stage that needed it. Now
   checkpointed after the write; the accepted cost is that a completed,
   paid-for answer is discarded, which is what "stops after the current
   stage" means. The suite was green over this because the cancel test
   gated on `grade` and never on `write_answer`.

THE OTHER THREE BLOCKING ONES:
3. **A passage link resolved against whatever workspace was ACTIVE when
   it was followed.** Switch workspace, press Back, open a source card,
   and you read a different workspace's section -- silently, looking
   entirely correct. That is F-01 isolation. The URL now carries the
   workspace id, and a test follows the same message/card coordinates
   against a second workspace and requires the "no longer on screen" page.
4. **THE ERROR PANEL COULD PRINT THE API KEY.** UX spec 5 wants "the exact
   failing value", and Google AI Studio puts `?key=...` in the request URL
   that its SDK exceptions carry. A failed call would have rendered the
   key on screen and into any screenshot or projector. Redacted by EXACT
   CONFIGURED VALUE rather than by guessing what a key looks like.
5. **`vector_store.open_store()` in the lifespan had never executed under
   test.** Every test passes a `ports_factory` and takes the early
   return. It ran live, twice, by hand -- which is evidence, not a check.
   Now covered.

NON-BLOCKING, all fixed here except where noted:
6. UX spec 4's "the chat area shows a one-line notice that the
   conversation context has moved" was simply **missing**, and had not
   been declared as missing either. Now rendered on the workspace switch.
7. **THE POLITE LIVE REGION NEVER ANNOUNCED ANYTHING.** The only path that
   added a message was a full page load, and a live region announces what
   is INSERTED into it, never what was already there when the document
   loaded. `aria-live` was correct markup doing nothing, and the test that
   asserted `role="status"` was in the page could not tell the difference.
   The poll now appends the finished answer into the existing list. The
   `<noscript>` path still reloads and still cannot announce; that cost is
   real and is accepted.
8. `.cited { padding: 0 2px }` was off UX spec 3.2's spacing scale ("a
   value not on this scale is a bug"). Fixed, and a test now sweeps every
   padding, margin and gap in the stylesheet -- proven by putting a 3px
   value back and watching it fail.
9. **CRITERION 4 IS UNVERIFIED and is not claimed.** "Closing the passage
   viewer returns focus to that same card" rests on `<dialog>.showModal()`
   doing it, which is the platform's own behaviour and the reason a
   `<dialog>` was chosen over a hand-rolled overlay. Nothing here drives a
   real browser, so nothing here has watched it happen. OWNER ST-38.

## AN ESCALATION FOR UX-01's OWNER (rule 1), raised not decided

**Two signed sentences disagree about the text inside a source card.**
Design principle 1 says a source card is "never smaller than body text".
Section 3.3 puts the Mono role at 13px, and file names and section labels
are exactly what that role is for. A card's file name is both things at
once, and body is 15px.

An earlier version of `sanad.css` settled this in a code comment, at
13px. That is the reinterpretation rule 1 forbids -- "if a spec is wrong
or ambiguous, escalate; never edit the spec to match the code" cuts both
ways, and quietly picking one clause over another is the same move.

SHIPPED AT BODY SIZE pending a ruling, for two stated reasons: between
two signed readings the accessible one is the safer place to sit, and
principle 1 is the more specific sentence -- it names this component.
Reverse it in one line if the ruling goes the other way.

WHAT THE SCREEN CANNOT DO YET, and none of it is hidden:
- **The clarification variant cannot appear live.** `ui/ports.py` stubs
  ST-22's `clarify` to None. The screen renders the variant and a test
  drives it through the real graph with a clarify port written out loud,
  but nothing in the running app produces one. ST-22 closes it.
- **F-07 memory does nothing.** The conversation really collects its
  completed turns and really passes them to `ask`; ST-25's `summarize`
  stub throws them away. ST-25 closes it.
- **No rewrite-and-split.** A two-part question is one search (ST-22).
- **"Partial text kept" is vacuously true.** Section 11 asks an
  interrupted answer to keep its partial text and mark it incomplete.
  Nothing streams in V1 -- `build_write_answer` returns a whole string or
  raises -- so there IS no partial text, and the interrupted message says
  so instead of showing an empty bubble labelled incomplete. Whoever adds
  streaming inherits the other half.
- **The sample questions are file names, not good questions.** Parked with
  an owner: ST-19's golden set is where real ones come from.

TWO MORE DRIFTS IN `designrag-main/`, found while building against it,
which take the recorded list from five to seven. Both are worse than the
five, because both are the product lying rather than a style mismatch:
6. **IT FABRICATES SOURCE CARDS.** `ChatScreen.tsx:168-177`: when the API
   returns no sources, it falls back to two hardcoded mock passages. An
   answer with no evidence renders with two citations. That is the exact
   inverse of G3 and of `Answer.__post_init__`.
7. **THE STAGE HINTS ARE A TIMER.** `ChatScreen.tsx:111-112` advances the
   stage on `setTimeout` at 650ms and 1300ms, so the label reads
   "Verifying retrieved passages" at 700ms whatever the pipeline is
   doing. Design principle 3 bans it in one sentence.
Also: the reference's copy promises "confidence scores", which Sanad does
not have and has never had.

THE FIVE THINGS MOST LIKELY TO WASTE A NEW SESSION'S TIME:
1. Assuming the UI is React. It is not. `designrag-main/` is a gitignored
   picture; CR-02 puts the interface on Jinja templates and ADR-10 rules
   out a JS toolchain.
2. Rebuilding the chat-model seam. `agent/chat.py` exists and works.
3. Writing a prompt inline. `prompts/` is the registry and
   `agent/prompts.py` is the loader; three entries now show the shape
   (`relevance-grader`, `query-reword`, `answer-writer`).
4. Trusting a pinned external value. One was dead for five weeks and
   nothing in the repo could see it.
5. Editing another owner's modules. `change_detection.py`, `conversion.py`,
   `chunking.py`, `parent_store.py`, `vector_store.py`, `sync.py` and
   `embeddings.py` are MB's. Read and call them; do not change them.

REVIEW DEBT, now owed on TWO stories, not three: ST-21 (24479ba) and
ST-23 (af14c4e) merged without the rule-5 partner review. **ST-12
(1862a58) was the oldest and is PAID -- PR #65, merged 2026-08-30.** It
graded 6/10 DO NOT APPROVE and found three real defects in a module two
earlier reviews had already corrected twice, which is the argument for
paying the other two rather than writing them off. ST-24 is NOT on this list -- it is the first story on this project
to get both passes before merging, and that is exactly why the debt is
worth paying: its rule-5 pass said DO NOT APPROVE and its blocking finding
was a defect that discarded correct answers, invisible to a green suite
and to a 29-mutation battery. Six stories running now.

WHAT THAT REVIEW ACTUALLY COST, because "get a review" is cheap advice
until you see the bill: two passes, three versions of one regex, and the
second pass found the first pass's defect only partly fixed. Neither
defect could be seen by reading the code -- both lived in the interaction
between the parser and a sentence the prompt itself asks the model to
write. If a future story has a model reply to interpret, budget for this.

## REVIEW OF MB's SIX PRs, 2026-08-30 (YL), and three findings left OPEN

WHAT WAS REVIEWED: #61 (the graph project name), #62 (ST-07 Corpus v1 and
its fetcher), #63 (the ST-18 spike), #64 (the config-documentation drift
check), #65 (the ST-12 fix), #66 (a re-stamp). 2,425 insertions.

MEASURED, not judged by reading:
- the whole gate re-run on her main: `uv sync --frozen` clean, ruff exit
  0, **529 passed / 2 skipped**, `gitleaks detect` "no leaks found" --
  which also closes the one gap she declared, since gitleaks is not
  installed on her machine and is on YL's.
- THREE FAULTS INJECTED into her fixes, all three caught by exactly the
  tests she named. Her "proven in both directions" claim is therefore
  reproduced independently, not accepted.
- her spec citations checked 4/4 against the signed pack: G5, the
  1,500-page capacity line, F-02 criterion 3, section 11's Skipped row.
  Zero fabricated.
- her published arithmetic recomputed 3/3 exact (18.2% margin, 2.455 s
  per page, 61.4 minutes).
- HER `pathlib` CLAIM VERIFIED AGAINST THE INSTALLED SOURCE:
  `_IGNORED_ERRNOS` really is (ENOENT, ENOTDIR, EBADF, ELOOP) and EACCES
  really is absent, so her correction of the review's own diagnosis was
  right and the review was wrong.
- `_skip_unsupported` wiring confirmed through the code graph: it does
  reach both derived stores and the registry row.

Assessed at **89%**. The weighting is a judgement and is stated so it can
be re-weighed; the measurements under it are not. 40% product-code
correctness (full marks), 25% verification depth (24 -- she could not run
gitleaks and said so), 20% truthfulness of claims (full marks), 15% new
code under test (5 -- see below).

**THREE BLOCKING FINDINGS FROM THE COLD READ ARE STILL OPEN.** A fourth
and fifth were fixed in PR #68. These three were NOT, because they are
ST-18/ST-07's own design decisions and the corpus is not on YL's machine
to test a fix against. Owner MB, fallback 2026-09-13:

1. **A PAID RUN CAN LEAVE NOTHING BEHIND.** `answer()`'s docstring calls
   `traces.json` "the real output" and "the raw material ST-19's golden
   set gets written FROM", but the write sits AFTER the `if failed:
   return 1`. So a run where even one of the twenty questions errors pays
   for every provider call and writes no file. The PR #63 message quotes
   a traces.json holding 15 errors and no answers -- under the code as it
   now stands that file could not have been produced, so the artifact
   came from a path that no longer exists.
2. **RE-RUNNING `index` DESTROYS THAT PAID EVIDENCE.** `_fresh_run_dir()`
   calls `shutil.rmtree(RUN_DIR)` with no check and no warning, and
   `RUN_DIR` is where `traces.json` lives. Anyone who runs `answer --yes`
   (up to 141 provider calls) and then re-checks a speed number with
   `index` silently deletes it.
3. **`verify` NEVER CHECKS THE TEXT IS FRENCH.** ST-07's signed exit gate
   (BUILD-PLAN line 49) is "files open, French text selectable (not
   scanned), source+date logged per file". Nothing checks the language,
   and `fetch` skips any file that already exists without inspecting it.
   PRD section 17 names an ENGLISH translation of the same labour code,
   so a teammate holding that PDF under the manifest's file name gets
   "have" from `fetch`, "EXIT GATE MET" from `verify`, and every
   retrieval number thereafter measured against a corpus that breaks the
   French premise. A gate that cannot fail on the thing it names is not
   a gate.

WHY ALL OF THIS GOT THROUGH, and it is a config line rather than a habit:
`pyproject.toml:58` sets `testpaths = ["tests"]`, so `scripts/` is
outside every check. MB has every skill and both agents -- all eight
files under `.claude/` are tracked, `settings.json` and its two hooks
included -- and she used them, running two rule-5 reviews on her own
branches and mutation-proving her product code in both directions. The
tools were not missing. They were all pointed at the product, and the bug
was in the RULER: measurement code that is wrong does not crash and does
not fail a gate, it reports a better number than the truth. Every tool
she has depends on a test existing, and there were none.

## WHAT A PLAN SURVEY FOUND, 2026-08-28 (three things nobody had flagged)
Done by reading BUILD-PLAN against the repo rather than against this file,
after ST-24 merged. All three are facts about the repo, checked, not
inferred from the journal.

1. **ST-05 WAS NEVER DONE.** There is no `Dockerfile` and no compose file
   anywhere in the repo. Its exit gate is "`docker compose up` serves a UI
   stub in the browser". Nothing in this journal says it is outstanding.
2. **ST-03 IS NOT WHAT THIS FILE ASSUMED, and it is in better shape than
   the last entry implied.** There is no `ci.yml` -- only `gate.yml` --
   which is why an earlier entry said ST-03 was not a confirm-and-close.
   But its exit gate is "a deliberately failing test blocks a PR", and
   that IS demonstrated by history: of 71 `gate.yml` runs, **8 have
   failed**, every one of them on a `pull_request` event, across four
   branches (ST-02 x5, ST-12, and two chore branches). The gate is not a
   check nobody has watched fail.
3. **CORRECTION, and it is a correction of something this session almost
   recorded as fact: `main` IS PROTECTED.** The legacy branch-protection
   API returns 404 for this repo, which reads exactly like "no protection"
   -- and that is what it was briefly reported as. The repo uses GitHub
   RULESETS instead: `protect-main`, active, requiring a pull request,
   requiring the `verify` status check with a strict up-to-date policy,
   and blocking force-push, deletion and non-linear history. So ST-04 is
   done, a red gate genuinely does block a merge, and direct pushes to
   main are rejected by the platform rather than by good manners.
   The lesson is the project's own absence rule, in a new place: an API
   that 404s is UNVERIFIED, never a negative finding. Query the other
   endpoint before concluding a guard is missing.

## UI DESIGN REVIEW -- `designrag-main/` vs the signed UX spec (2026-08-27)
Read before starting ST-27 or ST-28. The design is a good base and got
most of the hard parts right; five things drifted from UX-01 v1.0 and one
of them is a real accessibility failure, not a preference.

WHAT IT GOT RIGHT, and it is more than a generator usually manages: all
four message variants (user, answer, refusal, clarification), all six
sync statuses, all three focus-trapping overlays (passage viewer, delete
confirm, create/rename), and the awkward states most mockups skip --
interrupted answers, partial reports, the blocked second sync, the
over-capacity warning, the missing folder. It has `aria-live` regions and
real `focus-visible` rings.

FIVE DRIFTS. The first is MEASURED, not an opinion:
1. **`border-strong` fails its contrast floor in BOTH themes.** The
   design dropped the spec's palette for Tailwind defaults. Mostly
   harmless -- text, muted, accent and focus all still clear their floors
   -- except `border-strong`, which UX-01 section 3.4 says must clear
   **3:1** because it is the only thing identifying a control boundary.
   Computed, not estimated: **1.48:1 light** (#cbd5e1 on #ffffff) and
   **1.88:1 dark** (#334155 on #090d16). Both fail. That breaks UX-01
   acceptance criterion 10, and it is precisely the trap section 3.4
   names: "getting this backwards is the usual way an interface fails
   1.4.11 while looking fine". The spec's own values pass: #6E7681 gives
   4.59 light and 3.94 dark.
2. **It invented two screens**: `ScreenId` includes `analytics` and
   `settings`. UX-01 section 13 rules out an analytics screen BY NAME,
   and the inventory is three screens.
3. **An avatar component**, imported into the chat screen. Section 13:
   "no multi-user presence, avatars, or account UI" -- V1 is single-user.
4. **No skip-to-content link.** Section 4 makes it the first focusable
   element on the page. Not found by two greps.
5. **No reduced-motion handling** (acceptance criterion 12), and no
   768px/1024px behaviour, so the desktop-only notice and the stacking
   source rail do not exist yet.
Also cosmetic but worth fixing at the same time: it uses a system font
stack rather than the humanist-sans + monospace pairing section 3.3
requires, and Tailwind's 16px body rather than the spec's 15px scale.

NONE of this blocks ST-27/ST-28 -- they are fixes to a reference, not to
shipped code. Fix them in the design, or accept each one in writing.

## Next (ordered queue, top 3 only)

**UPDATE 2026-09-05: ENTRY 1 IS NO LONGER "NOT STARTED".** See the top of
"Now" above -- the runner is built and tested on a fake scorer, on branch
`feat/S3-ST-32-evaluation-runner`, not merged. What is left of entry 1: get
a real `.env` key (blocker below, unowned by any agent), resolve the RAGAS
dependency escalation, then run it live and let ST-33/ST-36 follow. The
survey text below is kept as-is; it was accurate the day it was written and
is superseded, not wrong.

REWRITTEN 2026-09-03 after #74 merged. Entry C below is done, so the queue
is now unambiguous and has one name at the top of it:

**1. ST-32 EVALUATION RUNNER (YL) -- the whole critical path.** ST-32 ->
ST-33 -> ST-36 -> ST-41, and none of the four has started. Exit gate from
BUILD-PLAN line 93: **"One command -> dated report with per-question +
overall scores."**

A SURVEY WAS RUN ON 2026-09-03 BEFORE ANY CODE, and it is written out here so
the story does not re-pay for it. **No code was written: ST-32 is YL's row and
the survey ran on MB's clone, so it stops at the brief on purpose.**

WHAT ALREADY EXISTS, and this is the half the queue got wrong:
- **A COMPOSITION ROOT ALREADY EXISTS.** `ui/ports.py` builds all eight
  callables -- `build_ports(client, model, *, parents_path=None)` and
  `build_default_ports(client)`. **The line elsewhere in this file saying "no
  composition root builds the real AgentPorts yet ... ST-51" is STALE**; ST-27
  built one. DECIDED 2026-09-03 (human, DECISIONS row): the runner IMPORTS
  that one rather than writing a second. Two composition roots free to drift
  would mean the evaluation measures a differently-wired product than the app.
- **THE DATABASE SIDE IS DONE**, since ST-10: `db/repo.py` has
  `insert_eval_run` (line 438) and `insert_eval_result` (line 477), and
  `db/schema.sql` has `eval_run` (line 64) and `eval_result` (line 78), with
  cascade-delete already tested in `tests/unit/test_db_repo.py` and
  `tests/unit/test_workspaces.py`. Do not design a new table.
- **`ragas` IS ALREADY A DECLARED DEPENDENCY** and 0.4.3 is installed. No
  dependency conversation is needed, which is the one thing that would have
  required stopping to ask.
- `config.reports_path` already defaults to `data/reports/`, and architecture
  line 359 fixes the layout: `data/reports/<workspace_id>/<run_at>.json`,
  referenced from `eval_run.report_path`.
- The golden set is frozen at 40 + 20 (`617c972`).
  `tests/unit/test_golden_set.py` is the executable copy of the row schema.

**THE DESIGN PROBLEM THIS STORY HAS TO SOLVE, found by reading the objects
rather than by assuming:** RAGAS faithfulness scores an answer against THE
PASSAGES IT WAS GIVEN, and **neither `Answer` nor `Trace` carries passage
text.** `Answer.sources` is `(file_name, section_label)` only, and `Trace`
exposes `searches`, `files_consulted` and `retries` -- no text anywhere. So
the contexts have to be captured while the graph runs.

The route is already in the repo and should be reused, not reinvented:
`ui/runs.py:221` `observed(ports)` decorates an `AgentPorts` with
`dataclasses.replace` on the frozen dataclass, leaving ST-23's and ST-24's
callables untouched underneath. The runner wraps `fetch_parents` the same way
and keeps what it returned.

**AND THE SUBTLE HALF, which decides whether the number means anything:** feed
RAGAS the sections the writer ACTUALLY READ, not the retrieved child chunks.
ST-24's `make_answer` builds one `cited` tuple and uses it BOTH as what the
writer sees AND as what the source list is built from, precisely so the two
cannot disagree; the trace can say "loaded 4 of 5". Scoring against the 5
retrieved children instead of the 4 loaded sections measures a document the
model never saw, and would score the product down for a defect it does not
have. `Answer.trace`'s own docstring says the steps are kept in-process "so
F-10 and the evaluation runner can read them without a round trip" -- that
sentence was written for this story.

WHAT THE REPORT MUST CARRY (PRD F-08 + architecture 5.3), all three, because
ST-33 gates on them and cannot compute what the runner did not record:
- per-question AND overall groundedness and relevancy, plus the run date;
- G2's refusal correctness per out-of-scope row -- 20 of 20, no invented
  answers. `Answer.refusal` is derived from `kind`, so it is not a judgement
  call the runner has to make;
- G3, sources on 100% of answers. Cheap here and worth recording explicitly:
  `Answer.__post_init__` already REFUSES to construct an answer with no
  sources, so a violation cannot reach the report as data -- it raises. Record
  it as measured rather than assuming it, or the report claims a gate nothing
  checked.
- **the failing questions BY ID**, because F-08 says the release is blocked
  and "the failing questions are listed".

**THE ONE THING THAT DOES BLOCK A REAL RUN, and the previous version of this
entry was wrong to say nothing blocks it: `.env` ON MB'S CLONE PINS
`CHAT_MODEL_CLOUD=gemini-2.0-flash`,** the name Google retired and PR #55
removed from `config.py`'s default. The code default is correct
(`gemini-3.6-flash`); the `.env` file overrides it with the dead one, and
pydantic-settings applies that override silently. A key IS present (56 chars).
`.env` is git-ignored and holds a secret, so no merge can fix it and no agent
should edit it -- it is a one-line by-hand change on that machine. This is the
`.env` blocker recorded above, now CONFIRMED LIVE rather than suspected. **Not
proven by an actual model call**, which would spend credits; the evidence is
that the loaded setting reads `gemini-2.0-flash` and PR #55 is the record of
that name being retired.

READ BEFORE SCORING ANYTHING: `evaluation/golden/README.md`'s caveats, and
note there are now **THREE arguable out-of-scope rows, not one** --
`g-out-005`, `g-out-019` and `g-out-020`, each refusing something the corpus
genuinely lacks while sitting beside something it holds. G2 wants 20 refusals
of 20, so a model that answers one of them WELL costs the gate a point.
`g-in-015` also quotes a figure from an undated guide.

UNVERIFIED, and it is the first thing to settle: **the RAGAS 0.4.3 metric API
has not been checked against current documentation.** That library renamed and
restructured its metrics across the 0.1 / 0.2 / 0.3 lines, and nothing in this
repo imports it yet, so there is no in-repo example to copy. Verify the import
path and the evaluate() signature against the current docs before writing
against remembered shapes -- and note RAGAS itself needs an LLM and an
embedding model configured, which is a second place credits get spent and a
second thing ADR-12's manual dispatch is protecting.

**2. THE UNPAID-REVIEW LIST IS DOWN FROM FOUR STORIES TO TWO HALF-STORIES.**
ST-21 (clean) and ST-23 (one defect fixed, one parked) are PAID on their
source; ST-19 and ST-29 are paid on their out-of-scope rows, which is the
half BUILD-STATE named as mattering. **What is still owed:**
- ST-19 + ST-29: their thirty IN-SCOPE rows and their reference answers.
- ST-21 + ST-23: their TEST FILES. Source was read; tests were not, and
  ST-21 alone ships 1,099 lines of them. This project has shipped six
  fixtures too small for their own property, so that is not a formality.

Every one of these reviews found something the green gate did not: ST-35's
freeze could not fail, `g-out-008` was a false refusal, and ST-23 was letting
user input into a prompt template. **Nine stories running.** Whoever argues
the remaining halves can be skipped is arguing against a nine-for-nine record.

**3. ST-22 CLARIFICATION + REWRITE-AND-SPLIT (YL)**, unchanged, detail below.

ONE THING THE ST-35 REVIEW LEFT FOR A LATER STORY, parked rather than
improvised: `FROZEN_TOTALS` closes the accidental-drift hatch but can still
be edited under its own version name. The stronger design is a committed
manifest the test does not generate. Not done here because it adds an
artifact whose only reader is one test, and because the residual is now
written down in two places instead of being invisible. Whoever owns the next
evaluation story decides.

Previous queue text, kept for its ST-27 entry:
MERGED 2026-08-31. ST-27 and MB's re-stamp (#71) rewrote this queue at
the same time; hers is the newer and fuller list and is kept as the base,
with ST-27 folded in. Her entry A stands unchanged and still outranks
both UI stories.

0. ~~MERGE ST-27~~ **DONE -- merged as #72, c70c654 on main, 2026-08-31.**
   Gate re-run on main after the merge: 621 passed / 2 skipped, ruff exit
   0, gitleaks clean over the whole tracked tree. Both review passes were
   paid before it landed and their nine findings, five blocking, are
   fixed. See the ST-27 review section above.
   IT IS ALSO THE COUNTER-EXAMPLE TO ENTRY B BELOW. Two of the five
   blocking findings were live thread races that a green suite, ruff and
   several by-hand runs of the real server had all passed over, and one
   was a Cancel button that did nothing on the only stage a user waits
   through. That is the seventh story running where a post-green review
   found something real, and it is what the four unpaid ones are being
   compared against.

REWRITTEN AGAIN 2026-08-30, after #67 and #70 merged. The previous version
of this queue named ST-19's review and ST-29 itself; both are overtaken.
The three that matter now:

A. **ST-32 EVALUATION RUNNER (YL).** The critical path to a V1.0 gate:
   ST-32 -> ST-33 -> ST-36 -> ST-41, and NONE of the four has started.
   Every blocker is gone -- it needed ST-24 (merged) and a golden set to
   run on (45 questions on main). It reads `evaluation/golden/*.jsonl`;
   the field list is in `evaluation/golden/README.md` and
   `tests/unit/test_golden_set.py` is the executable copy of it. Read the
   two honest caveats in that README before scoring anything: `g-in-015`
   quotes a figure from an undated guide, and `g-out-005` is arguable.
B. **THE FOUR UNPAID REVIEWS: ST-21, ST-23, ST-19, ST-29.** This list
   doubled today because both golden-set PRs merged on the human's
   instruction without a rule-5 pass. It is not bookkeeping: ST-12's
   review, when it was finally paid six weeks late, found three real
   defects, one of which let the product cite a file the report called
   Skipped. For ST-19 and ST-29 the rows to read are the fifteen
   out-of-scope questions, because those are what G2 is graded on.
C. ~~**ST-35 GOLDEN SET COMPLETE AND FROZEN (MB).**~~ **DONE -- merged as
   #74, `617c972` on main, 2026-09-03, branch deleted.** 40 + 20, grounding
   script green on all 60 rows. Gate re-run on main after the merge: 623
   passed / 2 skipped, ruff exit 0, grounding "OK: 60 rows grounded"; step 4
   on CI only, this clone has no gitleaks. **It was REVIEWED before merging,
   unlike #67 and #70, and the review is why this entry is worth re-reading:
   the freeze it was built to deliver could not fail.** 19 mutations had been
   reported all killed and the one realistic post-freeze edit was not among
   them. See the top of Now.
   The prediction in this entry held exactly -- it WAS one `EXPECTED_COUNTS`
   row plus `batch3.jsonl` -- but that was the cheap half twice over: first
   the two out-of-scope questions that had to be thrown away, then a freeze
   mechanism that read as done and was decoration.
   **What it unblocks: ST-36 now has a genuinely frozen set to score against,
   so the critical path is entirely entry A.**

A NOTE FOR WHOEVER WRITES BATCH 3, so the lesson is not re-paid: read
`evaluation/golden/README.md` before drafting a single out-of-scope
question, and run `uv run python scripts/golden_grounding.py` before
believing any of them is absent. See the byte-grep entry in Now -- a
byte-wise grep reported ZERO occurrences of `préavis` in a document holding
forty, and four questions were nearly written on that zero.

AND ONE THING NEITHER STORY FIXED, inherited from #69's root-cause finding:
`testpaths = ["tests"]` in pyproject.toml puts `scripts/` outside every
check. `scripts/golden_grounding.py` is in that blind spot. It has been RUN
and its output quoted with a date, but nothing asserts it, so a change to
it would break silently. Its control probe is all that stands in for a
test. Owner MB, alongside the three ST-07/ST-18 script findings #69 parked.

1. **ST-22 CLARIFICATION + REWRITE-AND-SPLIT (YL)**, whose value went UP
   with ST-27: the clarification message variant is now built, rendered
   and tested, and `ui/ports.py`'s stub is the only reason a live run
   cannot produce one. Filling `clarify` turns an already-built screen on.
2. **ST-28, THE WORKSPACES SCREEN (S2)**, which ST-27 now points at from
   four places -- the no-workspace state, the no-documents state, the nav,
   and the "run Sync" pointer. Until it exists a new operator cannot
   create a workspace from the interface at all; today that takes a
   script. The shell, the design tokens, the components and the
   state-resolution pattern are built and reusable, so S2 is mostly its
   own screen rather than its own system.

SUPERSEDED QUEUE, kept below because the ST-21 correction inside it is
still worth reading:
0. ST-22 CLARIFICATION + REWRITE-AND-SPLIT (YL). The last two model seams,
   `clarify` and `rewrite`, and the graph already routes to both -- so it
   is two registry prompts plus one module, the same shape as ST-23 and
   ST-24. Exit gate: an ambiguous fixture triggers exactly ONE clarifying
   question, and the flow RESUMES after the reply. The resume half is the
   part with a real design question in it: `make_clarify`'s docstring says
   ST-22 resumes by asking again with the reply in hand, and nothing has
   settled what the caller passes.
   Exit gate met and how: F-03 and F-05 both pass on real fixtures in
   `tests/integration/test_ask_sourced_answer.py` (8 tests, every port on
   the answer path real); "an answer without sources cannot render as
   final" is enforced structurally by `Answer.__post_init__` and pinned
   end to end by the lost-section test, which shows the product citing
   LESS rather than citing a document nothing read.
1. ST-22 clarification + rewrite-and-split (YL), which fills the last two
   seams (`clarify`, `rewrite`) and needs no new wiring. It is no longer
   on the critical path -- ST-24 closed that -- but it is the smallest
   remaining agent story and the graph already routes to it.
2. ST-27 / ST-28, the two UI screens, now that a design exists. Read the
   UI DESIGN REVIEW section above FIRST -- it lists five drifts from the
   signed UX spec, one of which is a measured contrast failure. And read
   `agent/ports.py` before assuming what the UI can call.
2. THE OWED REVIEW PASSES. **ST-12's is DONE -- PR #65, merged
   2026-08-30**, six weeks after it was agreed on 2026-07-28. What is
   still owed is ST-21 (24479ba, merged without the rule-5 partner review
   at the human's instruction) and ST-23 (af14c4e). ST-21 is now the
   oldest unpaid one and it has had NO agent review of any kind -- see
   the HISTORY note below, which is a correction of this file.

HISTORY, kept because the correction is the point: ST-21 HAS HAD NO AGENT
REVIEW PASS AT ALL. CORRECTION, and it is a
   correction of this file: an earlier version of this line said the
   branch "has had one COLD read (the verifier agent)". IT DID NOT. The
   verifier was launched and DIED before reading the diff -- "Agent
   terminated early due to an API error: You've hit your session limit".
   Its only output was "I'll start by getting the diff", which is an
   intention, not a review. Recording it as a completed read is exactly
   the failure this file exists to prevent, and it was caught by the
   human, not by me.
   WHAT DID REVIEW IT: the human, against the signed documents, and that
   read found the two structural gaps ST-21 shipped its first version
   with -- the missing parent fetch and the unrepresentable query split.
   Both are now closed (see Now).
   STILL OWED before merge: a cold verifier pass AND the rule-5 reviewer
   pass, on the branch as it now stands. Re-stamp this file's header at
   merge time, not before.
1. ST-22 and ST-23, both YL, both unblocked the moment ST-21 lands. Each
   one fills in named ports and needs no new wiring: ST-22 takes
   `clarify` + `rewrite` (F-06), ST-23 takes `retrieve` + `grade` +
   `reword` (F-04, and `retrieve` is where `vector_store.search` and the
   parent fetch land). The seams and their contracts are already written
   down in agent/ports.py -- read that file first, not this one.
2. ST-07 corpus v1 (MB). **DONE 2026-08-29 on `feat/S1-ST-07-corpus-v1`.
   ST-18 IS NO LONGER BLOCKED.** 13 files, hr 3 + manuals 10, every one
   CONVERTED by Sanad's own conversion ladder. Exit gate is a command,
   not a claim: `uv run python scripts/corpus.py verify`, exit 0.

   WHAT CHANGED FROM THE STAND-IN, because two files were DELETED and a
   graded report would otherwise have quoted them:
   - the labour code is now the MINISTRY OF JUSTICE CONSOLIDATED edition
     (loi 65-99 as at 2011-10-26, 201 pages, adala.justice.gov.ma), not
     the ILO's 2004 first-promulgation text. Both are named as verified
     sources in PRD section 17; the 2004 one is the code BEFORE its
     amendments, and an HR generalist answering a 2026 question from
     unamended 2004 wording is the exact failure this product exists to
     prevent. The ILO copy was deleted rather than kept alongside: two
     near-identical editions compete for the same retrieval hit and would
     have made the ST-19 golden set score noise;
   - `resume-legislation-travail.pdf` was DELETED. A private consulting
     firm's 2016 summary of Moroccan labour law -- dated, secondary, and
     authoritative-looking enough to be cited as law in a graded report.
     CORRECTED AFTER THE RULE-5 REVIEW, which called the first version of
     this bullet motivated reasoning and was right: it justified the
     deletion by quoting PRD section 14 ("public material: official legal
     texts, public manuals") as if that were a source-authority rule. It
     is not. That sentence sits under **Compliance** and its subject is
     personal data. Read as an authority rule it would also have excluded
     the CLEISS guide this corpus KEEPS. The deletion is EDITORIAL
     JUDGEMENT and is now claimed as nothing more. Third instance of this
     project's own recurring failure -- quote the clause before declaring
     something spec-bound -- after the withdrawn citation escalation and
     the invented "stand-in" blocker this same story removed;
   - the CNSS side is now the actual statute -- dahir 1-72-184, from
     ACAPS, the state regulator -- with the CLEISS guide kept and
     LABELLED SECONDARY, because a corpus of nothing but statute cannot
     answer "how does this work in practice".

   A CORRECTION THIS STORY OWED ITSELF, and it is why the manuals
   workspace needed no work at all: `data/corpus/SOURCES.md` called that
   workspace "a stand-in ... French software documentation, not anyone's
   manuals", and the Next queue repeated it for six days as a blocker.
   THAT STANDARD WAS INVENTED, not signed. LD-02 says only "workspace 2 =
   technical manuals"; PRD section 14 says "public manuals"; persona P2 is
   a junior developer who "lives inside long technical manuals". The
   French Python documentation is precisely that. Six days of ST-18 were
   blocked on a requirement no signed document contains -- the same shape
   as the withdrawn citation escalation of 2026-08-23: quote the clause
   before declaring something non-compliant.

   THE DELIVERY MECHANISM IS THE STORY. `data/` is git-ignored (LD-06), so
   a corpus can NEVER reach the other machine through git, and the last one
   did not: it sat on one laptop for six days. `scripts/corpus.py` is the
   tracked half -- manifest, `fetch`, `verify`, `sources` -- and rebuilds
   the corpus from nothing on any machine with one command. `verify` calls
   `conversion.convert_file`, the same call sync makes, rather than doing
   its own pymupdf inspection: a second opinion can disagree with the
   product while both look green. What is proven is "Sanad reads every
   file", which is what ST-18 needs. No new dependency (stdlib urllib).

   THE RULE-5 REVIEW GRADED THE FIRST VERSION 6/10, DO NOT APPROVE, and
   its two blocking findings are the entry worth reading in this whole
   section, because BOTH mean the gate did not prove its own sentence:

   (a) THE GATE PASSED A SCAN. It asserted only `outcome is CONVERTED`,
       and `config.conversion_min_text_chars` is 1 -- correct for the
       PRODUCT, since F-16 only needs to know a text layer exists, and far
       too low for a CORPUS. Reproduced rather than argued: a three-page
       PDF whose only text is the page numbers "1 2 3" converts cleanly at
       12 characters and the gate said EXIT GATE MET. The original
       "proof" used a BLANK PDF, which is the easy case. This is the
       fourth time on this project that a fixture was too small for the
       property under test (ST-14's round-trip, ST-16's batching, ST-16's
       first isolation corpus, now this). Fixed with a floor of 200
       characters per page, chosen from the corpus rather than from
       taste: the thinnest real file runs 1,783 per page, a footer-only
       scan lands at 4.
   (b) THE GATE ONLY LOOKED AT THE MANIFEST, and `scan_folder` walks the
       DIRECTORY. A file on disk that the manifest does not list was
       invisible to the gate and fully visible to Sync, so ST-18 would
       have measured a file nothing checked. The concrete case is this
       story's own: a deletion happens on ONE machine. YL runs `fetch`,
       receives the three new files, and keeps the two deleted ones -- a
       five-file HR workspace containing the superseded 2004 labour code
       this story removed for competing with the consolidated one. The
       gate would have said MET. Now fails on any unlisted file.

   Two more the review caught, both fixed: `_sha256` was a SECOND file
   hasher beside `change_detection.compute_fingerprint` (21 callers) and
   the worse of the two -- it read the whole 1.5 MB labour code into
   memory where the real one chunks, and raised a bare OSError instead of
   `UnreadableFileError`; and `fetch`'s docstring claimed "`verify` is
   what does that" about matching an existing file to the manifest, which
   `verify` does not do and cannot until ST-35 records a value to compare
   against. Said plainly in the docstring now instead of falsely.
   Corroboration that the hasher swap was behaviour-neutral: every
   digest printed after the change is identical to the one before.

   ALL FOUR FAILURE BRANCHES PROVEN, because a check that has never failed
   is untested: a moved file exits 1 as MISSING; a blank image-only PDF
   exits 1 as `skipped`; a page-numbers-only scan exits 1 naming "4
   characters per page over 3 pages (floor 200)"; an unlisted file exits 1
   naming it. Restored to exit 0 after each. `fetch` proven by deleting
   one PDF and one archive-member file and watching both come back.

   RE-REVIEW: 9/10, APPROVE, with two further defects it found by running
   the new checks rather than reading them. BOTH FAIL CLOSED -- they cause
   a false RED, never a false green, which is why they did not block:
   - the stray sweep flagged ANY file, and `scan_folder` only ever indexes
     a SUPPORTED extension. A `Thumbs.db` that Windows drops into any
     folder someone opens would have turned the gate red for a file sync
     could never touch, which is how a team learns to ignore a red gate.
     Now filtered through `is_supported`, the same predicate sync uses, so
     the two cannot drift about what a corpus file is.
   - CASE. Windows filesystems are case-insensitive and Linux ones are
     not, and comparing raw names in a set mixes the two. Reproduced: a
     file renamed `CNSS-....PDF` satisfied `Path.exists()`, so it CONVERTED
     and passed, and the same run also reported it as an unlisted stray --
     one file, present and missing at once. Linux fails the other way
     round (MISSING plus stray). Both sides of every comparison are
     case-folded now.

   ONE LIMIT OF THE 200-CHARACTER FLOOR, stated because it will otherwise
   be discovered by someone quoting a number: the density is a PER-DOCUMENT
   AVERAGE. Append 100 scanned pages to the 201-page labour code and the
   average is still about 1,190, so it passes. The gate catches a scanned
   DOCUMENT, not a scanned SECTION inside a good one. Worth knowing before
   ST-18 quotes a coverage figure. The floor is also not tuned to these
   three files: the thinnest real one runs 1,783 characters per page, so
   200 sits nearly nine times below it rather than just under it.

   KNOWN AND NOT FIXED, owner ST-35: the manuals workspace is NOT
   byte-reproducible. `howto-sockets.txt` was 23,215 bytes on 2026-08-23
   and 22,757 today -- docs.python.org rebuilds the archive upstream. The
   three HR PDFs are static files and are reproducible. `verify` and
   SOURCES.md now print a sha256 per file so the drift is VISIBLE;
   pinning and failing on a mismatch is deliberately left to the story
   that freezes the golden set, because a freeze invented here would be
   the wrong shape.
2. ST-18 SPIKE, NOW UNBLOCKED: index the real corpus, measure
   G4/G5 and 20-question latency, give the OR-1 verdict. FOUR things are
   already known to be unmeasured, so the spike does not have to
   rediscover them: the per-file registry commit cost; the cost of
   re-attempting a `failed` or `skipped` file on every sync (a scanned
   200-page PDF is re-converted each run, by design); whether the sparse
   retrieval branch improves anything on real text, which ST-16
   explicitly could not prove with fakes; and finding 1 above, the
   per-file workspace-wide parent scan.
   A REAL-DOCUMENT HARNESS ALREADY EXISTS and should be reused rather
   than rewritten: this session ran the whole engine on 13 real files
   (three French PDFs including the 119-page labour code, ten French
   .txt manuals; 672k chars, ~1,825 children) with real e5 and real
   BM25. It checks per-file sync results, both stores, the registry,
   real questions, cross-workspace isolation, parent resolution, a
   second sync, and the double-sync guard. It lives in the session
   scratchpad, not in the repo -- promoting it to `scripts/` is most of
   ST-18's plumbing done, and `scripts/` now EXISTS (ST-07 created it),
   so that promotion has somewhere to land. Query latency on that corpus
   was 0.17-0.22s and indexing was dominated by CPU embedding; NEITHER
   was a G4/G5 number, because it ran against the stand-in. ST-07 has
   since replaced the stand-in, so a re-run of that harness against
   `data/corpus/` IS a G4/G5 measurement -- with one caveat to state in
   the report rather than discover: the labour code grew from 119 pages
   to 201 when the consolidated edition replaced the 2004 one, so every
   earlier timing on this corpus is a floor, not a comparison.
3. Post-hoc reviewer pass owed on ONE story now, not two. ST-17
   (0210408) is DONE -- see the review-pass section above; it found one
   data-deleting defect, fixed on PR #40, plus three findings recorded
   with no owner and one probe that could not run on Windows. ST-12
   (1862a58) is STILL OWED one; owner MB by agreement 2026-07-28, a
   deliberate deviation from BUILD-PLAN line 60. ST-12's review is now
   the only one outstanding, and it is the module ST-17's review just
   changed for the second time, which makes it more worth doing, not
   less.

NOT ST-18, and this is unchanged from the last session's entry: it
depends on ST-07's corpus and `data/` on this machine holds nothing but a
stray `parents/` test artifact -- no labour-code PDF, no HR/CNSS guides.
Its numbers would be measured on fixtures and would mean nothing, and
they would be quoted in the report anyway once written down.

CORRECTION to the previous entry's item 3, found by reading the file
rather than the journal: it claimed gate.yml already carries an "INTENT
check" and a "dup gate". It does not. `.github/workflows/gate.yml` has
exactly four steps -- uv sync --frozen, ruff, pytest, gitleaks. There is
no jscpd step and no commit-message check anywhere in it. ST-03 is
therefore NOT a confirm-and-close; whoever takes it should diff the
story's exit criteria against the four steps that actually exist. The
duplication rule in the working rules is currently enforced by nothing.

CLOSED 2026-08-29 on `docs/fix-graph-project-name`, and the CORRECTION is
the part worth keeping. This item was parked by the ST-21 session as "two
wrong lines, a one-minute docs branch". Its first bullet was itself wrong,
and fixing it as written is what broke the other machine.

WHAT IT SAID: "CLAUDE.md gives the project name as
`C-Users-lenovo-Documents-Projects-RAG_project_ENSA`. The real name has
`OneDrive` in it, confirmed by `list_projects`."

WHY THAT WAS WRONG: there is no "the real name". The codebase-memory
project name is derived from the repo's ABSOLUTE PATH, so it differs per
machine. YL's clone sits under OneDrive and MB's does not. `list_projects`
confirmed the OneDrive name on the machine it was run on and said nothing
about the other. The parked item was acted on, the OneDrive name was
written into CLAUDE.md -- and that broke MB's machine, where
`index_status` with the documented name returns "project not found",
which reads exactly like the graph being unavailable. The line has now
been wrong in BOTH directions, one machine at a time.

THE FIX, and it is not a third name: CLAUDE.md no longer names a project
at all. It says to call `list_projects` and take the entry whose
`root_path` is this repo. A machine-specific value in a file both machines
share cannot be repaired by writing the other machine's value.

The second bullet needs no action: the node/edge counts it complained
about are already gone from CLAUDE.md, replaced by "no node count is
written here on purpose" -- and this session earned that rule again.
`index_status` returned **5,922 edges and then 5,917 edges roughly ten
minutes apart** on an unchanged working tree, because the index re-watches
in the background. A number that moves while nobody edits anything is not
a fact to write down. Run the call.

PARKED for ST-28, found while reading the UX spec for this story and not
fixed here because it is that story's decision: UX spec 7.2's file table
has a `size` column. Size is recoverable for any file with a document row
(`Fingerprint.parse(row["content_hash"]).size_bytes`, per ST-12's packing
decision) but an UNSUPPORTED file gets no document row at all, so its
report row has a name, a result and a reason and no size or type. Either
the column is blank for those rows or S2 stats the file at render time.

## Data-layer follow-ups (do not lose these)
Carried from ST-10, plus two the ST-11 reviewer surfaced. 3 and 4 were CLOSED
by ST-11, 5 and 7 by ST-12; all kept here so the closures stay auditable.
1, 2 and 6 remain OPEN and have no story assigned. ST-13 did NOT fold them
in as this line once suggested: it touches no SQL and no db/repo.py, so
they would have been unreviewable drive-by edits in its diff. They need
their own `chore/` branch, now together with 8.

1. OPEN. db/repo.py - `init_db` splits schema.sql on `;` after stripping
   full-line comments. Verified safe for the current schema (no triggers, no
   views, no semicolons inside string literals) but it WILL break the first
   time a trigger or a view is added. Harden the splitter or move to a real
   migration runner before extending the schema.
2. OPEN. The config-path default in `get_connection()` is exercised by exactly
   one test; most tests still pass an explicit tmp_path.
3. CLOSED by ST-11. Cascade tests now assert `== 1` pre-delete and `== 0`
   post-delete across all five child tables, so a degenerate count cannot pass
   vacuously.
4. CLOSED by ST-11. `ensure_schema()` now bootstraps the registry explicitly
   and `session()` calls it, so a fresh install works with no manual step.
   Deliberately NOT done inside `_connect_raw`: reads must never create a
   registry, or a mistyped path is indistinguishable from a fresh install.
5. CLOSED by ST-12. `repo.delete_document` exists;
   `test_delete_document_sets_sync_item_document_id_null` calls it instead of
   inline SQL, so the ON DELETE SET NULL test now exercises the real code
   path it claims to cover.
6. OPEN, new from the ST-11 review. `ensure_schema` can leave a half-built
   registry if `schema.sql` is truncated: the file then exists, so
   `get_connection` accepts it and reads succeed against a partial schema. It
   self-heals on the next write and needs a corrupt signed artifact to trigger,
   so it is low severity. Durable fix: `get_connection` should validate that
   the expected tables are present, not merely that the file exists. That also
   closes the `RegistryNotFoundError` blind spot.
7. CLOSED by ST-12, and now regression-tested after all. `_connect_raw`
   passes `timeout=config.sqlite_busy_timeout_seconds` (default 30.0)
   instead of inheriting sqlite3's 5 second default. Two tests cover it:
   one spies on `sqlite3.connect` to prove the config value is what gets
   passed, and one holds a real EXCLUSIVE lock and races a second
   connection. The second test needed a second look. With only a lower
   bound ("it waited at least 0.4s") it was VACUOUS: dropping the `timeout`
   argument yields sqlite3's 5.0 second default, which is longer than the
   0.5s the test configures, so the mutation stayed green while the config
   was being ignored entirely. It now asserts a ceiling as well. Generalize
   the lesson: when a mutation restores a DEFAULT rather than removing
   behaviour, a one-sided bound cannot see it.
8. CLOSED 2026-08-29 on `chore/env-example-drift-check`, and it is closed
   BY A CHECK rather than by a backfill, which is the difference that
   matters. Raised by ST-13 on 2026-08-09: `.env.example` had drifted from
   `config.py`. It had drifted further by the time anyone looked -- TEN
   settings were undocumented, not the six originally listed
   (`question_min_length`, `question_max_length`, `max_sub_queries`,
   `parent_citation_marker_pattern`, `supported_document_extensions`,
   `hash_read_chunk_bytes`, `sqlite_busy_timeout_seconds` and the three
   workspace-validation limits). All ten are documented now, each with a
   comment saying what it is FOR rather than restating its name.

   WHY IT STOPPED BEING A TIDY-UP. "Every config var documented in
   `.env.example`" is ST-02's own exit criterion and nothing ever enforced
   it, because `.env.example` is a text file no code reads. Three
   `tests/unit/test_config.py` checks now hold it in both directions: a
   setting in `config.py` and not in the template fails; a variable in the
   template that `config.py` does not define fails too. That second
   direction is the one that rots quietly -- pydantic-settings IGNORES an
   unknown environment variable, so a stale key is something you can fill
   in, restart, and watch do nothing, with no error anywhere.

   Each check was proven by watching it fail first: the drift check named
   all ten missing settings before they were added.

   WHAT THIS CANNOT DO, stated so nobody trusts it too far: it holds the
   TRACKED end only. A `.env` on someone's machine is git-ignored and holds
   a secret, so nothing can compare it to anything -- which is exactly how
   ST-18 lost its G4 measurement to a `.env` still naming a retired model
   two days after the tracked files were corrected. The template can no
   longer be silently incomplete; a machine can still be silently stale.

9. FOUND WHILE DOING 8, and it was already on main: `.env.example` began
   with a UTF-8 byte-order mark (EF BB BF). Harmless today by luck only --
   line 1 is a comment, so the three bytes are swallowed by a `#`. Move a
   setting to the top and the first variable becomes `﻿MODEL_MODE`,
   which pydantic-settings does not recognise and does not complain about.
   It matters more in this file than in most because line 1 says "copy to
   .env": the mark travels into the file that configures the product.
   Stripped, and a fourth test now refuses it, proven by watching it fail
   on the committed bytes first. CLAUDE.md's Windows write trap named this
   exact hazard; it is enforced somewhere now instead of remembered.

10. OPEN, PARKED NOT FIXED, found 2026-08-30 while adding a row to
    `DECISIONS.md`. **That file contains one raw NUL byte (`0x00`), at
    byte 36320, line 59.** It is inside the ST-16 row describing the
    child-point id: `uuid5(namespace, "<parent_id>\0<index>")`. Somebody
    wrote the separator as an actual NUL instead of escaping it, so the
    record now CONTAINS the byte it is describing.

    WHY IT MATTERS AND WHY IT IS NOT COSMETIC. Two tools already treat the
    file as unreadable because of it: `grep` reports "Binary file
    docs/journal/DECISIONS.md matches" and prints NO line, so every search
    of the decision log silently returns nothing usable; and the code
    index reports `parse_partial` on exactly line 59. The file is still
    valid UTF-8 (checked) and renders fine on GitHub -- which is why it
    went unnoticed. The damage is to SEARCH, and a decision log nobody can
    grep is a decision log nobody will read.

    NOT FIXED HERE ON PURPOSE. The fix is one character (`\0` written as
    the four literal characters `\x00`), but it edits an existing signed
    decision row, and this branch's job is a journal catch-up, not a
    record amendment. Whoever takes it: change the byte, not the meaning,
    and prove it by running `grep -c "" docs/journal/DECISIONS.md` before
    and after -- it should stop saying "Binary file".

## Blockers / waiting on human

- **G4 CANNOT BE MEASURED ON MB's MACHINE. Raised 2026-08-29 by ST-18.**
  Owner: a human, and only a human -- both halves live in `.env`, which is
  git-ignored and holds a secret, so no agent can fix either.
  Fallback: if still open on 2026-09-05, G4 is measured on YL's machine
  instead and the report says which machine produced it. ST-18's other
  numbers (G5, retrieval, the baseline) are DONE and do not depend on this.

  `scripts/spike_st18.py answer` ran all 15 questions and all 15 failed
  before reaching the model. Nothing was spent: every call was rejected at
  the door. TWO SEPARATE FAULTS, and the second is the interesting one:

  1. `CLOUD_API_KEY` is invalid. Google answers
     `400 INVALID_ARGUMENT ... API_KEY_INVALID: API key not valid`. A key
     IS present (56 characters), so this is a wrong or revoked key, not a
     missing one -- which is why nothing here reads as "unconfigured".
  2. `CHAT_MODEL_CLOUD` on this machine is still `gemini-2.0-flash`, THE
     MODEL GOOGLE RETIRED ON 2026-08-27. `config.py:61` says
     `gemini-3.6-flash` and `.env.example:8` says `gemini-3.6-flash` --
     both were corrected by PRs #55 and #58. The local `.env` was not,
     because `.env` is git-ignored and a merge cannot reach it.
     Confirmed by RUNNING it rather than by reading: `get_settings()`
     resolves `chat_model_cloud` to `gemini-2.0-flash` on this machine.

  THIS IS THE THIRD INSTANCE TODAY of one pattern, and it is worth naming
  rather than fixing three times: a correction lands in a tracked file and
  the machine keeps the old value. CLAUDE.md's graph project name was the
  first, the deleted corpus files were the second (fixed by making the
  gate fail on an unlisted file), and this is the third. The common shape
  is a value that lives in TWO places, one of which git cannot reach.
  There is no gate on `.env` at all: nothing compares it to
  `.env.example`, so any setting corrected in the tracked template stays
  wrong locally until something fails at runtime. A drift check between
  the two is the durable fix and NO STORY OWNS IT. It is not improvised
  here, because `config.py` is ST-02's and a new gate step is ST-03's.

  Note for whoever fixes the key: the invalid key masked the retired model
  entirely. A 400 on authentication happens before any model lookup, so
  fixing only the key would have produced a 404 on the model name as the
  NEXT failure, one run later. Fix both at once.

  UNVERIFIED, and it is the whole `answer` path: nothing in it has ever
  run to completion, because the key has been invalid for every attempt.
  What that means concretely, listed so the first successful run is
  watched rather than trusted:
  - the G4 verdict block has never executed. It crashed on a missing cold
    start until 244eaf2 and the fix is proven only by construction (a
    `Timing` with no cold start formats as 0.0s instead of raising), never
    by a real run;
  - `answer` now makes ONE throwaway provider call in its warm-up, so the
    first real question does not pay for TLS setup, credential resolution
    and the client's first metadata fetch. That cost was undisclosed until
    the re-review named it. It is now measured and printed -- and the
    measurement itself has never run, so nobody knows whether the handshake
    is a tenth of a second or five. The declared worst case is 141 calls:
    20 questions x 7 at retry ceiling 2, plus the warm-up;
  - `traces.json` has been written exactly once, holding 15 errors and no
    answers. ST-19 is waiting on a version of it that holds real answers.
  Treat the first green `answer` run as a likely failure and watch it.

- HALF CLOSED 2026-08-27, and closing it found a defect nothing else
  could have. A Gemini key now exists in a local `.env` and CLOUD MODE
  WORKS -- but only after a fix, because the first real call this project
  has ever made came back:
      404 NOT_FOUND: This model models/gemini-2.0-flash is no longer
      available. Please update your code to use models/gemini-3.6-flash
  THE PINNED MODEL NAME HAD BEEN RETIRED BY GOOGLE. It was correct when
  ST-02 wrote it on 2026-07-20 and dead by the time anything called it.
  Nothing in the repo could have caught that: ruff cannot, pytest cannot
  (docs/phase2/CLAUDE.md rightly forbids API keys in tests, so no test
  invokes a real provider), and the typechecker sees a valid string. The
  only check that finds a dead model name is a live call. That is the
  "verify, never remember" rule paying for itself, and it is now written
  into config.py beside the value so the next reader re-checks it.
  FIXED: `chat_model_cloud` is now `gemini-3.6-flash`, which is the
  successor Google's own error names, verified by a live call rather than
  trusted. 2.5-flash and 3.5-flash were also confirmed working, so there
  is a fallback if this one is retired next.
  AND THE SAME CALL SETTLED AN OPEN QUESTION ST-23 HAD LABELLED
  UNVERIFIED: whether a real model is chatty enough to break the grader's
  strict one-word parse. It is not. Four live calls across two models,
  each grading one on-topic and one off-topic case, returned EXACTLY
  "RELEVANT" or "OFF_TOPIC" -- no prose, no punctuation, no preamble --
  and all four verdicts were correct, including correctly rejecting a
  pump-maintenance manual as off-topic for a labour-law question. Zero
  parse failures. The strict parser stands, now on evidence.
  STILL OPEN, and narrowed rather than hand-waved:
    * `ollama` is still not installed and nothing listens on
      127.0.0.1:11434 (a real socket connect, not a guess), so ADR-06's
      strict_local mode remains unexercised and risk R4's offline demo
      fallback is still unproven.
    * The four calls used short passages and one prompt. Nothing is known
      about behaviour on a 4,000-character parent section or under load.
    * BUILD-PLAN's CHECKPOINT C2 is now REACHABLE but not reached: it
      needs ST-24's answer node and ST-07's real corpus, neither of which
      exists.
  Owner: YL. Raised 2026-08-26, half closed 2026-08-27.

- WAS, and kept because the reasoning is still the record of how it was
  found: NO MODEL OF ANY KIND IS REACHABLE ON THIS MACHINE, and it blocks
  more than one story. Found 2026-08-26 while starting ST-23, by checking
  rather than by assuming:
    * `cloud_api_key` is EMPTY and there is no `.env` file at all (only
      `.env.example`), so ADR-06's cloud mode cannot make a call. Note
      that `model_mode` DEFAULTS to `"cloud"`, so the out-of-the-box
      configuration is the one that cannot work.
    * `ollama` is not on PATH and nothing is listening on 127.0.0.1:11434
      (a real socket connect, not a guess), so ADR-06's strict_local mode
      cannot reach a model either.
  WHAT THIS DOES AND DOES NOT BLOCK. It does NOT block building ST-23 to
  ST-25: docs/phase2/CLAUDE.md already mandates that tests use a scripted
  fake chat model with no API keys anywhere, so the unit suite is honest
  without a model. It DOES block two things:
    * proving any agent story against a real model, which on this project
      has caught what a green suite could not on five stories running;
    * BUILD-PLAN's CHECKPOINT C2, "end-to-end sourced answer to a real
      labor-law question on YL's machine", which is unreachable today no
      matter how good the code is.
  Owner:    a human (YL). Raised 2026-08-26.
  Settled by EITHER a Gemini API key in a local `.env` (free tier, cloud
  mode) OR `ollama` installed with one instruct model >= 7B pulled
  (ADR-06's floor), whichever the operator prefers. Ollama also removes
  the data-egress question under LD-06.
  Fallback: if neither exists by 2026-09-05, say so in the report and in
  the defense: every agent claim is fake-model-only, and C2 was never
  demonstrated. Do not let "the tests are green" stand in for it.
- HARNESS GAPS after `chore/harness-fit` (2026-08-22). TWO OF THE FRAMING
  CLAIMS IN THIS SECTION WERE WRONG, both corrected 2026-08-23 by reading the
  files instead of the journal:
  (i)  "the permissions deny-list blocks `Edit(**/.claude/hooks/**)`,
       `Edit(**/.claude/settings.json)` and `Edit(~/.claude/**)`, so no agent
       can close any of them". There is no such deny-list any more. Both
       `~/.claude/settings.json` and `.claude/settings.local.json` have an
       EMPTY `permissions.deny`. Nothing was blocking an agent from any of
       this; item 1 below was fixed by an agent this session.
  (ii) item 1's claim that the user-level settings "already registers all of
       them correctly". It did not. That registration was itself the bug --
       see item 1.
  Item 1 is now CLOSED. The rest stand.
    Owner:    a human (YL). Raised 2026-08-22.
    Fallback: if still open on 2026-09-05, stop calling these fixed-in-progress
              and accept them in writing as standing gaps.
  1. CLOSED 2026-08-23. The project-level `.claude/settings.json` this item
     described no longer exists (only `settings.local.json` does), so its
     first half was moot. The real defect was the USER-level registration
     this item called correct: all 7 CBM hook commands were wrapped as
     `cmd.exe /d /v:off /s /c '""%USERPROFILE%\...\cbm-*.cmd""'`, and cmd.exe
     does not treat SINGLE QUOTES as quoting. cmd therefore started
     interactively, printed its banner, echoed the piped hook JSON as if it
     were a typed command and exited 0 -- which is the `Microsoft Windows
     [Version ...]` noise, and it means the hooks NEVER RAN. Diagnosed from
     this session's own SessionStart output, then reproduced on demand.
     Consequence, and it is the reason this mattered rather than being
     cosmetic: `cbm-session-reminder` (4 matchers) and `cbm-code-discovery-
     gate` (PreToolUse Grep|Glob, PostToolUse Read) are the two things that
     tell an agent to use the code graph before reading files. Both were
     dead, which is exactly why this session opened ST-17 with Read/Grep on
     a fully indexed repo and only used the graph when the human asked.
     Fixed by replacing the wrapper with the plain quoted path
     (`"C:\Users\lenovo\.claude\hooks\cbm-*.cmd"`), which was tested from
     both bash and cmd.exe BEFORE being written. Backup taken and verified
     byte-identical first (`settings.json.bak-2026-08-23-cbm`); the edit was
     made on the parsed JSON after proving it round-trips byte-exactly at
     indent=2, and asserted to change nothing outside `hooks`. All 7 stored
     commands were then executed as stored: 3 distinct commands, all exit 0,
     all emitting real `hookSpecificOutput` JSON. Proven in both directions
     -- the same harness reports FAIL on the old form, so the PASS means
     something. STILL UNVERIFIED, and only a new session settles it: that
     Claude Code itself invokes them cleanly at a real SessionStart. The
     next session start is the test.
  2. `~/.claude/hooks/` carries the SAME two defects fixed here in 368e3ea:
     `gate.mjs` still has the unconditional npm early-exit, `config-guard.mjs`
     still has zero `guardedPaths` references. Every OTHER project on this
     machine therefore still has a dead Stop gate and no spec lock. Verified
     by grep, not assumed.
  3. Guard gap, found by tripping it: `config-guard.mjs`'s protected-path
     regex is `/(^|[^\w.])\.claude([\/\\]|$)/i`, which requires `.claude` to be
     followed by a slash or end-of-string. A bare `.claude` argument (as in
     `git rm -r --cached .claude`) does NOT match and passes. That is how this
     session's own untracking got through. Narrow but real.
  4. Guard false-positive on READ-ONLY inspection, hit twice this session: any
     command containing `>` counts as a write, so `diff -q a b >/dev/null` plus
     a mention of `.claude` is blocked. Same shape as the old shell guard's
     `WRITE_VERBS` bug. Diagnose with the Read/Grep tools, not shell.
  5. CLOSED 2026-08-25 by the ST-21 session. `gitleaks` IS installed on this
     machine now: `gitleaks version` -> 8.30.1, on PATH at
     `~/AppData/Local/Microsoft/WinGet/Links/gitleaks` (a winget install, so
     the earlier `winget list` negative is simply out of date). gate.yml step
     4 was RUN here for the first time on the ST-21 branch: `gitleaks detect
     --no-banner --redact` exit 0, "no leaks found", 63 commits / 2.55 MB in
     5.6s. The header above quotes 65 commits / 2.60 MB for the same step;
     both are true and neither is a typo -- this run happened two commits
     earlier in the same session than that one, and a count of commits is a
     number that moves. The whole gate is now achievable locally, so the standing excuse
     "CI is the only place that step executes" is retired, and every future
     header in this file should carry a real gitleaks result rather than the
     proxy scan this item used to allow.
     WAS: not installed -- checked five install paths, `Get-Command` and
     `winget list`, all negative.
  6. CLOSED 2026-08-23 by the ST-17 session, which is the next session start
     that was waiting to settle it. The CBM MCP tools attach and answer:
     `list_projects` returned on the first call, and the project is indexed
     at 892 nodes / 3,228 edges with 0 skipped files. `check_index_coverage`
     over the repo root reports every source file indexed with no recorded
     gap; the only exclusions are by design (`.claude`, `.venv`, `data`,
     `__pycache__`, and four gitignored files) plus one parse_partial line
     in DECISIONS.md (a markdown table row). Used for real in this session:
     the absence protocol for "does a sync engine already exist" was run on
     the graph first (search_graph found only `insert_sync_run` and
     `insert_sync_item`), then grep, then a written scope line -- and
     `trace_path` confirmed 0 inbound callers on `detect_changes`,
     `upsert_children` and `vector_store.delete_document`, which is what
     made ST-17's blast radius on existing code provably nil.

- SAFETY SYSTEM: critical half FIXED 2026-08-01, remainder is low-priority
  debt. Full history so a future session does not re-litigate it.

  WAS: `guard.sh` parsed tool events with `python3`, which on this machine is
  the Microsoft Store alias stub (exits 49, no output), and the parse was
  wrapped in `|| exit 0`. The hook therefore permitted EVERY call and all 15
  deny checks were dead, silently. That is why an ST-12 commit briefly landed
  on `main` this session. The git-level `pre-commit` backstop was also never
  installed.

  NOW FIXED and verified: `pre-commit` is installed and executable (it was
  observed blocking a real commit on main). `guard.sh` tries `python3` then
  falls back to `python`, and prints a reason to stderr before `exit 2`, so
  it fails CLOSED and diagnosably. A 13-case harness confirmed it blocks
  --no-verify / force-push / the signed-spec lock / settings edits, allows
  normal commands and edits, and still behaves correctly under three
  simulated machines: python-only (here), python3-only (a teammate's
  macOS/Linux), and neither. That last case matters -- an interim fix that
  swapped `python3` for `python` outright was BAD ADVICE from the
  orchestrator and would have blocked every tool call for teammates.

  STILL OPEN, deliberately deprioritized by the human on 2026-08-01 after
  hook work had consumed most of a session. None of it blocks building:
  OWNER + DATE + FALLBACK, added 2026-08-09 because the rubric review found
  this blocker had sat since 2026-08-01 with none of the three, which makes
  it abandoned work rather than blocked work:
    Owner:    a human. Rule 4 locks agents out of `.claude/hooks/` entirely,
              so no agent can close this no matter how long it waits.
    Raised:   2026-08-01. Chased: 2026-08-09 (this entry).
    Fallback: if it is still open on 2026-08-16, stop calling it a blocker
              and accept it as a standing gap in writing -- the duplication
              gate and the post-edit verify gate are simply OFF, and every
              story from ST-15 on must be reviewed knowing that. It has not
              blocked a single story so far; carrying it as "blocked"
              implies work is waiting on it, and none is.
  1. Six sibling hooks still call `python3` and are inert:
     `verify-after-edit.sh` (line 8), `dup-sentry.sh` (7), `stop-gate.sh`
     (10), `log-change.sh` (6), `load-state.sh` (12), `save-state.sh` (7).
     Each needs the same two-line change guard.sh got: insert
     `PY=python3; "$PY" -c '' 2>/dev/null || PY=python` above the call, then
     use `"$PY"` instead of `python3`. Do it as ONE runnable script, not a
     hand-edit checklist -- a hand-edit list was tried and half-applied.
  2. `config.sh` now sets `TYPECHECK_CMD="uv run ruff check ."` and
     `TEST_CMD="uv run pytest -q"` (they had been left `""` since before the
     stack existed). Correct, but INERT until item 1 is done, because the two
     hooks that read them exit early on the dead `python3`. Half-fixed here
     is not harmful, just not yet active.
  3. `guard.sh` line 34: an empty `tool_name` falls through to `exit 0`,
     skipping every command check.
  4. `guard.sh` line 19: `FILEPATH` is `sed -n 2p`, so a newline inside
     `file_path` walks past the signed-spec lock.
  5. `set -u` survives only because `config.sh` defines
     `PROTECTED_BRANCHES`; if that vanishes the guard aborts fail-open.
  6. The guard false-positives on READ-ONLY inspection: `WRITE_VERBS`
     includes `>`, so any command containing `2>/dev/null` or `>>` looks
     like a write. Two legitimate read-only commands were blocked this
     session. Diagnose hooks with the Grep/Read tools, not shell heredocs.
  All of the above are human-only edits (rule 4 locks agents out).
- Open, unowned: data-layer follow-ups 1, 2 and 6 below. Deliberately NOT
  folded into the ST-12 branch -- they are unrelated to change detection and
  would have put unreviewable drive-by edits in PR #14 (.claude/rules
  boy-scout rule is scoped on purpose). They need their own `chore/` branch.
- RESOLVED 2026-07-28: the `gh` gap. This was the single reason MB's three
  branches never reached main - `gh` was unauthenticated, so b1 could not
  open a PR and handed over a prefilled compare URL that was never clicked.
  The branches sat pushed and invisible for three days. `gh` now works;
  PRs #6 and #7 were opened and merged through it. Note for the record that
  b1 correctly refused to extract the stored Git Credential Manager token to
  work around this - that is credential exfiltration, not authorization.
- MACHINE-SPECIFIC, not a blocker, found 2026-08-01: `gh` is installed and
  authenticated on this machine but is NOT on PATH for the agent shell, so
  a bare `gh` call fails with "command not found" and looks exactly like the
  old unauthenticated gh gap. It is not that. Call it by full path:
  `C:\Program Files\GitHub CLI\gh.exe`. Do not conclude gh is missing and do
  not hand over a compare URL -- that is what stranded three branches for
  three days in July.
- STALE, corrected 2026-08-29 in the same pass that closed the project-name
  item above, because it is the same subject and leaving it would send the
  next session to grep on a machine where the graph answers. It said: "the
  MCP server is not installed on MB's machine, so MB's agents run the
  absence protocol on grep and find alone." IT IS INSTALLED AND ANSWERING
  THERE. `list_projects`, `index_status` and `get_architecture` were all
  called from MB's machine this session and all returned; the repo is
  indexed with 0 skipped files. Both machines now have the graph. The rest
  of the original entry, kept because its history still stands: the graph
  was first indexed on YL's machine (357 nodes / 365 edges at 40e4ac0), and
  an earlier journal line stating flatly "the repo is NOT indexed" was true
  only of the other machine. The earlier refusal to install from an untrusted
  source that carried apparent prompt-injection text was the right call and
  still stands.

## Done this week
- ST-16 Vector store + parent JSON store. MERGED as 52ee47b (PR #33).
  Merged by its own author under the deviation YL authorised on
  2026-08-22, recorded as a DECISIONS row. Architecture §7.5's two derived
  stores. Exit gate met: an HR-workspace query returns nothing from the
  manuals workspace in either direction, and every search hit resolves to
  a parent whose text CONTAINS the chunk that matched -- asserted as a
  real round trip through both stores, not as "the payload has a
  parent_id key". 272 passed / 2 skipped, up from 191 / 1.
  What the branch is built on, and none of it came from a doc page:
  (a) qdrant-client 1.18.0 REJECTS a non-UUID point id outright
      (`ValueError: Point id X is not a valid UUID`). Children arrive
      from chunking with no id, so one is derived by uuid5 -- from the
      parent id plus the child's position WITHIN THAT PARENT, not within
      the document, so a resumed or partial sync lands on the same points
      instead of duplicating everything it already wrote;
  (b) fastembed 0.8.0's BM25 is ASYMMETRIC and silent about it: `embed`
      returns IDF-weighted values, `query_embed` returns flat 1.0 term
      indicators, and using the wrong side raises nothing. It went behind
      `embeddings.py`'s existing seam rather than into vector_store.py,
      because it is the same defect shape as ADR-05's `passage:`/`query:`
      rule. `vector_store` therefore never loads an encoder: `search`
      takes the raw QUESTION, not a vector, so no caller can hand it one
      encoded the wrong way;
  (c) a second QdrantClient on one storage path raises RuntimeError about
      a lock folder, which reads like a stale lock and invites deleting
      it. `open_store` turns ADR-04's single-process rule into a named
      error instead. Honest limit: the claim is per-PROCESS, so it says
      nothing about a second Sanad process on the same data directory.
  Deletion is ONE call over both stores, ordered vectors-then-parents.
  Both orders can fail halfway; only this one fails safely, leaving
  orphan FILES (invisible to search, cleaned by re-running the same call)
  rather than live vectors citing files that are gone.
  14 mutations, injected one at a time. Two SURVIVED and both were real:
  (d) the batching test was VACUOUS. `HR_DOCUMENT` merges into one parent
      holding one child, and for a single child a per-parent numbering
      and a document-wide one are indistinguishable, so replacing the
      counter with `enumerate` passed the whole suite. Same shape as
      ST-14's round-trip test that relied on a blank line landing where
      it did by luck: the fixture was too small for the property. Fixed
      with a fixture sized to produce several parents of several children
      and a test that states the property directly;
  (e) deleting the sparse prefetch from `search` outright broke nothing.
      No behavioural test in the file COULD catch it -- both fakes rank
      by word overlap, so the dense side alone returns what the hybrid
      returns. Replaced with an assertion on the shape of the query sent
      to Qdrant, labelled in the test for what it is worth: it proves
      both branches are issued and fused with RRF, and it does NOT prove
      the sparse branch improves retrieval on real text. That needs a
      real corpus and belongs to ST-18.
  Self-review after green found two more that no mutation would have,
  because neither is a wrong line -- both are a missing one:
  (f) the collection was created BEFORE the batch was encoded, so a
      document containing a whitespace-only window (chunking keeps any
      truthy window) raised with an empty collection already on disk.
      Not harmless: `search` uses "the collection exists" to tell "never
      synced" from "synced and found nothing", so a half-failed sync
      would answer that question wrongly for good;
  (g) `open_store` claimed the storage path before building the client
      but released it only around the yield, so an open that failed
      DURING construction stranded the claim for the life of the
      process -- one bad path making the store permanently unopenable,
      and looking exactly like a genuine double-open.
  RUN, not just tested, because a green suite has missed something on
  every story so far. Real multilingual-e5-base, real Qdrant/bm25, real
  embedded Qdrant, on French labour-code-shaped text whose two workspaces
  SHARE vocabulary on purpose ("dix heures par jour", "trente jours",
  "six mois", "2288", "44"), so a leak would score highly rather than
  merely appear. 4 parents / 28 children indexed for HR, 2 / 14 for the
  manuals; three questions, all three returned the correct article as the
  top hit; zero cross-workspace hits; every hit's parent resolved and
  CONTAINED the chunk that matched; `delete_document` took 28 points and
  4 parent files and left the manuals' 14 points untouched.
  The first attempt at that run is the part worth keeping. Its corpus was
  four short articles, which `parent_merge_below_chars` (2,000) MERGED
  INTO ONE PARENT -- so all three questions resolved to the same parent,
  the section label was a range spanning the whole file, and the hit/miss
  verdict measured nothing at all. It looked like a result. Padding the
  articles to realistic length is what turned it into one. A fixture too
  small for the property under test is now the third defect of that exact
  shape on this project (ST-14's round-trip test, ST-16's batching test,
  and this).
  NOT a G5 measurement and must not be read as one: indexing 42 children
  took 55.6s wall, dominated by the first SentenceTransformer load, and
  the first run of all took 539s because it was downloading 1.1GB of
  weights. Query time was 0.6s for three questions. Real numbers against
  the real corpus are ST-18's, and `data/` on this machine is still empty.
  Reused rather than rewritten: `parent_store.py` and its 29 tests were
  recovered from `feat/S1-ST-16-vector-store`, an abandoned branch cut
  before the journal moved to docs/journal. Only the two files were
  taken, not the branch. It gained `list_parent_ids`, which is what makes
  the deletion unit authoritative about what is on disk.
- Harness repaired, branch `chore/harness-fit` (2026-08-22). The control
  plane came BACK into the repo at project level (PR #31, `.claude/` now
  git-tracked, 96 files) after PRs #25/#28/#29 spent four merges taking it
  out. Whether it belongs in the repo is a HUMAN decision and is still open.
  What is settled is that it was not enforcing anything. Three defects, each
  found by firing the hooks rather than reading them:
  (a) the Stop gate was a permanent no-op. `gate.mjs` hard-exited on a
      missing package.json/node_modules BEFORE calling `checks()`, and
      `checks()` returned [] without a package.json anyway. A Python/uv repo
      could declare `uv run pytest` and it could never run: every turn ended
      green having executed nothing. Proven by injecting a ruff violation
      into a root module -- gate now exits 2, names the red check and writes
      `.claude/gate-last-failure.log`; restored, it goes green again;
  (b) `guardedPaths()` was exported by `_config.mjs` and imported by NO
      hook, so `guardedPaths: ["docs/phase2/"]` was enforced NOWHERE. A
      Write aimed at `Sanad_PRD_v1.0.md` passed all four PreToolUse hooks.
      CLAUDE.md rule 4 calls that lock non-negotiable; it did not exist;
  (c) `config-guard.mjs` inspected only `tool_input.command` AND was
      registered on the `Bash` matcher alone, so every Write/Edit bypassed
      it twice over. Now reads `file_path` and is registered on
      `Write|Edit|MultiEdit|NotebookEdit` too.
  Also fixed: the staleness scan could not see the flat root modules
  (`sourceDirs` was `["db","tests"]`), so editing `chunking.py` left the
  gate believing nothing had changed; `.venv`/`data`/`__pycache__` added to
  the skip set; `settings.json` permissions were pnpm/npx-shaped for a repo
  with no JS toolchain and are now uv-shaped, with `uv add`/`uv remove`
  routed to `ask` per the core-law dependency rule.
  CORRECTION worth keeping: the hook registrations were first reported as
  duplicated 2-4x. They are not. The repeats are separate `matcher` groups
  (startup/resume/clear/compact), which is correct design -- the duplicate
  reading was an artifact of flattening the config across matchers.
  VERIFIED live, not just by direct invocation: minutes after `settings.json`
  was written the guard fired unprompted on a real tool call and blocked
  `rm -f .claude/gate-last-failure.log` with exit 2. That was a correct
  block on a legitimate cleanup, and it was NOT worked around -- the file
  was unstaged with `git restore --staged` and added to `.gitignore`
  instead. A guard you step around on its first real firing is a sign, not
  a gate.
  STILL UNVERIFIED: the SessionStart and SubagentStart hooks. Nothing has
  started a session since the rewrite, so `session-map.mjs` and
  `phase-router.mjs` remain unproven at the wiring level. Next session
  start settles it.
- Harness migration completed. MERGED as 275886f (PR #25). Finished a
  half-done move: the Claude harness installer zip had unpacked into the
  repo root instead of a staging folder (./agents, ./commands, ./hooks,
  ./rules, ./skills, ./evals), burying Sanad's ~770-node code graph under
  5,637 nodes of vendored payload and failing ruff on 3 lines that were
  never Sanad's. Payload ignored in three places kept in step
  (.gitignore, ruff extend-exclude, new .cbmignore); old in-repo control
  plane deleted (41 files: .claude/agents, .claude/hooks, .claude/rules,
  .claude/skills, .claude/settings.json) since the control plane now
  lives at the user level (`~/.claude`); CLAUDE.md corrected to stop
  citing removed paths and to name the agents that actually exist
  (architect/scout/verifier/coach). Per commit body: ruff clean (down
  from 3 errors), 191 passed/1 skipped unchanged, graph rebuilt to 770
  nodes/2,393 edges (down from 5,637) with zero skipped/parse-partial, CI
  verify green. FOLLOW-UP found this session (2026-08-18): the payload
  had regrown in the repo root again after this merge (a second
  half-finished unpack), moved out to ~/claude-setup/ and the by-then-dead
  ignore entries removed on chore/separate-harness-payload -- see that
  branch's CHANGELOG-AI line. Graph re-verified at 769 nodes/2,392 edges
  (one less than 275886f's 770/2,393, accounted for by .cbmignore's own
  deletion removing one node).
- ST-15 Embeddings with enforced passage/query prefixes. MERGED as
  8e5a734. `embeddings.py` implements ADR-05's binding rule -- every
  indexed chunk embedded with `passage: `, every query with `query: `,
  because multilingual-e5-base needs both even for non-English text and
  silently degrades retrieval quality if either is missing, with no error
  raised. Built as one private encoder seam behind three public
  functions so the rule cannot be bypassed. Independent review graded
  7/10 and found three blocking defects, all fixed before merge:
  (a) the prefix tests were self-referential -- they built the expected
      prefixed string from the same `config.embedding_passage_prefix` the
      code reads, so emptying that setting in config left every
      assertion passing. This is the exact silent degradation ADR-05
      exists to prevent, reproduced with a green suite. Fixed by pinning
      expected prefixes as literals plus a separate test pinning config
      against the model card;
  (b) `load_model` was public and returned the raw encoder, so
      `load_model().encode(text)` bypassed the seam entirely, making the
      module's central claim false. Now private;
  (c) `embed_passages("text")` embedded one vector per CHARACTER, because
      a bare `str` satisfies `Sequence[str]`. Now raises.
  Also added: empty-text errors carry the batch index (chunking keeps any
  truthy window, including pure-whitespace ones); a vector-count check
  protecting the child/vector alignment ST-16 will rely on; model cache
  keyed on model name so it survives `get_settings.cache_clear()`.
  191 passed and 1 skipped (up from 173 at branch point), skip is the
  real-model test, opt-in via `SANAD_RUN_MODEL_TESTS=1`. All three fixes
  mutation-proven: emptying the config prefix now fails 6 tests (was 0);
  removing the code-side passage prefix fails 5, the query prefix fails
  1. CI green in 54s.
- ST-14 Parent/child chunking. MERGED as 711f7e0 (PR #20).
  `chunking.py` turns ST-13's markdown into §7.5 parents and children. The
  lesson worth keeping is about the two verification techniques and what
  each is blind to: mutation testing found nothing wrong with the module
  itself (its one survivor was an equivalent mutant), while self-review
  after green found an unguarded infinite loop and two silent data-loss
  configurations, and simply RUNNING a realistic document found an
  unreadable citation label that 39 tests had agreed was fine. Three
  techniques, three disjoint sets of defects. Running the thing is not
  optional just because the suite is green.
  27 mutations injected one at a time, then 5 more after the fixes, plus
  boundary tests asserted on BOTH sides at 2,000 and 4,000 characters and
  a 100-character overlap proven as an equality on the shared TEXT.
  Findings worth carrying forward:
  (a) one survivor, `<=` -> `<` on the split threshold, turned out to be
      an EQUIVALENT MUTANT: at exactly the threshold the early return and
      the paragraph packer produce byte-identical output, proven by
      running both paths -- which makes the PACKER the thing guaranteeing
      no text is lost, so it got its own byte-exact round-trip test;
  (b) that round-trip test failed to catch a "strip every piece" mutation
      on its first version, because the blank-line run it relied on
      landed mid-piece by luck. Rewritten at a small non-default limit so
      the boundaries are arithmetic, not luck;
  (c) it still could not see a mutation rejoining packed paragraphs with a
      single newline, needing a second, differently-shaped test.
  Self-review after green found the real defects, as on every story so far:
  (d) `_windows` guarded its own infinite loop from the start while
      `_split_oversized` had the IDENTICAL loop with no guard --
      `parent_split_above_chars <= 0` hangs forever (proven, killed at
      10s). Two sibling settings failed SILENTLY, worse than a hang: a
      non-positive child size indexes a document with zero children, and
      a NEGATIVE overlap leaves gaps so a passage sits in the parent but
      is never embedded. All four now refused up front by
      `_validate_settings`;
  (e) the merged-parent label separator was " - ", which on a REAL
      document rendered "Article 2 - Duree - Article 4 - Rupture" --
      unreadable as a range. Every test heading had been a tidy
      "Article 1". Fixed to " ... ". Parent ids are also now DERIVED
      (`uuid5` over source_file + position) rather than random, making
      `chunk_document` idempotent and removing chunking.py's only
      `db.repo` import.
- ST-13 Conversion ladder. MERGED as b75b584 (PR #18).
  `conversion.py` implements ADR-07 rung by rung and returns one of three
  outcomes per file with a plain-language reason. The design rule it is
  built on: `convert_file` NEVER raises for a bad document, because PRD
  F-02 criterion 3 says one broken file costs one row and the batch
  finishes. A caller that must wrap it in try/except to survive a real
  folder has the criterion backwards.
  37 tests, 93 -> 130, no converter mocked and no binary fixture
  committed: real PDFs (including a real AES-256 encrypted one) come from
  pymupdf, a real OOXML package from stdlib `zipfile`. That mattered --
  every one of the three library traps above was found by RUNNING the
  libraries against hostile input, and none of them is in a doc page.
  Also worth keeping: two of the module's own defects were found by the
  two different techniques, and neither technique could have found the
  other's. A surviving mutation meant dead code (the redundant
  `is_zipfile`), and reading the diff after green found a class nothing
  raised. Run both.
- ST-12 Content hashing + change detection. MERGED, PR #14 (1862a58),
  but NOT reviewed before merge -- see the correction under Now. New
  `change_detection.py` implements the architecture §5.1 hash-vs-registry
  decision and returns NEW/CHANGED/UNCHANGED/REMOVED per file. It decides and
  never acts: no write transaction, no conversion, no chunk deletion, so the
  four transitions are testable with no converter, embedder or vector store
  in existence. Fingerprint is `sha256:<digest>:<size>` packed into the
  existing `content_hash` column rather than a new `file_size` column,
  because §7.3's DDL is signed and write-locked (DECISIONS).
  34 tests, 51 -> 85. Every non-obvious assertion was mutation-proven: 12
  deliberate defects injected one at a time (size dropped from the compare,
  digest dropped, `removed` status ignored, recursive scan, missing folder
  treated as empty, last partial chunk dropped from the hash loop,
  `list_documents` losing its workspace scope, a write smuggled into
  `detect_changes`, and four more) and each turned the suite red. Three
  things worth carrying forward:
  (a) an `!r` in the folder-not-found message rendered a Windows path as
      'C:\\\\Users\\\\...'; only a test asserting the real path caught it;
  (b) the first mutation round produced one false "vacuous test" alarm --
      the mutation was weak, not the test. Mutate the DECISION site, not a
      helper whose output still compares unequal;
  (c) the dangerous near-miss is a missing folder vs an emptied folder. Both
      scan to zero files, but one means "report nothing" and the other means
      "delete every chunk in this workspace". It raises.
  A self-review pass AFTER CI went green found three more defects, all in the
  same blind spot -- what happens to a file that is present but unreadable:
  (d) `scan_folder` never caught `UnreadableFileError`, so one unreadable file
      aborted the entire sync. `compute_fingerprint`'s own docstring claimed
      the opposite. PRD F-02 #3 ("every other file completes") was broken;
  (e) worse, an unreadable file was absent from `fingerprints`, so the REMOVED
      sweep reported it as deleted -- ST-17 would have deleted the chunks of a
      document still sitting on disk;
  (f) `FileChange`'s docstring said `document_id` is None whenever the status
      is NEW. False for a file returning after removal, and the id is load
      bearing: ST-17 must UPDATE that row, because INSERT would violate
      UNIQUE (workspace_id, file_name).
  Fixed with `ScanResult.unreadable` / `ChangeReport.unreadable`, six tests and
  six more mutations. The lesson worth carrying: CI green and 34 tests said
  nothing about this, because every test asked "what happens to a file" and
  none asked "what happens to a file we cannot read".
- ST-11 Workspaces module. MERGED, PR #11 (1a4f3fb). Owner YL. `workspaces.py`
  holds the rules, `db/repo.py` stays pure SQL. All three signed F-01 criteria
  demonstrated at module level, including a delete test that writes real bytes
  to disk and verifies they survive byte-for-byte. Tests went 17 to 51.
  Reviewed three times, 7/10 then 8/10 then 9/10, and every pass found
  something the previous one missed WHILE THE SUITE WAS GREEN THROUGHOUT:
  (a) the scoping test was vacuous, it only ever fetched the first workspace;
  (b) reads fabricated a registry, so a mistyped path created an empty database
      and returned an empty list, making a typo indistinguishable from a fresh
      install and corrupting the exact criterion the story demonstrates;
  (c) the fix for a whitespace finding introduced a defect of the same shape,
      validating a stripped name while persisting the raw one.
  Every fix was mutation-proven in both directions, mutation applied AFTER
  fixture setup. Read that list before writing the next story's tests.
- ST-02: uv project skeleton (pinned stack, config, .env.example, smoke test),
  Gemini + Ollama providers. MERGED, PR #2 (3eb19f2).
- CI gate repaired: jscpd flags (--ignore/--exit-code), .venv excluded,
  gitleaks GITHUB_TOKEN. The verify job passes on every PR.
- Team handbook docs/START-HERE.md added, uv setup hardened. MERGED, PR #3
  (442abb0). Journal sync MERGED, PR #4 (868aab1).
- Root README.md with the three-phase Mermaid pipeline diagram (ingestion,
  vector retrieval, LLM prompt generation) from Architecture 5.1/5.2/7.5 and
  ADR-04/05/07. Diagram validated by rendering, not by eye. MERGED, PR #5
  (40e4ac0).
- MB's `.claude/worktrees/` and `.claude/agent-memory/` gitignore. MERGED,
  PR #6 (c844922).
- ST-04 PR template carrying the §12.2 checklist verbatim. MERGED, PR #7
  (7a51935). Its last open exit-gate item, branch protection on main, is
  satisfied: the active `protect-main` ruleset enforces required PRs, the
  strict `verify` status check, non-fast-forward, no deletion, and linear
  history, so direct push to main is rejected. ST-04 is closeable.
- ST-10 SQLite schema + data access. MERGED, PR #8 (6746234). Six-table
  registry per Architecture 7.3 under the 7.4 deviations, `PRAGMA
  foreign_keys=ON` at the single connect site, `session()` transaction helper,
  17 tests green. Reviewed twice and the passes disagreed: MB's session graded
  it 9/10 "zero blocking defects"; an independent pre-merge re-review graded it
  8/10 NOT safe to merge and was right. It found `init_db` committing on a
  caller-owned connection, which silently defeated rollback inside `session()`.
  Dropping the explicit `commit()` was not enough, because `executescript()`
  issues its own implicit COMMIT; `init_db` now runs each DDL statement via
  `conn.execute()` and never commits. The rollback test was proven to fail
  before the fix and pass after. Keep running the second review.
- Three of MB's branches were recovered and landed. They had been pushed on
  2026-07-25 and sat invisible for three days because `gh` was never
  authenticated, so no PR was ever opened for any of them. All merged with
  `Co-authored-by: meriem-mb` preserved.
- SETUP-000: kit configured for Sanad (uv stack), safety walls tested, two
  Windows guard gaps found AND fixed, .gitignore added, origin re-pointed.
- Phase 3 kickoff Steps 0-2: intake gate passed (pack clean), BUILD-PLAN.md
  approved and filed, repo indexed on YL's machine.
- Workflow rule added: no AI attribution in commits, PRs, or issues - no
  `Co-Authored-By` trailer naming an assistant, no `[AI]` subject marker, no
  "generated with" footer. This is graded academic work and the history
  carries the team's names only. Human co-authorship is still credited
  normally. Written into CLAUDE.md rule 6, .claude/rules/git-discipline.md,
  and the b1 merge checklist. History already on main was left unrewritten
  by decision - see DECISIONS.
