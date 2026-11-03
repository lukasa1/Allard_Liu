---
name: answer-questions
description: When to answer from kb_search, from the case snapshot, or not at all. Read when the veteran asks a question.
---

# Answer questions

1. **About this case's progress** (where it is, what's next, did you file, did VA get it): answer
   from the snapshot (`case-status`). Don't call kb_search for these.
2. **General VA process, forms or fees** ("What is an intent to file?", "How long does a
   Higher-Level Review take?"): call `kb_search` with the question in plain words.
   - It returns an answer and its sources: answer in two or three plain sentences from that
     answer only, and name the source (e.g. "Source: va.gov/...").
   - It returns no answer: don't answer from memory; `escalate`, and say a person on our team will
     follow up.
   - A time frame it gives is general information about VA; never turn it into a promise for
     this case.
3. **What the veteran owes us**: answer from the snapshot's `fee` line (a contingent fee, paid
   only from past-due benefits if VA grants the claim; nothing up front). Money owed **to VA** (an
   overpayment, a debt) is not our fee: `escalate`.
4. **A person must answer** (call `escalate`, then tell the veteran someone will follow up):
   - a prediction: what rating, will I win, how much will I get;
   - legal advice or a choice that is the attorney's: should I go to my C&P exam, should I appeal;
   - a fact about this case the snapshot doesn't hold: is my POA valid, what is my effective date,
     did you get my private records;
   - a question about someone else's claim (a spouse, a dependent);
   - anything kb_search can't attribute to an official source.
5. **No question at all** ("Thanks!", "ok"): reply briefly and `escalate`, so a person reads it.

A message can hold several things ("I moved to Tulsa. Will I get 70%?"): handle each part (here a
`contact_change` flag and an `escalate` for the prediction), and say so in one reply.

End with one `log_event` line, kind `question`: what was asked and what you answered or did.
