---
name: the-ilities
description: The nine qualities a system is judged on and how to check each one. Use when planning a feature, reviewing a design, writing acceptance criteria, arguing about whether something is good enough, or when someone says scalable, maintainable or reliable without saying how they would prove it.
---

# The nine qualities

The international standard for software quality (ISO/IEC 25010, revised November 2023) names nine [1][2][3]. Nine is a short enough list to walk every time.

Rule: pick the three that matter for this feature, write a number for each, and say out loud which of the other six you are choosing to ignore. A quality nobody named is a quality nobody built.

Three changes came in the 2023 revision. Quoting the old eight item version signals someone learned this once and stopped checking.

- **Safety** was added as a quality of its own: spotting risk, failing safely, warning of hazards, integrating safely.
- **Usability** became interaction capability, and picked up inclusivity. Accessibility is not a bonus in the current model.
- **Portability** became flexibility, and scalability sits inside it.

Honesty note: the standard itself is paywalled. This is built from the official summary of what changed plus several agreeing write ups, not the full document. Buy the standard before putting it in a client contract.

## Your words, mapped

| What you call it | Standard name |
| --- | --- |
| Valuability | Functional suitability |
| Optimizability | Performance efficiency |
| Reliability | Reliability |
| Maintainability | Maintainability |
| Modulability, customisable | Flexibility, and modularity under maintainability |
| Scalability | Sits under flexibility |
| Usability | Interaction capability, renamed in 2023 |

## Every one costs something

You cannot have all nine at full strength. Pushing one up pushes others down.

| Quality | What more of it costs you |
| --- | --- |
| Functional suitability | More features means more to maintain, test and explain, forever |
| Performance efficiency | Caching, batching and cleverness, all paid for in readability and new ways to be wrong |
| Compatibility | Every format you support becomes a promise you cannot break |
| Interaction capability | Design time, extra states, more testing, slower delivery of the next thing |
| Reliability | Spare parts, retries, health checks, more moving pieces to maintain |
| Security | Friction for real users, more steps, more support requests |
| Maintainability | Time spent now, on structure and tests, that shows nothing today |
| Flexibility | Layers of indirection so nothing is tied down, which makes everything harder to read |
| Safety | Checks, limits and refusals, so the system says no to things people want |

The pairs that fight most often: performance against maintainability, security against ease of use, flexibility against simplicity, reliability against cost. And functional suitability against all eight others, because every extra feature taxes the lot.

## Pick three, in writing, at the start

Before architecture, agree three qualities that lead. Written down. The same list looks wildly different by project.

| Project | The three that lead | Accepted as weak |
| --- | --- | --- |
| Internal admin tool, 12 staff | Maintainability, functional suitability, security | Speed, polish, scale |
| Public marketing site | Interaction capability, performance, flexibility | Deep features, fine grained access control |
| Payments feature | Security, reliability, safety | Speed of delivery, richness |
| Two week pitch prototype | Functional suitability, interaction capability | Maintainability, security, reliability |

That last row is the honest one and the one that most needs writing down. A throwaway prototype **should** be badly built. The failure is not building it fast. The failure is not recording that it was a prototype, and then letting it become the product.

## A quality with no number is a wish

| Wish | Requirement |
| --- | --- |
| It should be fast | Main content in under 2.5 seconds for 75 out of 100 real phone visits |
| It should be reliable | Under 0.5 percent of checkout attempts fail in any rolling day |
| It should be secure | No personal data in logs. Admin needs a second factor. Checked quarterly |
| It should be maintainable | A new developer ships a small change on day two, using only the written setup notes |
| It should scale | Handles four times current traffic with no design change. Tested to that point |
| It should be accessible | Zero failures in the six common categories, every screen usable by keyboard alone |

Look at the last two. Maintainability sounds unmeasurable until you turn it into an event you can watch: a new person, a real change, day two. Scale sounds vague until you attach a multiple and a test.

Rule: no number, no threshold, no watchable event, then it is not a requirement and nobody will be held to it.

## The nine, with the check for each

### 1. Functional suitability
Does it do the right job, correctly, completely.
Check: every acceptance line written as given, when, then. Run them. A feature with no acceptance line is not finished, it is abandoned.

### 2. Performance efficiency
Time, memory, storage, network, money.
Check: a p95 number and a cost number, both written before building. See `quality-metrics`.

### 3. Compatibility
Plays nicely with other systems, and with itself running twice.
Check: two versions of your own service running side by side during a deploy. If that breaks, your deploys need downtime.

### 4. Interaction capability
Can a real person use it. Includes accessibility.
Check: every screen has its empty, loading and error state built. Keyboard only, once, all the way through. See `accessibility-verification`.

### 5. Reliability
Works, keeps working, and recovers.
Check: kill a dependency on purpose (database, network, third party) and watch what the user sees. If they see a spinner forever, that is your finding.

### 6. Security
Keeps data in, keeps attackers out, proves who did what.
Check: run `threat-modeling` on anything touching money, login, files or the open internet. Secrets never in a committed file, already in `01-core-law`.

### 7. Maintainability
Can the next person change it without fear. Covers modularity, reuse, readability, testability.
Check: complexity and duplication numbers from `quality-metrics`. Plus the blast radius question: before changing a shared thing, name who else uses it.

### 8. Flexibility
Can it grow, move, install elsewhere, get swapped out. Scaling lives here.
Check: name the number it breaks at. Ten users or ten thousand. Then say which one you built for. Building for a million users you do not have is the most expensive kind of guessing.

### 9. Safety
Does it avoid harming people, money or data when things go wrong.
Check: for anything irreversible (payment, delete, send, publish), name the undo. No undo means a confirmation step and a written record.

## Where each one gets checked

| Quality | When | By what |
| --- | --- | --- |
| Functional suitability | Every merge | Tests, plus a person using it |
| Performance efficiency | Weekly and per release | Real visit numbers, see `quality-metrics` |
| Compatibility | Per release | Contract tests, agreed device list |
| Interaction capability | Per screen, before review | Keyboard walk, the six common failures |
| Reliability | Continuously | Error rate and recovery time |
| Security | Per release plus a scheduled review | Dependency check, access review, log check |
| Maintainability | Per change | Complexity and duplication numbers, blast radius |
| Flexibility | Once, deliberately | A load test to the agreed multiple |
| Safety | Per dangerous action | The blast radius questions |

The pattern: the qualities checked continuously stay healthy. The ones checked when someone gets round to it are the ones that show up as a client complaint. Maintainability and security are usually in that second group.

## How to use this in a plan

Write one line per quality for the feature. Three get a number. Six get the word "not this time" and a reason.

Then ask the only question that matters here: **which of these cannot be retrofitted?**

Three usually cannot: the audit trail, the module boundaries, and the shape of the data. Those stay on even in a rushed phase. Everything else can be added later, and pretending otherwise is how a small feature turns into a quarter.

## The sharpest question

**What is this project deliberately bad at?**

Every real system is weak somewhere. An answer means the choice was made on purpose. "Nothing" means the choice got made for you by whatever was easiest that week.

## Sources

1. ISO/IEC 25010:2023, product quality model, iso.org, published November 2023, accessed 2026-08-06.
2. ISO/IEC 25010 explained, Sonar, July 2026, accessed 2026-08-06.
3. ISO 25010 guide, TMS Outsource, March 2026, accessed 2026-08-06.
