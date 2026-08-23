---
name: report-brief
description: How to write every reply on Sanad - plain brief non-technical English, and the fixed Done/Ongoing/Left block that closes every finished task. Use when finishing any task, when reporting progress, when asked where things stand, and before saying anything is done.
---

# How to report back on Sanad

The reader steers this project and does not read code. Every reply is written
for a smart person who is not an engineer.

## Plain language

- Short sentences. Small words. Cut any sentence that does not change what the
  reader does next.
- No jargon unless the normal-English meaning sits right next to it.
- One small example or a one-line metaphor beats a paragraph of theory.

Translate before you name:

| Say this first | Then, if useful |
|---|---|
| the thing that finds your files | `change_detection.py` |
| we broke it on purpose and watched it fail | mutation testing |
| two lists that must always match | drift check |
| a change waiting for someone to look at it | an open PR |
| the folder that holds the finished text | the parent store |

## The block that closes every finished task

End the reply with exactly these three headings, in this order, never merged
and never renamed:

```
## Done
- <finished AND proven, with the proof attached: the command, the number, the
  file. "336 tests passed" is Done. "should work" is not Done.>

## Ongoing
- <started but not finished, and what it is waiting on. If nothing is in
  flight, write "Nothing in flight.">

## Left
- <not started yet, most important first.>

**Next:** <the single next step, one line.>
```

## Rules for the block, each one learned here

- **Done means watched.** An intention is not an outcome. If you issued the
  instruction but never saw the result, it is not Done. Put it in Ongoing with
  the words "not verified yet" and name what would settle it.
- **A blocked or denied tool call is not a finding.** It goes in Ongoing as
  "could not check X", never in Done and never as "X is absent".
- **One or two lines per bullet.** Detail belongs above the block, not inside it.
- **Plain language applies inside the block too.**
- **Never quietly drop an item.** If something moves out of Left, it moves to
  Ongoing or Done, or the reply says out loud that it was dropped and why.

## Why this exists

A long, dense reply hid an open pull request from the reader in a real session
on this project. The information was technically present and practically
invisible. The three headings exist so the state of the work survives a
five-second glance.