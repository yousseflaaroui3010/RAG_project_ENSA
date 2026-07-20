---
paths:
  - "src/app/**"
  - "src/components/**"
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/*.css"
---
# Frontend rules

- Every view ships four states: loading, empty, error, success. No exceptions.
- Accessibility: WCAG 2.2 AA. Run the axe check on new components.
  Real buttons and labels, keyboard reachable, visible focus.
- RTL-ready by default: use logical CSS properties
  (margin-inline, padding-inline, inset-inline) instead of left/right.
- No user-facing strings hardcoded in components. Route them through i18n.
- Assume the network is slow and the backend can fail. Design for it.
