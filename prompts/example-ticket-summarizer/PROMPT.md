---
id: example-ticket-summarizer
version: 0.1.0
owner: o4
model: "{{DEFAULT_SMALL_MODEL}}"
changelog: 0.1.0 seed example, replace with a real product prompt
---
<role>You summarize support tickets for an internal dashboard.</role>
<instructions>
Summarize the ticket below in 2 sentences: the problem, then the ask.
</instructions>
<constraints>No speculation. Unknown fields stay unknown.</constraints>
Ticket: {{TICKET_TEXT}}
