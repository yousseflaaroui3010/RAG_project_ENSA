# Automated accessibility audit, 2026-09-15

Lighthouse (Chrome DevTools MCP), navigation mode, against the app run from
branch `fix/S6-ST-38-reader-hints-and-log-names` (main plus #130) in the
login-free mode, on scratch data holding one workspace. No model key was set,
so no page showed an answer.

**What this is and is not.** An automated audit catches mechanical failures:
missing labels, contrast, landmark and heading structure, names on controls.
It does NOT replace the six ST-38 screen-reader rows. A page can score 100
here and still be confusing to hear. Those rows still need a person with
Narrator.

| Screen | Device | Accessibility | Best practices | SEO |
|---|---|---|---|---|
| Workspaces `/workspaces` | desktop | **100** | 100 | 90 |
| Chat `/` | desktop | **100** | 100 | 90 |
| Reports `/reports` | desktop | **100** | 100 | 90 |
| Admin `/admin` | desktop | **100** | 100 | 90 |
| Workspaces, Arabic `?lang=ar` | mobile | 98 | 100 | 90 |
| Workspaces, French `?lang=fr` | mobile | 98 | 100 | 90 |

## The two failures, read rather than trusted

- **`landmark-one-main` on mobile, both languages.** Not a language issue:
  French fails the same way. Below 768 px `sanad.css` hides `.main` and shows
  a "Sanad targets a desktop browser" notice, exactly as the signed UX spec
  requires ("Below 768px the app shows a plain notice ... Do not build a
  phone layout", UX spec line 49). The notice itself is not marked as the
  main landmark, so a phone screen-reader user has nothing to jump to.
  Recorded in `docs/known-issues.md`; not changed, because the layout is
  signed and the fix is outside it.
- **`meta-description` on every page (SEO).** Search-listing advice. Sanad
  is local-first and its published instance sits behind a password; it
  should not be listed. Not a defect.

Reports were written to the session scratch folder, not committed: each
HTML report is several hundred kilobytes and the table above is what they
say.

## Re-check after the fix (PR #132, same day)

Run against branch `fix/S6-ST-38-polish`, login-free mode, scratch data,
after the phone notice gained `role="main"` and the page gained an inline
tab icon.

| Screen | Device | Accessibility | Best practices | SEO |
|---|---|---|---|---|
| Workspaces, Arabic `?lang=ar` | mobile | **100** (was 98) | 100 | 90 |
| Workspaces `/workspaces` | desktop | **100** | 100 | 90 |

`landmark-one-main` no longer fails. The server's own request log for that
browser session shows 4 page loads and 0 requests for `/favicon.ico`,
where every page load had produced one. The remaining SEO item is still
`meta-description`, for the reason given above.
