#!/usr/bin/env node
// PreToolUse hook on Edit|Write.
// Before a source file is changed, tell Claude who imports it. It never chose
// to check; it got told.
//
// Telling an agent "always check who uses this first" fails, because an
// instruction is a suggestion and suggestions get skipped when a model is deep
// in a task. This is the blind-spot beeper: the car checks, every time,
// whether you wanted it to or not.
//
// This is a text search, not a symbol graph. It is fast and rough, and it will
// miss an import written through an unusual alias. A language server or a code
// graph is the exact version. Both together beat either alone.
//
// Never blocks. Any failure exits 0 silently — a broken advisory hook must not
// stop work.

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join, relative, basename, extname, sep } from "node:path";
import { ROOT, parseStdin, sourceDirs } from "./_config.mjs";

const MAX_CALLERS = 20; // hook output is capped at 10,000 characters
const SOURCE_EXT = new Set([".ts", ".tsx", ".mts", ".cts", ".mjs", ".cjs", ".js", ".jsx", ".vue", ".svelte"]);
const SKIP_DIRS = new Set(["node_modules", ".git", "build", "dist", ".next", "coverage"]);

function walk(dir, out) {
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    if (SKIP_DIRS.has(e.name)) continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (SOURCE_EXT.has(extname(e.name))) out.push(p);
  }
  return out;
}

try {
  const input = parseStdin();
  const file = input.tool_input?.file_path;
  if (!file) process.exit(0);

  const ext = extname(file);
  if (!SOURCE_EXT.has(ext)) process.exit(0);

  const base = basename(file);
  const stem = base.slice(0, base.length - ext.length);

  // Barrel files are imported by everything. The list would be noise.
  if (stem === "index") process.exit(0);

  const candidates = [];
  for (const d of sourceDirs()) {
    const p = join(ROOT, d);
    if (existsSync(p)) walk(p, candidates);
  }

  // from "…/stem" | require("…/stem") | import("…/stem")
  const pattern = new RegExp(
    `(?:from|require\\(|import\\()\\s*['"][^'"]*(?:^|/)${stem.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?:\\.[a-z]+)?['"]`,
  );

  const callers = [];
  for (const c of candidates) {
    if (c === file || relative(ROOT, c) === relative(ROOT, file)) continue;
    let text;
    try {
      text = readFileSync(c, "utf8");
    } catch {
      continue;
    }
    if (pattern.test(text)) callers.push(relative(ROOT, c).split(sep).join("/"));
    if (callers.length >= MAX_CALLERS) break;
  }

  if (callers.length === 0) process.exit(0);

  const truncated = callers.length >= MAX_CALLERS ? ` (truncated at ${MAX_CALLERS})` : "";
  const context = [
    `BLAST RADIUS for ${base}: ${callers.length} file(s) import it${truncated}.`,
    ...callers.map((c) => `  ${c}`),
    "",
    "Before changing anything this file exports, read these callers.",
    "If you change a signature, update every one of them in the same task.",
    "This is a text search and may have missed aliased imports.",
  ].join("\n");

  process.stdout.write(
    JSON.stringify({
      hookSpecificOutput: {
        hookEventName: "PreToolUse",
        permissionDecision: "defer",
        additionalContext: context,
      },
    }),
  );
} catch {
  // An advisory hook that throws must not block an edit.
}
process.exit(0);
