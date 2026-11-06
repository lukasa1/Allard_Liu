# baseline_clean (cfile)

A straightforward case. One period of honorable Army service, never filed, one condition.

Behaviours: none

## Conversation

**Agent**: [intake] Welcome, and thank you for reaching out to our firm. To start, have you served in the U.S. military, whether on active duty, in the Reserves, or in the National Guard?

**Veteran**: Yes, I served in the Army on active duty from June 2004 to May 2010. I was honorably discharged.

**Agent**: [intake] Thank you, that helps us a great deal. Did you serve in any other period, such as the Reserves or National Guard, or any other branch? And have you ever filed a claim with the VA before, and if so, do you know your current disability rating?

**Veteran**: No, just the Army active duty from 2004 to 2010. I've never filed a claim with the VA before, so I don't have a rating.

**Agent**: [intake] Thank you, that is very helpful. One last screening question: has an attorney or law firm ever helped you with a VA claim before? A VSO like the DAV or VFW doesn't count.

**Veteran**: No, I've never had an attorney or law firm help with a VA claim. I've only ever dealt with the VA directly, so this is all new to me.

**Agent**: [intake] Thank you, that's everything I need for the screening. You're a good fit for us to move forward. I've opened a secure form for your identity and contact details, so please fill it in there rather than here. Once it's submitted, I'll prepare your VA power of attorney form for you to review.

_App_: [veteran fills the secure form: address.city, address.line1, address.line2, address.state, address.zip, branch, date_of_birth, email, first_name, last_name, middle_initial, phone, service_number, ssn, va_file_number; errors: none]

**Agent**: [intake] Thank you, Jordan. We received your details safely. Before I prepare your power of attorney form, I need two choices from you, in your own words:
1. May the attorney see VA records about treatment for drug or alcohol use, HIV, or sickle cell anemia?
2. May the attorney update your home address with VA if it changes?

**Veteran**: Yes to both. The attorney can see those records if needed, and yes, they can update my address with VA if I move.

**Agent**: [intake] Thank you, Jordan. Your power of attorney form (VA Form 21-22a) is ready on your screen with your choices included. Please look it over. If everything is correct, tell me "yes" and I'll open the signature card for you. If something needs fixing, tell me what and I'll correct it.

**Veteran**: Yes, it looks right to me. Go ahead and open the signature card.

**Agent**: [intake] Thank you, Jordan. The signature pad is open on your screen. Please draw or type your signature there and save it. Once it's saved, I'll bring up the final signing step.

_App_: [veteran draws and saves a signature]

**Agent**: [intake] Thank you, Jordan. Your signature is saved. The Sign card for your power of attorney form is now on your screen. Please review it once more, and when you're ready, click to sign it there.

_App_: [veteran clicks Sign on the 21-22a]

**Agent**: [intake] Thank you, Jordan. Your power of attorney form is signed. Next is the fee agreement, which is now on your screen. Here is the plain version: the fee is 30% of any past-due benefits, and only if VA awards them, so there is no win, no fee. When VA pays the attorney directly at 20% or less, VA withholds the fee. Above 20%, you pay the firm directly. Costs are asked first, you can end the representation at any time, and nothing is guaranteed. Please check the preview. If it looks right, tell me "yes" and I'll open the signature card for you.

**Veteran**: Yes, the fee agreement looks good to me. Go ahead and open the signature card for it.

**Agent**: [intake] Thank you, Jordan. The fee agreement signature card is on your screen now. Please review it once more and click to sign when you're ready.

_App_: [veteran clicks Sign on the fee_agreement]

**Agent**: [intake] Thank you, Jordan. Both of your forms are signed: the power of attorney form and the fee agreement. The attorney is now reviewing them. Once the attorney countersigns, I'll file them with VA right away. If you have any questions in the meantime, just send them here.

_App_: [simulated attorney countersigns both documents]

**Agent**: [intake] Jordan, your power of attorney form (21-22a) and your fee agreement are both filed. The fee agreement also went to VA's Office of General Counsel. We also filed an intent to file with VA. It protects your potential start date of November 3, 2026, and it runs for one year, through November 3, 2027. This holds your place while your claim is prepared. It does not promise any outcome. The firm is now requesting your VA claims file, and we'll be in touch if we need anything else from you.

**Agent**: [orchestrator] Good news, Jordan: your VA forms are filed. Your 21-22a and fee agreement have gone in, and your intent to file is on record with a protected date of November 3, 2026. We have started the review of your file now. We will be in touch if we need anything from you.

**Agent**: [intake] Thank you, Jordan. Two quick questions for you:
1. Is this a claim for death benefits for a family member, such as DIC or accrued benefits? A yes or no is fine.
2. Are you currently earning more than $1,600 a month from work?

**Veteran**: No, this isn't a death benefits claim. And yes, I'm working right now and earning more than $1,600 a month.

**Agent**: [intake] Thank you, Jordan. That's helpful. Next question: do you currently receive Social Security benefits? A yes or no is fine.

**Veteran**: No, I don't receive Social Security benefits.

**Agent**: [intake] Thank you, Jordan. That's noted. Two more quick questions:
1. We work with a group of partner law firms. If one of our attorneys can't help you, may we share your contact information with a partner firm? A yes or no is fine.
2. Did you retire from the military?

**Veteran**: Yes, that's fine, you can share my contact info with a partner firm. And no, I didn't retire. I got out in 2010 after my active duty ended.

**Agent**: [intake] Thank you, Jordan. That's noted. Two more quick questions:
1. Would you like to talk with our Social Security benefits department as well? A yes or no is fine.
2. Were you exposed to anything like Agent Orange, burn pits, Camp Lejeune water, radiation or Gulf War hazards? List any that apply, or say none.

**Veteran**: No, I don't need to talk to the Social Security folks, I don't get SSA benefits. For exposures, burn pits is the one that applies. I was at Camp Taji in Iraq.

**Agent**: [intake] Thank you, Jordan. That's noted: burn pits from your time at Camp Taji, and no need to talk with the Social Security department. Two more questions:
1. Which medical conditions would you like our attorneys to help you with?
2. Are there any other medical conditions you're dealing with, service-connected or not, such as mental health, sleep apnea, heart problems, high blood pressure, cancer or diabetes? Say none if there aren't.

**Veteran**: Tinnitus is the one I want help with. It's constant ringing in both ears. And no, I don't have any other conditions I'm dealing with.

**Agent**: [intake] Thank you, Jordan. I've noted tinnitus as the condition you want help with, and that you have no other conditions. Two quick questions:
1. Is there any ongoing litigation about burn pit exposure? If there is, would you like an attorney to contact you about it? A yes or no is fine.
2. What is your marital status: single, married, divorced, separated, or widowed?

**Veteran**: No, I'm not in any litigation about burn pits. And I'm single.

**Agent**: [intake] Thank you, Jordan. That's noted. Two more questions:
1. Do you have any children under 18? A yes or no is fine.
2. Who is your next of kin? Please give their name, their relationship to you, and a phone number.

**Veteran**: No, I don't have any kids under 18. My next of kin is my mom, Maria Reyes. Her number is 262-555-0177.

**Agent**: [intake] Thank you, Jordan. That's noted, and thank you for sharing your mom's contact information. Last one for this part: how did you hear about us?

**Veteran**: A friend recommended you guys.

**Agent**: [intake] Thank you, Jordan, and thanks for letting us know about the referral. Next, I'd like to learn more about your tinnitus so the attorney has the full picture. 1. What symptoms do you have from your tinnitus? 2. At their worst, how bad do the symptoms get? Describe a flare-up or a bad day. 3. When did the tinnitus start: during service, right after, or gradually over time?

**Veteran**: It's a constant high-pitched ringing in both ears. On bad days it's so loud I can't concentrate or fall asleep. It started during service, after a convoy hit an IED near Baghdad in 2007.

**Agent**: [intake] Thank you, Jordan. That gives the attorney a clear picture of how it started. Two more questions about the ringing:
1. How often do you have it: daily, weekly or monthly?
2. Has the ringing continued since service, and has it gotten better or worse over time?

**Veteran**: Every day. It never went away after I got out, and it's gotten a little worse.

**Agent**: [intake] Thank you, Jordan. That helps the attorney understand how often it happens and how it has changed. Two more questions about when it started:
1. Where were you stationed or deployed when the ringing began?
2. At that time, were you on a base, in the field, in a vehicle, on a ship, or in a combat zone?

**Veteran**: I was at Camp Taji, Iraq when it started. And I was in a vehicle, on convoys through a combat zone.

**Agent**: [intake] Thank you, Jordan. That's very helpful, and I'm sorry the convoys were so hard. Two more questions about that time:
1. What were the conditions around you when the ringing began, such as noise, cramped spaces, extreme weather, or hazardous materials?
2. Did you report the ringing or get any treatment for it at the time? If not, what kept you from doing so?

**Veteran**: Constant engine noise, gunfire and explosions, usually without good hearing protection. And no, I never reported it or got treatment at the time. Everyone had ringing ears and I didn't want to be pulled off missions.

**Agent**: [intake] Thank you, Jordan. That's very helpful, and I understand why you didn't want to be pulled off missions. Two questions about work:
1. How does your tinnitus affect your ability to work?
2. Have you missed work, or been less productive, because of it?

**Veteran**: I drive a delivery truck now and it's hard to hear dispatch over the ringing. And yeah, I've left early a few times when it gets really bad, maybe once a month.

**Agent**: [intake] Thank you, Jordan. That's very helpful, and I'm sorry the delivery work has been hard with the ringing. Three more questions about the tinnitus:
1. How does it affect your daily activities, relationships or quality of life?
2. For your tinnitus, how were things before your military service compared to now?
3. Is there anything else you want the VA to know about your tinnitus?

**Veteran**: I avoid restaurants and parties because it's too hard to hear anything over the ringing. I also sleep with a fan on just to drown it out. Before the Army I had no hearing problems at all. And no, I think that covers it.

**Agent**: [intake] Thank you, Jordan. Your answers about the tinnitus give the attorney a clear picture, including how it affects work, sleep and time with people. The attorney reviews your file next. If anything else comes up, a person on the team will follow up with you.

## Decisions and moves

- #2 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 1: screen the veteran (every screening field answered or unknown, stop rules checked), get the 21-22a and fee agreement signed, file the 21-22a and intent to file, and fax the fee agreement. Send a one-line welcome to the veteran."}
- #4 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #5 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #8 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #9 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #12 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #13 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #15 `stage_changed` by derive: {"from": 1, "to": 2, "actor": "derive", "reason": "exit criteria met"}
- #17 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #20 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #23 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #24 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #27 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #32 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #36 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #37 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": "waiting_on_attorney", "actor": "derive", "reason": null}
- #41 `side_state_changed` by derive: {"from": "waiting_on_attorney", "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #43 `stage_changed` by derive: {"from": 2, "to": 3, "actor": "derive", "reason": "exit criteria met"}
- #45 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": "waiting_on_va", "actor": "derive", "reason": null}
- #46 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Pass 1 complete: 21-22a filed (VA-WZZNZXJZAO), fee agreement faxed to VA OGC (FAX-JDLGMYWCZY), intent to file filed (VA-GZGMIPBTJG, protected date 2026-11-03, expires 2027-11-03)", "wrote": ["documents.21-22a.filed", "documents.fee_agreement.faxed_ogc", "f
- #47 `stage_changed` by handoff: {"from": 3, "to": 4, "actor": "handoff", "reason": "Pull and read the veteran's C-file, prefill the intake answers it settles, and write and verify the face note."}
- #48 `handoff` by orchestrator: {"to": "claims_prep", "goal": "Pull and read the veteran's C-file, prefill the intake answers it settles, and write and verify the face note."}
- #49 `side_state_changed` by derive: {"from": "waiting_on_va", "to": null, "actor": "derive", "reason": null}
- #52 `side_state_changed` by derive: {"from": null, "to": "waiting_on_va", "actor": "derive", "reason": null}
- #53 `subagent_result` by claims_prep: {"result": {"agent": "claims_prep", "finished": "C-file pulled and read (D1 DD-214, D2 firm 21-22a, D3 STRs); 5 facts recorded; face note rendered and verify passed with no uncertain lines; prefill run (mos written, service_periods kept).", "wrote": ["F1 dob 1972-11-20 (D1 p.1)", "F2 service_period 
- #54 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 2 (close-gaps): ask only the fields still missing, which are rating percentage, service-connected conditions, prior claims, and confirmation of no prior representation, since the C-file does not settle them. Then run the narrative prompts."}
- #55 `side_state_changed` by derive: {"from": "waiting_on_va", "to": null, "actor": "derive", "reason": null}
- #57 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #58 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #61 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #62 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #65 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #66 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #69 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #70 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #73 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #74 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #77 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #78 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #81 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #82 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #85 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #86 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #89 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #90 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #93 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #94 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #97 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #98 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #101 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #102 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #105 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #106 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #109 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #110 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #112 `stage_changed` by derive: {"from": 4, "to": 5, "actor": "derive", "reason": "exit criteria met"}
- #114 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Pass 2 close-gaps: tinnitus narrative prompts h14-h16 recorded in the veteran's words; checklist empty; case at stage 5, ready for attorney review.", "wrote": ["narrative:tinnitus:h14", "narrative:tinnitus:h15", "narrative:tinnitus:h16"], "needs": ["Person
- #115 `task_created` by orchestrator: {"text": "Confirm the veteran's service-connected rating percentage (rating_pct) before attorney review. It was never asked or recorded. The face note shows 'SC (0%)' with no rating decision in the C-file, so ask the veteran or verify it from the C-file, then update the face note."}

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
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "prior_claim_probe": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "prior_attorney": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "first_name": {
  "value": "Jordan",
  "source": "secure form",
  "unknown": false
 },
 "last_name": {
  "value": "Reyes",
  "source": "secure form",
  "unknown": false
 },
 "street": {
  "value": "*** *** **reet",
  "source": "secure form",
  "unknown": false
 },
 "city": {
  "value": "Racine",
  "source": "secure form",
  "unknown": false
 },
 "state": {
  "value": "WI",
  "source": "secure form",
  "unknown": false
 },
 "zip": {
  "value": "*3403",
  "source": "secure form",
  "unknown": false
 },
 "cell_phone": {
  "value": "******0142",
  "source": "secure form",
  "unknown": false
 },
 "email": {
  "value": "j***@example.com",
  "source": "secure form",
  "unknown": false
 },
 "mos": {
  "value": [
   "88M Motor Transport Operator"
  ],
  "source": "C-file p. 1",
  "unknown": false
 },
 "dic_claim": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "earning_over_1600": {
  "value": true,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "receives_ssa": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "partner_share_consent": {
  "value": true,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "retired": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "exposures": {
  "value": [
   "burn pits"
  ],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "ssa_interest": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "claim_conditions": {
  "value": [
   "tinnitus"
  ],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "other_conditions": {
  "value": [],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "litigation_contact": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "marital_status": {
  "value": "single",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "children_under_18": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "next_of_kin": {
  "value": "Maria Reyes (mom), 262-555-0177",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "heard_about": {
  "value": "A friend recommended you guys.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h02": {
  "value": "It's a constant high-pitched ringing in both ears.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h03": {
  "value": "On bad days it's so loud I can't concentrate or fall asleep.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h04": {
  "value": "It started during service, after a convoy hit an IED near Baghdad in 2007.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h10": {
  "value": "It started during service, after a convoy hit an IED near Baghdad in 2007.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h05": {
  "value": "Every day.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h06": {
  "value": "It never went away after I got out, and it's gotten a little worse.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h07": {
  "value": "I was at Camp Taji, Iraq when it started.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h08": {
  "value": "I was in a vehicle, on convoys through a combat zone.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h09": {
  "value": "Constant engine noise, gunfire and explosions, usually without good hearing protection.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h11": {
  "value": "I never reported it or got treatment at the time. Everyone had ringing ears and I didn't want to be pulled off missions.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h12": {
  "value": "I drive a delivery truck now and it's hard to hear dispatch over the ringing.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h13": {
  "value": "I've left early a few times when it gets really bad, maybe once a month.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h14": {
  "value": "I avoid restaurants and parties because it's too hard to hear anything over the ringing. I also sleep with a fan on just to drown it out.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h15": {
  "value": "Before the Army I had no hearing problems at all.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h16": {
  "value": "No, I think that covers it.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 }
}
```

## Face note

```
FA 30%; No prior rep  [firm record; none in the C-file]
********************************************
DOB: 11/20/72  [p. 1]
Service Era: Gulf War  [p. 1]
Army 06/04 - 05/10, Honorable  [p. 1]
MOS: 88M Motor Transport Operator  [p. 1]
SC at time of signing Law Firm - 0% (no rating decision in the C-file)  [none in the C-file]
============================================
SC (0%)| none  [none in the C-file]
============================================
Law Firm Filed 0966 Intent on 11/03/26  [firm record]
--------------------------------------------
```

## Staff tasks

- [deadline] Send the fee agreement to VA OGC within 30 days of signing (38 CFR 14.636(g)) (due 2026-12-03)
- [staff] Confirm the veteran's service-connected rating percentage (rating_pct) before attorney review. It was never asked or recorded. The face note shows 'SC (0%)' with no rating decision in the C-file, so ask the veteran or verify it from the C-file, then update the face note.

## Score

```json
{
 "persona_id": "baseline_clean",
 "condition": "cfile",
 "expected_end": "attorney_review",
 "end_state": "attorney_review",
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
   "source": "veteran, chat 17:00 UTC; veteran, chat 17:00 UTC"
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
   "got": false,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
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
   "got": false,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "earning_over_1600",
   "expected": true,
   "got": true,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "receives_ssa",
   "expected": false,
   "got": false,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "ssa_interest",
   "expected": false,
   "got": false,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "partner_share_consent",
   "expected": true,
   "got": true,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "retired",
   "expected": false,
   "got": false,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "litigation_contact",
   "expected": false,
   "got": false,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "marital_status",
   "expected": "single",
   "got": "single",
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
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
   "got": false,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "next_of_kin",
   "expected": "Maria Reyes, mother, 262-555-0177",
   "got": "Maria Reyes (mom), 262-555-0177",
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "heard_about",
   "expected": "a friend",
   "got": "A friend recommended you guys.",
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
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
   "got": [
    "tinnitus"
   ],
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "other_conditions",
   "expected": [],
   "got": [],
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "mos",
   "expected": [
    "88m motor transport operator"
   ],
   "got": [
    "88m motor transport operator"
   ],
   "status": "correct",
   "source": "C-file p. 1"
  },
  {
   "field": "exposures",
   "expected": [
    "burn pits"
   ],
   "got": [
    "burn pits"
   ],
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
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
 "structured_questions": 20,
 "narrative_answers": 15,
 "clarifications": 0,
 "veteran_messages": 20,
 "cfile_prefilled": 1,
 "prefill_share": 0.047619047619047616,
 "turns_to_signed_poa": 8,
 "fee_expected": 30,
 "fee_got": 30,
 "kb_calls": 0,
 "kb_sourced": 0,
 "resumed_after": null,
 "ask_answer": {},
 "scripted_sent": null,
 "untested": false,
 "handoffs": [
  "intake",
  "claims_prep",
  "intake"
 ],
 "refused": {},
 "flag_decisions": [],
 "flag_decision_expected": null,
 "flag_decision_correct": null,
 "facenote_line_accuracy": 1.0,
 "facenote_lines": [
  8,
  8
 ],
 "facenote_checks": {
  "dob": true,
  "service_periods": true,
  "mos": true,
  "combined_rating": true,
  "sc_conditions": true,
  "decisions": true,
  "prior_reps": true
 },
 "verify_passed": true,
 "uncertain_lines": 0,
 "citation_precision": 1.0,
 "facts": 5,
 "by_agent": {
  "orchestrator": {
   "calls": 12,
   "input_tokens": 81873,
   "output_tokens": 4091,
   "cost_usd": 0.0102328,
   "latency_s": 27.381
  },
  "intake": {
   "calls": 104,
   "input_tokens": 886626,
   "output_tokens": 45250,
   "cost_usd": 0.11128759999999999,
   "latency_s": 290.5130000000001
  },
  "claims_prep": {
   "calls": 10,
   "input_tokens": 124678,
   "output_tokens": 5456,
   "cost_usd": 0.015195799999999999,
   "latency_s": 30.820999999999998
  },
  "simulator": {
   "calls": 20,
   "input_tokens": 0,
   "output_tokens": 0,
   "cost_usd": 0.009576600000000001,
   "latency_s": 0.0
  }
 },
 "cost_usd": 0.1462928,
 "model_failures": 0
}
```
