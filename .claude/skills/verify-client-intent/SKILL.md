---
name: verify-client-intent
description: >
  Verify any deliverable or decision against CLIENT.txt to ensure alignment
  with the client's original intent. Use before handoffs or when unsure.
triggers:
  - "verify against client"
  - "check client intent"
  - "does this match CLIENT.txt"
---

# Verify Client Intent Protocol

## Steps
1. Read `docs/CLIENT.txt` in full.
2. Read the deliverable or decision being verified.
3. For each claim/requirement in the deliverable:
   a. Find the corresponding line(s) in CLIENT.txt.
   b. If found → mark as TRACED.
   c. If not found but labeled as RECOMMENDATION → acceptable (must be labeled).
   d. If not found and NOT labeled as recommendation → FLAG as UNTRACED.
4. For each CLIENT.txt requirement:
   a. Check if it appears in the deliverable.
   b. If missing → FLAG as MISSING REQUIREMENT.
5. Output:
   - Traceability score: X/Y requirements traced
   - List of UNTRACED items
   - List of MISSING REQUIREMENTS
   - Verdict: PASS / FAIL (PASS = 100% traced, 0 missing)
