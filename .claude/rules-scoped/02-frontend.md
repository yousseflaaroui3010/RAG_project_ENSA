---
paths:
  - "**/*.tsx"
  - "**/*.jsx"
  - "**/*.vue"
  - "**/*.svelte"
  - "**/components/**/*"
  - "app/**/*"
---

<!-- BOOTSTRAP: replace the generic paths above with this project's real ones,
     or delete this file if there is no user interface. A rules file that does
     not apply is pure context cost. -->

# Frontend

## Every screen state must exist
Loading, error, empty and offline. Not just the happy path. If a screen can
show a spinner, it can show a failure — build both, in the same task.

## Accessibility floor
Semantic HTML. Keyboard reachable. Real labels on inputs. A button is a
`<button>`, never a clickable `<div>`. Every interactive path completable with
a keyboard alone.

Reach for a component library's accessible primitives before hand-rolling.
Hand-rolled focus management is where accessibility goes to die.

## Mobile first
Write the smallest-screen layout, then grow it with `min-width` queries.
Not `max-width`. Skip this only for a tool that is desktop-only by nature.

## When to extract a component
On the third use, or when a prop is passed through two levels to reach a child.
Not before.

## State
Keep it local until two components need it, then lift it. Reach for a global
store only when the data is genuinely app-wide.

## Never
- Convey a state with colour alone. Errors get text
- Remove a focus outline without replacing it with something as visible
- A positive `tabindex`
- Add `aria-*` to paper over wrong markup. Fix the markup
- `any` as a prop or state type

If a design needs an interaction with no accessible equivalent, stop and ask.
That is a design decision, not something to approximate.
