---
name: stage-playbook
description: The case's stages, each stage's exit criteria and owner, and what to do on each kind of wake. Read when you are unsure what the waking event asks of you.
---

# The stage playbook

Code derives the stage from the case file and moves it forward when the exit criteria hold. You
never move a case forward yourself: you hand it to the next owner. Your guard refuses anything
the table doesn't allow and tells you why.

| Stage | Owner | Exit criteria (checked in code) |
|---|---|---|
| 1 screening (pass 1) | intake | every screening field answered or unknown; no stop rule fired |
| 2 account opening (pass 1) | intake | the 21-22a submitted and the intent to file filed (intake waits for the attorney's countersign in `waiting_on_attorney`) |
| 3 filed (pass 1 ends) | you | you hand off with `run_prep` |
| 4 C-file requested | claims prep, then intake (pass 2) | claims prep returned (face note, verify, prefill), then every pass-2 field filled or unknown |
| 5 gaps closed | the attorney | ready for attorney review: the end of the demo flow |
| 6 file review done | - | not built yet |

Side states: `waiting_on_veteran` and `waiting_on_attorney` (the owner keeps the case),
`waiting_on_va` (between owners), `needs_human` and `closed` (a person, or nobody, has it).

## What each wake asks of you

- **case_opened** (stage 1, no owner): `run_intake` with a pass-1 goal: screen the veteran, sign
  the 21-22a and the fee agreement, file the 21-22a and the intent to file, fax the fee agreement.
  Send a one-line welcome in `reply`.
- **subagent_result from intake at stage 3**: `run_prep` with the goal: pull and read the C-file,
  prefill the intake answers it settles, write and verify the face note. A short `reply` telling
  the veteran their forms are filed and the file review has started is fine.
- **subagent_result from claims_prep** (stage 4): decide the held flags in the same wake (see
  `flags`), then `run_intake` for pass 2: ask only the fields still missing, confirm the C-file
  conflicts, then the narrative prompts. Put any new condition from a flag into the goal.
- **subagent_result from intake at stage 5**: nothing to hand off; the case waits for attorney
  review. Leave `reply` empty (intake already told the veteran). Don't move it back to stage 4
  unless a support flag names a new condition: a question intake left out is not a reason.
- **subagent_result with the case `closed` or `needs_human`** (a stop rule, a crisis, a request
  for a person): no handoff. Leave `reply` empty: the veteran was already told.
- **escalated**: a person has been asked to step in (a crisis or a request for a person is
  handled by rule before you wake). Make no handoff. If the case is not parked and the reason
  needs a person before the case may continue, `move_stage` to `needs_human` with the reason.
- **support_flag**: see the `flags` skill.
- **a staff event nobody owns** (for example a countersign that arrives while no one owns the
  case): record a `staff_task` if someone must act on it; otherwise do nothing.

## Rules

- One handoff per wake. After it, finish.
- `move_stage` moves back only from stage 5 to stage 4 (with a reason, which intake's pass-2
  checklist then shows; code hands the case to intake with it as the goal), or to `needs_human` /
  `closed`. `closed` is
  refused once anything was filed with VA: then a person decides on withdrawal (`needs_human`).
- One case-owning sub-agent at a time: a handoff is refused while another owns the case.
- `staff_task` only for something no open task covers. The case file's `open_tasks` already holds
  what code and claims prep raised (a face-note flag such as a DOB mismatch, a non-honorable
  period, an uncertain line, a deadline): don't restate one, and don't add a summary of the open ones.
