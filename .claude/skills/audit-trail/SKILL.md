---
name: audit-trail
description: Keep the history of a value, not just its current state. Use whenever the work touches money, permissions, approvals, legal records, or anything a client might ask about months later.
---

# Audit trail

For anything involving money, permissions or a record someone may rely on, the current value is not enough. Somebody will ask what it used to be.

## The four rules

1. **Keep the old value.** Who changed it, when, from what, to what. Appended, never overwritten.
2. **Mark as deleted instead of deleting**, for anything a client might ask about later. Then remove it properly on a schedule you agreed with them.
3. **The audit record is append only.** If your own code can edit or remove entries in it, it is not evidence, it is a note.
4. **Write the reason where a reason exists.** "Refunded by admin 12, reason: duplicate charge" answers the question. "Amount changed" starts an investigation.

## What a row holds

| Field | Why |
| --- | --- |
| When | The time it changed, not the time it was noticed |
| Who | A person or a system, named |
| What | The thing that changed, by id |
| From and to | Both values. One of them alone is useless |
| Why | Free text, when a human made the choice |

## Where this bites

| Case | Without a trail |
| --- | --- |
| A client disputes an invoice total | You have today's number and no way to show yesterday's |
| Someone's access changed | Nobody can say who granted it or when |
| A price looks wrong | You cannot tell whether it was always wrong or changed last Tuesday |
| A refund was issued | You know it happened, not who approved it |

## The question that decides it

A junior asks how to store the value. A senior asks **whether anyone will ever need to know what it was before.**

If the answer is yes, the trail goes in at the start. Retro fitting it means the months before it existed are gone for good, and those are usually the months somebody asks about.
