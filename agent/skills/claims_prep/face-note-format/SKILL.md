---
name: face-note-format
description: What the firm's face note needs from the C-file, which facts to record for each line, and how render builds it.
---

# Face-note format

`render` builds the note in code (`agent/cfile/facenote.py`) from your fact table. You never
write a line yourself: you record the facts, and each line carries the facts it came from.

## The lines and the facts behind them

| Line | Record (from which document) |
|---|---|
| `FA <fee>%; Prior rep NAME` or `No prior rep` | the fee comes from the case's own fee agreement. Record a `prior_representative` for **every** 21-22 / 21-22a in the C-file, with `revoked` when the form has revocation details |
| `DOB` | `dob` (DD-214) |
| `Service Era` | derived from the first `service_period`'s start |
| one line per period: branch, dates, discharge | `service_period` and `discharge` (DD-214; `period_start` links the two) |
| `MOS` | `mos` (DD-214 primary specialty) |
| `SC at time of signing` and the SC list | `combined_rating` and every `rated_condition` from the **most recent** code sheet |
| `Filed 0966 Intent on` | the firm's own ITF filing (the case file) |
| numbered entries: decisions less than a year old, newest first, with the filing form, the R.D. date and the AMA appeal deadline | `decision` (rating decision: date, every issue with its outcome and %, the filing form and date from the evidence list) and its `notification_letter` (its own date, and the `decision_date` it is about). Deadlines run from the letter: one year later |
| `<conditions>: pending` | `pending_filing` (a claim form no decision covers yet) |
| OLD CLAIMS | decisions more than a year old (the same `decision` facts) |

## Rules

- **Prior rep:** check every appointment form (21-22 or 21-22a) and record each one. Only a
  private attorney or agent counts as a prior rep; a VSO (a 21-22) never does. A form with
  revocation details is not a current prior rep either (the firm's SOP). With none left, the
  header says `No prior rep`; otherwise the newest one is the prior rep. The firm's **own** 21-22a is in the file too
  (it was filed before the pull): record it like the others; code knows it is not a prior rep.
- "Nothing found" lines (no DD-214 facts, no code sheet, no prior rep) hold only if every
  document of that type has a fact recorded from it.
- Use VA's condition names ("tinnitus", "left knee condition"); code normalizes them.
- Record dates as the document shows them or as YYYY-MM-DD; service dates as YYYY-MM.
- Facts with an `id` replace that fact: use it to correct a fact `verify` rejected.
- After any `record_facts`, render and verify again, then prefill again (recording clears both).

## Prefill (for intake's pass 2)

After `verify` passes, `prefill` with the questions the C-file settles: `service_periods`, `filed_before`,
`rating_pct`, `sc_conditions`, `prior_attorney`, `prior_attorney_name`, `mos`. Code builds the
values from your facts (only those whose cites hold) and compares them with the veteran's answers: the DD-214 wins on the
character of discharge; any other difference becomes a conflict that pass 2 asks the veteran to
confirm, with a staff task. You don't decide conflicts.
