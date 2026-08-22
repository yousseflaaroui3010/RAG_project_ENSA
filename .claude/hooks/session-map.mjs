#!/usr/bin/env node
// SessionStart hook. Injects the things CLAUDE.md cannot know: what is actually
// on disk and in git right now.
//
// Deliberately does NOT re-inject ARCHITECTURE.md. CLAUDE.md already points at
// it and loads every session; pasting it again would spend context twice on the
// same words. This hook carries only live state.
//
// The point is drift. A document describes the day it was written. This block
// describes this second, and when the two disagree the document is the one
// that is wrong.
//
// SessionStart cannot block. Any failure here exits 0 and says nothing.

import { execFileSync } from "node:child_process";
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { ROOT, sourceDirs, packageManager } from "./_config.mjs";

function git(...args) {
  try {
    return execFileSync("git", args, {
      cwd: ROOT,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
      timeout: 5000,
    }).trim();
  } catch {
    return "";
  }
}

const countLines = (t) => (t ? t.split("\n").filter(Boolean).length : 0);

const lines = [];

const branch = git("rev-parse", "--abbrev-ref", "HEAD");
if (branch) lines.push(`Branch: ${branch}`);

const log = git("log", "--oneline", "-5");
lines.push(log ? `Recent commits:\n${log}` : "Recent commits: none — nothing has been committed yet.");

const status = git("status", "--porcelain");
lines.push(`Working tree: ${countLines(status) || "clean"}${status ? " changed/untracked paths" : ""}`);

// What has actually been built, as opposed to what the docs describe.
const CODE = /\.(ts|tsx|mts|cts|mjs|cjs|js|jsx|vue|svelte|py|go|rs|rb|java|kt|cs|php)$/;
const empty = [];
for (const dir of sourceDirs()) {
  const p = join(ROOT, dir);
  let hasCode = false;
  try {
    hasCode = readdirSync(p, { recursive: true, withFileTypes: true }).some(
      (e) => e.isFile() && CODE.test(e.name),
    );
  } catch {
    /* unreadable */
  }
  if (!hasCode) empty.push(`${dir}/ (no source files yet)`);
}
if (empty.length) lines.push(`Still empty: ${empty.join(", ")}`);

if (existsSync(join(ROOT, "package.json"))) {
  lines.push(
    `node_modules: ${existsSync(join(ROOT, "node_modules")) ? "installed" : `NOT installed — ${packageManager()} install first`}`,
  );
}

// A brief that has never been read is the most common reason a session starts
// in the wrong place.
const briefDir = join(ROOT, "docs", "brief");
if (existsSync(briefDir)) {
  try {
    const files = readdirSync(briefDir).filter((f) => !f.startsWith(".") && f !== "README.md");
    lines.push(
      files.length
        ? `docs/brief/: ${files.length} file(s) — the project's own requirements. READ-ONLY.`
        : "docs/brief/: empty — no requirements have been supplied yet. Run /bootstrap once they are.",
    );
  } catch {
    /* ignore */
  }
}

if (!existsSync(join(ROOT, "CLAUDE.md"))) {
  lines.push("CLAUDE.md: missing — this repo has not been bootstrapped. Run /bootstrap.");
}

process.stdout.write(
  JSON.stringify({
    hookSpecificOutput: {
      hookEventName: "SessionStart",
      additionalContext: [
        "LIVE PROJECT STATE (from .claude/hooks/session-map.mjs, not from a document):",
        ...lines,
        "",
        "Anything a document claims about what runs is a claim from the day it was written. This block is from this second.",
      ].join("\n"),
    },
  }),
);
process.exit(0);
