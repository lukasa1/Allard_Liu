# colloquial_conditions (cfile)

Describes every condition in everyday words that are not in the code's synonym table (agent/intake/conditions.py), so the model itself must turn them into the VA-style names. Keep the phrases (and the stories' wording) out of that table.

Behaviours: colloquial_conditions

## Conversation

**Agent**: [orchestrator] Welcome. We're glad to help with your VA claim. Our intake team will be in touch shortly to start with a few screening questions.

**Agent**: [intake] Hello, thank you for reaching out. I'm here to help you get started. To begin, have you served in the U.S. military, whether on active duty, in the Reserves, or in the National Guard?

**Veteran**: Yes, I served in the Army on active duty from 2004 to 2010. Honorable discharge.

**Agent**: [intake] Thank you, that helps us a lot. Besides that Army active-duty period, did you ever serve in the Reserves or National Guard, or in any other stint? And have you filed a claim with VA before, even a long time ago?

**Veteran**: Nope, just the Army active duty, 2004 to 2010. And no, I've never filed a VA claim before.

**Agent**: [intake] Thank you, that helps a lot. One more question: has an attorney or a law firm ever helped you with a VA claim before? A VSO like the DAV or VFW doesn't count.

**Veteran**: Nope, no attorney or law firm before. I've only ever dealt with my VSO, and never filed anything on my own.

**Agent**: [intake] Thank you, that's very helpful. Just to double-check: have you ever gotten a letter from the VA about a claim, a decision or a rating, even many years ago?

**Veteran**: No, I've never gotten a letter from the VA about a claim or a rating. Like I said, this is my first time filing anything.

**Agent**: [intake] Thank you, that was very helpful, and I know those questions can feel like a lot. Your answers are saved. The next step is a short secure form, opened separately from this chat, where you can enter your identifying details. It's needed to prepare your power-of-attorney form (VA Form 21-22a) and the fee agreement. Please don't type those numbers into this chat. Once you've submitted it, I'll walk you through both documents to review and sign.

_App_: [veteran fills the secure form: address.city, address.line1, address.line2, address.state, address.zip, branch, date_of_birth, email, first_name, last_name, middle_initial, phone, service_number, ssn, va_file_number; errors: none]

**Agent**: [intake] Thank you, Kevin. Your details were received safely. Before I prepare your power-of-attorney form, I need two choices from you, in your own words:

1. Would you like the attorney to be able to see VA records about treatment for drug or alcohol use, HIV, or sickle cell anemia? (yes or no)
2. Would you like the attorney to be able to change your mailing address with VA if needed? (yes or no)

**Veteran**: Yes to both. The attorney can see those records and update my mailing address if needed.

**Agent**: [intake] Thank you, Kevin. Your power-of-attorney form (VA Form 21-22a) is ready to review in the preview. It has your yes to both choices: the attorney can see those health records and can update your mailing address with VA if needed. Please check your name, address and those two answers. If anything is wrong, tell me what to change. When it all looks right, let me know and I'll bring up the signing card for you.

**Veteran**: Yeah, I looked it over. My name, 88 Elm Street in Killeen, and both yes answers are right. It looks right to me, go ahead and bring up the signing card.

**Agent**: [intake] Thank you, Kevin. The signing pad for your power-of-attorney form (VA Form 21-22a) is open now. Please draw or type your signature on it and save. Once it's saved, I'll bring up the fee agreement for you to review next.

_App_: [veteran draws and saves a signature]

**Agent**: [intake] Thank you, Kevin. Your signature is saved. The signing card for your power-of-attorney form (VA Form 21-22a) is on your screen now. Please click it yourself to sign the form. Once that's done, I'll bring up the fee agreement for you to review.

_App_: [veteran clicks Sign on the 21-22a]

**Agent**: [intake] Thank you, Kevin. Your power-of-attorney form (VA Form 21-22a) is signed and saved. Next is the fee agreement, which is ready for you to review on your screen now.

Here is the plain version. The firm's fee is 30% of any past-due benefits, and only if VA awards them. If VA wins nothing, there is no fee. Because the fee is above 20%, you pay the firm directly from the award. Costs are asked first, you can end the representation at any time, and nothing is guaranteed.

Please read the preview. Do you agree to these terms? If you have a question about any part of it, tell me and I'll look it up or have a person on the team follow up.

**Veteran**: Yeah, I agree to the fee agreement. Thanks for explaining it in plain terms.

**Agent**: [intake] Thank you, Kevin. The fee agreement's signing card is on your screen now. Please click it yourself to sign. Once it's saved, I'll let you know what happens next.

_App_: [veteran clicks Sign on the fee_agreement]

**Agent**: [intake] Thank you, Kevin. Your fee agreement is signed and saved, and so is your power-of-attorney form (VA Form 21-22a). The attorney is reviewing both documents now. As soon as the attorney countersigns them, we'll file them with VA and send the fee agreement to VA's Office of General Counsel. I'll message you when that's done. If you have any questions in the meantime, just ask me here.

_App_: [simulated attorney countersigns both documents]

**Agent**: [intake] Kevin, good news: the attorney has countersigned your power-of-attorney form and fee agreement, and both are now filed with VA.

Here is what was done:
- Your VA Form 21-22a was filed with VA (confirmation VA-VAGSKJRXYJ).
- Your fee agreement was sent to VA's Office of General Counsel (fax confirmation FAX-ELAJDGRXOR).
- Your intent to file was submitted (confirmation VA-YRGJTIYRVQ). It protects a potential start date of November 3, 2026 for one year, through November 3, 2027. This holds your place while your claim is prepared. It does not promise any particular result.

Next, the firm will request your VA claims file so the team can review your records. A person on the team may follow up with you about that. If you have questions in the meantime, ask me here.

**Agent**: [orchestrator] Kevin, your forms are filed with VA: the 21-22a, the fee agreement (sent to VA's Office of General Counsel), and the intent to file, which holds your place for one year. We have started the review of your VA claims file. We will be in touch if we need anything from you.

**Agent**: [intake] Thank you, Kevin. Two quick questions to finish the details. First, is this a claim for death benefits for a family member, such as DIC or accrued benefits? Second, did you retire from the military?

**Veteran**: No, this isn't for a family member, it's my own claim. And no, I didn't retire, I got out in May 2010.

**Agent**: [intake] Thank you, Kevin. Thanks for those answers. Two more quick ones. Are you currently earning more than $1,600 a month from work? And do you currently receive Social Security benefits?

**Veteran**: Yeah, I'm working and earning more than $1,600 a month. And no, I don't get Social Security benefits.

**Agent**: [intake] Thank you, Kevin. Two more quick questions. We work with a group of partner law firms. If one of our attorneys can't help, may we share your contact information with a partner firm? And were you exposed to anything like Agent Orange, burn pits, Camp Lejeune water, radiation or Gulf War hazards? List any that apply, or say none.

**Veteran**: Yeah, you can share my contact info with a partner firm if needed. And I was exposed to burn pits in Iraq, that's the only one I know of.

**Agent**: [intake] Thank you, Kevin. Thanks for telling us about the burn pit exposure. Two more quick questions. Would you like to talk with our Social Security benefits department as well? And what's your marital status: single, married, divorced, separated, or widowed?

**Veteran**: No, I don't need the Social Security department, I don't get those benefits. I'm married.

**Agent**: [intake] Thank you, Kevin. I've noted that you're married. Two more quick questions. If there's ongoing litigation about the burn pit exposure, would you like an attorney to contact you about it? And do you have any children under 18?

**Veteran**: No, I don't have any litigation going on about burn pits, so no need for that. And yes, I've got kids under 18.

**Agent**: [intake] Thank you, Kevin. I've noted that you have children under 18. Two more quick ones. What's your spouse's name? And which medical conditions would you like our attorneys to help you with?

**Veteran**: My wife's name is Amy Doyle. For the conditions, my ears buzz all the time, the low part of my spine, above my hips, has been wrecked since that fall, and my wife says I quit breathing in my sleep.

**Agent**: [intake] Thank you, Kevin. I've noted Amy Doyle as your wife, and tinnitus, lumbar strain and sleep apnea as the conditions you'd like help with. Are there any other medical conditions you're dealing with, service-connected or not, such as mental health, heart problems, high blood pressure, cancer or diabetes? Say none if there aren't.

**Veteran**: Nope, none of those. Those three are the ones I've got. Oh, and I'm not sure what you'd call the ear thing officially, but it's the buzzing that never stops.

**Agent**: [intake] Thank you, Kevin. That's helpful, and I've noted the three conditions you want help with. Who is your next of kin? Please give their name, their relationship to you, and a phone number.

**Veteran**: Amy Doyle, she's my wife, and her number is 254-555-0131.

**Agent**: [intake] Thank you, Kevin. I've noted Amy Doyle as your next of kin. Last one for this part: how did you hear about us?

**Veteran**: A friend told me about you guys.

**Agent**: [intake] Thanks, Kevin. Let's talk a little more about your ears. What symptoms do you have from your tinnitus? At their worst, how bad do the symptoms get? Describe a flare-up or a bad day. And when did the buzzing start: during service, right after, or gradually over time?

**Veteran**: It's a constant high-pitched buzz in both ears. On bad days it's so loud I can't concentrate or fall asleep. It started during service, after a convoy hit an IED near Baghdad in 2007, and it never went away after I got out.

**Agent**: [intake] Thank you, Kevin. That helps me understand what the buzzing is like. How often do you notice it: daily, weekly or monthly? And where were you stationed or deployed when it started?

**Veteran**: Every day, all day. It started at Camp Taji, Iraq, when I was there in 2007.

**Agent**: [intake] Thank you, Kevin. Camp Taji in 2007 is helpful to know. When the buzzing started there, were you on a base, in a vehicle, or out in the field? And since you got out, has the tinnitus stayed about the same, or has it gotten better or worse?

**Veteran**: Mostly in a vehicle, on convoys through the combat zone. And it never went away after I got out, it's gotten a little worse.

**Agent**: [intake] Thank you, Kevin. That gives me a clear picture of the convoys. Next, what were the conditions around you when the buzzing started, such as the noise, cramped spaces, heat or dust, or anything hazardous in the air? Then, what event or exposure do you think led to it, and what happened? And did you report the buzzing or get any treatment for it back then? If not, you can tell me why.

**Veteran**: Mostly constant engine noise, gunfire and explosions, and we usually didn't have good hearing protection. I think the IED blast in 2007 plus years of truck and weapons noise is what did it. No, I didn't report it or get treated back then. Everyone's ears buzzed and I didn't want to get pulled off missions.

**Agent**: [intake] Thank you, Kevin. That helps me understand what those years were like. How does the tinnitus affect your ability to work? And have you missed work, or been less productive, because of it?

**Veteran**: It's hard to follow what people say at work over the buzzing. And I've left early a few times when it gets really bad, maybe once a month.

**Agent**: [intake] Thank you, Kevin. That helps me see how the buzzing gets in the way at work. How does the tinnitus affect your daily life, your relationships or how you feel day to day? And for your ears, how were things before your military service compared to now?

**Veteran**: I avoid restaurants and parties because it's hard to hear anyone over the buzzing, and I sleep with a fan on just to drown it out. Before the Army I had no hearing problems at all.

**Agent**: [intake] Thank you, Kevin. That helps me understand how much the buzzing affects your work, sleep and time out with people. Is there anything else you want the VA to know about your tinnitus? And turning to your back, what symptoms do you have from your lumbar strain?

**Veteran**: Nope, I think that covers the ears. For my back, it's a sharp pain low down in my spine, and it gets stiff in the morning. Some days I can't even bend over to tie my shoes.

**Agent**: [intake] Thank you, Kevin. That helps me understand what your back is like day to day. On your bad days, how much does the pain and stiffness get in the way? When did the back symptoms start: during service, right after, or gradually over time? And how often do you have them: daily, weekly or monthly?

**Veteran**: Bad days, I can barely bend over to tie my shoes, and I'm stiff for a while every morning. It started after I fell about six feet off a truck bed onto concrete at Fort Hood in 2008, and it's gotten worse every year since. It's pretty much daily.

**Agent**: [intake] Thank you, Kevin. I'm sorry about that fall at Fort Hood, and I can see how much the mornings and the bad days take out of you. When the back trouble started, were you on a base, in the field, in a vehicle, or somewhere else? And what were the conditions around you then, like the load you were carrying, the work, or the weather?

**Veteran**: I was on the base at Fort Hood, in the motor pool. It was heavy lifting all day, hauling parts and gear, and I was on my feet in the heat most of the time.

**Agent**: [intake] Thank you, Kevin. Heavy lifting and being on your feet in the heat all day would wear anyone down. What event or injury in service do you think led to your back trouble, and what happened? And did you report the back problem or get any treatment for it at the time? If not, you can tell me why.

**Veteran**: I already told you, I fell about six feet off a truck bed onto concrete at Fort Hood in 2008. I went to sick call after that and they gave me Motrin, but that was about it. I had to give up warehouse work after that, and I miss a few days a month because of it.

**Agent**: [intake] Sorry, Kevin, I didn't mean to make you repeat the fall. Thank you for telling me about sick call and the Motrin, and about having to leave warehouse work. How does your back affect your daily activities, your relationships or how you feel day to day? And for your back, how were things before your military service compared to now?

**Veteran**: I can't pick up my kids anymore, and I've had to give up a lot of what I used to do. Before the Army I was an athlete, so my back was fine back then. It's a whole different story now.

**Agent**: [intake] Thank you, Kevin. That helps me understand how much your back has changed, especially being unable to pick up your kids. Is there anything else you want the VA to know about your lumbar strain? And for the sleep apnea you mentioned, what symptoms do you have from it?

**Veteran**: Nope, I think the back stuff covers it. For the sleep apnea, I'm loud snoring and I wake up gasping, sometimes choking five or six times a night. My wife says she sleeps in another room because of it, and I'm wiped out the next day.

**Agent**: [intake] Thank you, Kevin. Waking up gasping and choking, and your wife sleeping in another room, sounds exhausting. How often do you have these sleep apnea symptoms: daily, weekly or monthly? And when did they start: during service, right after, or gradually over time?

**Veteran**: Every night, pretty much. It started in Iraq, at Camp Taji, when guys in my tent said I stopped breathing in my sleep. It's gotten worse since I got out.

**Agent**: [intake] Thank you, Kevin. Every night, and worse since you got out, is a lot to carry. When the sleep apnea is at its worst, what does a bad night look like? And when it started at Camp Taji, were you in a base, in a vehicle, or in a combat zone?

**Veteran**: On bad nights I'm waking up choking five or six times, and I'm wrecked the next day. I nod off at work in the afternoon, and I've been sent home a couple times for falling asleep. As for Camp Taji, I was on the base, sleeping in tents and barracks.

**Agent**: [intake] Thank you, Kevin. Waking up choking and then being sent home from work is a lot to carry. When the sleep apnea began at Camp Taji, what were the conditions around you, like noise, cramped spaces, extreme weather or hazardous materials? And do you know what event, injury or exposure in service you think led to it? Please tell me in your own words.

**Veteran**: Mostly dust and smoke, and sleeping in tents with short, broken sleep when we were on night missions. I think years of bad sleep and breathing that dust and smoke is what caused it. I never went to medical for it, so there's no record.

**Agent**: [intake] Thank you, Kevin. Dust, smoke and broken sleep on night missions is a lot to carry, and I've noted that you never went to medical for it. Have you missed work or been less productive because of your sleep apnea? And how does it affect your daily activities, your relationships or your quality of life?

**Veteran**: Yeah, I've nodded off at work in the afternoons, and I've been sent home a couple times for falling asleep. My wife sleeps in another room because of the noise, and I'm wiped out most days.

**Agent**: [intake] Thank you, Kevin. Nodding off at work and being sent home is hard, and I've noted how it affects your wife and your days. Two last questions about your sleep apnea: before your military service, how were things with your sleep compared to now? And is there anything else you want the VA to know about it?

**Veteran**: I slept fine before the Army, no problems at all. And nope, I think the sleep stuff covers it. I've put on weight since my back started acting up, and it's gotten worse since I got out.

**Agent**: [intake] Thank you, Kevin. I've saved everything you shared about your back, tinnitus and sleep apnea, in your own words. Your file is complete on our end, and the attorney reviews it next. A person on the team will follow up with you from there.

## Decisions and moves

- #2 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 1: screen the veteran (every screening field answered or unknown, stop rules checked), sign the 21-22a and fee agreement, file the 21-22a and intent to file, and fax the fee agreement."}
- #5 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #6 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #9 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #10 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #13 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #14 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #17 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #18 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #20 `stage_changed` by derive: {"from": 1, "to": 2, "actor": "derive", "reason": "exit criteria met"}
- #23 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #26 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #28 `refused` by intake: {"tool": "record_answer", "args": {"q": "authorize_7332_records", "a": "Yes to both. The attorney can see those records.", "value": true, "unknown": false}, "reason": "no checklist field 'authorize_7332_records': use an id from your checklist"}
- #30 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #31 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #34 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #39 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #43 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #44 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": "waiting_on_attorney", "actor": "derive", "reason": null}
- #48 `side_state_changed` by derive: {"from": "waiting_on_attorney", "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #50 `stage_changed` by derive: {"from": 2, "to": 3, "actor": "derive", "reason": "exit criteria met"}
- #52 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": "waiting_on_va", "actor": "derive", "reason": null}
- #53 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Pass 1 complete (stage 3): 21-22a filed (VA-VAGSKJRXYJ), fee agreement faxed to VA OGC (FAX-ELAJDGRXOR), intent to file filed (VA-YRGJTIYRVQ, itf_date 2026-11-03, expires 2027-11-03).", "wrote": ["21-22a filed", "fee_agreement faxed to VA OGC", "itf filed"
- #54 `stage_changed` by handoff: {"from": 3, "to": 4, "actor": "handoff", "reason": "Pull and read the veteran's C-file, prefill the intake answers it settles, and write and verify the face note; raise any face-note flags as open tasks."}
- #55 `handoff` by orchestrator: {"to": "claims_prep", "goal": "Pull and read the veteran's C-file, prefill the intake answers it settles, and write and verify the face note; raise any face-note flags as open tasks."}
- #56 `side_state_changed` by derive: {"from": "waiting_on_va", "to": null, "actor": "derive", "reason": null}
- #59 `side_state_changed` by derive: {"from": null, "to": "waiting_on_va", "actor": "derive", "reason": null}
- #60 `subagent_result` by claims_prep: {"result": {"agent": "claims_prep", "finished": "C-file pulled and read (DD-214 p.1, firm 21-22a p.2). Five facts recorded, face note rendered and verified with no uncertain lines, prefill run.", "wrote": ["F1 dob", "F2 service_period (army active 2004-06 to 2010-05)", "F3 discharge (honorable)", "F
- #61 `task_created` by orchestrator: {"text": "Check face note line 7 for the veteran's case f6f0f11ee581: it reads 'SC at time of signing Law Firm - 0% (no rating decision in the C-file)'. The 'Law Firm' text looks misplaced; confirm or correct the line before attorney review."}
- #62 `handoff` by orchestrator: {"to": "intake", "goal": "Pass 2 (stage 4, close-gaps): ask the veteran only about filed_before, prior_attorney and prior_attorney_name, since the C-file settled the rest; confirm there are no C-file conflicts; then ask the narrative prompts in the pass-2 checklist."}
- #63 `side_state_changed` by derive: {"from": "waiting_on_va", "to": null, "actor": "derive", "reason": null}
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
- #165 `side_state_changed` by derive: {"from": null, "to": "waiting_on_veteran", "actor": "derive", "reason": null}
- #166 `side_state_changed` by derive: {"from": "waiting_on_veteran", "to": null, "actor": "derive", "reason": null}
- #168 `stage_changed` by derive: {"from": 4, "to": 5, "actor": "derive", "reason": "exit criteria met"}
- #170 `subagent_result` by intake: {"result": {"agent": "intake", "finished": "Pass 2 (close-gaps) complete: checklist empty, case at stage 5 (ready for attorney review).", "wrote": ["narrative:sleep apnea:h15", "narrative:sleep apnea:h16"], "needs": ["Attorney review of the stage 5 file", "Attorney or staff to resolve the face-note 

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
  "value": "Kevin",
  "source": "secure form",
  "unknown": false
 },
 "last_name": {
  "value": "Doyle",
  "source": "secure form",
  "unknown": false
 },
 "street": {
  "value": "** *** **reet",
  "source": "secure form",
  "unknown": false
 },
 "city": {
  "value": "Killeen",
  "source": "secure form",
  "unknown": false
 },
 "state": {
  "value": "TX",
  "source": "secure form",
  "unknown": false
 },
 "zip": {
  "value": "*6541",
  "source": "secure form",
  "unknown": false
 },
 "cell_phone": {
  "value": "******0119",
  "source": "secure form",
  "unknown": false
 },
 "email": {
  "value": "k***@example.com",
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
 "retired": {
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
 "exposures": {
  "value": [
   "burn pits (Iraq)"
  ],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "ssa_interest": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "marital_status": {
  "value": "married",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "litigation_contact": {
  "value": false,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "children_under_18": {
  "value": true,
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "spouse_name": {
  "value": "Amy Doyle",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "claim_conditions": {
  "value": [
   "tinnitus",
   "lumbar strain",
   "sleep apnea"
  ],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "other_conditions": {
  "value": [],
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "next_of_kin": {
  "value": "Amy Doyle, she's my wife, and her number is 254-555-0131.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "heard_about": {
  "value": "A friend told me about you guys.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h02": {
  "value": "It's a constant high-pitched buzz in both ears.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h03": {
  "value": "On bad days it's so loud I can't concentrate or fall asleep.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h04": {
  "value": "It started during service, after a convoy hit an IED near Baghdad in 2007, and it never went away after I got out.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h05": {
  "value": "Every day, all day.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h07": {
  "value": "It started at Camp Taji, Iraq, when I was there in 2007.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h06": {
  "value": "And it never went away after I got out, it's gotten a little worse.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h08": {
  "value": "Mostly in a vehicle, on convoys through the combat zone.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h09": {
  "value": "Mostly constant engine noise, gunfire and explosions, and we usually didn't have good hearing protection.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h10": {
  "value": "I think the IED blast in 2007 plus years of truck and weapons noise is what did it.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h11": {
  "value": "No, I didn't report it or get treated back then. Everyone's ears buzzed and I didn't want to get pulled off missions.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h12": {
  "value": "It's hard to follow what people say at work over the buzzing.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h13": {
  "value": "I've left early a few times when it gets really bad, maybe once a month.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h14": {
  "value": "I avoid restaurants and parties because it's hard to hear anyone over the buzzing, and I sleep with a fan on just to drown it out.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h15": {
  "value": "Before the Army I had no hearing problems at all.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:tinnitus:h16": {
  "value": "Nope, I think that covers the ears.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h02": {
  "value": "For my back, it's a sharp pain low down in my spine, and it gets stiff in the morning. Some days I can't even bend over to tie my shoes.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h04": {
  "value": "It started after I fell about six feet off a truck bed onto concrete at Fort Hood in 2008, and it's gotten worse every year since.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h03": {
  "value": "Bad days, I can barely bend over to tie my shoes, and I'm stiff for a while every morning.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h05": {
  "value": "It's pretty much daily.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h06": {
  "value": "It's gotten worse every year since.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h07": {
  "value": "It started after I fell about six feet off a truck bed onto concrete at Fort Hood in 2008.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h08": {
  "value": "I was on the base at Fort Hood, in the motor pool.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h09": {
  "value": "It was heavy lifting all day, hauling parts and gear, and I was on my feet in the heat most of the time.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h10": {
  "value": "I already told you, I fell about six feet off a truck bed onto concrete at Fort Hood in 2008.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h11": {
  "value": "I went to sick call after that and they gave me Motrin, but that was about it.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h12": {
  "value": "I had to give up warehouse work after that.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h13": {
  "value": "I miss a few days a month because of it.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h14": {
  "value": "I can't pick up my kids anymore, and I've had to give up a lot of what I used to do.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h15": {
  "value": "Before the Army I was an athlete, so my back was fine back then. It's a whole different story now.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:lumbar strain:h16": {
  "value": "Nope, I think the back stuff covers it.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h02": {
  "value": "I'm loud snoring and I wake up gasping, sometimes choking five or six times a night. My wife says she sleeps in another room because of it, and I'm wiped out the next day.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h05": {
  "value": "Every night, pretty much.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h04": {
  "value": "It started in Iraq, at Camp Taji, when guys in my tent said I stopped breathing in my sleep.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h07": {
  "value": "It started in Iraq, at Camp Taji, when guys in my tent said I stopped breathing in my sleep.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h06": {
  "value": "It's gotten worse since I got out.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h03": {
  "value": "On bad nights I'm waking up choking five or six times, and I'm wrecked the next day.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h08": {
  "value": "As for Camp Taji, I was on the base, sleeping in tents and barracks.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h12": {
  "value": "I nod off at work in the afternoon, and I've been sent home a couple times for falling asleep.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h09": {
  "value": "Mostly dust and smoke, and sleeping in tents with short, broken sleep when we were on night missions.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h10": {
  "value": "I think years of bad sleep and breathing that dust and smoke is what caused it.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h11": {
  "value": "I never went to medical for it, so there's no record.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h13": {
  "value": "Yeah, I've nodded off at work in the afternoons, and I've been sent home a couple times for falling asleep.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h14": {
  "value": "My wife sleeps in another room because of the noise, and I'm wiped out most days.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h15": {
  "value": "I slept fine before the Army, no problems at all.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 },
 "narrative:sleep apnea:h16": {
  "value": "Nope, I think the sleep stuff covers it. I've put on weight since my back started acting up, and it's gotten worse since I got out.",
  "source": "veteran, chat 17:00 UTC",
  "unknown": false
 }
}
```

## Face note

```
FA 30%; No prior rep  [firm record; none in the C-file]
********************************************
DOB: 08/17/82  [p. 1]
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
- [staff] Check face note line 7 for the veteran's case f6f0f11ee581: it reads 'SC at time of signing Law Firm - 0% (no rating decision in the C-file)'. The 'Law Firm' text looks misplaced; confirm or correct the line before attorney review.

## Score

```json
{
 "persona_id": "colloquial_conditions",
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
   "expected": "Amy Doyle",
   "got": "Amy Doyle",
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "children_under_18",
   "expected": true,
   "got": true,
   "status": "correct",
   "source": "veteran, chat 17:00 UTC"
  },
  {
   "field": "next_of_kin",
   "expected": "Amy Doyle, wife, 254-555-0131",
   "got": "Amy Doyle, she's my wife, and her number is 254-555-0131.",
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
    "lumbar strain",
    "sleep apnea",
    "tinnitus"
   ],
   "got": [
    "lumbar strain",
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
    "burn pits (iraq)"
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
   "source": "veteran, chat 17:00 UTC; months: DD-214, C-file p. 1; veteran, chat 17:00 UTC"
  }
 ],
 "field_accuracy": 1.0,
 "structured_questions": 21,
 "narrative_answers": 45,
 "clarifications": 0,
 "veteran_messages": 33,
 "cfile_prefilled": 1,
 "prefill_share": 0.045454545454545456,
 "turns_to_signed_poa": 9,
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
   "input_tokens": 86929,
   "output_tokens": 4138,
   "cost_usd": 0.0107619,
   "latency_s": 27.176000000000002
  },
  "intake": {
   "calls": 174,
   "input_tokens": 1816312,
   "output_tokens": 97000,
   "cost_usd": 0.23013120000000006,
   "latency_s": 575.1049999999994
  },
  "claims_prep": {
   "calls": 12,
   "input_tokens": 154151,
   "output_tokens": 6741,
   "cost_usd": 0.0187856,
   "latency_s": 38.166000000000004
  },
  "simulator": {
   "calls": 33,
   "input_tokens": 0,
   "output_tokens": 0,
   "cost_usd": 0.024915299999999994,
   "latency_s": 0.0
  }
 },
 "cost_usd": 0.28459400000000007,
 "model_failures": 0
}
```
