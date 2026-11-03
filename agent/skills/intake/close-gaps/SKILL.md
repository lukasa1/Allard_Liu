---
name: close-gaps
description: Pass 2, stage 4: after claims prep read the C-file, ask only what is still missing, confirm the C-file conflicts, then the narrative prompts.
---

# Close the gaps (pass 2, stage 4)

Claims prep has read the C-file and pre-filled what it settles (sources "C-file p. N" in your
known fields). Your `pass2` checklist lists only what is still missing. Never ask about a field
that is already known.

Work through the checklist in this order:
1. **Questions that became relevant.** The C-file can make a pass-1 question apply (an earlier
   claim makes the rating questions visible). They are in the checklist like any other.
2. **C-file conflicts** (`how: "confirm"`). Tell the veteran what the claims file shows and what
   is on file, and ask which is right, without suggesting an answer. Record their answer with
   `record_answer` on that question id: it replaces the value and resolves the conflict.
3. **The rest of the firm's form** (`how: "chat"`). Contact fields (`how: "secure_form"`) go
   through `request_secure_info`; if the veteran has none (no email), record them as `unknown`.
4. **Narrative prompts** for each claimed condition (`narrative:<condition>:<prompt id>`): ask
   two or three related ones per message, in order, warmly, and record each answer in the
   veteran's own words (one `record_answer` per prompt; a prompt they didn't answer stays open).

A new condition the orchestrator's goal mentions: record `claim_conditions` again with the full
list, which adds its narrative prompts to the checklist.

Stop-rule fields (`is_veteran`, the service periods, `receiving_va_pay`, `rating_pct`,
`prior_attorney`) take the structured value you understood in `value`, with the veteran's words in
`a`, here too (a C-file conflict on the rating included); a hedged answer is confirmed first.

The stop rules still run on every answer (after filing, a fired rule sends the case to a person).
When the checklist is empty, code moves the case to stage 5 (ready for attorney review) and the
pass ends: thank the veteran and say the attorney reviews their file next.
