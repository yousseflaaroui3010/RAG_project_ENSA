---
name: blast-radius
description: Work out how far a change reaches before writing it, and shrink that reach on purpose. Use before editing shared code, before touching stored data, before anything that deletes, sends, charges or publishes, and before any release.
---

# Blast radius

Blast radius is how much breaks when this breaks.

A change with a small radius touches one screen, for one client, and can be switched off in a minute. A change with a large radius touches every user's stored data and cannot be undone. Same amount of code, completely different risk. Telling them apart before starting is most of the skill.

A ship floats not because the hull never gets holed, but because the inside is split into sealed rooms. One flooded room is a bad day. A hull with no walls is a sinking.

## The four questions

Answer these in writing, in the ticket, before opening the editor.

1. **Who is touched?** One user, one client, everyone.
2. **What is the worst thing that happens?** Wrong screen, wrong number, lost data, money moved twice.
3. **How would I find out?** A client email is a failed answer. A number on a screen is an answer.
4. **How do I undo it?** A revert, a switch, a restore. If the answer is "we would rebuild the data by hand", the change needs redesigning before it needs coding.

Junior answers question 2. Senior answers all four, and 4 first.

## Before changing shared code

Find every place that uses it, by name, before touching it. Not by reading folders. Ask the code graph or grep the whole project.

Then decide which of three you are doing:

| Doing | What it means |
| --- | --- |
| Adding something new | Safe. Nothing existing changes shape |
| Changing what goes in or comes out | Every caller must be updated in the same change, or it breaks |
| Removing something | Stop using it, wait, remove it later once nothing complains |

Adjusting a shared value without finding its callers is like cutting a random wire in a car without checking whether it powers the brakes. You might fix the radio.

## Moves that shrink the radius

| Move | What it buys |
| --- | --- |
| Ship behind a switch | Turn it off in seconds with no release |
| Release to a few users first | The first mistake reaches ten people, not ten thousand |
| Add before you remove | Old code keeps working while the new shape fills in |
| Never delete the same day | Stop writing to it, wait, then remove once nothing complains |
| Separate the reads from the writes | A read that is wrong is wrong today. A write that is wrong is wrong forever |
| One change per release | When something breaks you know what did it |
| Keep the dangerous action behind a person | Bulk changes and deletes get a human confirming, not a schedule |
| Split the work into compartments | A slow report cannot eat the resources checkout needs |
| Release in the morning, midweek | Not because Friday is cursed, but because the people who understand it are awake |

## The five that transfer to any project, day one, near zero cost

1. A time limit on every outside call.
2. Retries in one place, capped, with randomness.
3. A switch to turn each new feature off.
4. Add then remove, for anything touching stored data.
5. One written answer before each change: how do I undo this.

## Junior against senior

| Moment | Junior | Senior |
| --- | --- | --- |
| Before a change | Thinks about whether it works | Thinks about what it touches and how to undo it |
| Deleting anything | Deletes it | Stops using it, waits, deletes once nothing complains |
| Data changes | One change reshapes everything | Add, fill, switch over, remove, as separate steps |
| Release day | Ships it all | Ships behind a switch, to a few, and watches |
| A fix during an outage | Changes things until it improves | Checks what changed recently and considers putting it back first |

## The one that matters most for client work

The undo row. Client trust survives a bug fixed in five minutes. It does not survive a week of "we are still investigating".
