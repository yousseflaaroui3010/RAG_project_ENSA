# Accessibility audit

WCAG 2.2 AA is the floor. `screen-states` covers building the states; this file
covers checking them.

Three passes, in this order. The automated one is cheapest and catches the
least. The keyboard walk catches the most for the least effort. The screen
reader catches what neither can see.

## 1. Automated scan

Tool: axe DevTools in the browser, or `@axe-core/playwright` wired into the E2E
suite so it runs on every screen without anyone remembering.

Zero CRITICAL or SERIOUS violations before sign-off.

Know what this pass is worth. Automated tools catch roughly a third of real
issues. A clean axe run means the obvious things are handled, not that the page
is usable.

The six failures that account for most of what gets found anywhere: low
contrast text, missing image descriptions, missing form labels, empty links,
empty buttons, missing page language. None are hard. They are just unchecked.

## 2. Keyboard walk, by hand

Unplug the mouse. Walk every critical path with Tab, Shift+Tab, Enter, Space,
Escape and the arrow keys.

- Tab order follows the visual order. No jumps to the footer and back.
- Every interactive element is reachable. If you can click it, you can Tab to it.
- Buttons fire on Enter and Space.
- Focus is visible at all times. If you cannot see where you are, neither can
  the person who needs this.
- Modals trap focus inside, close on Escape, and return focus to whatever
  opened them.
- File uploads work without a mouse.
- No keyboard trap. You can always Tab out of anything you Tabbed into.

This pass takes ten minutes and finds more than the scanner did.

## 3. Screen reader

Tool: NVDA on Windows (free) with Chrome, or VoiceOver on Mac with Safari.

- The page title announces on navigation.
- Headings form a logical outline: one H1, then H2s, no skipped levels.
- Images that carry meaning have alt text that says what they mean. Decorative
  images have empty alt, so they are skipped instead of read out.
- Custom controls announce their role. An upload zone says it is an upload zone.
- Loading states announce through `aria-live="polite"`.
- Errors announce immediately through `aria-live="assertive"`.
- A result that appears after an action gets announced. Content that arrives
  silently does not exist to a screen reader user.

## RTL

If the product ships in Arabic, Hebrew, Farsi or Urdu, every screen gets checked
in RTL, not just translated. Layout mirrors, icons with direction mirror, and
numbers and code blocks do not.

## What to write down

Findings go in the bug log with a severity, same as any other bug. An
accessibility failure that blocks a task is a P0, not a nice-to-have with a
different label.