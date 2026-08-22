---
name: work-journal
description: Keep the running record of what is done, doing, left, blocked and why, in docs/journal. Use at the end of every session, when something gets blocked, when new work appears, when asked how far along something is, and before any handover.
---

# The work journal

Two files, both under `docs/journal/`. They already exist in the global rules, so use these and do not invent a third.

| File | Holds |
| --- | --- |
| `docs/journal/BUILD-STATE.md` | The current state. Overwritten as things move |
| `docs/journal/CHANGELOG-AI.md` | One line per change, appended, never edited |

The changelog line format is fixed: `YYYY-MM-DD | T-xxx | file(s) | what changed | why`.

## Why "how much is left" cannot be trusted

This is a measurement problem, not a discipline problem.

- Reviews of software estimation put the average effort overrun at roughly **30 to 44 percent**. Most find 60 to 80 percent of projects overrun.
- Confidence is wrong too. When a professional gives a minimum and maximum they are 90 percent sure about, reality lands inside it only **60 to 70 percent** of the time.
- Naming more risks was found to **increase** over confidence, not reduce it.
- People in technical roles perceive they are judged as more skilled when they give **low** estimates. The incentive points the wrong way, quietly, all the time.

So stop recording opinions about progress. Record countable things and name what is unknown. A journal made of judgements inherits every bias above. A journal made of facts does not.

Treat those percentages as an order of magnitude, not as fact. Consultancy figures on this are inflated and the researchers say so.

## The five headings in BUILD-STATE.md

| Heading | What goes in | What must never go in |
| --- | --- | --- |
| Done | Finished and checked, with the check named | Anything unverified |
| Doing | What is in hand right now, ideally one item | A list of six |
| Left | The remaining items, as items | "About 20 percent left" |
| Blocked | What is stuck, and on whom or what | "Waiting on the client" with no name or date |
| Why | The reason, and what would unblock it | Blame |

The rule doing the most work: **Left is a list of things, never a percentage.** A percentage is a feeling wearing a number's clothes. Four remaining items is a fact. And when new work appears the list gets longer, which is the honest signal a percentage hides.

## What an entry looks like

```
2026-08-06

Done:     Payment webhook now handles duplicate delivery.
          Checked: sent the same event twice, one charge recorded.
Doing:    Refund path. Rough shape working, error states not built.
Left:     Refund error states. Refund audit record. Refund tests.
          Client email copy (waiting on text).
Blocked:  Refund audit record. Needs the "who approved it" field,
          which nobody has decided on.
Why:      Asked Sara Tuesday, no answer. Chased today.
          If no answer by Friday I store the user id and write a
          decision record saying why.
```

Somebody else can read that and know the exact state, what is being decided, who owes an answer, and what happens if the answer never comes. Nobody has to ask.

"Made good progress on refunds, about 80 percent done" contains no information at all.

## Three more sections, folded in from the old STATUS.md

`BUILD-STATE.md` is now the only state file. It carries three sections beyond the five headings, and it must still fit on one screen. A state file nobody finishes reading is a state file nobody reads.

**Where this is.** Three or four sentences at the top. What works, proven by having been run. What does not exist yet. No adjectives. If a check has never run, write "never run", and never round it up to "should work".

**Next, stop at three.** The next thing worth doing and why it is next rather than the others. Three items maximum. A longer list is a backlog, and a backlog lives somewhere else. This is not the same as Left, which holds everything.

**Waiting on a human.** A table, three columns: what, who, why it needs a person. Reasons are things an agent structurally cannot do: it spends money, it is irreversible, or it is a judgement about risk rather than an engineering call. If the table is empty write "nothing", because an empty table reads as an oversight.

This section is not the same as Blocked. Blocked is waiting on an answer. Waiting on a human is work that will never be an agent job.

**Updated line at the top.** The date, and by whom or what. Without it nobody knows whether they are reading something stale.

## Seven rules that keep it honest

1. **Written as it happens.** A journal written Friday about Monday is fiction, because memory smooths things.
2. **Done needs its check named.** If you cannot say how you verified it, it belongs in Doing.
3. **One thing in Doing.** Two at most. Six things in progress means six things half open, each costing the price of remembering it.
4. **Every blocker has a name and a date.** "Waiting on the client" is a shrug. "Waiting on Sara for the approval field, asked Tuesday, chased Thursday" is a fact someone can act on.
5. **Every blocker has a fallback.** What happens if the answer never comes. This one line separates a journal from a complaint.
6. **New work goes into Left, visibly.** A list that only ever shrinks is being managed for appearances.
7. **No hours.** This is not a timesheet. The moment it becomes one, people write it for the reader instead of for the record.

## The blocked entry is the valuable one

A blocker written down the day it appears, with a name and a date, does three things nothing else does. It puts the cost of the delay where the delay happened. It surfaces the pattern, because five blockers pointing at one missing decision is one problem, not five. And it gives you the fallback, so work keeps moving.

The failure to watch for: a blocker recorded and then nothing. A blocker older than three days with no chase and no fallback is not blocked work, it is abandoned work with an excuse attached.

## The weekly four lines

Once a week the journal becomes something a client can read.

```
Shipped this week:   Duplicate payments fixed, verified.
In progress:         Refunds.
Next:                Refund tests, then the email copy.
Needs you:           The "who approved it" decision. Asked 4 Aug.
                     Without it by Friday we store the user id
                     and note the choice.
```

No percentages, no adjectives, nothing to interpret. The "needs you" line is what protects the timeline, and it should never be missing when something is genuinely waiting.

## What a journal is not

Not a diary of feelings. Not a timesheet. Not a replacement for a decision record, because the journal records this week and a decision record captures a choice that still matters in two years. Different lifespans, different files.

## The test of the whole practice

**A journal that works makes bad news arrive early.** One that looks fine right up to the deadline is not being kept, it is being written for an audience.

And a warning before rolling this out: if a journal is used to catch someone out, it becomes a document written for whoever holds the whip, and then it is worse than nothing. Writing "blocked, and it is my own misunderstanding" has to cost nothing.
