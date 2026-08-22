# Tooling discipline (all projects)

Written 2026-08-03. Two habits I failed at for an entire session without
noticing. Neither is about code quality. Both are about not wasting the user's
money and not lying to them by accident.

## Use the code index that is already configured

A SessionStart hook told me, in capitals, to use the codebase graph tools first
for any code exploration, and to index the repository if it was not indexed yet.
I read that instruction and then spent the whole session on Read, Grep, Glob and
shell commands.

When I finally checked, the server was running and healthy with three other
projects in it. This project had never been indexed, so there was no graph to
query even if I had reached for one. Indexing took one call.

**At the start of real work in a repo, check whether the index exists, and
create it if not.** One call up front, then symbol lookups and call tracing cost
a fraction of grepping. The honest caveat: an index usually excludes
directories, so check what it skipped before trusting a negative answer from it.
Mine excluded `scripts/`, which was where most of that session's work lived.

Where a graph genuinely beats grep: finding every caller of a symbol, tracing a
call chain, locating an enum or interface by name. Where it does not help at
all: greenfield writing, config files, running commands, reading prose
documents. Do not force it, and do not skip it either.

Same applies to an LSP tool if one is available. Available and unused is still
unused.

## Verify that a write actually landed

An editing tool returned "internal error" three times in one session on three
different files. Twice I noticed and worked around it. Once I did not, reported
the change as made, and only caught it later because I happened to grep the file
for an unrelated reason. For a while I was describing a state of the world that
did not exist.

**A tool error is not the same as a tool refusal, and neither is proof of what is
on disk.** After any write that errors, times out, or returns something you did
not expect, read the file back or grep it for the new content before you say it
is done.

On Windows, write repo files with the Write tool, or with
[IO.File]::WriteAllText, or Set-Content -Encoding utf8NoBOM.
Never use `>` redirection or `-Encoding utf8`. Both add three invisible
bytes at the start of the file on PowerShell 5.1, and tools read them as
part of the first line.

## Report the state of the world, not the state of your intentions

The two habits above share one failure mode. I described work as finished
because I had issued the instruction to finish it. The instruction is not the
outcome.

Before writing "done" in a message: name the specific observation that makes it
true. An exit code you read. A file you grepped. A frame you looked at. If you
cannot name one, write "attempted" instead and go get the observation.

## A backup is not a restore point until you have read it

Before restoring from a `.bak`, diff it against the live file and say what
changes. Two bad restores dropped things added after the backup was taken.
Prefer version control over loose `.bak` copies beside the live config. Name
what the file must carry before you restore, then check for those specific
things afterwards, not a bare "it parses".

## Pass the dangerous path in, never patch it

A script that can write to a live location takes its destination as a
parameter. A regex that rewrites the path can fail silently and fall back to
the real folder, which is how a test run wrote to `~/.claude`. Same blind spot
as the formatter rule: the guard reads your command line, the script writes
through its own process.
