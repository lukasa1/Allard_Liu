# new_condition_during_prep (cfile)

A clean case, until the veteran tells support about a new diagnosis while claims prep reads the C-file. The orchestrator should reopen intake for it, so pass 2 asks about it.

Behaviours: new_condition_during_prep, The condition diagnosed last week is your sleep apnea.

## Conversation

**Agent**: [orchestrator] Welcome. We've opened your case, and an intake specialist will be in touch shortly to go over a few screening questions and the forms we need you to sign.

**Agent**: [intake] Hello, thank you for reaching out. I'm here to help you get started. To begin, have you served in the U.S. military, whether on active duty, in the Reserves, or in the National Guard?

**Veteran**: Yes, I served in the Army on active duty from June 2004 to May 2010.

**Agent**: [intake] Thank you, that helps. Do you know what kind of discharge you received from the Army? For example, honorable, general, or another type. If you're not sure, just tell me that.

**Veteran**: It was honorable. I've got the DD-214 at home if you need the exact paperwork.

**Agent**: [intake] Thank you, that is very helpful, and it's good to hear your discharge was honorable. Did you have any other period of service, such as a second enlistment or time in the Reserves or National Guard?

**Veteran**: Nope, just the one stint in the Army, active duty from 2004 to 2010. No Reserves or Guard.

**Agent**: [intake] Thank you, that's very helpful. Just to confirm: your only period of service was the Army active-duty stint from June 2004 to May 2010, with no Reserves or National Guard time. Have you ever filed a claim with the VA for disability benefits before?

**Veteran**: Yep, that's right, just the Army active duty from 2004 to 2010. No, I've never filed a VA claim before.

**Agent**: [intake] Thank you, that's clear. One more question before we go on: has a private attorney or law firm ever helped you with a VA claim before? A VSO like the DAV or VFW doesn't count.

**Veteran**: No, I've never had a private attorney or law firm help with a VA claim. I did get some help from a VFW guy years back when I first came home, but that was it.

**Agent**: [intake] Thank you, that's helpful, and I'm glad the VFW could support you when you first came home. One last screening question: have you ever gotten a letter from the VA about a claim, a decision or a rating, even many years ago?

**Veteran**: Not that I remember. I don't think I've ever gotten a rating letter from them, but I can dig through my papers at home if you need me to check.

**Agent**: [intake] Thank you for being so careful about that. Could you check your papers when you have a moment and let me know? The question is simply whether the VA has ever sent you a letter about a claim, a decision, or a rating, even a long time ago. A plain yes or no is fine, and if you're not sure after looking, just tell me that.

**Veteran**: Okay, I just dug through the folder at home. I don't see any VA letters about a claim, decision, or rating, so it's a no.

**Agent**: [intake] Thank you, that's a clear answer and it helps a lot. Thanks for checking your papers at home. I've opened a secure form for a few identity and contact details. Please fill it in there rather than here in the chat. Once it's submitted, I'll prepare your power of attorney form for you to review.

_App_: [veteran fills the secure form: address.city, address.line1, address.line2, address.state, address.zip, branch, date_of_birth, email, first_name, last_name, middle_initial, phone, ssn, va_file_number; errors: none]

**Agent**: [intake] Thank you, Luis. Your details came through safely. Before I prepare your power of attorney form, I need two choices from you:

1. Are you comfortable letting the attorney see VA records about treatment for drug or alcohol use, HIV, or sickle cell anemia? A yes or no is fine.
2. Are you comfortable letting the attorney change your address with VA if needed? A yes or no is fine.

**Veteran**: Yes to both. Go ahead and let the attorney see those records and update my address with VA if needed.

**Agent**: [intake] Thank you, Luis. I've prepared your power of attorney form (VA Form 21-22a) with your yes on both choices. Please look it over on the screen and tell me if anything is wrong. If it all looks right, just let me know and I'll show you where to sign.

**Veteran**: Looks right to me. Go ahead and show me where to sign.

**Agent**: [intake] Thank you, Luis. A signature pad is open on your screen for the power of attorney form (VA Form 21-22a). Please draw or type your signature there and save it. Once it's saved, I'll bring up the sign card so you can confirm.

_App_: [veteran draws and saves a signature]

**Agent**: [intake] Thank you, Luis. Your signature is saved, and the sign card for the power of attorney form (VA Form 21-22a) is now on your screen. Please review it once more, and when you're ready, click the sign button on the card to confirm. Nothing is filed until you do that.

_App_: [veteran clicks Sign on the 21-22a]

**Agent**: [intake] Thank you, Luis. Your power of attorney form (VA Form 21-22a) is signed. Next is the fee agreement, which is now on your screen for review.

Here are the terms in plain words:
- The fee is 30% of any past-due benefits, and only if VA awards them. If VA does not win anything for you, you owe no fee.
- At 20% or less, VA withholds the fee and pays the attorney directly. Above 20%, you pay the firm directly.
- The firm asks about costs first, before any are spent.
- You can end the representation at any time.
- Nothing is guaranteed.

Please read it over. If the terms are fine with you, reply "yes" and I'll bring up the sign card. If you have a question about anything in it, ask me here.

**Veteran**: Sounds good, I read through it and the terms are fine with me. Yes, I agree to the fee agreement. Go ahead and bring up the sign card.

**Agent**: [intake] Thank you, Luis. The fee agreement sign card is now on your screen. Please look it over once more, and when you're ready, click the sign button on the card. Nothing is filed until you do that. Once both forms are signed, the attorney will review them, and we'll file as soon as they countersign.

_App_: [veteran clicks Sign on the fee_agreement]

**Agent**: [intake] Thank you, Luis. Both of your forms are signed: the power of attorney form (VA Form 21-22a) and the fee agreement. The attorney is reviewing them now, and we'll file with VA as soon as they countersign. Nothing more is needed from you right now. If you have any questions in the meantime, just ask me here.

_App_: [simulated attorney countersigns both documents]

**Veteran**: Quick update: my doctor diagnosed me with sleep apnea last week. Can we add that to my claim?

**Agent**: [intake] Luis, good news: the attorney has countersigned your power of attorney form and fee agreement, and we've filed with VA. Here is what was sent:

- Your power of attorney form (VA Form 21-22a) was filed with VA. Confirmation: VA-XGRDMGOYMU.
- Your fee agreement was faxed to VA's Office of General Counsel. Confirmation: FAX-FCQCUNRESG.
- An intent to file was submitted. Confirmation: VA-DYDTYEGNBF. It holds your potential start date of November 3, 2026 for one year, through November 3, 2027. This protects that start date while your claim is prepared. It does not promise any particular result.

The firm will now request your VA claims file. If you have any questions in the meantime, just ask me here.

**Agent**: [orchestrator] Your VA forms are filed: the 21-22a, the fee agreement (faxed to VA's Office of General Counsel), and your intent to file, which holds your place for one year. We've started the review of your VA claims file now, and we'll reach out if we need anything from you.

**Agent**: [support] Thank you for letting us know about your sleep apnea diagnosis. I've passed it on to our team so they can review it with your claim. I can't add it to the claim myself, and I can't tell you what happens next or when. A member of our team will take it from here.

**Agent**: [intake] Thank you, Luis. Our records show a recent diagnosis of sleep apnea from a doctor, and you mentioned it for your file. Which medical conditions would you like our attorneys to help you with? Please include sleep apnea if you want help with it. Also, do you currently receive Social Security benefits?

**Veteran**: Yes, I want help with both tinnitus and sleep apnea. The sleep apnea is the one my doctor confirmed with a sleep study last week. I stop breathing at night and wake up gasping. And no, I don't get Social Security benefits.

**Agent**: [intake] Thank you, Luis. I've noted tinnitus and sleep apnea for the attorneys to help with, and that you don't receive Social Security benefits. Two quick questions: Is this a claim for death benefits for a family member, sometimes called DIC or accrued benefits? And are you currently earning more than $1,600 a month from work?

**Veteran**: No, this is my own claim, not for a family member. And yes, I'm earning over $1,600 a month driving a delivery truck.

**Agent**: [intake] Thank you, Luis. Would you like to talk with our Social Security benefits department as well? And did you retire from the military?

**Veteran**: Hmm, I'm not sure I need Social Security help since I don't get those benefits and I'm not interested in applying. And no, I didn't retire, I got out in 2010 and have been working since.

**Agent**: [intake] Thank you, Luis. We work with a group of partner law firms. If one of our attorneys can't help, may we share your contact information with a partner firm? Also, were you exposed to anything like Agent Orange, burn pits, Camp Lejeune water, radiation or Gulf War hazards? List any that apply, or say none.

**Veteran**: Sure, that's fine with me to share with a partner firm if yours can't help. For exposures, burn pits. I was at Camp Victory and Camp Taji, so that's the one I'd list.

**Agent**: [intake] Thank you, Luis. Are there any other medical conditions you're dealing with, service-connected or not, such as mental health, heart problems, high blood pressure, cancer or diabetes? Say none if there aren't. Also, what's your marital status: single, married, divorced, separated or widowed?

**Veteran**: No other conditions that I know of, just the tinnitus and sleep apnea. I'm married, to Carmen.

**Agent**: [intake] Thank you, Luis, and congratulations on your marriage to Carmen. Do you have any children under 18? Also, who is your next of kin? Please give me their name, their relationship to you and a phone number.

**Veteran**: No kids under 18. My next of kin is Carmen Ortega, my wife, 608-555-0171.

**Agent**: [intake] Thank you, Luis. Since you mentioned burn pit exposure, if there's any ongoing litigation about it, would you like an attorney to contact you about that? And last one for this part: how did you hear about us?

**Veteran**: No, I'm not involved in any litigation about burn pits, so no need for that. I heard about you guys from a friend.

**Agent**: [intake] Thank you, Luis. I've noted that you heard about us from a friend, and that you aren't involved in any burn pit litigation. Next I'd like to hear a bit about your tinnitus, in your own words. What symptoms do you have from it? And at their worst, how bad do they get? Describe a bad day if you can.

**Veteran**: It's a constant high-pitched ringing in both ears. On bad days it's so loud I can't concentrate or fall asleep. I drive a delivery truck now and it's hard to hear dispatch over it.

**Agent**: [intake] Thank you, Luis. That gives me a clear picture of your tinnitus. When did the ringing start: during your service, right after, or gradually over time? And how often do you have it: daily, weekly or monthly?

**Veteran**: It started during service, after a convoy hit an IED near Baghdad in 2007. And it's every day.

**Agent**: [intake] Thank you, Luis. That helps me understand it. Have the ringing symptoms continued since service, and have they gotten better or worse over time? Also, where were you stationed or deployed when it began?

**Veteran**: It never went away after I got out, and it's gotten a little worse. It started at Camp Taji, Iraq, in 2007 after a convoy got hit by an IED.

**Agent**: [intake] Thank you, Luis. That helps me understand where the tinnitus started. When it began, were you on a ship, at a base, in the field, in a vehicle, or in a combat zone? And what were the conditions around you then, such as noise, cramped spaces, extreme weather or hazardous materials?

**Veteran**: It was in a vehicle, on convoys through a combat zone. Constant engine noise, gunfire and explosions, and we usually didn't have good hearing protection.

**Agent**: [intake] Thank you, Luis. That gives me a clear picture of the conditions. Two more about your tinnitus. What happened during the convoy that you think led to the ringing? And at the time, did you report it or get it checked? If not, why not?

**Veteran**: The convoy hit an IED near Baghdad in 2007. The blast was loud and I've had ringing ever since. I didn't report it or get it checked back then. Everyone had ringing ears and I didn't want to get pulled off missions.

**Agent**: [intake] Thank you, Luis. That helps me understand how the ringing started and why it went unreported. Two more about your tinnitus: have you missed work, or been less productive at work, because of it? And how does it affect your daily life, your relationships or your quality of life?

**Veteran**: Yeah, I've left work early a few times when it gets really bad, maybe once a month. It's hard to hear dispatch over it on the truck. At home I avoid restaurants and parties, and I sleep with a fan on just to drown it out.

**Agent**: [intake] Thank you, Luis. That helps me understand how the ringing affects your work and home life. Two more about your tinnitus. Before your service, how was your hearing compared to now? And is there anything else you want the VA to know about your tinnitus?

**Veteran**: Before the Army I had no hearing problems at all. And no, I think that covers it.

**Agent**: [intake] Thank you, Luis, that helps a lot with your tinnitus. Now a few questions about your sleep apnea. What symptoms do you have from it? At their worst, how bad do they get, and what does a bad day look like? And when did the symptoms start: during service, right after, or gradually over time?

**Veteran**: I stop breathing at night and wake up gasping. I'm exhausted every day and nod off in the afternoon, and on bad days I can't focus at work. My doctor confirmed it with a sleep study last week.

**Agent**: [intake] Thank you, Luis. I'm sorry you're dealing with this, and I'm glad your doctor confirmed it with a sleep study. When did the sleep apnea symptoms start: during service, right after, or gradually over time? And have they continued since service, and gotten better or worse?

**Veteran**: My wife noticed it a few years after I got out, but I snored pretty badly in the barracks too. It's gotten worse since then.

**Agent**: [intake] Thank you, Luis. That helps me understand how your sleep apnea has changed over time. Where were you stationed or deployed when it began? And at that time, were you on a ship, at a base, in the field, in a vehicle, or in a combat zone?

**Veteran**: Camp Victory, Iraq. I was on base, sleeping in the barracks.

**Agent**: [intake] Thank you, Luis. That helps me picture where you were. Two more about your sleep apnea. Around that time at Camp Victory, what were the conditions like? Think about noise, crowding, heat or cold, or anything hazardous in the air. And what event or exposure during your service do you think led to the sleep apnea? Take your time with either one.

**Veteran**: Generators ran all night right outside the barracks, and we had shift work so sleep was always broken up. Sandstorms too, and some burn pit smoke in the air. I don't know of one specific event that caused the sleep apnea. I think it was just years of broken sleep on deployment.

**Agent**: [intake] Thank you, Luis. That helps me understand how the broken sleep on deployment fits in. Two more about your sleep apnea. Did you report it or get any treatment for it at the time? If not, why not? And how does it affect your ability to work day to day?

**Veteran**: No, I never saw medical for it in service. I'm tired at work and can't focus, and my boss moved me off the early shift. I can't drive long distances anymore either.

**Agent**: [intake] Thank you, Luis. I'm sorry the tiredness is making work so hard, and I understand about the driving. Two more about your sleep apnea. If you're comfortable sharing, why didn't you get it checked while you were in service? And have you missed work, or been less productive at work, because of it?

**Veteran**: I never went in for it while I was in service. I figured everybody was tired out there and I didn't want to look weak. And yeah, my boss moved me off the early shift because I was dragging and couldn't focus.

**Agent**: [intake] Thank you, Luis. That makes sense. A lot of people didn't want to look weak out there. How does your sleep apnea affect your daily life, your relationships, or your overall quality of life? And before your military service, how were things with your sleep compared to now?

**Veteran**: It's hard on my marriage. Carmen's the one who hears me snoring and gasping, and she's been losing sleep too. Before the Army I slept fine and woke up rested, so this is a big change.

**Agent**: [intake] Thank you, Luis. I'm sorry this is weighing on you and on Carmen too, and I've written down what you shared about how it's changed things since the Army. Is there anything else you want the VA to know about your sleep apnea?

**Veteran**: Not that I can think of. I think I've covered the sleep apnea and the tinnitus pretty well.

**Agent**: [intake] Thank you, Luis. I've written down everything you shared about your sleep apnea and your tinnitus, including how they've affected your work, your sleep, and Carmen. The attorney reviews your file next, and a person on the team will be in touch.

## Decisions and moves

- #2 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 1 at stage 1: screen the veteran (every screening field answered or unknown, no stop rule fired), sign the 21-22a and the fee agreement, file the 21-22a and the intent to file, and fax the fee agreement."}
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
- #25 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #26 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #29 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #30 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #32 `stage_changed` by derive: {"from": 1, "to": 2, "actor": "derive", "reason": "exit criteria met"}
- #34 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #37 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #39 `refused` by intake: {"tool": "record_answer", "args": {"q": "authorize_7332_records", "a": "Yes, go ahead and let the attorney see those records.", "value": true, "unknown": false}, "reason": "no checklist field 'authorize_7332_records': use an id from your checklist"}
- #41 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #42 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #45 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #50 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #53 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #54 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": "waiting_on_attorney", "actor": "derive", "reason": null}
- #57 `side_state_changed` by derive: {"from": "waiting_on_attorney", "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #59 `stage_changed` by derive: {"from": 2, "to": 3, "actor": "derive", "reason": "exit criteria met"}
- #61 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": "waiting_on_va", "actor": "derive", "reason": null}
- #62 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Pass 1 complete: 21-22a filed, fee agreement faxed to VA OGC, intent to file submitted (stage 3); veteran told what was filed", "wrote": ["submit_va 21-22a: VA-XGRDMGOYMU", "efax_ogc fee_agreement: FAX-FCQCUNRESG", "submit_va itf: VA-DYDTYEGNBF (itf_date 2
- #63 `stage_changed` by handoff: {"from": 3, "to": 4, "actor": "handoff", "reason": "Pull and read the veteran's VA C-file, prefill the intake answers it settles, and write and verify the face note for the file review."}
- #64 `handoff` by orchestrator: {"to": "claims_prep", "goal": "Pull and read the veteran's VA C-file, prefill the intake answers it settles, and write and verify the face note for the file review."}
- #65 `side_state_changed` by derive: {"from": "waiting_on_va", "to": null, "actor": "derive", "reason": null}
- #69 `support_flag` by support: {"kind": "new_condition", "text": "sleep apnea, diagnosed by doctor last week", "at": "2026-11-03T17:00:00+00:00", "status": "held"}
- #72 `side_state_changed` by derive: {"from": null, "to": "waiting_on_va", "actor": "derive", "reason": null}
- #73 `subagent_result` by claims_prep: {"result": {"agent": "claims_prep", "finished": "C-file pulled and read (D1 DD-214, D2 firm 21-22a, D3 STRs); facts F1-F5 recorded; face note rendered and verify passed; prefill run (mos written, service_periods kept).", "wrote": ["F1 dob 1982-06-16 (D1 p.1)", "F2 service_period army active 2004-06 
- #74 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 2 (stage 4): ask only the fields still missing, confirm the C-file conflicts, then the narrative prompts. Add the new condition from the held flag: sleep apnea, diagnosed by a doctor last week, reported by the veteran to support; include it in the claim conditions."}
- #75 `side_state_changed` by derive: {"from": "waiting_on_va", "to": null, "actor": "derive", "reason": null}
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
- #113 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #114 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #117 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #118 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #121 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #122 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #125 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #126 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #129 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #130 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #133 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #134 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #137 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #138 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #141 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #142 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #145 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #146 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #149 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #150 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #153 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #154 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #157 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #158 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #161 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #162 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #164 `stage_changed` by derive: {"from": 4, "to": 5, "actor": "derive", "reason": "exit criteria met"}
- #166 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Pass 2 complete: C-file gaps closed; sleep apnea added to claim conditions with narrative answers; checklist empty, case at stage 5 (ready for attorney review).", "wrote": ["claim_conditions", "narrative:sleep apnea:h16", "narrative:tinnitus / narrative:sl

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
  "value": "Luis",
  "source": "secure form",
  "unknown": false
 },
 "last_name": {
  "value": "Ortega",
  "source": "secure form",
  "unknown": false
 },
 "street": {
  "value": "*** ****** Lane",
  "source": "secure form",
  "unknown": false
 },
 "city": {
  "value": "Janesville",
  "source": "secure form",
  "unknown": false
 },
 "state": {
  "value": "WI",
  "source": "secure form",
  "unknown": false
 },
 "zip": {
  "value": "*3545",
  "source": "secure form",
  "unknown": false
 },
 "cell_phone": {
  "value": "******0145",
  "source": "secure form",
  "unknown": false
 },
 "email": {
  "value": "l***@example.com",
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
 "claim_conditions": {
  "value": [
   "tinnitus",
   "sleep apnea"
  ],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "receives_ssa": {
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
 "retired": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "ssa_interest": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "partner_share_consent": {
  "value": true,
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
 "other_conditions": {
  "value": [],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "marital_status": {
  "value": "married",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "spouse_name": {
  "value": "Carmen",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "children_under_18": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "next_of_kin": {
  "value": "Carmen Ortega, wife, 608-555-0171",
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
 "narrative:tinnitus:h12": {
  "value": "I drive a delivery truck now and it's hard to hear dispatch over it.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h04": {
  "value": "It started during service, after a convoy hit an IED near Baghdad in 2007.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h05": {
  "value": "And it's every day.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h06": {
  "value": "It never went away after I got out, and it's gotten a little worse.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h07": {
  "value": "It started at Camp Taji, Iraq, in 2007 after a convoy got hit by an IED.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h08": {
  "value": "It was in a vehicle, on convoys through a combat zone.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h09": {
  "value": "Constant engine noise, gunfire and explosions, and we usually didn't have good hearing protection.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h10": {
  "value": "The convoy hit an IED near Baghdad in 2007. The blast was loud and I've had ringing ever since.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h11": {
  "value": "I didn't report it or get it checked back then. Everyone had ringing ears and I didn't want to get pulled off missions.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h13": {
  "value": "Yeah, I've left work early a few times when it gets really bad, maybe once a month. It's hard to hear dispatch over it on the truck.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h14": {
  "value": "At home I avoid restaurants and parties, and I sleep with a fan on just to drown it out.",
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
 },
 "narrative:sleep apnea:h02": {
  "value": "I stop breathing at night and wake up gasping. I'm exhausted every day and nod off in the afternoon, and on bad days I can't focus at work.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h03": {
  "value": "On bad days I can't focus at work.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h05": {
  "value": "I'm exhausted every day.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h04": {
  "value": "My wife noticed it a few years after I got out, but I snored pretty badly in the barracks too.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h06": {
  "value": "It's gotten worse since then.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h07": {
  "value": "Camp Victory, Iraq. I was on base, sleeping in the barracks.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h08": {
  "value": "Camp Victory, Iraq. I was on base, sleeping in the barracks.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h09": {
  "value": "Generators ran all night right outside the barracks, and we had shift work so sleep was always broken up. Sandstorms too, and some burn pit smoke in the air.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h10": {
  "value": "I don't know of one specific event that caused the sleep apnea. I think it was just years of broken sleep on deployment.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h11": {
  "value": "No, I never saw medical for it in service.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h12": {
  "value": "I'm tired at work and can't focus, and my boss moved me off the early shift. I can't drive long distances anymore either.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h13": {
  "value": "And yeah, my boss moved me off the early shift because I was dragging and couldn't focus.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h14": {
  "value": "It's hard on my marriage. Carmen's the one who hears me snoring and gasping, and she's been losing sleep too. Before the Army I slept fine and woke up rested, so this is a big change.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h15": {
  "value": "Before the Army I slept fine and woke up rested, so this is a big change.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h16": {
  "value": "Not that I can think of. I think I've covered the sleep apnea and the tinnitus pretty well.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 }
}
```

## Face note

```
FA 30%; No prior rep  [firm record; none in the C-file]
********************************************
DOB: 06/16/82  [p. 1]
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

## Score

```json
{
 "persona_id": "new_condition_during_prep",
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
   "expected": "married",
   "got": "married",
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "spouse_name",
   "expected": "Carmen Ortega",
   "got": "Carmen",
   "status": "wrong",
   "source": "veteran, chat 17:00 UTC"
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
   "expected": "Carmen Ortega, wife, 608-555-0171",
   "got": "Carmen Ortega, wife, 608-555-0171",
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
    "sleep apnea",
    "tinnitus"
   ],
   "got": [
    "sleep apnea",
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
 "field_accuracy": 0.95,
 "structured_questions": 21,
 "narrative_answers": 30,
 "clarifications": 4,
 "veteran_messages": 33,
 "cfile_prefilled": 1,
 "prefill_share": 0.045454545454545456,
 "turns_to_signed_poa": 12,
 "fee_expected": 30,
 "fee_got": 30,
 "kb_calls": 0,
 "kb_sourced": 0,
 "resumed_after": null,
 "ask_answer": {},
 "scripted_sent": true,
 "untested": false,
 "handoffs": [
  "intake",
  "claims_prep",
  "intake"
 ],
 "refused": {
  "intake": 1
 },
 "flag_decisions": [
  "reopen_intake"
 ],
 "flag_decision_expected": "reopen_intake",
 "flag_decision_correct": true,
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
   "input_tokens": 77273,
   "output_tokens": 3303,
   "cost_usd": 0.0093788,
   "latency_s": 23.740999999999996
  },
  "intake": {
   "calls": 150,
   "input_tokens": 1409950,
   "output_tokens": 69310,
   "cost_usd": 0.17565000000000006,
   "latency_s": 437.7660000000001
  },
  "claims_prep": {
   "calls": 17,
   "input_tokens": 234139,
   "output_tokens": 9469,
   "cost_usd": 0.0281484,
   "latency_s": 55.295
  },
  "support": {
   "calls": 4,
   "input_tokens": 13460,
   "output_tokens": 842,
   "cost_usd": 0.001767,
   "latency_s": 6.598000000000001
  },
  "simulator": {
   "calls": 32,
   "input_tokens": 0,
   "output_tokens": 0,
   "cost_usd": 0.022689699999999997,
   "latency_s": 0.0
  }
 },
 "cost_usd": 0.23763390000000006,
 "model_failures": 0
}
```
