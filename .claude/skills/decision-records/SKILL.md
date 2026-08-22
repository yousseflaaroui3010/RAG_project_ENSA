---
name: decision-records
description: Record a choice so it can be traced later without damaging the older record. Use when a decision is costly to reverse, when a client asks for something against advice, when a deadline shapes a choice, when taking a shortcut, and whenever a previous decision changes.
---

# Decision records

This is the answer to tracing every change without harming what came before.

## Two files, one system

The global rules already name `DECISIONS.md`. Keep it, and give it a job.

| Where | What it holds |
| --- | --- |
| `docs/journal/DECISIONS.md` | The index. One row per decision: id, date, one line, status |
| `docs/journal/decisions/ADR-0001.md` and so on | One file per decision, for anything costly to reverse |

Small choices get a row and nothing else. Big ones get a row plus a file. Never two records of the same decision in two places.

## The format

```
ADR-0014: Store order totals as whole cents

Status:       Accepted
Date:         2026-08-06
Context:      Decimal rounding differed between the app and the
              accounting export, causing one cent mismatches on
              3 percent of orders.
Decision:     All money is stored and passed around as whole
              numbers of cents. Formatting happens at display time only.
Consequences: Fixes the mismatch. Every existing amount needs
              converting. Anyone reading the database sees 4200,
              not 42.00.
```

Five parts: title, status, the situation that forced the choice, the choice, and what it costs. One page. Long documents never stay current. Short ones at least have a chance.

## The three rules that make it work

1. **Numbered in order, and numbers are never reused.** ADR-0014 means one thing forever.
2. **Once accepted, you do not edit it.** Fix a typo, yes. Change the substance, no.
3. **When the decision changes, write a new one.** The new record says what it replaces. The old record's status becomes `Superseded by ADR-0023` and **its content stays exactly as written**.

Rule 3 is the whole answer. You never lose what was believed in March. You gain what is believed in September, and the link between them.

The consequence worth understanding: **the truth about the system is the whole chain, not the newest record.** Reading the latest one tells you where you are. Reading the chain tells you why, which is what stops the next person repeating a mistake already paid for.

## When to write one

**Write one if:** undoing it would cost weeks, it affects more than one part or person, it involves a real trade off, or someone will later ask "why on earth is it like this".

**Do not write one for:** which date library to use, anything trivially reversible, or a choice with no real alternative. A pile of records about nothing teaches people to ignore the pile.

**Three cases that earn one every time on client work:** anything the client asked for against your advice, anything shaped by a deadline rather than judgement, and every shortcut. Those three get forgotten and then blamed on whoever inherits the project.

## Status values

| Status | Meaning |
| --- | --- |
| Proposed | Written, not agreed |
| Accepted | In force |
| Superseded by ADR-xxxx | No longer in force. Content unchanged |
| Rejected | Considered and not taken. Keep it, because it stops the idea coming back every quarter |

## The senior signal

Having written a record is ordinary. Having **superseded** one is the signal, because it means someone went back to their own reasoning and dated it instead of quietly overwriting it.
