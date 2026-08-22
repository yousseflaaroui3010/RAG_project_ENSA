---
name: logging-and-tracing
description: Write logs a stranger can use six months later, and find where time went. Use when adding any log line, when a bug is hard to trace, when a request is mysteriously slow, and before shipping anything that can fail.
---

# Logs and traces

A log line exists for a stranger reading it in the future, under time pressure. That stranger is usually you.

So each line answers: when, who, what was being attempted, what happened, and enough facts to act without opening the code.

```
Bad:   "Error saving"
Bad:   "Payment failed for user"
Good:  level=error event=payment_declined user=8821 order=A-4471
       amount=4200 currency=MAD provider_code=insufficient_funds
       attempt=2 request_id=7f3a9c
```

The good one can be searched, counted, grouped and graphed. The bad ones can only be read one at a time, which means they will never be read.

## Six rules

1. **Fields, not sentences.** Name and value pairs, so a machine can group them. Prose logs cannot be counted, and a log you cannot count cannot become a number you watch.
2. **One identifier follows the whole request.** Make an id at the front door, pass it into every call, print it on every line. Without it you have fragments from a hundred users at once. With it you have one story you can pull out by name.
3. **Log the decision, not only the event.** "Chose the cached price because the live lookup timed out" is worth fifty lines of "entering function".
4. **Use levels honestly.** Error means a person should look. Warning means it survived but something is off. Info means a business event worth counting. Debug means noise you switch on while hunting. When everything is an error, nothing is.
5. **Never log a secret or personal detail.** No passwords, no tokens, no card numbers, no full personal records. Logs get pasted into chat, into tickets, into other people's tools. Treat every line as public.
6. **Log at the boundaries.** Coming in, going out, and every call to something you do not control. The middle of your own code rarely needs it, because that is what a trace is for.

## Traces

A log line says this happened. A trace says **where the time went**.

A trace follows one request across every part it touches and records how long each part took, nested. Twelve seconds of waiting stops being a mystery and becomes a picture: 200 milliseconds of your code, and eleven seconds of one outside call being retried three times.

You cannot get that from logs without doing arithmetic across timestamps by hand, which nobody does at midnight.

Two practical notes. On busy systems keep a sample rather than everything, but always keep the failures and the slow ones, because those are the only ones anyone looks at. And use the open standard format rather than one supplier's own, so changing supplier later does not mean rebuilding the instrumentation.

## What to log for every failure

- What was being attempted, in one field.
- Which identifiers were involved: user, order, request.
- The cause as the system reported it, not your guess.
- Which attempt this was, if retries are in play.

## Junior against senior

| Moment | Junior | Senior |
| --- | --- | --- |
| Adding a log | Adds one while debugging, removes it after | Adds the ones a future stranger needs, keeps them |
| Content | A sentence | Fields with values, countable |
| Following a request | Guesses from timestamps | Pulls the whole story with one id |
| Levels | Everything is an error, or everything is info | Error means act, and it is rare |
| Personal data | Logs the whole object | Logs the id, never the contents |
| Slow request | Adds timers by hand | Reads the trace |
| Volume | Logs everything, everywhere | Logs at the boundaries and at the decisions |

## The check

Pick any recent error. Can you produce the full story of that one request from the logs, using one identifier? If not, rule 2 is not in place, and nothing else here matters yet.
