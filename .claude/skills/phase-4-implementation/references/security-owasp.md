# Security: the OWASP Top 10, 2025 edition

Verified against owasp.org/Top10/2025 on 2026-08-15. Two categories are new
since 2021 and SSRF was absorbed into A01 [1]. Re-check before quoting the list
in anything client-facing.

`threat-modeling` covers how to walk a feature's risks. This file is the
checklist for code you are writing now.

## The list

| # | Category | Note |
|---|---|---|
| A01 | Broken Access Control | Still #1. Now includes SSRF |
| A02 | Security Misconfiguration | Up from #5 |
| A03 | Software Supply Chain Failures | New. Highest incidence, lowest scanner coverage |
| A04 | Cryptographic Failures | Down from #2 |
| A05 | Injection | Down from #3 |
| A06 | Insecure Design | Down from #4 |
| A07 | Authentication Failures | Stable |
| A08 | Software and Data Integrity Failures | Stable |
| A09 | Security Logging and Alerting Failures | Renamed. Logging without alerting is worth little |
| A10 | Mishandling of Exceptional Conditions | New. Failing open, improper error handling |

Three of these deserve a sentence beyond the checklist.

**A01** is two separate questions, and the second is the one that gets skipped:
is this person authenticated, and does *this* user own *this* resource.
Object-level and function-level authorization are the most exploited patterns in
API-heavy apps. SSRF lives here now, because a server-side fetch of a
user-supplied URL is an access control decision, not a networking detail.

**A03** covers the build system and the distribution path, not just what sits in
`package.json`. Scanners are behind on this category, so a clean scan is not a
clean bill. `dependency-vetting` owns the procedure for admitting a package.

**A10** is where the error shape in `backend-contract.md` becomes a security
control rather than a nicety. Failing open is the failure mode.

## The checklist, run before sign-off

**A01 Broken Access Control**
- Every endpoint checks authentication and, separately, ownership.
- Any id in a URL is validated against the session, never trusted.
- CORS restricted to known origins. No wildcard in production.
- Any server-side fetch of a user-supplied URL is checked against an allowlist.

**A02 Security Misconfiguration**
- No stack traces, internal paths or version numbers in a response.
- No debug mode or verbose logging outside development.
- No hardcoded credentials in code or config.
- Content-Security-Policy set and tested.
- X-Frame-Options, X-Content-Type-Options and Referrer-Policy set.
- Least privilege for services, database users and humans.

**A03 Software Supply Chain Failures**
- Audit clean of HIGH and CRITICAL. Anything MODERATE gets logged with a
  written accepted-risk note from the human.
- Lockfile committed and current.
- Every dependency has a licence you have actually looked at.
- Subresource integrity on any script loaded from a CDN.

**A04 Cryptographic Failures**
- HTTPS everywhere, HSTS set, no HTTP fallback.
- Passwords with bcrypt at cost 12 or higher, or argon2id. Never a
  general-purpose hash.
- Session tokens random, 128 bits or more, HttpOnly and Secure and
  SameSite=Strict.
- No MD5, no SHA-1.
- Secrets in environment variables or a secret manager. Never committed, never
  in the browser bundle, never in git history.

**A05 Injection**
- Parameterized queries only. No string building.
- Escape output by context, not once globally.
- No `eval`, no `innerHTML` with unsanitized input.
- Any HTML that came from a model gets sanitized before it renders.

**A06 Insecure Design**
- File type checked by magic bytes, not by extension.
- File size limited, enforced on the server.
- A timeout on any processing that could hang.
- Rate limits on anything expensive.

**A07 Authentication Failures**
- Never roll your own identity. Keycloak, Auth0, Clerk or NextAuth.
- Access token expiry short. Refresh token rotated on use.
- Lockout or a challenge after repeated failures.
- Password reset tokens time-limited and single use.

**A08 Software and Data Integrity Failures**
- Any JSON from a model validated against a schema before use. Never trust raw
  model output as a data structure.
- No deserialization of untrusted data.

**A09 Security Logging and Alerting Failures**
- Auth failures, rejected uploads and rate-limit hits all logged.
- No personal data, tokens or file contents in a log line.
- An alert defined for quota thresholds, before the bill arrives.
- `logging-and-tracing` owns the shape of a log line.

**A10 Mishandling of Exceptional Conditions**
- Fail closed. A timeout or an unexpected type lands in a branch you wrote.
- Every case in `backend-contract.md` handled, not assumed away.
- Generic errors to the user, detail to the logs.

## Sources

[1] OWASP Top 10:2025 Introduction, owasp.org, accessed 2026-08-15.
    https://owasp.org/Top10/2025/0x00_2025-Introduction/