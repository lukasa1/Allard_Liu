---
name: cite-check
description: How verify checks every face-note line against its cited pages, and what to do with a failed line. Read when verify fails.
---

# Cite check

`verify` is code. For every face-note line it checks that the line has source facts and that
each fact's cited page shows the fact's key values. It normalizes first: dates in any form
(2024-03-14, 03/14/2024, 20240314, March 14, 2024), service months, percentages (10%,
10 percent) and condition names. A rating must be the first percentage after its condition's
name, and a decision issue's outcome must follow its condition.

Values must sit where their label puts them: the date of birth after "date of birth" (not the
entry date), a period's start after "entered" and its end after "separation date" (record `end`
when the page has one; start is never after end), the MOS and a representative's name as the
whole field value (code and title: "88M Motor Transport Operator", not "88M"; "Alan Smith", not
"Smith"), and a decision lists every condition its DECISION section decides.

## A failed line

Each failure names the line and the fact: "fact F3 cites p. 2, which does not show 1985-04-07".
For each one, in this order:
1. **Re-cite:** the value is right but on another page. `search` for it, `read_pages` that page,
   and `record_facts` the fact again with `id: "F3"` and the new cite.
2. **Re-record:** the value is wrong. Read the cited page again and record the right value
   with `id: "F3"`.
3. **Missing facts:** a "nothing found" line fails when a document of that type has no fact
   recorded from it: read it and record its facts.
4. **Uncertain:** only when the C-file can't settle it (illegible, contradictory, or missing).
   Call `verify(uncertain=[{line: N, reason: "..."}])`. The line is marked uncertain on the note
   and becomes a staff task; a person checks it.

Then `render` and `verify` again. Claims prep is done when `verify` passes (or the only failing
lines are escalated as uncertain) and `prefill` has run. Never mark a line uncertain to skip
reading a document you haven't read.
