import { readFileSync, existsSync } from "node:fs";
import { join, dirname, resolve, relative } from "node:path";

const MIN_PHASE = 4;
const CODE_TOOLS = ["Write","Edit","MultiEdit","NotebookEdit"];
const CODE_RE = /\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|rb|php|sql|vue|svelte|css|scss|html)$/i;
const WRITE_TOKENS = [">>", ">", "tee ", "sed -i", "set-content", "out-file", "add-content", "new-item", "touch ", "cp ", "mv "];
const PHASE_NAMES = ["discovery","requirements","MVP","architecture","implementation","testing","deploy","monitor"];

function ok() { process.exit(0); }
function block(m) { process.stderr.write("PHASE GATE: " + m + "\n"); process.exit(2); }

let raw = "";
try { raw = readFileSync(0, "utf8"); } catch { block("cannot read hook input"); }
if (!raw.trim()) block("empty hook input");
let input;
try { input = JSON.parse(raw); } catch { block("hook input was not valid JSON"); }

const tool = input.tool_name || "";
const ti = input.tool_input || {};

let suspect = null;
if (CODE_TOOLS.includes(tool)) {
  const t = ti.file_path || ti.notebook_path || "";
  if (t && CODE_RE.test(String(t))) suspect = String(t);
} else if (tool === "Bash") {
  const cmd = String(ti.command || "").replace(/\d*>&\d*/g, " ").replace(/2>\s*\/dev\/null/g, " ").replace(/=>|>=|->/g, " ");
  if (WRITE_TOKENS.some(w => cmd.toLowerCase().includes(w))) {
    const m = cmd.match(/[\w./\\-]+\.(ts|tsx|js|jsx|mjs|cjs|py|go|rs|java|rb|php|sql|vue|svelte|css|scss|html)\b/i);
    if (m) suspect = m[0];
  }
}
if (!suspect) ok();

function findRoot(start) {
  const e = process.env.CLAUDE_PROJECT_DIR;
  if (e && existsSync(join(e, ".claude"))) return e;
  let d = resolve(start || process.cwd());
  for (let i = 0; i < 8; i++) {
    if (existsSync(join(d, ".claude"))) return d;
    const up = dirname(d);
    if (up === d) break;
    d = up;
  }
  return null;
}
const root = findRoot(input.cwd);
if (!root) ok();

const rel = relative(root, resolve(root, suspect)).replace(/\\/g, "/");
if (rel.startsWith(".claude/") || rel.includes("/.claude/")) ok();
if (rel.startsWith("docs/") || rel.startsWith("openspec/") || rel.startsWith("..")) ok();

const phaseFile = join(root, ".claude", "PHASE");
if (!existsSync(phaseFile)) ok();
let txt;
try { txt = String(readFileSync(phaseFile, "utf8")).replace(/^\uFEFF/, "").trim(); } catch { block(".claude/PHASE exists but cannot be read. Blocking until a human fixes it."); }
if (!/^[0-7]$/.test(txt)) block(".claude/PHASE must hold exactly one digit, 0 to 7. It holds something else, so the gate stays shut.");
const phase = parseInt(txt, 10);

if (phase >= MIN_PHASE) ok();
if (phase === 2 && rel.startsWith("mvp/")) ok();

block("this project is in phase " + phase + " (" + PHASE_NAMES[phase] + ") and " + rel + " is source code. Code opens at phase 4; during phase 2, only inside mvp/. Write plans, specs and docs instead. Only the human advances .claude/PHASE, and do not route around this gate.");