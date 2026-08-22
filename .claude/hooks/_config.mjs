// Shared by every hook. Reads .claude/harness.json and works out the things
// that differ between projects: which package manager, which checks, which
// directories hold source.
//
// Everything here fails soft. A harness.json that is missing, malformed, or
// half-filled gives you sensible defaults rather than a jammed session — a
// broken config must never be able to stop you working.

import { readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { homedir } from "node:os";

import { fileURLToPath } from "node:url";

// Walk up from this file until we find a project root marker.
// Find the project. In order of trust:
//   1. what the caller told us, if it is real
//   2. where the process started, walked up until a project appears
//   3. where this file sits, which only helps a project-local copy
// Never accept the home folder. It holds .claude but it is not a project.
// Proven, not guessed: an earlier version returned the Windows temp folder.

function isProject(dir) {
  if (!dir) return false;
  return existsSync(join(dir, ".claude")) || existsSync(join(dir, "package.json"));
}

function walkUp(start) {
  let dir = start;
  for (let i = 0; i < 8; i++) {
    if (isProject(dir)) return dir;
    const up = dirname(dir);
    if (up === dir) return null;
    dir = up;
  }
  return null;
}

function findRoot() {
  const home = homedir();
  const fixDrive = (p) => p.replace(/^([a-z]):/, (_m, d) => `${d.toUpperCase()}:`);

  const told = (process.env.CLAUDE_PROJECT_DIR ?? "").trim();
  if (isProject(told) && told !== home) return fixDrive(told);

  const fromCwd = walkUp(process.cwd());
  if (fromCwd && fromCwd !== home) return fixDrive(fromCwd);

  const here = walkUp(dirname(dirname(fileURLToPath(import.meta.url))));
  if (here && here !== home) return fixDrive(here);

  return fixDrive(process.cwd());
}

export const ROOT = findRoot();

// Windows PowerShell prepends a BOM when piping a string into a native command,
// and JSON.parse throws on it. That made a guard hook exit 0 and fail open,
// silently, for every path. Found by testing, not by reading.
export function readStdin() {
  try {
    return readFileSync(0, "utf8").replace(/^﻿/, "").trim();
  } catch {
    return "";
  }
}

export function parseStdin() {
  try {
    return JSON.parse(readStdin() || "{}");
  } catch {
    return {};
  }
}

function readJson(path, fallback) {
  try {
    return JSON.parse(readFileSync(path, "utf8").replace(/^﻿/, ""));
  } catch {
    return fallback;
  }
}

const raw = readJson(join(ROOT, ".claude", "harness.json"), {});

const LOCKFILES = [
  ["pnpm-lock.yaml", "pnpm"],
  ["yarn.lock", "yarn"],
  ["bun.lockb", "bun"],
  ["package-lock.json", "npm"],
];

export function packageManager() {
  const declared = raw.packageManager;
  if (declared && declared !== "auto") return declared;
  for (const [file, pm] of LOCKFILES) {
    if (existsSync(join(ROOT, file))) return pm;
  }
  return "npm";
}

// `<pm> run <script>` works for npm, pnpm, yarn and bun alike.
export function runScript(script) {
  return `${packageManager()} run ${script}`;
}

export function packageScripts() {
  const pkg = readJson(join(ROOT, "package.json"), null);
  return pkg?.scripts ?? null;
}

// The checks the gate runs. Declared ones win. Otherwise: whichever of the
// three usual ones actually exist. A script that is not in package.json is
// skipped rather than failed — a stack with no typecheck step is not a
// project in breach, it is a project without that step.
export function checks() {
  const declared =
    Array.isArray(raw.checks) && raw.checks.length > 0 ? raw.checks : null;

  // A check may declare a literal `cmd`. That form wins and needs no
  // package.json, because not every project is a Node project.
  //
  // Without this branch a Python/uv, Go or Rust repo could declare checks
  // that can NEVER run: `packageScripts()` returns null, the function
  // returns [] and the gate reports green having executed nothing at all.
  // That is not a hypothetical — it is exactly what this repo was doing.
  if (declared) {
    const explicit = declared
      .filter(
        (c) =>
          c &&
          typeof c === "object" &&
          typeof c.cmd === "string" &&
          c.cmd.trim() !== "",
      )
      .map((c) => ({ name: c.name ?? c.cmd, cmd: c.cmd }));
    if (explicit.length > 0) return explicit;
  }

  const scripts = packageScripts();
  if (!scripts) return [];
  const wanted = declared
    ? declared.map((c) => (typeof c === "string" ? { name: c, script: c } : c))
    : ["typecheck", "lint", "test"].map((s) => ({ name: s, script: s }));
  return wanted
    .filter((c) => c && c.script && Object.hasOwn(scripts, c.script))
    .map((c) => ({ name: c.name ?? c.script, cmd: runScript(c.script) }));
}

export function sourceDirs() {
  const dirs = Array.isArray(raw.sourceDirs) && raw.sourceDirs.length > 0
    ? raw.sourceDirs
    : ["src", "app", "lib", "server", "worker", "tests", "test"];
  return dirs.filter((d) => existsSync(join(ROOT, d)));
}

export function guardedPaths() {
  return Array.isArray(raw.guardedPaths) ? raw.guardedPaths : [];
}

export function maxGateBlocks() {
  const n = Number.parseInt(raw.maxGateBlocks, 10);
  return Number.isFinite(n) && n > 0 ? n : 3;
}