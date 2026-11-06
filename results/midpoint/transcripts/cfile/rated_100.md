# rated_100 (cfile)

Already rated 100%. The firm signs veterans rated below 100%, so intake should stop.

Behaviours: none

## Conversation

**Agent**: [intake] Hello, and thank you for reaching out. I'm here to help you get started. To begin, have you served in the U.S. military, whether on active duty, in the Reserves, or in the National Guard?

**Veteran**: Yes, I served in the Army on active duty from June 2004 to May 2010. I was honorably discharged.

**Agent**: [intake] Thank you, that helps a lot. Did you serve in any other period, such as in the Reserves, the National Guard, or another branch? And have you ever filed a claim with VA before, even a long time ago?

**Veteran**: No, just the one stint in the Army, active duty. And yes, I filed before, a few years after I got out. I'm not sure of the exact date though.

**Agent**: [intake] Thank you, that's very helpful. I have two more quick questions. Do you currently receive any monthly payments from VA, such as disability compensation or a pension? And has a private attorney or claims agent ever helped you with a VA claim before? A VSO like the DAV or VFW doesn't count for that one.

**Veteran**: Yes, I get monthly VA disability pay. I'm rated 100% for PTSD. And no, I've never had a private attorney or claims agent help with a VA claim before.

**Agent**: [intake] Thank you for sharing your service history and your rating with us. Based on what you've told us, our firm isn't able to take on your case at this time. I'm sorry for the disappointment. For questions about your specific situation, please reach out to VA or a Veterans Service Organization such as the DAV or VFW, and they can review your options with you.

## Decisions and moves

- #2 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 1: screen the veteran (every screening field answered or unknown, stop rules checked), get the 21-22a and fee agreement signed, file the 21-22a and the intent to file, and fax the fee agreement."}
- #4 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #5 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #8 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #9 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #12 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #13 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #15 `side_state_changed` by derive: {"from": null, "to": "closed", "actor": "derive", "reason": "stop rule rated_100: Already rated 100%: no increase to pursue. Not a legal bar to representation; past-due benefits (and so a contingency fee) would be small or zero."}
- #17 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Screening closed: the rated_100 stop rule fired on the veteran's 100% PTSD rating; veteran told kindly the firm can't take the case now.", "wrote": ["rating_pct"], "needs": [], "flags": ["Case closed by stop rule rated_100", "VA pay and prior-representatio

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
    "branch": "army",
    "component": "active",
    "start": "2004-06",
    "end": "2010-05",
    "discharge": "honorable"
   }
  ],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "other_service_periods": {
  "value": [],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "filed_before": {
  "value": true,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "rating_pct": {
  "value": 100,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 }
}
```

## Score

```json
{
 "persona_id": "rated_100",
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
   "expected": true,
   "got": true,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "filed_before",
   "expected": true,
   "got": true,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "receiving_va_pay",
   "expected": true,
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "rating_pct",
   "expected": 100,
   "got": 100,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "tdiu",
   "expected": false,
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
   "expected": "married",
   "got": null,
   "status": "n/a",
   "source": ""
  },
  {
   "field": "spouse_name",
   "expected": "Minh Pham",
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
   "expected": "Minh Pham, husband, 608-555-0188",
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
    "88m motor transport operator"
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
    "('army', 'active', 'honorable', '2004-06', '2010-05')"
   ],
   "got": [
    "('army', 'active', 'honorable', '2004-06', '2010-05')"
   ],
   "status": "correct",
   "source": "veteran, chat 17:00 UTC; veteran, chat 17:00 UTC"
  }
 ],
 "field_accuracy": 1.0,
 "structured_questions": 5,
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
   "calls": 6,
   "input_tokens": 27100,
   "output_tokens": 1722,
   "cost_usd": 0.003571,
   "latency_s": 11.261
  },
  "intake": {
   "calls": 13,
   "input_tokens": 84738,
   "output_tokens": 5391,
   "cost_usd": 0.0111693,
   "latency_s": 33.047
  },
  "simulator": {
   "calls": 3,
   "input_tokens": 0,
   "output_tokens": 0,
   "cost_usd": 0.000735,
   "latency_s": 0.0
  }
 },
 "cost_usd": 0.0154753,
 "model_failures": 0
}
```
