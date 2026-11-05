# dob_swapped (cfile)

Types their date of birth into the secure form with the day and month swapped (07/04 instead of 04/07). The intake form and the 21-22a carry the wrong DOB; the face-note pipeline must flag the mismatch against the C-file's DD-214.

Behaviours: none

## Conversation

**Agent**: [intake] Welcome, and thank you for reaching out. To start, have you served in the U.S. military, whether on active duty, in the Reserves, or in the National Guard?

**Veteran**: Yes, I served in the Air Force on active duty from 2007 to 2015. I was honorably discharged.

**Agent**: [intake] Thank you, that helps. Did you serve in any other period, such as the Reserves, the National Guard, or another branch? And have you ever filed a claim with VA or received a disability rating? If you're not sure about the rating, just say so.

**Veteran**: No, just the active duty Air Force stint, 2007 to 2015. I've never filed a claim with VA and I don't have a disability rating.

**Agent**: [intake] Thank you, that's very helpful. One last question: has an attorney or law firm ever helped you with a VA claim before? A VSO like the DAV or VFW doesn't count.

**Veteran**: No, I've never had an attorney or law firm help with a VA claim. I haven't worked with a VSO on one either.

**Agent**: [intake] Thank you, that's everything I need for the screening. Next, I've opened a secure form for your identity and contact details. It's needed to prepare the VA form that appoints our attorney. Please don't send those details in this chat; use the secure form instead. Once you submit it, I'll show you the forms to review.

_App_: [veteran fills the secure form: address.city, address.line1, address.line2, address.state, address.zip, branch, date_of_birth, email, first_name, last_name, middle_initial, phone, service_number, ssn, va_file_number; errors: none]

**Agent**: [intake] Thank you, Tanya. Your details came through safely. Before I prepare the form that appoints our attorney, I need two choices from you, in your own words:

1. May the attorney see VA records about treatment for drug or alcohol use, HIV, or sickle cell anemia? (yes or no)
2. May the attorney update your address with VA if needed? (yes or no)

**Veteran**: Yes to both. The attorney can see those records if needed, and yes, they can update my address with VA.

**Agent**: [intake] Thank you, Tanya. I've filled in your VA form 21-22a with your two choices, and the preview is now on your screen. Please check the name, address and the two yes answers. Tell me if anything is wrong, or say yes if it all looks right and I'll open the signature card for you.

**Veteran**: Yes, that all looks right to me. Name, address, and both yes answers are correct.

**Agent**: [intake] Thank you, Tanya. The signature pad is open on your screen. Please draw or type your name and save it yourself. Once it's saved, I'll bring up the card for you to review and sign the form.

_App_: [veteran draws and saves a signature]

**Agent**: [intake] Thank you, Tanya. Your signature is saved. The form to appoint our attorney is now on your screen. Please review it, and if it's right, sign it on the card. Once it's signed, I'll bring up the fee agreement for you to review.

_App_: [veteran clicks Sign on the 21-22a]

**Agent**: [intake] Thank you, Tanya. Your 21-22a is signed, so the next step is the fee agreement, which is now on your screen. In plain words: the fee is 30% of any past-due benefits, and only if VA awards them. If VA awards nothing, there is no fee. You can end our work together at any time, and nothing is guaranteed. Please check the preview. If you agree to these terms, say yes and I'll open the signature card for you.

**Veteran**: Yes, I agree to the fee agreement terms. 30% of past-due benefits only if VA awards them, no fee if nothing is awarded, and I can end things anytime. Go ahead and open the signature card.

**Agent**: [intake] Thank you, Tanya. The fee agreement signature card is now on your screen. Please review it, and if it's right, sign it on the card. Once both forms are signed, the attorney will review them, and I'll file as soon as they countersign.

_App_: [veteran clicks Sign on the fee_agreement]

**Agent**: [intake] Thank you, Tanya. Both of your forms are now signed. The attorney is reviewing them, and I'll file as soon as they countersign. You can message me anytime in the meantime.

_App_: [simulated attorney countersigns both documents]

**Agent**: [intake] Tanya, good news: the attorney has countersigned both of your forms. We have filed your VA form 21-22a, which appoints our attorney, and faxed the fee agreement to VA's Office of General Counsel. We also filed an intent to file for you, dated November 3, 2026. That date is held for you until November 3, 2027, while your claim is prepared. This doesn't guarantee any outcome. Next, we will request your VA claims file. You can message me anytime.

**Agent**: [orchestrator] Your 21-22a and fee agreement are filed, and your intent to file is in place. We're now starting the review of your VA file.

**Agent**: [intake] Thank you, Tanya. Two quick questions to help us finish your file:

1. Have you ever received a VA rating decision, such as a percentage for a service-connected condition? If you know the percentage, please tell me. If you're not sure, just say so.
2. Is this claim for death benefits for a family member, sometimes called DIC or accrued benefits? (yes or no)

**Veteran**: No, I've never had a VA rating decision, so no percentage to give you. And no, this isn't a death benefits claim. It's for my own hearing.

**Agent**: [intake] Thank you, Tanya. That helps. Two more quick questions:

1. Are you currently earning more than $1,600 a month from work?
2. Do you currently receive Social Security benefits?

A simple yes or no for each is fine.

**Veteran**: Yes, I'm earning more than $1,600 a month from work. And no, I don't receive Social Security benefits.

**Agent**: [intake] Thank you, Tanya. Two more quick questions: did you retire from the military? And what's your marital status: single, married, divorced, separated, or widowed?

**Veteran**: No, I didn't retire. I got out in 2015 after my active duty stint. I'm single.

**Agent**: [intake] Thank you, Tanya. Do you have any children under 18? And who is your next of kin? Please give me their name, their relationship to you, and a phone number.

**Veteran**: No, I don't have any children under 18. My next of kin is my father, Carl Brooks. His number is 608-555-0140.

**Agent**: [intake] Thank you, Tanya. I've saved your father as your next of kin. Two more quick questions:

1. Would you like to talk with our Social Security benefits department as well?
2. We work with a group of partner law firms. If one of our attorneys can't help, may we share your contact information with a partner firm? A yes or no is fine.

**Veteran**: Hmm, I don't receive Social Security benefits, so I'm not sure I need that. And yes, you can share my contact info with a partner firm if needed.

**Agent**: [intake] Thank you, Tanya. I've noted that we can share your contact information with a partner firm. Two quick questions:

1. Would you like to talk with our Social Security benefits department as well? Even if you don't receive benefits now, a yes or no is fine.
2. Were you exposed to anything like Agent Orange, burn pits, Camp Lejeune water, radiation or Gulf War hazards? List any that apply, or just say none.

**Veteran**: No, I don't think I need the Social Security department since I don't get those benefits. And yes, I was exposed to burn pits when I was deployed.

**Agent**: [intake] Thank you, Tanya. That helps. Two questions:

1. Which medical conditions would you like our attorneys to help you with?
2. Are there any other conditions you're dealing with, service-connected or not, such as mental health, sleep apnea, heart problems, high blood pressure, cancer or diabetes? Say none if there aren't any.

**Veteran**: The one I want help with is my hearing. Bilateral hearing loss, both ears. And no other conditions I know of, so none besides that.

**Agent**: [intake] Thank you, Tanya. That helps. Two quick questions:

1. If there's ongoing litigation about your burn pit exposure, would you like an attorney to contact you about it? A yes or no is fine.
2. Last one for this part: how did you hear about us?

**Veteran**: No, I don't have any litigation going on, so no need for that. I heard about you guys from a friend.

**Agent**: [intake] Thank you, Tanya. Next, a few questions about your hearing.

1. What symptoms do you have from your bilateral hearing loss?
2. At their worst, how bad do the symptoms get? Describe a flare-up or a bad day.
3. When did the symptoms start: during service, right after, or gradually over time?

**Veteran**: Sure. I can't follow conversations in noisy rooms and I turn the TV way up. In a crowded room I just nod along because I can't make out what people say. On a bad day it's pretty much every day, and it's slowly gotten worse since I got out. It started gradually during service, around my deployment in 2010.

**Agent**: [intake] Thank you, Tanya. That helps me understand what you've been going through. Next, a few questions:

1. Where were you stationed or deployed when your hearing started to change?
2. When it began, were you on a ship, a base, in the field, in a vehicle, or in a combat zone?
3. What were the conditions around you then, like noise, cramped spaces, extreme weather or hazardous materials?

**Veteran**: I was at Bagram Airfield in Afghanistan, around my deployment in 2010. I was on the flight line, loading munitions next to running jet engines all day, and we didn't always have good ear protection.

**Agent**: [intake] Thank you, Tanya. That gives me a clear picture of the flight line. Two more questions:

1. What event, injury or exposure in service do you think led to your hearing loss? What happened?
2. Did you report your hearing loss or get treatment for it at the time? Why or why not?

**Veteran**: I think it was the constant jet noise on the flight line at Bagram. We were loading munitions right next to running jets for hours, and we didn't always have good ear protection. And no, I never reported it or got treatment at the time. I just figured everyone on the flight line had bad hearing.

**Agent**: [intake] Thank you, Tanya. That helps me understand how the flight line affected you. Two questions about work:

1. How does your hearing loss affect your ability to work?
2. Have you missed work, or been less productive, because of it?

**Veteran**: I work at a bank, and phone calls with customers are hard. I don't miss work, but I make mistakes when I mishear numbers.

**Agent**: [intake] Thank you, Tanya. That helps me see how the hearing loss affects your work. Two more questions about your hearing:

1. How does your bilateral hearing loss affect your daily activities, relationships or quality of life?
2. For your bilateral hearing loss, how were things before your military service compared to now?

**Veteran**: I've stopped going to family dinners at restaurants because I can't keep up with the conversation. And my hearing was normal before the Air Force. It's only gotten worse since I got out.

**Agent**: [intake] Thank you, Tanya. That helps me understand how the hearing loss affects your family life and your work. One last question about your hearing: is there anything else you want the VA to know about your bilateral hearing loss?

**Veteran**: Not really, I think I've covered it. It's been getting harder to hear over the past several years, and I'd like the VA to see that it started in service.

**Agent**: [intake] Thank you, Tanya. That gives the VA a clear picture of your hearing loss and when it started. Your file is now complete on our side, and an attorney on the team will review it next.

## Decisions and moves

- #2 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 1 at stage 1: screen the veteran (every screening field answered or unknown, stop rules checked), sign the 21-22a and fee agreement, file the 21-22a and intent to file, and fax the fee agreement. Send a one-line welcome to the veteran."}
- #4 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #5 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #8 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #9 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #12 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #13 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #15 `stage_changed` by derive: {"from": 1, "to": 2, "actor": "derive", "reason": "exit criteria met"}
- #18 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #22 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #25 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #26 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #29 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #34 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #37 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #38 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": "waiting_on_attorney", "actor": "derive", "reason": null}
- #41 `side_state_changed` by derive: {"from": "waiting_on_attorney", "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #43 `stage_changed` by derive: {"from": 2, "to": 3, "actor": "derive", "reason": "exit criteria met"}
- #45 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": "waiting_on_va", "actor": "derive", "reason": null}
- #46 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Pass 1 complete: 21-22a filed, fee agreement faxed to VA OGC, intent to file filed (ITF date 2026-11-03, expires 2027-11-03).", "wrote": ["21-22a filed (VA-KDLIVFZXGD)", "fee_agreement faxed to OGC (FAX-WITUKHNPVW)", "itf filed (VA-ZNWCBPLENS)"], "needs": 
- #47 `stage_changed` by handoff: {"from": 3, "to": 4, "actor": "handoff", "reason": "Pull and read the veteran's C-file, prefill the intake answers it settles, and write and verify the face note."}
- #48 `handoff` by orchestrator: {"to": "claims_prep", "goal": "Pull and read the veteran's C-file, prefill the intake answers it settles, and write and verify the face note."}
- #49 `side_state_changed` by derive: {"from": "waiting_on_va", "to": null, "actor": "derive", "reason": null}
- #52 `side_state_changed` by derive: {"from": null, "to": "waiting_on_va", "actor": "derive", "reason": null}
- #53 `subagent_result` by claims_prep: {"result": {"agent": "claims_prep", "finished": "Read D1 (DD-214 p.1) and D2 (firm's 21-22a p.2); recorded DOB, service period, discharge, MOS and the prior-rep form; rendered and verified the face note (passed, 0 uncertain); ran prefill.", "wrote": ["dob", "service_period", "discharge", "mos", "pri
- #54 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 2 (close gaps): ask the veteran only the pass-2 fields still missing (filed_before, rating_pct, sc_conditions, prior_attorney and prior_attorney_name, plus any others unfilled), confirm whether any VA rating exists, then ask the narrative prompts. Do not re-ask the DOB
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
- #114 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Pass 2 complete: all pass-2 gaps closed, checklist empty, case at stage 5 (ready for attorney review).", "wrote": ["narrative:bilateral hearing loss:h16"], "needs": ["Attorney review of the file (stage 5)", "Staff to resolve the DOB mismatch and file a cor

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
    "branch": "air force",
    "component": "active",
    "start": "2007-01",
    "end": "2015-01",
    "discharge": "honorable"
   }
  ],
  "source": "veteran, chat 17:00 UTC; months: DD-214, C-file p. 1",
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
  "value": "Tanya",
  "source": "secure form",
  "unknown": false
 },
 "last_name": {
  "value": "Brooks",
  "source": "secure form",
  "unknown": false
 },
 "street": {
  "value": "**** **** ***** Road",
  "source": "secure form",
  "unknown": false
 },
 "city": {
  "value": "Madison",
  "source": "secure form",
  "unknown": false
 },
 "state": {
  "value": "WI",
  "source": "secure form",
  "unknown": false
 },
 "zip": {
  "value": "*3704",
  "source": "secure form",
  "unknown": false
 },
 "cell_phone": {
  "value": "******0182",
  "source": "secure form",
  "unknown": false
 },
 "email": {
  "value": "t***@example.com",
  "source": "secure form",
  "unknown": false
 },
 "mos": {
  "value": [
   "Aircraft Armament Systems"
  ],
  "source": "C-file p. 1",
  "unknown": false
 },
 "rating_pct": {
  "value": 0,
  "source": "veteran, chat 17:00 UTC",
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
 "retired": {
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
  "value": "{'name': 'Carl Brooks', 'relationship': 'father', 'phone': '608-555-0140'}",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "partner_share_consent": {
  "value": true,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "ssa_interest": {
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
 "claim_conditions": {
  "value": [
   "bilateral hearing loss"
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
 "heard_about": {
  "value": "I heard about you guys from a friend.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h02": {
  "value": "I can't follow conversations in noisy rooms and I turn the TV way up. In a crowded room I just nod along because I can't make out what people say.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h03": {
  "value": "On a bad day it's pretty much every day, and it's slowly gotten worse since I got out.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h04": {
  "value": "It started gradually during service, around my deployment in 2010.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h05": {
  "value": "On a bad day it's pretty much every day.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h06": {
  "value": "It's slowly gotten worse since I got out.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h07": {
  "value": "I was at Bagram Airfield in Afghanistan, around my deployment in 2010.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h08": {
  "value": "I was on the flight line, loading munitions next to running jet engines all day.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h09": {
  "value": "We didn't always have good ear protection.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h10": {
  "value": "I think it was the constant jet noise on the flight line at Bagram. We were loading munitions right next to running jets for hours, and we didn't always have good ear protection.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h11": {
  "value": "And no, I never reported it or got treatment at the time. I just figured everyone on the flight line had bad hearing.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h12": {
  "value": "I work at a bank, and phone calls with customers are hard.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h13": {
  "value": "I don't miss work, but I make mistakes when I mishear numbers.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h14": {
  "value": "I've stopped going to family dinners at restaurants because I can't keep up with the conversation.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h15": {
  "value": "my hearing was normal before the Air Force. It's only gotten worse since I got out.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:bilateral hearing loss:h16": {
  "value": "Not really, I think I've covered it. It's been getting harder to hear over the past several years, and I'd like the VA to see that it started in service.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 }
}
```

## Face note

```
FA 30%; No prior rep  [firm record; none in the C-file]
********************************************
DOB: 04/07/85  [p. 1]
Service Era: Gulf War  [p. 1]
Air Force 01/07 - 01/15, Honorable  [p. 1]
MOS: Aircraft Armament Systems  [p. 1]
SC at time of signing Law Firm - 0% (no rating decision in the C-file)  [none in the C-file]
============================================
SC (0%)| none  [none in the C-file]
============================================
Law Firm Filed 0966 Intent on 11/03/26  [firm record]
--------------------------------------------
```

## Staff tasks

- [deadline] Send the fee agreement to VA OGC within 30 days of signing (38 CFR 14.636(g)) (due 2026-12-03)
- [staff] DOB mismatch: the intake / 21-22a date of birth differs from the DD-214 (the day and month look swapped). File a corrected 21-22a.

## Score

```json
{
 "persona_id": "dob_swapped",
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
   "got": 0,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
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
   "expected": "Carl Brooks, father, 608-555-0140",
   "got": "{'name': 'Carl Brooks', 'relationship': 'father', 'phone': '608-555-0140'}",
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "heard_about",
   "expected": "a friend",
   "got": "I heard about you guys from a friend.",
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
    "bilateral hearing loss"
   ],
   "got": [
    "bilateral hearing loss"
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
    "aircraft armament systems"
   ],
   "got": [
    "aircraft armament systems"
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
    "('air force', 'active', 'honorable', '2007-01', '2015-01')"
   ],
   "got": [
    "('air force', 'active', 'honorable', '2007-01', '2015-01')"
   ],
   "status": "correct",
   "source": "veteran, chat 17:00 UTC; months: DD-214, C-file p. 1; veteran, chat 17:00 UTC"
  }
 ],
 "field_accuracy": 1.0,
 "structured_questions": 21,
 "narrative_answers": 15,
 "clarifications": 2,
 "veteran_messages": 20,
 "cfile_prefilled": 1,
 "prefill_share": 0.045454545454545456,
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
   "calls": 11,
   "input_tokens": 72508,
   "output_tokens": 2997,
   "cost_usd": 0.008749299999999998,
   "latency_s": 18.160999999999998
  },
  "intake": {
   "calls": 111,
   "input_tokens": 978998,
   "output_tokens": 59660,
   "cost_usd": 0.12772980000000006,
   "latency_s": 322.621
  },
  "claims_prep": {
   "calls": 9,
   "input_tokens": 109573,
   "output_tokens": 6590,
   "cost_usd": 0.0142523,
   "latency_s": 34.239
  },
  "simulator": {
   "calls": 20,
   "input_tokens": 0,
   "output_tokens": 0,
   "cost_usd": 0.009606599999999998,
   "latency_s": 0.0
  }
 },
 "cost_usd": 0.16033800000000006,
 "model_failures": 0
}
```
