---
name: cfile-vs-intake
description: Compare the C-file with the intake record and decide what pass 2 must confirm. Read when the C-file and the veteran disagree.
---

# The C-file against intake

`agent/cfile/reconcile.py`: a service period the veteran didn't list, a different discharge on
the DD-214, an earlier VA decision, an earlier private representative, a different combined
rating. Each becomes a staff review task. In fetch/confirm modes the C-file's version is applied
(the DD-214 is the authority on discharge; the rating is only flagged, the code sheet may be old);
in confirm mode pass 2 also asks the veteran.
