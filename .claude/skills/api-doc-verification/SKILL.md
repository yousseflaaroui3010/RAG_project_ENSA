---
name: api-doc-verification
description: Verify an external API, SDK method, or config option against current official documentation before writing code that uses it. Use whenever code will call an interface not already used in this repo.
---

# API Documentation Verification (docs-verifier procedure)

Coding against a remembered API is dialing a phone number from memory:
one wrong digit and you are talking to a stranger.

## Steps
1. Pin the version: read the lockfile or config for the exact installed
   version. Verify against that version's docs, never "latest" blindly.
2. Fetch the official page for the exact method, endpoint, or option.
   Official docs and the primary repo outrank blogs; blogs outrank forums.
3. Confirm: signature, required and optional parameters, auth, rate
   limits, error shapes, deprecation notices.
4. One disconfirming query: "<thing> deprecated" or "<thing> breaking
   changes". Migrations hide in changelogs, not landing pages.
5. Write the verified shape into the task card so the builder codes
   against text from the doc, never from memory.

## Rules
- A page that will not load downgrades its claim to unverified; say so.
- Never invent a fallback signature. Cannot verify = stop and report.
