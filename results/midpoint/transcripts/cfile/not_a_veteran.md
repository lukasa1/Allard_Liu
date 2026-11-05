# not_a_veteran (cfile)

Never served. Intake should stop politely at the first question.

Behaviours: none

## Conversation

**Agent**: [intake] Welcome, and thank you for reaching out. To start, have you served in the U.S. military, whether on active duty, in the Reserves, or in the National Guard?

**Veteran**: No, I never served in the military, not active duty, Reserves, or National Guard. A friend told me your firm helps people with disability benefits, so I wanted to ask if you could help me.

**Agent**: [intake] Thank you for reaching out, and for answering so clearly. Our firm represents only veterans, so we are not able to take on your case. I'm sorry we can't help with this one. Your friend may be able to point you to other resources for disability questions.

## Decisions and moves

- #2 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 1: screen the veteran (every screening field answered or unknown, no stop rule fired), have the veteran sign the 21-22a and fee agreement, file the 21-22a and intent to file, and fax the fee agreement. Send a one-line welcome to the veteran."}
- #4 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #5 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #7 `side_state_changed` by derive: {"from": null, "to": "closed", "actor": "derive", "reason": "stop rule not_veteran: The firm represents veterans only."}
- #9 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Screening closed: veteran status recorded as false; not_veteran stop rule fired and the case is closed.", "wrote": ["is_veteran"], "needs": [], "flags": ["not_veteran stop rule fired; case closed"]}, "stage": 1}

## Answers

```json
{
 "is_veteran": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 }
}
```

## Score

```json
{
 "persona_id": "not_a_veteran",
 "condition": "cfile",
 "expected_end": "closed",
 "end_state": "closed",
 "scenario_pass": true,
 "split": "dev",
 "critical_errors": [],
 "completed": true,
 "error": "",
 "fields": [
  {
   "field": "is_veteran",
   "expected": false,
   "got": false,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "filed_before",
   "expected": false,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "receiving_va_pay",
   "expected": null,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "rating_pct",
   "expected": null,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "tdiu",
   "expected": null,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "prior_attorney",
   "expected": false,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "prior_attorney_name",
   "expected": null,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "dic_claim",
   "expected": false,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "earning_over_1600",
   "expected": true,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "receives_ssa",
   "expected": false,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "ssa_interest",
   "expected": false,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "partner_share_consent",
   "expected": true,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "retired",
   "expected": false,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "litigation_contact",
   "expected": null,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "marital_status",
   "expected": "single",
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "spouse_name",
   "expected": null,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "children_under_18",
   "expected": false,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "next_of_kin",
   "expected": "Pat Lang, mother, 262-555-0109",
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "heard_about",
   "expected": "a friend",
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "internet_source",
   "expected": null,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "claim_conditions",
   "expected": [],
   "got": [],
   "status": "n/a",
   "source": ""
  },
  {
   "field": "other_conditions",
   "expected": [],
   "got": [],
   "status": "n/a",
   "source": ""
  },
  {
   "field": "mos",
   "expected": [],
   "got": [],
   "status": "n/a",
   "source": ""
  },
  {
   "field": "exposures",
   "expected": [],
   "got": [],
   "status": "n/a",
   "source": ""
  }
 ],
 "field_accuracy": 1.0,
 "structured_questions": 1,
 "narrative_answers": 0,
 "clarifications": 0,
 "veteran_messages": 1,
 "cfile_prefilled": 0,
 "prefill_share": 0.0,
 "turns_to_signed_poa": null,
 "fee_expected": null,
 "fee_got": null,
 "kb_calls": 0,
 "kb_sourced": 0,
 "resumed_after": null,
 "ask_answer": {},
 "scripted_sent": null,
 "untested": false,
 "handoffs": [
  "intake"
 ],
 "refused": {},
 "flag_decisions": [],
 "flag_decision_expected": null,
 "flag_decision_correct": null,
 "facenote_line_accuracy": null,
 "facenote_lines": [
  0,
  0
 ],
 "facenote_checks": {},
 "verify_passed": null,
 "uncertain_lines": 0,
 "citation_precision": null,
 "facts": 0,
 "by_agent": {
  "orchestrator": {
   "calls": 5,
   "input_tokens": 20035,
   "output_tokens": 1083,
   "cost_usd": 0.002545,
   "latency_s": 7.319999999999999
  },
  "intake": {
   "calls": 5,
   "input_tokens": 29160,
   "output_tokens": 1324,
   "cost_usd": 0.0035780000000000005,
   "latency_s": 9.25
  },
  "simulator": {
   "calls": 1,
   "input_tokens": 0,
   "output_tokens": 0,
   "cost_usd": 0.0001716,
   "latency_s": 0.0
  }
 },
 "cost_usd": 0.0062946,
 "model_failures": 0
}
```
