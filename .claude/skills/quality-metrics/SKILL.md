---
name: quality-metrics
description: The numbers that decide whether work is done. Use when setting a target, writing a gate, judging whether code is good enough, reviewing a pull request, or when someone says fast, clean, stable or scalable without a number attached.
---

# The numbers

A word without a number is an opinion. This file turns the usual words into numbers you can check.

Every threshold here is a starting line, not a law. Move it on purpose, in writing, with a reason. Never move it to make a red check turn green. That is cheating the check, and `01-core-law` already bans it.

## Rule zero

Before you use any number below, answer four things about it:

1. What it measures.
2. How it is scored.
3. What it is measured on.
4. Over what time window.

Vague on any one of those, set the number aside. A number nobody can reproduce is decoration.

## Code you write

| Thing | Number | What happens at the line |
| --- | --- | --- |
| Duplicated lines | Over 3 percent | Build fails. Already in `00-global` |
| Cyclomatic complexity, per function | Warn at 10, stop at 15 | Split the function. McCabe proposed 10 in 1976 and it is still the common default. NDepend calls anything over 15 hard to maintain and over 30 a must split [1][2] |
| Files touched in one change | Over 5 | Stop and ask. Already in `01-core-law` |
| Nesting depth | Over 3 | Use an early return instead |
| Function length | Over 50 lines | Look for a second job hiding inside it |

### Complexity, in plain words

Count the decision points inside one function, then add 1. Every `if`, `else if`, loop, `case`, `&&`, `||` and `catch` counts as one.

The score is also the smallest number of tests needed to walk every path through that function. A score of 15 means 15 tests. Nobody writes 15, so most paths stay untested. It is a road with 15 forks and a map for 3 of them.

## Tests

| Thing | Number | Note |
| --- | --- | --- |
| Line coverage | A floor, never a goal | 100 percent coverage of code nobody tested properly is a green light on a broken car |
| Bug fixes | Every single one gets a test | The test must fail before the fix and pass after. No exception |
| New check | Must fail on purpose once | A check that has never failed has never been proven. Already in `engineering-seniority` |
| Mutation score | Measure it before setting a target | It tells you whether tests catch a change, which coverage cannot. No agreed industry threshold found (unverified, checked 2026-08-06) |
| Flaky tests | Zero tolerated | A test that fails one time in ten teaches everyone to ignore red |

## Speed

Measure the 95th out of 100, never the average. The average hides the people having the worst time, and they are the only ones who complain. It hides it the way an average pond depth of one metre hides the hole in the middle.

Worked example of why. A service with 1,000 workers normally answers in 100 ms. Then 5 percent of requests start hanging, and the timeout is set to 100 seconds. Those 5 percent tie up the worth of 5,000 workers. There are 1,000. The error rate does not go to 5 percent, it goes to about 80 percent, and the average barely moves.

### Screens, the three official numbers

Google publishes three, and these are the ones to hold work against.

| What it measures | Number to beat |
| --- | --- |
| How fast the main content appears | 2.5 seconds or less |
| How fast the page answers a tap | 200 milliseconds or less |
| How much the layout jumps while loading | 0.1 or less |

Three rules that ship with them. Judge at the 75th out of 100 of real visits, split phone and desktop, so the fourth slowest visitor in five still has a good time. Real visits decide, not a test on your laptop, because a lab test has nobody tapping and can only use a stand in. And the set changes slowly, at most once a year with notice, so quoting a retired number means someone learned this once and stopped checking.

### Everything else

| Thing | How to set it |
| --- | --- |
| Any target | Written as a percentile with a window. "95th out of 100 under 400 ms over 7 days", never "fast" |
| Database query | Anything over 100 ms gets an index check |
| A timeout | Close to how long the call actually takes. A limit many times longer than normal is a trap, not a safety net |

## Watching a running system, the four signals

If you can only measure four things about anything users touch, measure these.

| Signal | Plain meaning | The mistake |
| --- | --- | --- |
| Latency | How long a request takes | Mixing failed requests in with successful ones |
| Traffic | How much is coming in | Watching only the total, never the shape |
| Errors | How many fail | Counting instead of using a rate |
| Saturation | How full the thing is | Watching the level, not how fast it is rising |

Keep the timing of failures separate from successes. A request that fails instantly because the database is gone is fast, and mixing it in makes your average response time **improve** while the service falls over.

A slow error is worse than a fast one. If it is going to fail, fail now.

Alert on what users feel, never on what servers feel. A busy machine with everyone served happily is not an emergency. Everyone served slowly on an idle looking machine is.

## Shipping, the DORA numbers

From Google's DevOps Research programme, running since 2018 across tens of thousands of responses [3]. There are now five, not four.

| Number | Plain meaning | Top tier |
| --- | --- | --- |
| Deployment frequency | How often work reaches users | On demand, several times a day [3][4] |
| Lead time for changes | Finished code to users having it | Under a day, under an hour for the fastest [3][5] |
| Change failure rate | Share of releases that break something | Sources disagree, about 5 to 15 percent [3][4][6]. Use your own baseline and watch the direction |
| Failed deployment recovery time | Time to put right a release that broke | Under an hour [4] |
| Deployment rework rate | Share of releases that are unplanned fixes | Added around 2024 |

Two renames worth knowing, because quoting the old shape signals someone learned this once and stopped checking. "Time to restore service" became failed deployment recovery time, and it now covers only failures a release caused. The stability grouping was renamed instability, on the reasoning that a low failure rate is a sign of health, not proof of it, the way a normal temperature does not mean you are well.

Three warnings that came with the research.

Read them together. A team whose deploy count doubles while the failure rate holds is shipping twice as many failures, not improving [7].

Never set a goal on the metric itself. Set the goal on the outcome and use the metric to see whether you are moving.

Never score a person on these. They measure a system [3]. Score people on behaviour, and keep these at team level as a thermometer.

## Numbers that lie

| Number | Why it fails |
| --- | --- |
| Lines of code | Barely predicts how long work takes |
| Test coverage | Only a low to moderate link with catching faults, and its own researchers say do not target it |
| Commits or pull requests closed | Rewards slicing work thinner |
| Hours logged | Measures presence |
| Story points | The team owns both halves of the sum |
| Tickets closed | Rewards closing, which is not finishing |
| Bugs found by QA | Punishes QA for being good at the job |

The test before adopting any number: **could this improve while nothing actually gets better?** Yes means it is a stand in, not evidence.

## How numbers get gamed

Not by dishonest people. By normal people answering what you reward.

- Target coverage, get tests that run code and check nothing.
- Reward deploy frequency, get one change split into six releases.
- Reward closed tickets, get tickets split and closed early.
- Punish failure rate, get incidents quietly relabelled as maintenance.
- Reward speed with no quality guard, get speed and no quality.

## How to write a number down

Seven lines, once per number, somewhere the whole team can see.

```
Name:        Checkout failure rate
Measures:    Share of checkout attempts ending in an error
Rule:        failed / all, excluding user cancelled
Population:  All customers, all devices
Window:      Rolling 24 hours
Good:        Under 0.5 percent
Act at:      Above 1 percent for 15 minutes, notify a named person
Owner:       Name
```

The last three lines are the ones people leave off, and they are the ones that turn a fact into a metric. A number with no threshold is trivia. A threshold with no owner is a wish.

## How often to look

| Rhythm | What you look at |
| --- | --- |
| Live, automatic | Errors and saturation, with a person notified on a threshold |
| Daily, one minute | The four signals for the main service |
| Weekly | The speed numbers, and anything drifting the wrong way |
| Monthly | The shipping numbers, team level, a discussion not a score |
| Per release | Before and after, for a set period, with a named watcher |

That last row is the cheapest and the most skipped. Shipping is not the gate. Shipping and nothing going wrong for an hour is the gate.

## Uptime

| Promise | Downtime allowed per 30 days |
| --- | --- |
| 99 percent | About 7 hours 12 minutes |
| 99.9 percent | About 43 minutes |
| 99.99 percent | About 4 minutes 20 seconds |

Pick one on purpose. The gap between three nines and four nines is the gap between a hobby and a night shift.

## Cost

| Thing | Number |
| --- | --- |
| Model or API spend per session | A hard cap, set before the first run |
| Any check the gate runs | Over 2 minutes, and people start skipping it. Over 10 minutes, they will disable it |
| Monthly infrastructure | A written number in the blueprint, checked against the real bill each month |

## When a number and reality disagree

Every number here stands in for one question: does the thing work, for the people using it, and can it still be changed safely. When a number and that question disagree, the question wins.

## Sources

1. Cyclomatic complexity guidance, Sourcegraph, accessed 2026-08-06.
2. Threshold guidance, JetBrains resharper-cyclomatic-complexity repo, accessed 2026-08-06.
3. DORA metrics explained, Taskade, June 2026, accessed 2026-08-06.
4. DORA metrics complete guide, Larridin, June 2026, accessed 2026-08-06.
5. DORA benchmarks, Koalr, March 2026, accessed 2026-08-06.
6. DORA benchmarks, CI/CD Watch, 2026, accessed 2026-08-06.
7. DORA metrics guide, Gitmore, 2026, accessed 2026-08-06.
