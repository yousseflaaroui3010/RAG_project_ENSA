import { readFileSync, existsSync, statSync } from "node:fs";
import { join, dirname, resolve } from "node:path";

const MIN_PHASE = 6;
const PATTERNS = [
  /\b(npm|pnpm|yarn|bun)\s+publish\b/,
  /\bvercel\b/, /\bnetlify\b/, /\bwrangler\b/, /\bflyctl\b/, /\bfly\s+deploy\b/,
  /\brailway\s+up\b/, /\bsst\s+deploy\b/, /\bheroku\b/,
  /\bdocker\s+push\b/, /\bkubectl\s+apply\b/, /\bhelm\s+(install|upgrade)\b/,
  /\bterraform\s+apply\b/, /\bgh\s+release\b/,
  /\baws\s+(s3\s+sync|deploy|cloudformation)\b/,
  /\bsupabase\s+db\s+push\b/,
  /\bprisma\s+migrate\s+deploy\b/, /\bdrizzle-kit\s+push\b/,
  /\b(npm|pnpm|yarn|bun)\s+(run\s+)?(deploy|publish|release|ship|promote)\b/
];

function ok() { process.exit(0); }
function block(msg) { process.stderr.write("PHASE GATE: " + msg + "\n"); process.exit(2); }

function findRoot(start) {
  const envRoot = process.env.CLAUDE_PROJECT_DIR;
  if (envRoot && existsSync(join(envRoot, ".claude"))) return envRoot;
  let d = resolve(start || process.cwd());
  for (let i = 0; i < 8; i++) {
    if (existsSync(join(d, ".claude"))) return d;
    const up = dirname(d);
    if (up === d) break;
    d = up;
  }
  return null;
}

const PROTECTED = [/^main$/, /^master$/];
const RELEASEISH = /^v?\d+\.\d+/;
const VALUE_FLAGS = ["-o", "--push-option", "--repo", "--exec", "--receive-pack"];

function isProtectedRef(ref) {
  if (!ref) return true;
  if (ref.includes("*")) return true;
  let r = String(ref).trim().replace(/^\+/, "");
  if (/^refs\/tags\//.test(r)) return true;
  r = r.replace(/^refs\/heads\//, "");
  if (RELEASEISH.test(r)) return true;
  return PROTECTED.some(p => p.test(r));
}

function currentBranch(root) {
  try {
    let g = join(root, ".git");
    if (!existsSync(g)) return null;
    if (statSync(g).isFile()) {
      const m = /gitdir:\s*(.+)/.exec(readFileSync(g, "utf8"));
      if (!m) return null;
      g = resolve(root, m[1].trim());
    }
    const head = String(readFileSync(join(g, "HEAD"), "utf8")).trim();
    const m2 = /^ref:\s*refs\/heads\/(.+)$/.exec(head);
    return m2 ? m2[1] : null;
  } catch { return null; }
}

function pushTargetsProtected(cmd, root) {
  const seg = String(cmd).split(/&&|\|\||[;|\n]/).find(s => /\bgit\s+push\b/.test(s)) || cmd;
  const toks = seg.replace(/["']/g, "").trim().split(/\s+/);
  const i = toks.findIndex(t => t === "push");
  const args = i === -1 ? [] : toks.slice(i + 1);
  const pos = [];
  for (let j = 0; j < args.length; j++) {
    const a = args[j];
    if (a.startsWith("-")) {
      if (/^(--all|--mirror|--tags|--follow-tags)$/.test(a)) return true;
      if (VALUE_FLAGS.includes(a)) j++;
      continue;
    }
    pos.push(a);
  }
  const refspecs = pos.slice(1);
  if (refspecs.length === 0) return isProtectedRef(currentBranch(root));
  return refspecs.some(rs => {
    const dst = rs.includes(":") ? rs.slice(rs.lastIndexOf(":") + 1) : rs;
    if (!dst || dst === "HEAD") return isProtectedRef(currentBranch(root));
    return isProtectedRef(dst);
  });
}

let raw = "";
try { raw = readFileSync(0, "utf8"); } catch { raw = ""; }
if (!raw.trim()) block("empty hook input");
let input;
try { input = JSON.parse(raw); } catch { block("hook input was not valid JSON"); }
if ((input.tool_name || "") !== "Bash") ok();
const cmd = (input.tool_input && input.tool_input.command) || "";
if (!cmd) ok();

const hit = PATTERNS.find(p => p.test(cmd));
const isPush = /\bgit\s+push\b/.test(cmd);
if (!hit && !isPush) ok();

const root = findRoot(input.cwd);
if (!root) block("a deploy command ran outside any known project. Refusing.");

if (isPush && !hit) {
  let shipping = true;
  try { shipping = pushTargetsProtected(cmd, root); } catch { shipping = true; }
  if (!shipping) ok();
}

const phaseFile = join(root, ".claude", "PHASE");
if (!existsSync(phaseFile)) block("a deploy command ran in a project with no PHASE file. Refusing.");
const phase = parseInt(String(readFileSync(phaseFile, "utf8")).trim(), 10);
if (!Number.isInteger(phase)) block("the PHASE file does not hold a number");
if (phase >= MIN_PHASE) ok();
block("this project is in phase " + phase + ". Anything that ships opens at phase 6. Feature-branch pushes are free; main, master and tags count as shipping.");