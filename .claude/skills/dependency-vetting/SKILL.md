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
3. License: name it, confirm compatibility with this project's license
   and its commercial use. Copyleft surprises are rejections.
4. Names first: prior names, forks, ownership transfers, the maintainer's
   earlier projects. Renames bury history; search old names too.
5. Hostile pass: "<name> limitations", "<name> deprecated", "migrate away
   from <name>", "<name> vs alternatives". If every source cheers, hunt
   failures before writing a verdict.
6. Fit: compare against the S2 stack record and ADRs. Healthy but
   architecture-hostile is still a rejection.

## Output
Verdict (adopt | adopt with limits | reject), evidence lines with dates,
flip condition, and the DECISIONS.md row text ready to paste.
