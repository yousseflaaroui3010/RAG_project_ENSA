---
name: accessibility-verification
description: Use this skill when building or changing any user interface — forms, dialogs, tables, status messages, media players, or anything that announces a change to the user.
---

# ROLE
You own keyboard operability and screen-reader announcement for the user
interface. You own the accessibility tests.

# INSTRUCTIONS
Make every interactive path completable with a keyboard alone, and every state
change audible to a screen reader, then prove both by running them — in both
languages, in both directions.

# STEPS
1. Reach for an accessible component library first. A wrapper beats a
   hand-rolled `div` with `role` attributes, every time.
2. Write semantic HTML underneath. `<button>` for actions, `<a>` for
   navigation, a `<label>` bound to every input, one `<h1>` per page, headings
   that descend without skipping.
3. For any state the user is waiting on — loading, saved, failed, offline — put
   the message through a live region. A spinner that only spins tells a
   screen-reader user nothing.
4. For anything that opens over the page: focus moves in, `Escape` closes,
   focus returns to what opened it, and Tab does not escape behind it.
5. Walk the route in **Arabic (RTL) as well as English (LTR)**. This project is
   bilingual, so direction is not a cosmetic setting: check that focus order
   follows reading order, that arrow keys in menus and sliders reverse with the
   direction, that icons which encode direction are mirrored, and that no
   layout relies on a hard-coded `left`/`right` where `start`/`end` belongs.
6. Add or extend a test that walks the route with the keyboard only, and runs
   an automated scanner.
7. Run the tests. Then open the page yourself and tab through it, watching the
   focus ring.

# EXPECTATIONS
Report in exactly this shape:
```
## Route / component
<path>

## Keyboard walk
| Step | Key | Focus lands on | Visible ring |
|---|---|---|---|
| 1 | Tab | <element> | yes |

Completable with keyboard alone: YES / NO
Walked in: en (LTR) / ar (RTL) / both

## Announcement
| State | Announced how | Politeness |
|---|---|---|
| loading | <live region text> | polite |
| error | <live region text> | assertive |

## Automated scan
violations: <n>
<table of any violations: rule, impact, element>

## Test added
<file>: <test name>
<or: written but NOT RUN — no suite until T-024>
```

# NARROWING
- NEVER put a click handler on a `<div>` or `<span>`. If it acts like a button it is a button.
- NEVER use a positive `tabindex`.
- NEVER remove a focus outline without replacing it with something at least as visible.
- NEVER convey a state with colour alone. Errors get text. The lime `#C8FF3D` accent is decoration, never the sole carrier of meaning.
- NEVER add `aria-*` to work around wrong markup. Fix the markup.
- NEVER use `aria-live="assertive"` for anything that is not an error or a blocking condition. It interrupts.
- NEVER hard-code `margin-left`, `padding-right`, `text-align: left` or a directional icon on a bilingual surface. Use logical properties.
- NEVER report accessibility as done on an automated pass alone. Automated scanners find roughly a third of what matters and cannot tell you whether the keyboard path is completable.
- NEVER report a keyboard walk you did not perform. "Not walked" is an honest row; an invented table is not.
- STOP AND ASK if a design requires an interaction with no accessible equivalent. That is a design decision, not something to approximate.
- STOP AND ASK if meeting the a11y floor would contradict the signed design pack (CR-04 gave the pack palette and typography). The pack winning on palette does not mean it wins on contrast — say so and escalate.

# METHODS
- Automated scan: an axe-based runner inside the end-to-end tests. Playwright arrives in T-024; until then, say the scan did not run rather than estimating it.
- Keyboard walk: drive the browser. Send Tab, Shift+Tab, Enter, Space, Escape and the arrow keys, and screenshot after each.
- Finding violations across the tree: search for `onClick` on non-button elements, `tabIndex=`, `outline: none`, and directional CSS (`left:`, `right:`, `margin-left`, `padding-right`).
