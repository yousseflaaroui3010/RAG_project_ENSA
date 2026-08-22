---
name: debug-loop
description: The order to work in when something is broken. Use whenever a bug, error or unexpected behaviour appears, when a fix is not holding, or when stuck for more than the agreed number of attempts.
---

# The debug loop

Seven steps, in this order. Juniors jump straight to step 4.

Debugging is not cleverness, it is a search, and the whole skill is shrinking the space you search. Someone senior looking for a lost key checks the four places it could be. A junior searches the house.

## 1. Make it happen on purpose

No fixes until you can produce the problem when you want to. Without that, you cannot know you fixed it. You will only know you stopped seeing it.

If you cannot reproduce it, that is now the problem to solve. Get the exact steps, screen, time, account and browser first.

## 2. Write what you expected and what you got

Two lines. Half of all bugs die here, because the two lines do not match the story in your head.

## 3. Order the checks by cost, not by hunch

The check that takes thirty seconds goes first, even if it feels unlikely. A hunch that takes two hours to test goes last.

## 4. Change one thing, test, write it down

Two changes at once means a break has two possible causes and you cannot tell them apart. Keep a running list: change made, result. Every attempt goes in, including the ones that did nothing.

## 5. Cut the space in half

Does it happen with half the data? Half the steps? Last week's version? Each halving turns twenty suspects into one in about five moves.

With small working commits you can test the middle of the range, then the middle of the half, and land on the exact change in a handful of steps.

## 6. Question the assumption, not only the code

"The input is valid." "That service is up." "This runs once." "The config I am reading is the config being used."

Bugs live in the sentence you never thought to check. Tonight's own example: a hook file was correct and did nothing, because it was wired to the wrong tool.

## 7. Stop at the budget

Decide the number of attempts before you start. When you hit it, stop fixing and question the problem itself. You are probably solving the wrong one.

## Two extra rules

**A change made it go away.** Do not ship yet. Ask why that change worked. If you cannot say, the fix is a coincidence and it will come back.

**Read the whole error**, including the part below the first line. The useful sentence is usually not the first one.

## Junior against senior

| Moment | Junior | Senior |
| --- | --- | --- |
| The report arrives | Starts reading code | Gets the exact steps, screen, time and account first |
| Cannot reproduce | Says it works for them | Treats "cannot reproduce" as the first thing to solve |
| Reading the error | Skims it, starts guessing | Reads all of it |
| Making changes | Several at once to save time | One at a time, with a note after each |
| A change works | Ships the fix | Asks why it worked |
| Stuck | Keeps going, quieter and quieter | Stops at the agreed number and brings someone in |
| Fixed | Closes the ticket | Adds the test that would have caught it, then closes |
| An old similar bug | Does not know about it | Checks whether this is the same thing wearing a new hat |

## Then fix why nobody saw it sooner

The bug is half the job. The other half is why it was invisible. A duplication check failed on a renamed flag, and the real defect was that the command was unpinned and resolved to whatever was newest, so the gate could break on a stranger's release schedule. Fix the flag, then pin the tool.
