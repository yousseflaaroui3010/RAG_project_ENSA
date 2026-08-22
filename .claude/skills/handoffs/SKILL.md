---
name: handoffs
description: The moments work passes between people or roles, and what each side owes the other. Use when passing work on, when receiving it, when agreeing an API shape, when a design arrives, and when the same handoff keeps going wrong.
---

# Handoffs

Work spends most of its life waiting, not being worked on. Waiting for review, for a decision, for a design, for someone to test it, for a release.

One quoted case: a feature with about 106 hours of actual work in it took 38 weeks to arrive. Roughly 7 percent of its life being worked on.

**A warning about that.** You will see a claim everywhere that 10 to 20 percent is typical. There is no solid study behind that figure, every source repeating it sells flow tooling, and the case above is one project reported by a consultancy. Take the direction as real and the percentages as marketing.

The direction is enough: **speeding up an engineer barely moves delivery. Removing a wait does.** If a change sits ready for review for two days, typing faster helps nobody.

## The universal rule

Every handoff has two written sides.

- **Ready:** what must be true before I accept this work.
- **Done:** what must be true before I pass it on.

They are the same sentence from either end. Write them once per pair, per project, and stop arguing.

The failure is always the same shape: someone passes work along in a state that seems obviously complete to them and obviously incomplete to the receiver, because nobody wrote down which.

## Backend and frontend

The most important one, because both sides are blocked by it.

| Backend owes frontend | Frontend owes backend |
| --- | --- |
| The shape agreed **before** either side builds | The screens and what data each needs, early |
| The shape written down, not described in a chat message | Which fields are actually used, so nothing is built for nobody |
| Errors in one consistent form, with codes the app can act on | Errors shown as the user needs, not the raw message |
| A note when anything changes shape, before it ships | A check on the shape at its edge, so a change fails loudly |
| Something to build against on day one, even if it returns fake data | Not treating the backend as the reason nothing is finished |

Three rules prevent most of the pain. Agree the shape first, in writing, which takes twenty minutes and lets both sides build at once. Add, never remove, because a field appearing is safe and a field vanishing breaks the app. And never let the frontend adapt silently to a backend surprise, because that is how a temporary patch becomes permanent and nobody remembers which side is wrong.

## Whoever writes it should be able to watch it run

An engineer who cannot see the logs of their own feature cannot own it, and will not.

If there is no separate operations person, these do not disappear. They become the same engineer's job, and they belong on the ticket: every setting named with which are secret, data changes as ordered reversible steps, a health check, the rollback in writing, and a rough idea of the resources needed.

## Designers and frontend

| Designer owes frontend | Frontend owes designer |
| --- | --- |
| The empty, loading and error states | A build review before the client sees it |
| Behaviour at small and large widths | The specific reason when something cannot be built as drawn |
| Behaviour of long text, missing images, many items | The real thing with real content, not a screenshot |
| Named colours and spacing, not one off values | A flag when a colour fails the contrast check |
| Which parts are fixed and which can flex | Nothing invented silently to fill a gap |

## The four ways a handoff fails

1. **Over the wall.** Passed on without checking, because it is someone else's problem now. Creates a round trip costing more than the check would have.
2. **The silent assumption.** Each side assumes the other handles validation, or the empty state, or the error message. Nobody does.
3. **The verbal agreement.** Decided in a call, never written. Two weeks later there are two versions and no way to settle it.
4. **The stale artefact.** The design, the shape document or the ticket says one thing and the built product says another. Everyone reads the wrong one for a month.

The fix for all four is the same and it is cheap: **write it down where both sides look, and say when it changed.**

## Scope arriving sideways

Scope that arrives in a chat message is still scope. If it does not pass through the same door as everything else, the timeline stops meaning anything, and whoever builds it gets blamed for the difference.

Name the trade off, in writing, before absorbing anything.

## Junior against senior

| Moment | Junior | Senior |
| --- | --- | --- |
| Receiving work | Starts on it | Checks it meets ready, sends it back if not |
| Passing work on | Passes it when their bit is finished | Passes it when the receiver can start without asking questions |
| The shape between two sides | Discovers it while building | Agrees it in writing before either side builds |
| A gap in the design | Invents something | Asks, and records the answer |
| A blocking dependency | Waits | Builds against a stand in, and records what it is waiting for |
| Agreed in a call | Remembers it | Writes it in the ticket the same day |
| The same handoff keeps failing | Complains about the other side | Proposes a written ready and done for that pair |

## Honesty note

Almost nothing in this file rests on measured research. It is settled craft practice, widely agreed and rarely studied. Treat it as a sensible default, and change anything that does not fit how the work actually flows.
