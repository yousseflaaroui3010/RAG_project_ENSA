# Jury question drill (ST-46)

Status: DRAFT, 2026-09-12. Thirty likely questions, each with an owner and
a one-minute answer built from the signed docs and the measured numbers.
Exit gate: every question owned and answered, and one mock defense held.
**Owners must rewrite each answer in their own words**; a memorised
paragraph sounds memorised.

Owners: **YL** = build and architecture, **MB** = research, quality and
evaluation. Where both are listed, the first answers and the second adds.

## The product

1. **What problem does Sanad solve?** (MB) Small teams keep rules in
   documents nobody reads end to end. General chat assistants answer
   fluently but without sources, and invent when they do not know. Sanad
   answers only from your own documents, shows the exact passage, and says
   "not in the documents" when it is not.
2. **Who is the user?** (MB) One person on one machine, over a folder of
   documents (HR rules, legal texts, manuals). No accounts, by design
   (PRD non-goals). Personas rest on reasoning; the three interviews (ST-50)
   were the planned check. Say honestly whether they happened.
3. **Why not just use ChatGPT with the PDF?** (MB, YL) Three things it does
   not promise: a source on every answer (G3, 37/37), a refusal when the
   answer is absent (G2, 20/20), and a release gate that blocks a version
   that fails either. Plus: documents stay on this machine.
4. **What does "local-first" mean here, exactly?** (YL) Documents, index,
   database and reports stay on the machine. The question and the retrieved
   passages go to the cloud model to write the answer. A fully offline mode
   with a local model is designed (ADR-06) but was not rehearsed for this
   defense (a recorded ruling); say so plainly.
5. **Is the data safe with Gemini?** (YL) The demo corpus is public law and
   public manuals, chosen so this question has a safe answer. The provider
   is the Gemini free tier; its terms were flagged for review before any
   non-public document (DECISIONS row, OR-2), and PRD open risk R3 says real
   personal data needs a data-protection review first. Do not claim more.

## How it works

6. **Walk us through one question.** (YL) Memory summary, then the planner
   either asks one clarifying question or splits the question into
   searches; hybrid search (meaning-based E5 vectors plus keyword BM25) in
   this workspace's own index; a grader checks the passages actually
   address the question, rewording at most twice; the full parent sections
   are loaded; the writer answers only from them, with sources, or refuses.
7. **Why parent and child chunks?** (YL) Small children (500 characters)
   are precise to search; the parents (whole sections, merged below 2,000
   characters) give the writer enough context to answer and to cite an
   article correctly.
8. **Why hybrid search?** (YL) Legal questions mix meaning ("probation
   period") with exact tokens ("Article 14", "CNSS"). Vectors catch the
   first, keywords the second.
9. **Why multilingual-e5-base?** (YL) French corpus, runs on a CPU, free.
   It needs its `query:` / `passage:` prefixes, and a test fails if any
   embedded text lacks one.
10. **What stops it from answering without a source?** (YL) The answer
    object cannot be built without sources; the code raises instead. So an
    unsourced answer cannot reach the screen, and G3 measures it anyway.
11. **Why LangGraph?** (YL) The flow has loops (reword and retry) and a
    branch (clarify or search). A graph makes the retry ceiling and every
    step visible in the trace.
12. **How are workspaces kept apart?** (YL) One vector collection per
    workspace; a test proves an HR question never returns a Manuals chunk.

## Evaluation

13. **How do you know the answers are right?** (MB) A frozen set of 60
    French questions written before tuning: 40 the documents answer, 20
    they do not. Each answer is scored for groundedness (every claim
    supported by the passages it was given).
14. **Your results?** (MB) G1 37 of 40 fully grounded (target 36), G2 20 of
    20 refused, G3 37 of 37 answers with sources. The release gate passed.
15. **What were the 3 failures?** (MB) g-in-014, 026 and 033 (v1.0.1): in-scope
    questions the system refused. The safe way to fail: it declined, it did
    not invent.
16. **Who grades the answers? Isn't a model grading itself biased?** (MB,
    YL) The plan named RAGAS; it would not import on our pinned libraries
    (verified by running it), so a change request replaced it with an
    in-house judge prompt on the same model family. That is a real bias
    risk, and it is recorded. Mitigations: the judge sees exactly the
    passages the writer saw, the score must be a full 1.0 to count, and we
    read the low-scoring answers by hand (ST-36 triage).
17. **Did you tune on the test set?** (MB) The set was frozen at v1 before
    the first full run, and later edits need a new version. Two v1 edits
    skipped that rule; we found it (issue #88), published v2 with the history
    written down, and re-measured v1.0.1 on v2 (evaluation/golden/README.md). One tuning
    iteration was allowed by the plan (ST-36) and is documented question by
    question.
18. **Why French only?** (MB) The flagship corpus is Moroccan labour law in
    French. Arabic is the next corpus; the interface already mirrors
    right-to-left.

## Speed and scale

19. **How fast is it?** (YL) Median answer 8.3 s, slowest 18.1 s over 20
    timed questions (target 20 s median, 60 s at the 95th percentile).
    The first question after a start takes about 23 s while models load.
20. **How long to add documents?** (YL) Measured three times, cold, on a laptop
    CPU: 449.4 s and 375.3 s per 200 pages in two quiet runs (target
    600 s), and 731.6 s in one run while other work was running. We report both, because the
    honest answer is "within target, but sensitive to load". Most of the
    time is the embedding model (about 0.29 s per chunk) and PDF reading.
    A second Sync of unchanged files takes under 0.1 s.
21. **How big can a workspace be?** (YL) The soft cap is 50 files or 1,500
    pages; above it Sanad warns and suggests splitting. It is a warning, not
    a hard limit.

## Engineering and quality

22. **How did you test it?** (YL) About 810 automated tests, run on every
    pull request with lint and a secret scan; main is protected so a red
    check blocks a merge. Tests were proven by breaking the code on purpose
    and watching them fail.
23. **What happens if it crashes mid-sync?** (YL) Each file's result is
    saved as it goes; on the next start, an abandoned Sync is closed from
    what it already saved, and an interrupted evaluation keeps its finished
    questions as Partial.
24. **Is it accessible?** (MB) Sampled keyboard paths, visible focus, contrast
    above 4.5:1 in both themes, reduced motion, right-to-left mirroring:
    35 of 41 manual QA rows pass. The other 6 needed a person listening with
    a screen reader, and we dropped that check from the plan: say so plainly.
    The markup a screen reader relies on (live regions, labels, sort state)
    is there and was audited automatically -- but nobody listened.
25. **What is the API for?** (YL) The same engine through 9 endpoints under
    a signed OpenAPI contract, with tests that fail if the code drifts from
    it.
26. **How did two people split the work?** (MB, YL) One build owner, one
    research and quality owner, scrum-style sprints, one branch per story,
    and every branch reviewed before merge.

## Limits and future

27. **What does it NOT do?** (MB) No legal advice (the disclaimer says so),
    no internet answers, no accounts, no scanned-PDF reading (no OCR), no
    streaming text, no learning from your chats.
28. **What would you do next?** (YL) Faster intake (smaller embedding
    model or batching, measured against G5), the offline mode rehearsed,
    PowerPoint intake and an answer-trace screen (planned V1.1).
29. **What was the hardest bug?** (YL) Pick one real story from the journal
    and tell it in 45 seconds: symptom, wrong first guess, proof, fix. The
    missing CLEISS guide is a good one: three refusals turned out to be a
    document the evaluation workspace never had, not a model problem.
30. **How did you use AI tools in this project?** (both) Answer truthfully
    and consistently with each other. The journal records how work was done.
