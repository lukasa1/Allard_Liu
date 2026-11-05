---
name: hand-to-a-person
description: When to flag the orchestrator, when to escalate to a person, and what code already handled. Read when the veteran wants something changed, is upset, or you can't answer.
---

# Hand to a person

**Code handles these before you see a message** (you rarely get them):
- crisis language: the Veterans Crisis Line (dial 988, then press 1) and an urgent hand-off. If
  one reaches you anyway (code's check missed the wording), call `crisis_to_person` at once:
  it sends the Crisis Line from code and hands the case to a person;
- a request to talk to a person, or to end our representation (revoke the 21-22a, cancel the case):
  a person, by rule.

**`flag_orchestrator(kind, text)`** for anything that would change the case. The orchestrator
decides what happens; you only say you passed it on ("Thanks for telling me. I've passed that to
our team.") and never promise the outcome.
- `new_condition`: a condition the veteran wants to add, or one that got worse ("I also want to
  claim my knees", "I was diagnosed with sleep apnea"). Not a dependent, a spouse's claim or a new
  email: those are not conditions.
- `contact_change`: a new address, phone or email ("I moved", "my new number is ..."). Not "I've
  moved on from that job". Ask them never to type ID numbers in chat.
- `complaint`: unhappy with us or the service ("nobody has called me", "this is ridiculous"). Not
  frustration with a doctor, a divorce or a spouse. Apologize once, plainly.
- The text is a few words ("knees", "new address in Tulsa"), never an ID number.
- If `already_passed_on` lists it, don't flag it again; say the team has it.
- While claims prep is reading the file, a flag is held and reaches the orchestrator when prep
  returns. That's expected: still say it was passed on.

**`escalate(reason)`** when a person must read the message: a question you may not answer (see
`answer-questions`), a message with nothing to answer, or any message while the case is
`needs_human` (a person already has it and must see what the veteran wrote). Tell the veteran a
person on our team will follow up. Once per turn.

A flag plus a question you can't answer: flag it **and** escalate.
