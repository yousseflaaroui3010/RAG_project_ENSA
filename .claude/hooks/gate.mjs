#!/usr/bin/env node
// The gate. Refuses to let a turn finish while a check is red.
//
// Wired to Stop. It was briefly wired to TaskCompleted as well; that was
// removed, because TaskCompleted fires only for the TaskCreate tool, so it
// added almost no coverage while giving two test runs a second chance to
// collide over the same cache directory. One reported a red that was not red.
//
// Exit 2 is the ONLY code that blocks. Exit 1 is treated as a non-blocking
// error and the action proceeds anyway. That trap breaks more hooks than
// anything else — a script that fails "properly" gets ignored.
//
// Two loop guards, because a blocking hook that loops jams a session:
//   1. stop_hook_active, built in to Stop. If we already blocked this turn,
//      stand down.
//   2. A hand-rolled circuit breaker. Do not remove it. It is the only thing
//      standing between a persistently red check and an unusable session.
//
// Speed: running every check on every turn would be unbearable. The hook first
// compares the newest source file timestamp against the last known green run.
// Nothing touched since then means nothing to re-check, and it exits in
// milliseconds.

import { execSync } from "node:child_process";
import { readFileSync, writeFileSync, unlinkSync, existsSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";
import { tmpdir } from "node:os";
import { ROOT, parseStdin, checks, sourceDirs, maxGateBlocks } from "./_config.mjs";

const SOURCE_EXT = new Set([
  ".ts", ".tsx", ".mts", ".cts", ".mjs", ".cjs", ".js", ".jsx",
  ".vue", ".svelte", ".py", ".go", ".rs", ".rb", ".java", ".kt", ".cs", ".php", ".sql",
]);

const input = parseStdin();

// LOOP GUARD 1.
if (input.stop_hook_active === true) process.exit(0);

if (!existsSync(join(ROOT, "package.json"))) process.exit(0);
if (!existsSync(join(ROOT, "node_modules"))) process.exit(0);

const CHECKS = checks();
if (CHECKS.length === 0) process.exit(0);

function newestSourceMtime(dir, acc = 0) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return acc;
  }
  for (const e of entries) {
    if (e.name === "node_modules" || e.name === ".git" || e.name === "dist" || e.name === "build") continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) acc = newestSourceMtime(p, acc);
    else if (SOURCE_EXT.has(extname(e.name))) {
      try {
        acc = Math.max(acc, statSync(p).mtimeMs);
      } catch {
        /* ignore */
      }
    }
  }
  return acc;
}

let newest = 0;
for (const d of sourceDirs()) newest = Math.max(newest, newestSourceMtime(join(ROOT, d)));

const key = ROOT.replace(/[^\w]/g, "_").slice(-60);
const stampFile = join(tmpdir(), `cc-gate-green-${key}`);
const counterFile = join(tmpdir(), `cc-gate-count-${key}`);
const lockFile = join(tmpdir(), `cc-gate-lock-${key}`);

// Nothing changed since the last green run.
try {
  const lastGreen = Number.parseFloat(readFileSync(stampFile, "utf8"));
  if (Number.isFinite(lastGreen) && newest <= lastGreen) process.exit(0);
} catch {
  /* no stamp yet */
}

// LOCK. Two gate runs at once means two test runs sharing one cache directory,
// and one of them can fail for reasons that have nothing to do with the code.
// That happened: a red `test` that was green before and after. The usual cause
// is two Claude sessions open on the same repository, which no amount of hook
// wiring can prevent. If another gate is running, stand down rather than race it.
const LOCK_STALE_MS = 10 * 60 * 1000;
try {
  const heldSince = Number.parseFloat(readFileSync(lockFile, "utf8"));
  if (Number.isFinite(heldSince) && Date.now() - heldSince < LOCK_STALE_MS) {
    process.stderr.write(
      "Gate skipped: another gate run is already in progress, probably a second Claude session on this repo. This turn was NOT verified.\n",
    );
    process.exit(0);
  }
} catch {
  /* no lock */
}
writeFileSync(lockFile, String(Date.now()), "utf8");
process.on("exit", () => {
  try {
    unlinkSync(lockFile);
  } catch {
    /* ignore */
  }
});

let tries = 0;
try {
  tries = Number.parseInt(readFileSync(counterFile, "utf8"), 10) || 0;
} catch {
  tries = 0;
}

// LOOP GUARD 2. Never remove this.
const MAX = maxGateBlocks();
if (tries >= MAX) {
  try {
    unlinkSync(counterFile);
  } catch {
    /* ignore */
  }
  process.stderr.write(
    `GATE OPENED after ${MAX} blocks. Stop working. Tell the user exactly which check is still red and what you tried, and let them decide.\n`,
  );
  process.exit(0);
}

// Capture the output instead of discarding it. A check that reports a name and
// nothing else is undiagnosable: a spurious red looks exactly like a real one,
// and you cannot tell them apart after the fact.
const failed = [];
const evidence = [];
for (const { name, cmd } of CHECKS) {
  try {
    execSync(cmd, { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"], timeout: 300000 });
  } catch (err) {
    failed.push({ name, cmd });
    const out = `${err.stdout ?? ""}${err.stderr ?? ""}`.toString().trim();
    evidence.push(
      [
        `### ${name} — exit ${err.status ?? "?"} — ${new Date().toISOString()}`,
        `$ ${cmd}`,
        out ? out.split("\n").slice(-40).join("\n") : "(no output captured)",
      ].join("\n"),
    );
  }
}

if (failed.length > 0) {
  try {
    writeFileSync(join(ROOT, ".claude", "gate-last-failure.log"), evidence.join("\n\n") + "\n", "utf8");
  } catch {
    /* ignore */
  }
}

if (failed.length === 0) {
  try {
    writeFileSync(stampFile, String(newest), "utf8");
    unlinkSync(counterFile);
  } catch {
    /* ignore */
  }
  process.exit(0);
}

writeFileSync(counterFile, String(tries + 1), "utf8");

process.stderr.write(
  [
    `NOT DONE. These are red: ${failed.map((f) => f.name).join(", ")}.`,
    "",
    "The captured output is in .claude/gate-last-failure.log — read it first.",
    "Then re-run the check yourself and read the exit code, not the last lines:",
    ...failed.map((f) => `  ${f.cmd}`),
    "",
    "If your own run comes back green, say so plainly and do NOT silently accept",
    "the pass. A check that is red once and green next is a flaky check, and that",
    "is a defect in the gate worth reporting, not noise to work around.",
    "",
    "Fix them properly. Do not disable a check, skip a test, weaken an assertion,",
    "add an ignore comment, or raise a threshold to get green. That is cheating the",
    "check, not meeting it. If you cannot fix it, say so plainly and stop.",
    "",
    `Attempt ${tries + 1} of ${MAX} before this gate opens on its own.`,
  ].join("\n") + "\n",
);
process.exit(2);