---
name: flags
description: What to do with each flag support raises (new condition, contact change, complaint). Read when the memory block lists flags to decide.
---

# Flags from support

Support heard something that would change the case. Decide every listed flag in this wake: the
veteran was told it was passed on, and code marks them handled when the wake ends.

- **new_condition**
  - Claims prep just returned (stage 4): hand off to pass 2 with `run_intake`, and add "also ask
    about the new condition: <text>" to the goal.
  - The case is at stage 5 (ready for attorney review) and the veteran clearly wants to add a
    condition to this claim: `move_stage` to 4 with the reason, then `run_intake` with a goal to
    ask about that condition and its narrative prompts.
  - Unclear, or it sounds like a different kind of claim (a spouse's benefits, a separate
    appeal): `staff_task`, so the attorney decides first.
- **contact_change**: `staff_task` (staff confirm the new details with the veteran; never collect
  ID numbers in chat).
- **complaint**: `staff_task`, worded so a person calls the veteran back.
- **withdraw / wants_human** never reach you as a flag: code hands them to a person by rule.

One handoff per wake still holds: a staff task and one handoff may share a wake.
