---
name: routing
description: Who answers the veteran's messages and who gets each event, as code routes them. Read when you need to know why a message or event did or did not reach you.
---

# Routing (done in code, not by you)

You never route messages; code does, on every message, before any model:

1. **Crisis language** in any stage: the veteran gets the Veterans Crisis Line from code, a staff
   task is created, the case goes to `needs_human`, and you wake on `escalated`.
2. **A request for a person, or to end the representation**, while the case isn't parked: a
   person is asked by rule, the case goes to `needs_human`, and you wake on `escalated`.
3. Otherwise:
   - **intake owns the case** (pass 1 or pass 2, including while it waits for the attorney's
     countersign): the message goes to intake, questions included;
   - **claims prep is reading the C-file, or nobody owns the case, or it is parked**: the message
     goes to customer support, which reads the case but never changes it.

Events: a card action or a staff action goes to intake while intake owns the case; otherwise it
wakes you. Support's flags wake you, except while claims prep runs: then they are held and come
to you with claims prep's result, in the same wake.
