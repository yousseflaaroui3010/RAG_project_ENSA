---
name: threat-modeling
description: Walks security and privacy risks of a feature. Use when the work touches user data, money, login, file uploads, or anything reachable from the internet.
---

# Security and threat modeling (all projects)

Threat modeling happens **while the design is still cheap to change**, not
as a review at the end. Name the threats in the architecture artifact that
creates the surface, not in a separate document nobody opens.

## The three lenses, applied per feature

**STRIDE** for security, per element (each entry point, data store, process,
data flow):
- **S**poofing - can someone claim to be another principal?
- **T**ampering - can data be altered in transit or at rest?
- **R**epudiation - can an actor deny having done it? Is there an audit trail?
- **I**nformation disclosure - what leaks, to whom, through which path?
- **D**enial of service - what is unbounded? Payloads, queries, retries, jobs.
- **E**levation of privilege - where can a lower role reach a higher one?

**LINDDUN** for privacy, which STRIDE does not cover and which most builds
skip entirely:
- **L**inking - can two records be tied to the same person?
- **I**dentifying - can a pseudonymous record be resolved to a human?
- **N**on-repudiation - is someone forced to be provably associated with an
  action they should be able to deny?
- **D**etecting - does the mere existence of a record leak something?
- **D**ata disclosure - excessive collection or exposure.
- **U**nawareness - does the person know what is held about them?
- **N**on-compliance - retention, erasure, lawful basis, cross-border.

LINDDUN matters most wherever a real person's identifier is a primary key,
where staging holds a copy of production, and where analytics or exports
leave the system.

**OWASP** as the checklist layer: Top 10 for the common shapes, **ASVS** when
a real verification level is needed, and the relevant cheat sheets at
implementation time.

## Tooling

**Threagile** is the preferred threat-modeling tool: a USENIX evaluation of
six open-source threat-modeling tools scored it highest. It is
model-as-code (YAML describing assets, data flows and trust boundaries),
which means the threat model lives in the repository, diffs in review, and
runs in CI like any other check rather than rotting in a diagram.

## Session tokens: the position, and the reasoning behind it

**Never store session identifiers or tokens in `localStorage`.** Anything in
local storage is readable by any JavaScript on the page, including injected
script. Cookies can be marked `httpOnly`, which puts them out of reach of
JavaScript entirely.

But be precise about what that buys, because the common advice is sloppy:

**If you have XSS, it barely matters where the token lives.** The attacker
is executing in the user's origin and can simply send requests as that user.
Moving the token does not stop that.

**The real win from `httpOnly` is exfiltration.** The attacker cannot copy
the token out and replay it later from their own machine, at their leisure,
after the user has closed the tab. That is the difference between an attack
bounded by the victim's session and one that outlives it.

So the answer is not "use cookies". The answer is:

- **`httpOnly`** so script cannot read it
- **`SameSite`** to blunt cross-site request forgery
- **a CSRF token** because SameSite alone is not a complete defence
- **refresh token in the cookie, access token in memory** - the long-lived
  credential is unreadable by script, the short-lived one dies with the tab

**State the limit honestly whenever recommending this: it shrinks the blast
radius, it does not remove the risk. The real fix is not having XSS.**
Output encoding, a strict Content Security Policy, framework escaping left
switched on, and no `dangerouslySetInnerHTML` / `v-html` / `innerHTML` on
anything a user can influence.

## How to raise these

Do not produce a threat-model appendix nobody reads. Put the finding where
the decision is made: name the STRIDE or LINDDUN category in the decision
row, and if a control is missing say which task owns it. An unowned risk
becomes a false sense of coverage.
