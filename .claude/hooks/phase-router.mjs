#!/usr/bin/env node
// SessionStart + SubagentStart. Reads .claude/PHASE and names the exact skill
// for that phase, so phase work never depends on description matching.
// Cannot block. Any failure exits 0 and says nothing.

import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { ROOT, parseStdin } from "./_config.mjs";

const SKILLS = {
  "1": "phase-1-discovery",
  "2": "phase-2-mvp",
  "3": "phase-3-architecture",
  "4": "phase-4-implementation",
  "5": "phase-5-testing",
  "6": "phase-6-deploy",
  "7": "phase-7-monitor",
};

const input = parseStdin();
const event = input.hook_event_name || "SessionStart";

const phaseFile = join(ROOT, ".claude", "PHASE");
if (!existsSync(phaseFile)) process.exit(0);

let digit;
try {
  digit = String(readFileSync(phaseFile, "utf8")).replace(/^\uFEFF/, "").trim();
} catch { process.exit(0); }

const skill = SKILLS[digit];
if (!skill) process.exit(0);

const text =
  `PHASE ROUTER: this project is in phase ${digit}. Load the \`${skill}\` skill ` +
  `before doing any work belonging to this phase. Do not guess which phase ` +
  `skill applies; the PHASE file decides, and only the human changes it.`;

process.stdout.write(JSON.stringify({
  hookSpecificOutput: { hookEventName: event, additionalContext: text },
}));
process.exit(0);