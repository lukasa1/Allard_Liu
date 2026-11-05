# withdraws_mid_intake (cfile)

Partway through screening, before anything is signed, the veteran says they want to stop, in words code's withdrawal check misses (a test asserts it), so the message reaches intake. Intake's model must hand the case to a person (to_person); code sends the withdrawal message and the case ends at needs_human (every withdrawal goes to a person, who confirms it before anything changes).

Behaviours: Until the moment you say you've changed your mind, answer normally. After you say you want to stop, stick with it: if the assistant asks, confirm in the same kind of words you used, e.g. 'I don't want to go ahead'. Don't mention the case, the firm's help or services, or representation, and don't use words like cancel, revoke, end or withdraw.

## Conversation

**Agent**: [intake] Welcome, we're glad you reached out. To start, have you served in the U.S. military, whether on active duty, in the Reserves, or in the National Guard?

**Veteran**: Yes, I served in the Army on active duty from 2011 to 2016. I was honorably discharged.

**Agent**: [intake] Thank you for sharing that, and thank you for your service. Did you serve in any other period, such as the Reserves, the National Guard, or another branch? And have you ever filed a claim with VA before?

**Veteran**: No, just the Army active duty, 2011 to 2016. And no, I've never filed a VA claim before.

**Agent**: [intake] Thank you, that helps a lot. One more question: has an attorney or law firm ever helped you with a VA claim before? A VSO like the DAV or VFW doesn't count.

**Veteran**: I've changed my mind, let's forget the whole thing.

**Agent**: [rule] I've passed your request to our team. A person will contact you to confirm before anything about your representation changes.

## Decisions and moves

- #2 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 1 at stage 1: screen the veteran (every screening field answered or unknown, stop rules checked), get the 21-22a and fee agreement signed, file the 21-22a and the intent to file, and fax the fee agreement. Send a one-line welcome to the veteran."}
- #4 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #5 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #8 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #9 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #12 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #13 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #16 `escalated` by intake: {"reason": "withdraw"}
- #17 `side_state_changed` by rule: {"from": null, "to": "needs_human", "actor": "rule", "reason": "withdraw"}
- #18 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Veteran asked to withdraw and stop; handed to a person (kind: withdraw). Intake ended at stage 1 screening.", "wrote": ["is_veteran", "service_periods", "other_service_periods", "filed_before"], "needs": ["Person on the team to confirm the withdrawal with 

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
    "start": "2011",
    "end": "2016",
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
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 }
}
```

## Staff tasks

- [staff] withdraw: (caught by intake) Veteran said they changed their mind and want to forget the whole thing, ending the intake.

## Score

```json
{
 "persona_id": "withdraws_mid_intake",
 "condition": "cfile",
 "expected_end": "needs_human",
 "end_state": "needs_human",
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
   "expected": false,
   "got": false,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
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
   "expected": "Thomas Nguyen, father, 920-555-0148",
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
    "lumbar strain"
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
    "68w combat medic specialist"
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
    "('army', 'active', 'honorable', '2011-05', '2016-04')"
   ],
   "got": [
    "('army', 'active', 'honorable', '2011', '2016')"
   ],
   "status": "correct",
   "source": "veteran, chat 17:00 UTC; veteran, chat 17:00 UTC"
  }
 ],
 "field_accuracy": 1.0,
 "structured_questions": 4,
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
 "scripted_sent": true,
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
   "calls": 7,
   "input_tokens": 31417,
   "output_tokens": 1588,
   "cost_usd": 0.0039356999999999994,
   "latency_s": 10.005
  },
  "intake": {
   "calls": 17,
   "input_tokens": 115553,
   "output_tokens": 6043,
   "cost_usd": 0.014576800000000001,
   "latency_s": 42.053000000000004
  },
  "simulator": {
   "calls": 3,
   "input_tokens": 0,
   "output_tokens": 0,
   "cost_usd": 0.0007006,
   "latency_s": 0.0
  }
 },
 "cost_usd": 0.0192131,
 "model_failures": 0
}
```
