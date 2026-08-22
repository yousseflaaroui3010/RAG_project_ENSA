---
name: incident-review
description: What to write after something broke for real users. Use after any outage, data loss, out of hours call out, or near miss, and whenever someone asks for the root cause.
---

# After it breaks

Fixing the problem is one job. Working out why the system allowed it is a different job with different rules. This file is the second one.

## "The root cause" is usually a lie

The most quoted paper on this is Richard Cook's *How Complex Systems Fail* (1998), eighteen short points, free to read. Four of them change how a review should be written.

**Big failures need several small failures.** One thing going wrong is almost never enough. The system has defences and they mostly work. A real outage happens when several harmless looking faults line up. Each small failure is necessary, only the combination is sufficient. So looking for the one cause means looking for something that is not there.

**Your system is already running broken.** Any complex system contains flaws right now. It keeps working because it has slack and because people patch around it. Reviews that find "the flaw" usually found one of many that were already there.

**Naming a root cause is a social habit, not a technical finding.** Cook says this directly, and says the reason people do it anyway is a cultural need to blame something specific.

**Knowing the ending makes everyone look careless.** Once you know the outcome, the warning signs look obvious. They were not obvious at the time. Cook calls hindsight the main obstacle to investigating properly, which is why "they should have seen it" is a worthless sentence.

One more that agencies feel often: **every change creates new ways to fail.** Fixing a frequent small problem with new machinery often opens a rare large one.

## So write conditions, not a cause

A list of **contributing conditions**, and for each one, what would have blocked it.

The switch that does the most work is asking **how** instead of **why**. "Why did you deploy on Friday" invites someone to defend themselves. "How was it possible to deploy without the check running" points at the system. That reframing comes from John Allspaw's essay *The Infinite Hows* (2014). Widely adopted, not measured, so treat it as strong practice rather than proven fact.

## The five whys, and where it fails

Ask why five times, each answer feeding the next. It came from Toyota's factories.

**Good for:** a simple contained problem with one chain. A form that saves the wrong value. A job that runs twice.

**Bad for:** a live system incident. Three known problems, all written about at length. It is a single line, so each why picks one parent and throws the others away, flattening several causes into one story. It is not repeatable, so three people produce three different root causes. And it promises a single root, which is not there to find.

A middle path that works: use it to explore one chain, repeat it separately for each contributing condition, and never let the last answer be a person.

## Blameless, and what it actually means

Blameless does not mean nobody is responsible. It means the review does not name a person as the cause, because doing so destroys the thing you need most. Someone expecting punishment stops volunteering the details the review depends on, and those details are the whole value.

The line to hold: accountability applies to conduct, not to mistakes. Hiding an incident is conduct. Typing the wrong command is a mistake, and a system that a wrong command can take down is the finding.

## When to run one

Any of these: users were affected, data was lost, someone had to step in out of hours, or it took longer than an agreed limit to put right.

Also run one for a near miss. It is a free lesson with no damage attached.

## The template

Six headings. Nothing else.

1. **What users experienced**, and for how long.
2. **Timeline**, in plain times, from first signal to fully fixed.
3. **What we thought was happening at each point.** Not what was true. What the people on it believed, and why that was reasonable.
4. **Contributing conditions.** A list, not a chain.
5. **What would have blocked each one.** Detection, a check, a limit, a smaller change.
6. **Actions**, each with one owner and one date. Fewer is better. Five actions that happen beat twenty that do not.

Notice what is missing. No root cause heading. No "who". No lessons learned paragraph nobody reads.

## Junior against senior

| Moment | Junior | Senior |
| --- | --- | --- |
| Framing | Looks for the mistake | Looks for the conditions that made it possible |
| The timeline | What actually happened | What people believed at the time, alongside what was true |
| The finding | One cause | Several conditions, each with a block |
| Human error | Names it as the cause | Treats it as the thing to be explained |
| Hindsight | "Obviously it would break" | Resists it, because it was not obvious before the outcome |
| Actions | A long list of good intentions | Two or three with owners, dates, and a check that they landed |
| A near miss | Ignores it, nothing broke | Reviews it |

## The uncomfortable closing point

Running without failures requires experience with failure. A team that has never dealt with an outage does not know where the edges of their system are. That is not a reason to break things on purpose in client work. It is a reason to treat every incident as the most valuable training available, and to write it down properly.
