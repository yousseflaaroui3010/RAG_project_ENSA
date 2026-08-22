---
name: release-safely
description: How to put something in front of real users without needing luck. Use before any deploy, publish or release, when planning a data change on a live system, and in the hour after anything ships.
---

# Releasing

Shipping is not the finish line. **Shipping and nothing going wrong for an hour is the finish line.**

## The five things before you ship

1. **A switch.** The new thing can be turned off without a release. If it cannot, you have no brakes.
2. **A tested way back.** Not a plan you believe in. One you have run at least once. An undo button you have never pressed is not an undo button.
3. **A few users first.** The first mistake reaches ten people, not ten thousand.
4. **One change per release.** When something breaks you know what did it.
5. **A named watcher for a set period.** Somebody is actually looking at the error rate afterwards, not just hoping.

Release in the morning, midweek. Not because Friday is cursed, but because the people who understand it need to be awake.

## Data changes go in steps

Never one change that reshapes everything. Five steps, and each one can be stopped.

1. Add the new shape. Nothing reads it yet.
2. Write to both old and new at the same time.
3. Move the existing data across in small batches.
4. Switch the reads to the new shape.
5. Remove the old shape, later, once nothing has complained.

Carving a new engine part while the plane is flying is how you lock up a system. Adding a second part and switching over is how you land.

## Secrets

Keys live outside the code, always. Never in a committed file, never in a log line, never pasted into a chat. If a key has ever been in a commit, it is burned and needs replacing, not deleting.

## The hour after

This is the cheapest gate there is and the one most often skipped. Watch four things.

| Watch | Bad sign |
| --- | --- |
| Error rate | Any rise at all, even a small one |
| Response time at the 95th out of 100 | Slower than before, even if nothing errors |
| The specific thing you changed | It works, and nothing near it broke |
| Cost | A jump means something is looping |

If any of them move the wrong way, use the switch. Turning it off costs you nothing. Debugging in front of users costs you the client's confidence.

## When something is wrong right now

In this order.

1. **Stop the bleeding.** Switch it off, or put back the last working version. Do this before understanding anything.
2. **Then find the cause.** See `debug-loop`.
3. **Then write it down.** See `incident-review`.

Ask what changed recently before anything else. Most breakages are the thing you just did.

And remember the cascade rule: a system that fell over does not recover when the load returns to normal. Turn almost everything off, let it settle, then ease back.

## Junior against senior

| Moment | Junior | Senior |
| --- | --- | --- |
| Release day | Ships it all | Ships behind a switch, to a few, and watches |
| Rollback | Has a plan | Has run the plan once |
| After shipping | Moves to the next task | Watches for a set period, with the switch in reach |
| A live problem | Changes things until it improves | Stops the bleeding first, then investigates |
| Data change | One migration | Five ordered steps, each stoppable |
| A key in a commit | Deletes the line | Replaces the key, because the old one is public now |
