---
name: stage-playbook
description: The case's stages in order, each stage's exit criteria, and which subagent owns it. Read before choosing an action when you are unsure which stage the case is in or what must happen next.
---

# The stage playbook

The stage table in code (`agent/orchestrator.py` ACTIONS) enforces these gates; this is the same
playbook in words, for the model choosing among the allowed actions.

| Stage (phase) | Owner | Exit criteria | Next action |
|---|---|---|---|
| new | orchestrator | VA sign-in offered, or not offered (the default) | request_va_sign_in, or start_screening |
| va_sign_in | the veteran | consent granted (records fetched) or declined | fetch_va_records, start_screening |
| screening (pass 1) | intake | eligibility, stop rules and fee questions answered | start_poa (or close_case / hand_off_to_staff) |
| poa | intake (POA skill) | the veteran signed the 21-22a | request_attorney_signoff |
| attorney_signoff | the attorney, then tools | countersigned; 21-22a submitted; intent to file filed | submit_poa_to_va, file_intent_to_file, fetch_cfile |
| case_prep | claims prep | the C-file arrived (`cfile_ready`) and was read: face note, prefill, conflicts | run_claims_prep, then continue_intake |
| intake (pass 2) | intake | the remaining gaps, the C-file check, the narratives | send_to_attorney_review |
| attorney_review | the attorney | (terminal for now; claims investigation is not built) | reopen_intake_for_new_condition, pass_flags_to_staff |

Rules that are never a choice: after a crisis or a request for a person, only hand_off_to_staff.
Nothing is filed before the attorney countersigns. A stop found after filing (not a veteran,
rated 100%) goes to a person, who decides whether to withdraw the 21-22a; it is not closed.
