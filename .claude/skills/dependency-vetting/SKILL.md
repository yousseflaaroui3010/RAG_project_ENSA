---
name: dependency-vetting
description: Vet a library, framework, or service before it enters the project. Use for any new dependency request or when an existing dependency looks abandoned, renamed, or risky.
---

# Dependency Vetting (tech-scout procedure)

A dependency is a hire: you check references before it touches payroll.

## Checks, in order
1. Vitals: last commit date, release cadence, open-issue response time,
   maintainer count, bus factor. One maintainer and six silent months is
   a decay signal.
2. Security: CVE and GitHub advisory history for the package AND its
   direct dependencies. Scope every absence claim: "no CVEs as of <date>,
   checked NVD and GitHub advisories".
   **Then actually install it and run `npm audit`.** Reading advisories
   is not the same as seeing what the resolver produces. T-014 installed
   a stack whose every pin had just been verified current and got three
   high-severity advisories, all transitive, one of them reachable in
   production.
3. License: name it, confirm compatibility with this project's license
   and its commercial use. Copyleft surprises are rejections.
4. Names first: prior names, forks, ownership transfers, the maintainer's
   earlier projects. Renames bury history; search old names too.
5. Hostile pass: "<name> limitations", "<name> deprecated", "migrate away
   from <name>", "<name> vs alternatives". If every source cheers, hunt
   failures before writing a verdict.
6. Fit: compare against the S2 stack record and ADRs. Healthy but
   architecture-hostile is still a rejection.

## When `npm audit` is red (the T-014 procedure)

**Read the advisories. Never obey the tool's suggested fix blindly.**
`npm audit fix --force` offered `next@9.3.3` to patch a Next 16 project:
a seven-major downgrade dressed as a security fix.

1. Locate the vulnerable package in the tree. Nested under a dependency
   (`node_modules/next/node_modules/postcss`) means the parent pins it,
   so upgrading the parent will not help.
2. Judge REACHABILITY, and say which it is. Build-time over files we
   author ourselves is low. In the request path over attacker-supplied
   input is not. A libvips CVE reached through `next/image` on uploaded
   product images is a live path, and that is what decided T-014.
3. Check whether the parent can even reach the fix. **A caret on a `0.x`
   version locks the minor**: `^0.34.5` can never resolve to 0.35, so a
   package can be structurally unable to adopt its own patch. That is an
   `overrides` case, not a wait-for-upstream case.
4. Prefer an override that is semver-compatible (8.4 -> 8.5 is safe). An
   override outside the parent's declared range is a real risk: take it
   when reachability demands, and **label it unverified until exercised
   at runtime**, with the task that will exercise it named.
5. Re-run `npm audit` and quote the result. Record the before and after.

## Output
Verdict (adopt | adopt with limits | reject), evidence lines with dates,
flip condition, `npm audit` before/after counts, any override with its
unverified label and exercising task, and the DECISIONS.md row text ready
to paste.
