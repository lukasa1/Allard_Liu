---
name: intent-to-file
description: Filing the intent to file (VA Form 21-0966) right after the countersigned 21-22a, and how to explain it. Read before submit_va(form="itf") or when the veteran asks about their start date.
---

# Intent to file

An intent to file holds the veteran's potential start date for benefits for one year while the
claim is prepared, so they don't lose back pay.

1. File it in the same turn as the 21-22a, in this order: `submit_va(form="21-22a")`, then
   `efax_ogc(doc="fee_agreement")` (38 CFR 14.636(g): within 30 days of signing), then
   `submit_va(form="itf")`. All three wait for the attorney's countersign (the guard refuses before).
2. The result has the ITF date and when it expires. Pass 1 ends when both are filed (stage 3):
   tell the veteran the date that is protected, in plain words, with no promise about the outcome.
3. If the veteran asks what it means, explain it from `kb_search`.
