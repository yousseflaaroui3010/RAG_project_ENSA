---
name: source-evaluation
description: How to weigh a source you found, not a check you ran. Use when reading search results, citing anything, judging a statistic, comparing vendor claims, researching a company or product, or when every source agrees.
---
# Weighing sources

Companion to `research-discipline` (which covers verifying your own checks) and
`absence-claims.md` (which covers what "nothing found" may claim).

## Interest test

Ask who gains money, market, or narrative if this claim is believed. A source
that profits from its own claim is a witness for its own case: a lead, never a
finding. Confirm with a party that gains nothing either way.

A vendor's docs calling its own tool read-only is a claim. The OAuth scopes it
actually requests are evidence. When they disagree, the request wins.

## Vendor statistics never ship alone

"73% of firms suffer X", published by the company selling the X-solver, or by
its sponsored study or PR. Trace it to the raw survey: who ran it, who paid, N,
sampling, year. Untraceable numbers get tagged "origin unknown" and carry no
weight in the verdict.

## Party claims, for states and politics

State-funded or state-aligned outlets covering rivals, or covering themselves,
are parties to the dispute, never referees. Triangulate with third-country
records, supranational bodies, court filings, or raw primary data. When every
available source is a party, present each claim as "X says, Y says" with the
interest tag attached, and withhold the verdict.

## Statement against interest outranks self-praise

A vendor admitting a flaw. A state confirming its own failure. A paper reporting
a null result. The heaviest evidence there is. Believe that part hardest.

## Circular sources collapse

Ten articles citing one press release are one source. Dedupe by origin before
counting confirmations. "Independent" means separate reporting, never one wire
story echoed twice.

## Scope match

Before attaching a statistic to a claim, check region, timeframe, population,
and definition. A US 2019 number cannot carry a global 2026 claim.

## Authority ranking

Papers, official docs, primary repos, and government or court records outrank
journalism and corporate blogs, which outrank forums, social posts, and videos.
Lower tiers produce leads. A lead becomes a finding only after a higher tier
confirms it. Authority is half the check; the interest test is the other half.

## Citation audit

- Never cite from a snippet. Fetch and read the page before the citation lands.
- Chase to the primary. If B cites A, read A and cite A, or mark it secondhand.
- Recheck before shipping: re-open each source and match the exact sentence to
  the claim it carries. A real link under a wrong claim is the top failure mode.
- Label the relation: "source states X", "source implies X", or "my inference
  from the source". Never blur the three.
- Date every citation with publication date and access date.
- If a source fails to load at recheck, downgrade its claim to unverified.

## Source routes

- Papers: exact title or DOI, then an open copy (arXiv, PubMed Central, author
  pages). Read methods, N, funding, conflicts. Check citing papers for
  retractions and failed replications.
- Forums: mine for failure reports. One anecdote is noise. Five matching
  anecdotes are a signal worth verifying upstream.
- Video and audio: work from the transcript. Never quote something you have not
  read or watched. Cite the timestamp.
- Books: snippets and passages quoted elsewhere. Say when full text is out of reach.
- Paywalls: report what the abstract and metadata support. Mark the rest unread.

## Digging on a company, person, or product

- Names first. Current name, prior names, rebrands, parent and subsidiaries,
  founders' earlier ventures. Renaming buries history, so search the old names.
- Pull records directly: court dockets, regulator actions, CVE and NVD, recall
  databases, sanctions lists. Go to the record rather than waiting for
  journalism to surface it.
- Time-travel key pages. Archived versions catch claims that changed, pricing
  that moved, promises that vanished. A quiet edit is a finding. Cite both
  versions with dates.
- Insider signals (review sites, ex-employee threads, hiring waves) are leads
  only. Confirm upstream.
- Ghost content: report what existed, who referenced it, and that it is gone.
- Search in the subject's own language. Local press carries what English misses.

## Base rates before verdicts

One lawsuit in a litigious industry. One bad review among thousands. One CVE in
a decade-old codebase. Zoom out first. Dirt counts only against the baseline for
that industry, size, and age.

Status-tag every negative finding: allegation, regulator finding, court
judgment, settlement, resolved, or retracted, plus its date. A resolved 2014
issue is history. Label it that way.

## Every claim gets one hostile query

When every source cheers, hunt the failures before writing a word.