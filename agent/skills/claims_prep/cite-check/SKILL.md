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
entry date); a decision's date after "decision date" and its `filed` after "received"; a
letter's date after "date of this letter" and its `decision_date` after "decision dated". A
service period matches as one: on a DD-214, its branch field with the component ("NAVY -
RESERVE" is `reserve`), its start after "entered" and its end after "separation date" (record
`end` when the page has one; start is never after end); on a narrative, one "{branch} from
{start} to {end}" (a component it names must be the fact's). The MOS and a representative's name are the
whole field value, or one whole entry of a list (code and title: "88M Motor Transport Operator",
not "88M"; "Alan Smith", not "Smith"), and a decision lists every condition its DECISION section
decides.

After the lines, `verify` checks coverage: every DD-214 needs a `service_period`, a `discharge`
(when it shows one) and a `mos` (when its specialty is filled in), every rating decision a
`decision`, every notification letter a `notification_letter` and every 21-22/21-22a (the
firm's own too) a `prior_representative` recorded from it; every claim
form needs a decision that lists it as filed, or a `pending_filing` from it; every condition on
the newest code sheet's SERVICE CONNECTED list needs a `rated_condition`; `combined_rating` and
each `rated_condition` must cite the newest rating decision (or its notification letter); and no
fact may be unlinked (a discharge with no period, a letter with no decision). These items
are numbered after the face-note lines and are fixed the same way.

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
