# oth_only_period (cfile)

The only period of service ended with an other-than-honorable discharge. Under the firm's rule an attorney decides whether to take such a case, so intake should stop and send it to attorney review rather than collect everything.

Behaviours: You know for certain your discharge was other than honorable (OTH); when asked, say so plainly, without "I think" or "not sure". You don't have the DD-214 at hand, and you don't need it to know.

## Conversation

**Agent**: [intake] Hello, and thank you for reaching out to us. I'm here to help get your questions started. To begin, have you served in the U.S. military, whether on active duty, in the Reserves, or in the National Guard?

**Veteran**: Yes, I served in the Marine Corps on active duty from 2009 to 2011.

**Agent**: [intake] Thank you for your service, and thank you for sharing that. Do you remember what kind of discharge you received from the Marine Corps? Common answers are "honorable," "general," or "other than honorable," and it's fine if you're not sure of the exact wording.

**Veteran**: Yeah, it was other than honorable. I know that for sure.

**Agent**: [intake] Thank you for telling me that, and I'm sorry it went that way. I have your Marine Corps active duty service from 2009 to 2011 noted. Did you have any other period of service, such as a second enlistment, or time in the Reserves or National Guard?

**Veteran**: No, just the one stint on active duty with the Marines. Nothing in the Reserves or Guard.

**Agent**: [intake] Thank you for telling me about your service, and for answering my questions so clearly. Based on what you shared, an attorney on our team will review your situation personally and contact you. I can't say more about what that review will decide, but you won't have to figure out next steps alone. If you have any questions in the meantime, a person on the team can follow up with you.

## Decisions and moves

- #2 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 1: screen the veteran (every screening field answered or unknown, no stop rule fired), get the 21-22a and fee agreement signed, file the 21-22a and the intent to file, and fax the fee agreement."}
- #4 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #5 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #8 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #9 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #12 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #13 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #15 `side_state_changed` by derive: {"from": null, "to": "needs_human", "actor": "derive", "reason": "stop rule non_honorable_period: Every service period ended other than honorable (OTH), with a bad conduct discharge or with a dishonorable discharge: an attorney decides whether the firm takes the case. When only some periods did, int
- #17 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Screening stopped at stage 1: the only service period (Marine Corps active duty, 2009 to 2011) ended OTH, so the case went to a person (needs_human) and the veteran was told an attorney will review and contact them.", "wrote": ["other_service_periods"], "n

## Answers

```json
{
 "is_veteran": {
  "value": true,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "service_periods": {
  "value": [
   {
    "branch": "marine corps",
    "component": "active",
    "start": "2009",
    "end": "2011",
    "discharge": "oth"
   }
  ],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "other_service_periods": {
  "value": [],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 }
}
```

## Score

```json
{
 "persona_id": "oth_only_period",
 "condition": "cfile",
 "expected_end": "needs_human",
 "end_state": "needs_human",
 "scenario_pass": true,
 "split": "heldout",
 "critical_errors": [],
 "completed": true,
 "error": "",
 "fields": [
  {
   "field": "is_veteran",
   "expected": true,
   "got": true,
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
   "expected": false,
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
   "expected": "Linda Boone, mother, 910-555-0151",
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
   "expected": [
    "tinnitus"
   ],
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
   "expected": [
    "3531 motor vehicle operator"
   ],
   "got": [],
   "status": "n/a",
   "source": ""
  },
  {
   "field": "exposures",
   "expected": [
    "burn pits"
   ],
   "got": [],
   "status": "n/a",
   "source": ""
  },
  {
   "field": "service_periods",
   "expected": [
    "('marine corps', 'active', 'oth', '2009-08', '2011-03')"
   ],
   "got": [
    "('marine corps', 'active', 'oth', '2009', '2011')"
   ],
   "status": "correct",
   "source": "veteran, chat 17:00 UTC; veteran, chat 17:00 UTC"
  }
 ],
 "field_accuracy": 1.0,
 "structured_questions": 3,
 "narrative_answers": 0,
 "clarifications": 0,
 "veteran_messages": 3,
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
   "input_tokens": 22228,
   "output_tokens": 1151,
   "cost_usd": 0.0027983,
   "latency_s": 7.7459999999999996
  },
  "intake": {
   "calls": 11,
   "input_tokens": 68691,
   "output_tokens": 3530,
   "cost_usd": 0.0086341,
   "latency_s": 24.421999999999997
  },
  "simulator": {
   "calls": 3,
   "input_tokens": 0,
   "output_tokens": 0,
   "cost_usd": 0.0006714,
   "latency_s": 0.0
  }
 },
 "cost_usd": 0.012103800000000001,
 "model_failures": 0
}
```
