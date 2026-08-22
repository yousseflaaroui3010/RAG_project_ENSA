---
name: fail-loud
description: Make errors impossible to miss instead of easy to swallow. Use when writing error handling, adding a try or catch, validating input, or when a bug was hard to find because nothing complained.
---

# Fail loud

A silent error is a slow leak in a basement. It rots the wood for months before anyone sees water. Make the leak spray, so it gets patched the same day.

## The four rules

1. **Crash early on bad input.** Check what comes in at the door and refuse it there, with a clear message. A bad value that travels three functions before breaking gives you a mystery instead of a bug.
2. **Never catch an error and say nothing.** Either handle it properly, or log it with everything you know and pass it on. An empty catch block is a hole with a rug over it.
3. **Keep the logs clean so real errors stand out.** When every line is a warning, nobody reads any of them.
4. **Let errors travel up with their context attached.** The place that can decide what to do is usually not the place that noticed.

## What this looks like

```
// Swallowed. The user sees nothing, you learn nothing.
try { save(order) } catch (e) { }

// Swallowed politely, which is worse, because it looks handled.
try { save(order) } catch (e) { return null }

// Loud. The caller can decide, and you can find it later.
try {
  save(order)
} catch (e) {
  log.error({ event: "order_save_failed", orderId: order.id, cause: e.message })
  throw e
}
```

## Loud while building, careful in front of users

Two different jobs.

| Where | Behaviour |
| --- | --- |
| While building | Crash immediately, print everything, make it annoying |
| In front of a user | A plain message they can act on, detail kept in the log, never a stack trace on screen |

A user does not need the column name. You do.

## The check

Break it on purpose and watch. Feed it an empty value, a missing field, a wrong type, a value twice the size you expected. If nothing complains anywhere, the handling is decoration.
