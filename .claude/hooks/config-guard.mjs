import { readFileSync } from "node:fs";

// Blocks writes whose RESOLVED TARGET is a protected path.
// Mentioning a path in prose is not writing to it.
// A guard that cannot read its input must BLOCK.

let raw = "";
try { raw = readFileSync(0, "utf8"); } catch {
  console.error("CONFIG-GUARD: could not read hook input. Blocking.");
  process.exit(2);
}
raw = raw.replace(/^\uFEFF/, "").trim();
if (raw === "") { console.error("CONFIG-GUARD: hook input was empty. Blocking."); process.exit(2); }
let d;
try { d = JSON.parse(raw); } catch (e) {
  console.error("CONFIG-GUARD: hook input was not readable JSON. Blocking.\nReason: " + e.message);
  process.exit(2);
}
const cmd = d?.tool_input?.command;
if (typeof cmd !== "string" || cmd === "") process.exit(0);

const PROTECTED = [
  /(^|[^\w.])\.claude([\/\\]|$)/i,
  /(^|[\/\\])\.env(\.[\w-]+)?$/i,
  /(^|[\/\\])\.ssh([\/\\]|$)/i,
  /(^|[\/\\])\.aws([\/\\]|$)/i,
  /\.pem$/i, /\.key$/i, /(^|[\/\\])id_rsa/i,
  /(^|[\/\\])harness\.json$/i,
  /(^|[\/\\])PHASE$/
];
const isProtected = t => PROTECTED.some(r => r.test(String(t).replace(/^["']|["']$/g, "")));

// Strip quoted strings and comments: prose is not a target.
const bare = cmd
  .replace(/'[^']*'/g, " ")
  .replace(/"[^"]*"/g, " ")
  .replace(/`[^`]*`/g, " ")
  .replace(/(^|\s)#[^\n]*/g, " ")
  .replace(/\d?\s*>\s*&\s*\d/g, " ")
  .replace(/2\s*>\s*(\/dev\/null|NUL)/gi, " ")
  .replace(/=>|>=|->/g, " ");

const WRITE_CMDS = /\b(tee|cp|mv|rm|truncate|dd|install|Out-File|Set-Content|Add-Content|Copy-Item|Move-Item|Remove-Item|New-Item)\b/i;
const hasWrite = /(^|[^0-9&])>{1,2}/.test(bare) || WRITE_CMDS.test(bare) || /\bsed\s+-i/i.test(bare);
if (!hasWrite) process.exit(0);

// Resolve targets.
const targets = [];
for (const m of bare.matchAll(/>{1,2}\s*([^\s;|&]+)/g)) targets.push(m[1]);
for (const seg of bare.split(/&&|\|\||[;|\n]/)) {
  const t = seg.trim().split(/\s+/).filter(a => a && !a.startsWith("-"));
  if (!t.length) continue;
  const verb = t[0].replace(/^.*[\/\\]/, "");
  if (/^(tee|truncate|dd|install)$/i.test(verb) || /^(Out-File|Set-Content|Add-Content|New-Item|Remove-Item)$/i.test(verb)) targets.push(...t.slice(1));
  else if (/^(cp|mv|rm|Copy-Item|Move-Item)$/i.test(verb)) targets.push(...t.slice(1));
  else if (/^sed$/i.test(verb) && /-i/.test(seg)) targets.push(...t.slice(1));
}

// A write token plus a protected mention but no resolvable target = built from a variable. Block.
const mentionsProtected = PROTECTED.some(r => r.test(cmd.replace(/["'`]/g, " ")));
const unresolvable = /\$\{?\w+|%\w+%|\$\(|`/.test(bare);
if (targets.length === 0 || (unresolvable && mentionsProtected)) {
  if (!mentionsProtected) process.exit(0);
  console.error("BLOCKED: this command writes, mentions a protected path, and its target cannot be resolved (built from a variable or substitution).\n  " + cmd + "\nWrite it with a literal path, or say what you wanted changed.");
  process.exit(2);
}

const hits = targets.filter(isProtected);
if (hits.length === 0) process.exit(0);

console.error(`BLOCKED: that command writes to a protected path.
  target: ${hits.join(", ")}
Config under .claude and secret files (.env, .ssh, .aws, keys, certs)
are edited by the user in a text editor. Never by a tool.
Reaching for Bash to get past the Edit denial is the exact thing the
denial exists to stop. Say what you wanted changed, and stop.`);
process.exit(2);