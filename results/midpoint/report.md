# Case eval: midpoint

Trials per persona: 1 · runs: 20

Conditions: `ask_no_probes` = intake without the verification probes and without C-file prefill; `ask` = with the probes, no prefill; `cfile` = probes, prefill from the C-file and a confirmation of each conflict (the default, and what the demo runs).

## Headline: structured questions settled in chat

Structured intake questions settled from the veteran's chat answers (narratives and the secure form excluded), mean over **completed** runs. Fewer is better only with zero critical errors and field accuracy held, so they share the row.

| Condition | Structured questions | n | Runs w/ critical errors | Field acc. | Prefilled (share) | Clarifications | Turns to signed 21-22a | pass^k |
|---|---|---|---|---|---|---|---|---|
| cfile | **17.8** | 20/20 | 0 of 20 | 99% | 4% | 1.2 | 9.6 | 100% |

## Intake

KB: kb_search calls and those with a sourced answer. Persona question (asks_question_mid_intake, sent alone, answering nothing): `resumed after` = veteran replies until intake recorded an answer again (1 = it answered and asked its question again at once); `answer ok` = the LLM judge (intake_eval/judge.py) found every point of the persona's answer key and nothing wrong.

| Condition | Narrative answers | Veteran messages | KB calls / sourced | Question: resumed after / answer ok | Scripted messages sent | Model failures |
|---|---|---|---|---|---|---|
| cfile | 12.8 | 18.8 | 2 / 1 | 1.0 / 0/1 | 5/5 | 2 |

## Orchestrator

Scenario pass: the run completed and the case ended where the persona's expected decision says. Flag decisions: labelled scenarios (a persona's `expected.flag_decision`). Refused: tool calls and moves the guards refused, per agent.

| Condition | Scenario pass | Flag decisions correct | Refused (per agent) |
|---|---|---|---|
| cfile | 100% | 1/1 | intake 11 |

## Claims prep

Face-note lines: the note's lines against the note rendered from the ground-truth facts. Fact checks: the share of fact groups (DOB, periods, MOS, ratings, decisions, prior reps) read right. Citation precision: facts whose cited page shows their values.

| Condition | Face-note lines | Fact checks | Verify passed | Citation precision | Uncertain lines |
|---|---|---|---|---|---|
| cfile | 99% | 99% | 15/16 | 100% | 2 |

## Cost and latency per agent

From the traces (prices in agent/config.py). Calls and cost are means per case; latency is per model call. The simulated veteran is counted separately; kb_search's model call is counted to the agent that searched.

| Condition | Agent | Calls / case | Cost / case | Cost total | Latency / call |
|---|---|---|---|---|---|
| cfile | orchestrator | 10.7 | $0.0087 | $0.1742 | 2.04s |
| cfile | intake | 96.5 | $0.1080 | $2.1607 | 2.80s |
| cfile | claims_prep | 10.2 | $0.0166 | $0.3311 | 2.94s |
| cfile | support | 0.2 | $0.0001 | $0.0018 | 1.65s |
| cfile | simulator | 18.9 | $0.0104 | $0.2076 | 0.00s |
| cfile | judge | 0.1 | $0.0000 | $0.0003 | 0.00s |
| cfile | **all** |  | $0.1438 | $2.8757 |  |

## Per persona

### cfile

| Persona | Expected end | Got | Fields | Structured q | Prefilled | Face-note lines | Citations | Critical | Cost |
|---|---|---|---|---|---|---|---|---|---|
| asks_question_mid_intake | attorney_review | ✅ attorney_review | 100% | 21 | 1 | 100% | 100% | 0 | $0.1805 |
| baseline_clean | attorney_review | ✅ attorney_review | 100% | 20 | 1 | 100% | 100% | 0 | $0.1463 |
| colloquial_conditions | attorney_review | ✅ attorney_review | 100% | 21 | 1 | 100% | 100% | 0 | $0.2846 |
| corrects_after_preview | attorney_review | ✅ attorney_review | 100% | 23 | 1 | 100% | 100% | 0 | $0.1703 |
| crisis_backstop | needs_human | ✅ needs_human | 95% | 21 | 1 | 100% | 100% | 0 | $0.1187 |
| crisis_disclosure | needs_human | ✅ needs_human | 100% | 20 | 1 | 100% | 100% | 0 | $0.1136 |
| dd214_discharge_differs | attorney_review | ✅ attorney_review | 100% | 21 | 1 | 100% | 100% | 0 | $0.1889 |
| dob_swapped | attorney_review | ✅ attorney_review | 100% | 21 | 1 | 100% | 100% | 0 | $0.1603 |
| family_ssa_exposure | attorney_review | ✅ attorney_review | 100% | 23 | 1 | 100% | 100% | 0 | $0.1922 |
| forgot_prior_claim | attorney_review | ✅ attorney_review | 95% | 24 | 1 | 90% | 100% | 0 | $0.1806 |
| new_condition_during_prep | attorney_review | ✅ attorney_review | 95% | 21 | 1 | 100% | 100% | 0 | $0.2376 |
| not_a_veteran | closed | ✅ closed | 100% | 1 | 0 | – | – | 0 | $0.0063 |
| oth_one_of_two | attorney_review | ✅ attorney_review | 100% | 20 | 1 | 100% | 100% | 0 | $0.1638 |
| oth_only_period | needs_human | ✅ needs_human | 100% | 3 | 0 | – | – | 0 | $0.0121 |
| prior_attorney | attorney_review | ✅ attorney_review | 100% | 23 | 3 | 100% | 100% | 0 | $0.1834 |
| rated_100 | closed | ✅ closed | 100% | 5 | 0 | – | – | 0 | $0.0155 |
| recent_decision | attorney_review | ✅ attorney_review | 100% | 23 | 2 | 100% | 100% | 0 | $0.1657 |
| reserve_not_in_records | attorney_review | ✅ attorney_review | 100% | 19 | 1 | 100% | 100% | 0 | $0.1680 |
| two_service_periods | attorney_review | ✅ attorney_review | 95% | 21 | 1 | 100% | 100% | 0 | $0.1679 |
| withdraws_mid_intake | needs_human | ✅ needs_human | 100% | 4 | 0 | – | – | 0 | $0.0192 |

## Critical errors

None.

## Field mismatches

- **cfile / crisis_backstop** `spouse_name` (wrong, from veteran, chat 17:00 UTC): expected `Diane Kowalski`, got `Diane`
- **cfile / forgot_prior_claim** `spouse_name` (wrong, from veteran, chat 17:00 UTC): expected `Daniel Okafor`, got `Daniel`
- **cfile / new_condition_during_prep** `spouse_name` (wrong, from veteran, chat 17:00 UTC): expected `Carmen Ortega`, got `Carmen`
- **cfile / two_service_periods** `spouse_name` (wrong, from veteran, chat 17:00 UTC): expected `Joan Whitaker`, got `Joan`
