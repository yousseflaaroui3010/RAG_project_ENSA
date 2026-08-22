---
name: phase2-architecture
description: >
  Phase 2: Architecture & Tooling. Tech stack, system design, security model,
  data model, API contracts, infrastructure, CI/CD, tech scouting.
triggers:
  - "phase 2"
  - "architecture"
  - "tech stack"
  - "system design"
  - "data model"
  - "API contract"
  - "infrastructure"
  - "tech scout"
  - "security model"
  - "design patterns"
---

# PHASE 2 — ARCHITECTURE & TOOLING

## SPRINT DISCIPLINE
Work in MICRO-SPRINTS (1 blueprint section per cycle):
1. Tech Scout → Security Model → Data Model → Project Structure → API Contracts → Infra/CI-CD → Threat Model
2. `/compact` after each section. `/clear` after phase completion.
3. Update contextlog.md + gapslog.md before every compact/clear.

## INPUTS & VERIFICATION
Read: PRD.md (full) → CLIENT.txt (verify alignment) → BA + UX Reports (context).
Every decision must trace to a PRD requirement. Ambiguous? → gapslog.md → PM. Never assume.

## SEQUENCE
```
PRD.md (input)
  → Tech Scout: FIRST — find what exists before anyone designs anything
  → Solutions Architect: system design, data model (using scout's tool registry)
  → Tech Lead: project structure, design patterns, code standards
  → Security Engineer: threat model, auth architecture
  → DevOps: infrastructure, CI/CD, environments
  → Validation: all sections unified into Tech_Blueprint.md
```

---

## TECH SCOUT — THE ANTI-REINVENTION ROLE

**Purpose:** For every capability the PRD requires, find the best existing tool/library/service/model BEFORE anyone writes architecture. Don't build what already exists. Don't pay for what's free. Don't guess — search, evaluate, confirm.

### Process (for each PRD requirement/capability)

```
1. IDENTIFY — What capability does the PRD need?
   Example: "Users need to log in with email, Google, and SSO"

2. SEARCH — What already exists that does this?
   - Search: "[capability] open source currentYear"
   - Search: "[capability] best practices senior engineers"
   - Search: "[capability] vs [alternative] comparison"
   - Check: GitHub trending, awesome-lists, community recommendations
   - Check: Official docs of candidates for current version + status


3. EVALUATE each candidate against:
   Solves our need? | Latest stable version? | Maintained (<6mo commits)? | Community (stars, SO presence)? | License OK? | Known CVEs? | Good docs? | Integration effort vs build-from-scratch? | Free > freemium > paid? | Swappable later (no lock-in)?

4. COMPARE — Build vs Buy vs Integrate
   For each capability, show:
   - Option A: Build from scratch — estimated effort, risk, maintenance burden
   - Option B: Use [tool X] — integration effort, trade-offs, cost
   - Option C: Use [tool Y] — integration effort, trade-offs, cost
   - RECOMMENDATION with reasoning, confidence %, probability of being wrong

5. CONFIRM — Validate the choice
   - Read the official docs (not just blog posts)
   - Check GitHub issues for deal-breaker bugs
   - Verify it works with our stack (framework, language, DB)
   - Check if the community actually recommends it for our use case (not just marketing)
```

### Tech Scout Output Format (per capability)
```
CAPABILITY: [What we need — e.g., "Authentication & SSO"]
  CHOSEN: KeyCloak v26.x
    Why: Open-source, OAuth2/OIDC/SAML/SSO, admin UI, self-hosted, active community
    Integrate: ~2 days | Build from scratch: ~3-4 weeks (worse security)
    Source: [URL] | Confidence: HIGH | Wrong probability: 5%
  REJECTED: Auth0 — paid at scale, vendor lock-in
  REJECTED: Firebase Auth — Google lock-in, limited SSO
  NOTE: If client uses Azure → Azure Entra ID instead

CAPABILITY: "API Contract Generation"
  CHOSEN: Orval v7.x — generates typed clients from OpenAPI, keeps FE/BE in sync
  REJECTED: Manual HTTP clients — drift-prone, tedious, error-prone

CAPABILITY: "Summarize uploaded documents" (AI/ML)
  CHOSEN: HuggingFace facebook/bart-large-cnn — free, pre-trained, local or API
  REJECTED: OpenAI GPT-4o — better quality but paid per token
  REJECTED: Custom model — months to build, no justification
  FALLBACK: If quality insufficient → escalate to PM for paid LLM budget

CAPABILITY: "Agent orchestration" (if needed)
  CHOSEN: LangGraph — stateful multi-step workflows, human-in-the-loop
  USE WITH: LangChain — tool/retrieval integration (Graph=flow, Chain=tools)

CAPABILITY: "File Storage"
  REJECTED: MinIO — AGPL, not truly open-source for commercial
  EVALUATE: Supabase Storage / CloudFlare R2 / S3-compatible
```

### Scouting Domains
**Infra:** auth, storage, email, search, cache, queues, CDN, monitoring, logging.
**Frontend:** UI libs, forms, state mgmt, data fetching, charts, rich text, animation.
**Backend:** ORM, validation, jobs, PDF/image processing, rate limiting, WebSockets.
**AI/ML:** pre-trained models (HuggingFace), embeddings, vector DBs, LLM (free>paid), agents (LangGraph/LangChain), RAG.
**DevOps:** CI/CD, IaC, containers, secrets, deployment. **Testing:** runners, mocking, load, SAST/DAST, a11y.

---

## REMAINING BLUEPRINT SECTIONS (built on Tech Scout's registry)

All sections use tools from the scout's registry. Every decision justified with ADR (Context → Options → Decision + WHY → Consequences → Sources).

1. **Security Model** — Auth from scout's pick, RBAC/ABAC from PRD, OWASP 2025 mitigations, secrets mgmt, CORS/CSP/rate limiting
2. **Data Model** — ERD from PRD entities, table defs (cols, types, constraints, indexes), soft/hard delete, migrations, seeding, backup
3. **Project Structure** — Mono/polyrepo (justified), feature-based dirs, layer separation (routes→services→repos→domain), env validation at startup
4. **Design Patterns** — Per concern (Repository, Strategy, Factory, etc.), justified for THIS project, anti-patterns forbidden
5. **API Contracts** — OpenAPI spec all endpoints, typed schemas, auth+rate limits per endpoint, error format, versioning (/api/v1/)
6. **System Architecture** — High-level diagram, component comms, scalability, caching, background jobs
7. **Infra & CI/CD** — Environments (dev→staging→prod), CI pipeline (lint→types→test→security→build), rollback, monitoring, IaC
8. **Threat Model** — Attack surface per feature, STRIDE on critical flows, mitigations mapped to architecture

## ALL ROLES — RULES
- Search online for EVERY choice. Sources, versions, reasoning required.
- Confidence level + probability of being wrong on every recommendation.
- Don't build what exists. Don't pay for what's free. Don't guess — verify.
- Every decision traces to PRD. Bus factor = ∞.

## PHASE 2 COMPLETE WHEN
□ Tech Scout registry covers all PRD capabilities (build vs integrate justified)
□ Blueprint has all sections □ Tools verified (version, license, CVEs, maintenance)
□ ADRs for major decisions □ Security model covers OWASP 2025
□ API contracts cover all PRD endpoints □ Data model covers all entities
□ Verified vs PRD.md + CLIENT.txt □ Phase 3 + 4 teams confirm readiness
□ contextlog.md clean → `/compact` → `/clear`