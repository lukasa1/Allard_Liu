---
name: flags
description: What to do with each flag support raises (new condition, contact change, complaint). Read when `open_flags` is not empty.
---

# Flags from support

The veteran said something, while the case was parked, that would change the case.

- **new_condition** after attorney review has the case: prefer `reopen_intake_for_new_condition`
  when the veteran is clearly asking to add a condition to this claim (intake asks which one and
  its narrative prompts, then the case returns to attorney review). Choose `pass_flags_to_staff`
  instead when it is unclear, or when it sounds like a different kind of claim (a spouse's
  benefits, a separate appeal), so the attorney decides first.
- **new_condition** before pass 2: `pass_flags_to_staff`; pass 2 asks for every condition anyway.
- **contact_change**: `pass_flags_to_staff` (staff confirm the new details with the veteran;
  never collect ID numbers in chat).
- **complaint**: `pass_flags_to_staff` (it becomes an urgent task).
- **withdraw / wants_human** never reach you as a choice: they are handed off by rule.

Never leave a flag open: the veteran was told it was passed on.
