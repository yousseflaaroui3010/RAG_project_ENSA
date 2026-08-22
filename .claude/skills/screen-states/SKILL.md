---
name: screen-states
description: Build every state a screen will really be in, not just the one in the design. Use when building or changing any screen, form, list, dialog or table, and before asking anyone to review a screen.
---

# Screen states

A junior builds the screen in the design. A senior builds every state that screen will actually be in.

The design file shows one moment: everything loaded, a short name, three items in the list, good network. Real users live in all the other moments. **A design is a photograph. A screen is a film.**

## The states every screen needs

| State | The question |
| --- | --- |
| Loading | What is on screen while the data is coming? |
| Empty | What does a brand new user with no records see, and what do they do next? |
| Error | The request failed. What can the user do about it? |
| Partial | Some data arrived, some did not |
| Too much | 500 items, not 3. A name 80 characters long |
| Offline or slow | The reply arrives after the user moved on |

A design without its empty, loading and error states is **not ready to build**. That is not a complaint, it is a definition of ready. It costs a designer ten minutes to draw the empty state and costs the project a day to add it later, with an unhappy client attached.

## The six failures to check before every review

An annual scan of the top million home pages found 95.9 percent had failures a tool could detect automatically, averaging 56 problems per page. Six categories accounted for 96 percent of everything found, and the same six have topped the list for seven years.

| Failure | Share of home pages |
| --- | --- |
| Text with too little contrast against its background | 83.9 |
| Images with no text description | 53.1 |
| Form inputs with no label | 51 |
| Links with nothing inside them | 46.3 |
| Buttons with nothing inside them | 30.6 |
| Page with no language set | 13.5 |

None of these are hard. They are the basics, still unfixed at enormous scale. The list is short enough to memorise, which is the point.

Two things from the same report. Automated tools only catch part of the problem, so no detected errors does not mean the page is fine. And pages using extra accessibility markup averaged **more** errors (59.1) than pages using none (42), which they call a correlation not a cause. The practical version: accessibility markup added without understanding it makes things worse. The organisation publishing this sells accessibility training, so they gain from it looking bad, but the method and the tool are public.

These six are pass or fail, not a scale. Never ship a screen with an unlabelled input.

## Before asking for review

- Walk the whole screen with the keyboard only. Know where focus goes after every action, and never trap it.
- Check the contrast number, and push back on the design when it fails.
- Try it on a mid range phone on a slow connection, not your laptop.
- Paste in a name twice as long as expected, and text in another language. Some read right to left.
- Submit the form twice quickly. Nothing should happen twice.
- Make the request fail on purpose. Read what the user sees.

## Forms, specifically

Label every input. Put the error next to the field, not at the top. Never wipe what the user typed when validation fails. Block the double submit.

## Speed

The three numbers live in `quality-metrics`. Judge them on real visits at the 75th out of 100, split phone and desktop, never on your own machine.

## Junior against senior

| Moment | Junior | Senior |
| --- | --- | --- |
| A design lands | Builds what the picture shows | Asks about empty, long names, slow network, failed request |
| Keyboard | Checks with a mouse | Walks the screen with the keyboard before review |
| Colour | Copies from the design | Checks contrast, pushes back when it fails |
| Data from the server | Assumes the shape is right | Treats every response as possibly late, missing or wrong shaped |
| Speed | Tests on their fast laptop | Tests on a cheap phone on a slow connection |
| Repeated pieces | Copies the component and edits the copy | One piece with options, or keeps the copy on purpose and says why |
| The design looks wrong | Builds it anyway | Says so once, in writing, naming the exact problem |
