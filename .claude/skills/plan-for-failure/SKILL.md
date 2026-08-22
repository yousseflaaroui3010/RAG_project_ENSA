---
name: plan-for-failure
description: Assume it will break, then decide what breaking looks like. Use when calling any outside service, adding retries or a cache, setting a timeout, sizing capacity, or when something is falling over right now.
---

# Plan for failure

The question is never "will this fail". It is "when this fails, what does the failure look like, and who notices first".

Any complex system contains flaws right now. It keeps working because it has slack and because people patch around it. A big failure is not one thing going wrong, it is several small things lining up.

## Failures do not undo themselves

A service is fine at 10,000 requests a second and starts crashing at 11,000. Traffic falls back to 9,000. Does it recover?

No. It stays down. Most of its capacity is dead, and the servers that come back get hit immediately and die again. In the worked example, traffic has to fall to roughly 1,000 before the system can stand up.

So when things are falling over, "put the traffic back to normal" is not a recovery plan. Turning almost everything off, letting it settle, then easing back is.

## The retry trap

Retries look like kindness and behave like an attack.

Three layers, each retrying four times. One user action becomes 4 x 4 x 4, which is sixty four hits on the database, arriving exactly when the database can least take them.

Five rules, all cheap:

1. **Retry at one layer only.** Usually the one closest to what is failing. Not at every layer, because the attempts multiply.
2. **Always add randomness to the wait.** Double the wait each time, then shift it by a random amount. Without the randomness, one network hiccup makes every client retry at the same instant, in waves.
3. **Cap the attempts.** Three to five, then give up and pass the error on.
4. **Give the whole service a retry allowance.** Sixty retries a minute per process, for example. Over that, stop retrying and fail. This is the difference between a bad hour and a full outage.
5. **Split errors into retryable and not.** A malformed request will never succeed, so retrying it is pure waste. And when your own service is overloaded, say so in the response, so callers back off instead of pushing.

## Timeouts, and the number that should scare you

Set a time limit on every call out, and keep the limit close to how long the call actually takes.

A service has 1,000 workers and normally answers in 100 milliseconds. Then 5 percent of requests start hanging forever, and the timeout is 100 seconds. Those 5 percent tie up the worth of 5,000 workers. There are 1,000.

The error rate does not go to 5 percent. It goes to about 80 percent.

Three things follow. A timeout many times longer than the normal response is a trap, not a safety net. When something is clearly down, fail immediately instead of waiting out the clock. And look at the spread of response times, never the average, because the average hides exactly this.

Also pass the remaining time down the chain. If the top gave the request thirty seconds and seven are gone, the next call gets twenty three, not a fresh thirty. Work finished after the caller gave up is work nobody gets credit for.

## Your cache might be a hidden dependency

One question about every cache: **could the system serve normal traffic with the cache completely empty?**

Yes means it is making things faster. No means it is not a cache, it is a required part nobody wrote down, and the day it empties is the day you find out.

Decide in advance when cached data goes stale. A cache is a second copy of the truth, and two copies of the truth disagree eventually.

## Degrade instead of dying

Better to give everyone something slightly worse than to give a few people everything and the rest an error.

Under pressure, the example service stops sending the pictures and the maps, and keeps sending the text. Nobody is delighted. Everybody is served.

And the warning that applies to every backup path ever written: **the code path you never use is the code path that does not work.** If the degraded mode only runs during disasters, it has never been tested, and it will fail during the disaster. Run it on purpose, occasionally, on a small slice.

## Find the shape of failure on purpose

You cannot plan for a failure whose shape you have never seen.

- Push load up until it actually falls over. Note the number. That is your real capacity, and it is usually not the one anyone guessed.
- Test a slow climb and a sudden spike separately. They fail differently, because of caches.
- Check whether it recovers on its own or needs a person.
- Test the non essential parts being **slow**, not only being **down**. A service that never answers is far more dangerous than one that errors quickly, because your side sits holding resources.

## An honest note about scale

All of the above comes from services far larger than one client project. Copy the thinking, not the machinery.

Do not build load shedding, traffic dropping or autoscaling policies into a small project. They add moving parts you will not maintain. And the same source warns that changes made to improve the normal case, retries and caches and killing unhealthy servers, can each raise the chance of a big outage. Be careful you are not trading one failure for a worse one.

## Junior against senior

| Moment | Junior | Senior |
| --- | --- | --- |
| Calling another service | Calls it and waits | Sets a limit, and decides what happens when the limit hits |
| Something failed | Retries it | Retries with growing randomised gaps, capped, at one level only |
| Under load | Hopes | Knows the number it falls over at, because they measured it |
| A backup path exists | Assumes it works | Runs it on purpose, because untested paths are broken paths |
| Cache | Adds one to make it faster | Asks what happens the moment it is empty |
