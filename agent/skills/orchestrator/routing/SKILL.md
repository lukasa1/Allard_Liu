---
name: routing
description: Who answers the veteran's message in each stage. Read when a message arrives and you need to know which subagent has the conversation.
---

# Routing

Routing is deterministic (code in `CaseSession.message`), following these rules:

- While intake (pass 1 or pass 2) or the POA step is working the case, every message goes to it,
  questions included: it has the conversation and answers from the Q&A tool.
- Otherwise (attorney_signoff, case_prep, and the terminal stages) messages go to customer
  support, which reads a snapshot of the case and never changes it.
- In every stage, crisis language is checked first: the veteran gets the Veterans Crisis Line and
  a person is alerted.
- A withdrawal of the representation or a request for a person, in any stage that isn't parked
  with a person already, stops the case for a person (by rule).
- Anything else that would change the case comes back from support as a flag for the
  orchestrator (see the `flags` skill).
