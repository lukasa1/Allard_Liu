---
name: case-status
description: Explain where the case stands in plain words, per stage, from the snapshot. Read when the veteran asks for news or what happens next.
---

# Case status

Use only the snapshot (in your context; `get_case` reloads it): `stage`, `side_state`, `why`,
`working_on_it_now`, `done` and `deadlines`. Start with what is done (with its dates), then say what happens next for the
situation below, in two or three warm sentences.

**Never promise a VA date or a time frame.** Say: "I can't predict VA's timing, but we'll message
you as soon as anything changes."

| Situation | What happens next |
|---|---|
| stage 3, waiting_on_va | "We've filed your VA Form 21-22a and your intent to file, which protects your start date for benefits. Next we ask VA for your claims file." |
| stage 4, claims prep reading, file not arrived | "We've asked VA for your claims file. When it arrives, our team reads it to prepare your case." |
| stage 4, claims file arrived | "We've received your VA claims file, and our team is reading it to prepare your case." |
| stage 4, file read, nobody working | "Our team has finished reading your claims file. We'll be in touch soon with a few follow-up questions." |
| stage 5 | "Your file is now with our attorney for review, and someone from our team will contact you about next steps." |
| needs_human | "A member of our team is handling your case personally and will contact you directly." Also `escalate`, so that person sees the message. |
| closed, rated 100% | "Your case with us is closed: since you're already rated at 100%, there's no increase for us to pursue right now. Someone will reach out if that changes." |
| closed, other | "Your case with us is closed." Give `why` in plain words if it is there, and say: "If something has changed, tell me and I'll pass it to our team." |

- "Did VA accept it?", "Is my claim approved yet?": say what we filed and when (from `done`), and
  that VA hasn't told us a decision; never guess one.
- "Has the attorney looked at my file yet?": only stage 5 means it is with the attorney.
- If `earlier_qa` shows you answered this before, stay consistent with it.

End with one `log_event` line, kind `status`: what was asked and what you said.
