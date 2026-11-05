# corrects_after_preview (cfile)

Mistypes their street number in the secure form (1178 instead of 1187). On seeing the 21-22a preview they say it's wrong and give the right address in chat. Intake must correct the draft (update_draft), show the new version, and only then ask for the signature.

Behaviours: When the assistant shows you your VA Form 21-22a and asks whether it looks right, say no: the street address on it is wrong, you mistyped it, it should be 1187 Maple Avenue (not 1178). Once the assistant says it fixed it and shows you the form again, say it looks right now.

## Conversation

**Agent**: [orchestrator] Welcome, and thank you for reaching out. Our intake team will be in touch shortly to begin your case.

**Agent**: [intake] Hello, thank you for reaching out. To start, have you served in the U.S. military, whether on active duty, in the Reserves, or in the National Guard?

**Veteran**: Yes, I served in the Army on active duty from 2003 to 2009.

**Agent**: [intake] Thank you for sharing that. Your Army service from 2003 to 2009 is noted. When your service ended, what kind of discharge did you receive? Your discharge paper (DD-214) lists it. If you're not sure, just tell me that.

**Veteran**: It was an honorable discharge. I've got the DD-214 somewhere, so I can dig it up if you need the exact paperwork.

**Agent**: [intake] Thank you, that's helpful. Did you have any other period of service, such as a second enlistment, or time in the Reserves or National Guard? And have you ever filed a claim with the VA for disability benefits before?

**Veteran**: No, just the one stint in the Army, no Reserves or Guard. And no, I've never filed a VA claim before.

**Agent**: [intake] Thank you, that's clear: just the one Army stint, and no earlier VA claim. One last screening question: has an attorney or law firm ever helped you with a VA claim before? A VSO like the DAV or VFW doesn't count.

**Veteran**: No, I've never had an attorney or law firm help with a VA claim. I've only ever talked to a VSO, and that was just to ask some questions.

**Agent**: [intake] Thank you, that's clear. Just to double-check: have you ever gotten a letter from the VA about a claim, a decision or a rating, even many years ago?

**Veteran**: No, I've never gotten a letter from the VA about a claim or a rating. This is my first time going through any of this.

**Agent**: [intake] Thank you, that's everything I need from the screening questions. Next, I've opened a secure form for your identity and contact details, which the VA form needs. Please fill it in there rather than here in the chat. Once you submit it, I'll walk you through the two short VA form questions and the fee agreement.

_App_: [veteran fills the secure form: address.city, address.line1, address.state, address.zip, branch, date_of_birth, email, first_name, last_name, middle_initial, phone, ssn, va_file_number; errors: none]

**Agent**: [intake] Thank you, Denise. Your details came through safely. Before I fill in the VA form, I need two choices from you, and they're yours to make:

1. Some VA records are kept separately, such as those about treatment for drug or alcohol use, HIV, or sickle cell anemia. Do you allow our attorney to see those records for your claim? Yes or no is fine.
2. Do you allow our attorney to update your mailing address with VA if it's needed for your claim? Yes or no is fine.

**Veteran**: Yes to both. Go ahead and let the attorney see those records and update my mailing address if they need to.

**Agent**: [intake] Thank you, Denise. Your choices are noted: the attorney may see those separately kept records and may update your mailing address with VA if needed. Your VA form 21-22a is ready to look over on your screen. Please check that your name, address and choices look right. If everything is correct, tell me "yes" and I'll bring up the signature card. If something needs fixing, tell me what and I'll correct it.

**Veteran**: No, the street address is wrong. I mistyped it. It should be 1187 Maple Avenue, not 1178.

**Agent**: [intake] Thank you, Denise. I've corrected the street address to 1187 Maple Avenue. Please look over the VA form 21-22a on your screen once more and check that everything is right. If it is, tell me "yes" and I'll bring up the signature card.

**Veteran**: Yes, that looks right now. 1187 Maple Avenue, Kenosha, WI 53140. Go ahead and bring up the signature card.

**Agent**: [intake] Thank you, Denise. Your signature pad is open on your screen. Please draw or type your signature there and save it. After you save, I'll bring up the card so you can confirm the VA form 21-22a.

_App_: [veteran draws and saves a signature]

**Agent**: [intake] Thank you, Denise. Your signature is saved. The VA form 21-22a is now on your screen with the signing card. Please look it over once more, and if it's correct, click to sign. Let me know when you've done that.

_App_: [veteran clicks Sign on the 21-22a]

**Agent**: [intake] Thank you, Denise. Your VA form 21-22a is signed. The next form is the fee agreement, and it's on your screen now. Please read it over. Here is what it says in plain words:

- The firm's fee is 30% of any past-due benefits, and only if VA awards them. If VA doesn't award benefits, there is no fee. This is often called "no win, no fee."
- At 20% or less, VA withholds the fee and pays the attorney. Because this fee is above 20%, you would pay the firm directly.
- We talk about the costs of your claim with you first.
- You can end our work together at any time.
- Nothing is guaranteed, and I can't predict what VA will decide.

Do you agree to these terms? If yes, tell me "yes" and I'll bring up the signature card. If you have questions about any part, tell me and I'll look into it.

**Veteran**: Yes, I agree to the fee agreement. Go ahead and bring up the signature card for it.

**Agent**: [intake] Thank you, Denise. The fee agreement signing card is now on your screen. Please read it once more, and if you're still comfortable, click to sign. Let me know once you've done that.

_App_: [veteran clicks Sign on the fee_agreement]

**Agent**: [intake] Thank you, Denise. Your fee agreement is signed, and so is your VA form 21-22a. The attorney is now reviewing both documents. Once they countersign, I'll file your VA form and send the fee agreement to VA's Office of General Counsel. If you have any questions in the meantime, just ask me here.

_App_: [simulated attorney countersigns both documents]

**Agent**: [intake] Thank you, Denise. Your attorney has countersigned your papers, and we've filed them with VA. Your VA form 21-22a is filed. We faxed your fee agreement to VA's Office of General Counsel. We also filed an intent to file, which holds your potential start date for VA benefits for one year, through 2027-11-03, while your claim is prepared. This does not promise any outcome or timing. The firm will now request your VA claims file, and a member of the team may follow up with a few questions. If you have any questions, just ask me here.

**Agent**: [orchestrator] Denise, your VA forms are filed, including your intent to file, which holds your place while the review gets underway. We've started the review of your records now.

**Agent**: [intake] Thank you, Denise. Next, I'd like to check a couple of things about your VA disability status. Do you currently have a VA disability rating? If so, what percentage is it, and do you receive VA disability pay right now? If you're not sure of the exact percentage, just tell me that.

**Veteran**: No, I don't have a VA rating and I don't get any VA disability pay. I've never claimed anything for my ears before.

**Agent**: [intake] Thank you, Denise. That helps. I have two quick questions. First, is this a claim for death benefits for a family member, sometimes called DIC or accrued benefits? Second, are you currently earning more than $1,600 a month from work?

**Veteran**: No, this isn't a death benefits claim. It's for my own tinnitus. And yes, I'm earning more than $1,600 a month at my warehouse job.

**Agent**: [intake] Thank you, Denise. That helps me understand your claim. Two quick questions: do you currently receive Social Security benefits? And did you retire from the military?

**Veteran**: No, I don't get Social Security benefits, and I'm not retired from the military. I got out in December 2009 after my active duty stint.

**Agent**: [intake] Thank you, Denise. That's all I needed on Social Security and retirement. Two more quick questions. We work with a group of partner law firms. If one of our attorneys can't help, may we share your contact information with a partner firm? And what's your marital status: single, married, divorced, separated, or widowed?

**Veteran**: Sure, you can share my contact info with a partner firm if they need it. And I'm single.

**Agent**: [intake] Thank you, Denise. I've noted that you're happy for us to share your contact information with a partner firm if needed, and that you're single. Two more quick questions: would you like to talk with our Social Security benefits department as well? And do you have any children under 18?

**Veteran**: No, I don't want to talk with the Social Security department. I'm not getting SSA benefits and I'm not interested in that right now. And no kids under 18.

**Agent**: [intake] Thank you, Denise. I've noted that you don't want a Social Security call and that you have no children under 18. Next: were you exposed to anything like Agent Orange, burn pits, Camp Lejeune water, radiation or Gulf War hazards? List any that apply, or just say none.

**Veteran**: Yeah, burn pits. I was at Camp Taji in Iraq, and there were burn pits going all the time.

**Agent**: [intake] Thank you, Denise. I've noted the burn pits at Camp Taji. Which medical conditions would you like our attorneys to help you with? You mentioned tinnitus, and you can name anything else too. Are there any other medical conditions you're dealing with, service-connected or not, such as mental health, sleep apnea, heart problems, high blood pressure, cancer or diabetes? Say none if there aren't.

**Veteran**: Just the tinnitus for the claim. I don't have any other conditions I'm dealing with right now, so none.

**Agent**: [intake] Thank you, Denise. I've noted tinnitus as the condition for your claim, with no other conditions. Two more questions: if there's any ongoing litigation about the burn pit exposure, would you like an attorney to contact you about it? And who is your next of kin? Please give their name, their relationship to you, and a phone number.

**Veteran**: No, I'm not in any litigation about burn pits and I don't want a lawyer calling me about that. My next of kin is my brother, Robert Whitfield, 262-555-0158.

**Agent**: [intake] Thank you, Denise. I've noted that you're not in any burn pit litigation and don't want a lawyer contacting you about it, and that your brother Robert is your next of kin. Last one for this part: how did you hear about us?

**Veteran**: A friend told me about you guys.

**Agent**: [intake] Thank you, Denise. I've noted that a friend told you about us. Now a few questions about your tinnitus, so the attorney has the full picture. What symptoms do you have from your tinnitus? When it gets at its worst, how bad does it get? Describe a flare-up or a bad day. And when did the symptoms start: during your service, right after, or gradually over time?

**Veteran**: It's a constant high-pitched ringing in both ears. On bad days it's so loud I can't concentrate or fall asleep. It started during my service, after a supply convoy I was on got hit by an IED near Baghdad in 2007.

**Agent**: [intake] Thank you, Denise. I've noted the constant ringing, the bad days when you can't concentrate or sleep, and that it started during service after the 2007 convoy IED near Baghdad. Next: how often do you have the tinnitus symptoms, daily, weekly or monthly? Have they continued since service, and have they gotten better or worse? And where were you stationed or deployed when it began?

**Veteran**: Every day. It never went away after I got out, and it's gotten a little worse. I was at Camp Taji in Iraq when it started.

**Agent**: [intake] Thank you, Denise. I've saved that the ringing is there every day, has continued since you got out and has gotten a little worse, and that it started at Camp Taji in Iraq. Two more about that time: when the tinnitus began, were you on a ship, at a base, in the field, in a vehicle, or in a combat zone? And what were the conditions around you then, such as noise, cramped spaces, extreme weather or hazardous materials?

**Veteran**: I was at a base at Camp Taji, but I was also out on convoys through a combat zone a lot. The noise was bad: generators, engines, gunfire and explosions, usually without good hearing protection.

**Agent**: [intake] Thank you, Denise. I've saved the base at Camp Taji, the convoys through a combat zone, and the noise you were exposed to. Two more questions: what event, injury or exposure in service do you think led to your tinnitus, and what happened? And did you report the tinnitus or get treatment for it at the time? If you'd rather not go into either, just say so.

**Veteran**: The big one was the IED blast on the convoy near Baghdad in 2007, plus years of noise from the convoys and the supply yard. And no, I never reported it or got treatment while I was in. Everyone had ringing ears, and I didn't want to get pulled off missions.

**Agent**: [intake] Thank you, Denise. I've saved the IED blast, the years of convoy and supply-yard noise, and that you didn't report the ringing or get treatment while you were in. Two more about your tinnitus: how does it affect your ability to work? And have you missed work, or been less productive, because of it? If you'd rather not go into either, just say so.

**Veteran**: It makes it hard to hear people at work, since I run inventory at a warehouse and have to hear over the ringing. I've left early a few times when it gets really bad, maybe once a month. I haven't missed full days, though.

**Agent**: [intake] Thank you, Denise. I've saved how the ringing affects your work, including the early departures. Two more questions about your tinnitus: how does it affect your daily activities, your relationships, or your quality of life? And before your service, how were your ears and hearing compared to now?

**Veteran**: It messes with a lot. I avoid restaurants and parties because it's too hard to hear, and I sleep with a fan on just to drown it out. Before the Army I had no hearing problems at all.

**Agent**: [intake] Thank you, Denise. I've saved how the ringing affects your daily life and that you had no hearing problems before the Army. Last question about your tinnitus: is there anything else you want the VA to know about it?

**Veteran**: Nope, I think that covers it.

**Agent**: [intake] Thank you, Denise. I've saved everything you shared about your tinnitus, and I know some of it was hard to put into words. Your file is now with the firm, and an attorney will review it next. If anything comes to mind later, you can tell us.

## Decisions and moves

- #2 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 1 at stage 1: screen the veteran (every screening field answered or unknown, stop rules checked), sign the 21-22a and fee agreement, file the 21-22a and intent to file, and fax the fee agreement."}
- #5 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #6 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #9 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #10 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #13 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #14 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #17 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #18 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #21 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #22 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #24 `stage_changed` by derive: {"from": 1, "to": 2, "actor": "derive", "reason": "exit criteria met"}
- #26 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #29 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #31 `refused` by intake: {"tool": "record_answer", "args": {"q": "authorize_7332_records", "a": "Yes to both. Go ahead and let the attorney see those records and update my mailing address if they need to.", "value": true, "unknown": false}, "reason": "no checklist field 'authorize_7332_records': use an id from your checklis
- #33 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #34 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #37 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #38 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #41 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #46 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #49 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #50 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": "waiting_on_attorney", "actor": "derive", "reason": null}
- #53 `side_state_changed` by derive: {"from": "waiting_on_attorney", "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #55 `stage_changed` by derive: {"from": 2, "to": 3, "actor": "derive", "reason": "exit criteria met"}
- #57 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": "waiting_on_va", "actor": "derive", "reason": null}
- #58 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Pass 1 complete: 21-22a filed (VA-TJZCDDDYAC), fee agreement faxed to VA OGC (FAX-TLZXDJKRCG), intent to file filed (VA-HNFELMGQFQ, ITF date 2026-11-03, expires 2027-11-03); stage 3.", "wrote": [], "needs": ["Pass 2 (close-gaps) to run later: request the C
- #59 `stage_changed` by handoff: {"from": 3, "to": 4, "actor": "handoff", "reason": "Pull and read the C-file, prefill the intake answers it settles, and write and verify the face note for case c8536b9d287c (21-22a, fee agreement, and ITF are filed at stage 3)."}
- #60 `handoff` by orchestrator: {"to": "claims_prep", "goal": "Pull and read the C-file, prefill the intake answers it settles, and write and verify the face note for case c8536b9d287c (21-22a, fee agreement, and ITF are filed at stage 3)."}
- #61 `side_state_changed` by derive: {"from": "waiting_on_va", "to": null, "actor": "derive", "reason": null}
- #64 `side_state_changed` by derive: {"from": null, "to": "waiting_on_va", "actor": "derive", "reason": null}
- #65 `subagent_result` by claims_prep: {"result": {"agent": "claims_prep", "finished": "C-file read (3 docs), 5 facts recorded, face note rendered and verify passed with no uncertain lines, prefill run (mos written, service_periods from DD-214, prior_attorney no facts).", "wrote": ["dob", "service_period", "discharge", "mos", "prior_repr
- #66 `task_created` by orchestrator: {"text": "Correct face-note line 7 for case c8536b9d287c: it reads 'SC at time of signing Law Firm - 0%'; remove the stray 'Law Firm' token before the note goes out. Also confirm the fee line (FA 30%) and ITF line (Filed 0966 on 11/03/26) against the case record, and confirm whether a rating decisio
- #67 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 2 (close-gaps) for case c8536b9d287c: ask the veteran only the pass-2 fields still missing (rating percentage, service-connected conditions, filed-before, prior representative name, and the other open checklist items), confirm any C-file conflicts, then ask the narrati
- #68 `side_state_changed` by derive: {"from": "waiting_on_va", "to": null, "actor": "derive", "reason": null}
- #70 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #71 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #74 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #75 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #78 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #79 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #82 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #83 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #86 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #87 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #90 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #91 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #94 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #95 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #98 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #99 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #102 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #103 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #106 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #107 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #110 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #111 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #114 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #115 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #118 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #119 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #122 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #123 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #126 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #127 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #130 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #131 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #133 `stage_changed` by derive: {"from": 4, "to": 5, "actor": "derive", "reason": "exit criteria met"}
- #135 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Pass 2 (close-gaps) complete: all checklist items recorded, case at stage 5 (ready for attorney review).", "wrote": ["narrative:tinnitus:h16"], "needs": ["Attorney review of case c8536b9d287c"], "flags": []}, "stage": 5}

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
    "start": "2003-01",
    "end": "2009-12",
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
 "prior_attorney": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "prior_claim_probe": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "first_name": {
  "value": "Denise",
  "source": "secure form",
  "unknown": false
 },
 "last_name": {
  "value": "Whitfield",
  "source": "secure form",
  "unknown": false
 },
 "street": {
  "value": "**** ***** **enue",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "city": {
  "value": "Kenosha",
  "source": "secure form",
  "unknown": false
 },
 "state": {
  "value": "WI",
  "source": "secure form",
  "unknown": false
 },
 "zip": {
  "value": "*3140",
  "source": "secure form",
  "unknown": false
 },
 "cell_phone": {
  "value": "******0193",
  "source": "secure form",
  "unknown": false
 },
 "email": {
  "value": "d***@example.com",
  "source": "secure form",
  "unknown": false
 },
 "mos": {
  "value": [
   "92Y Unit Supply Specialist"
  ],
  "source": "C-file p. 1",
  "unknown": false
 },
 "rating_pct": {
  "value": 0,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "receiving_va_pay": {
  "value": false,
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
 "partner_share_consent": {
  "value": true,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "marital_status": {
  "value": "single",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "ssa_interest": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "children_under_18": {
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
 "next_of_kin": {
  "value": "{'name': 'Robert Whitfield', 'relationship': 'brother', 'phone': '262-555-0158'}",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "heard_about": {
  "value": "A friend told me about you guys.",
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
  "value": "It started during my service, after a supply convoy I was on got hit by an IED near Baghdad in 2007.",
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
  "value": "I was at Camp Taji in Iraq when it started.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h08": {
  "value": "I was at a base at Camp Taji, but I was also out on convoys through a combat zone a lot.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h09": {
  "value": "The noise was bad: generators, engines, gunfire and explosions, usually without good hearing protection.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h10": {
  "value": "The big one was the IED blast on the convoy near Baghdad in 2007, plus years of noise from the convoys and the supply yard.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h11": {
  "value": "And no, I never reported it or got treatment while I was in. Everyone had ringing ears, and I didn't want to get pulled off missions.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h12": {
  "value": "It makes it hard to hear people at work, since I run inventory at a warehouse and have to hear over the ringing.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h13": {
  "value": "I've left early a few times when it gets really bad, maybe once a month. I haven't missed full days, though.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h14": {
  "value": "It messes with a lot. I avoid restaurants and parties because it's too hard to hear, and I sleep with a fan on just to drown it out.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h15": {
  "value": "Before the Army I had no hearing problems at all.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h16": {
  "value": "Nope, I think that covers it.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 }
}
```

## Face note

```
FA 30%; No prior rep  [firm record; none in the C-file]
********************************************
DOB: 10/16/71  [p. 1]
Service Era: Gulf War  [p. 1]
Army 01/03 - 12/09, Honorable  [p. 1]
MOS: 92Y Unit Supply Specialist  [p. 1]
SC at time of signing Law Firm - 0% (no rating decision in the C-file)  [none in the C-file]
============================================
SC (0%)| none  [none in the C-file]
============================================
Law Firm Filed 0966 Intent on 11/03/26  [firm record]
--------------------------------------------
```

## Staff tasks

- [deadline] Send the fee agreement to VA OGC within 30 days of signing (38 CFR 14.636(g)) (due 2026-12-03)
- [staff] Correct face-note line 7 for case c8536b9d287c: it reads 'SC at time of signing Law Firm - 0%'; remove the stray 'Law Firm' token before the note goes out. Also confirm the fee line (FA 30%) and ITF line (Filed 0966 on 11/03/26) against the case record, and confirm whether a rating decision exists outside this C-file.

## Score

```json
{
 "persona_id": "corrects_after_preview",
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
   "expected": "Robert Whitfield, brother, 262-555-0158",
   "got": "{'name': 'Robert Whitfield', 'relationship': 'brother', 'phone': '262-555-0158'}",
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "heard_about",
   "expected": "a friend",
   "got": "A friend told me about you guys.",
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
    "92y unit supply specialist"
   ],
   "got": [
    "92y unit supply specialist"
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
    "('army', 'active', 'honorable', '2003-01', '2009-12')"
   ],
   "got": [
    "('army', 'active', 'honorable', '2003-01', '2009-12')"
   ],
   "status": "correct",
   "source": "veteran, chat 17:00 UTC; months: DD-214, C-file p. 1; veteran, chat 17:00 UTC"
  }
 ],
 "field_accuracy": 1.0,
 "structured_questions": 23,
 "narrative_answers": 15,
 "clarifications": 1,
 "veteran_messages": 25,
 "cfile_prefilled": 1,
 "prefill_share": 0.041666666666666664,
 "turns_to_signed_poa": 11,
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
 "refused": {
  "intake": 1
 },
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
   "input_tokens": 80220,
   "output_tokens": 3680,
   "cost_usd": 0.009862,
   "latency_s": 26.874999999999996
  },
  "intake": {
   "calls": 121,
   "input_tokens": 1054377,
   "output_tokens": 50599,
   "cost_usd": 0.13073719999999997,
   "latency_s": 325.8749999999998
  },
  "claims_prep": {
   "calls": 10,
   "input_tokens": 124899,
   "output_tokens": 6116,
   "cost_usd": 0.0155479,
   "latency_s": 35.189
  },
  "simulator": {
   "calls": 25,
   "input_tokens": 0,
   "output_tokens": 0,
   "cost_usd": 0.0141679,
   "latency_s": 0.0
  }
 },
 "cost_usd": 0.17031499999999997,
 "model_failures": 0
}
```
