---
name: poa-and-fees
description: Pass 1, stage 2: fill and sign the 21-22a and the fee agreement, wait for the attorney's countersign, then fax the fee agreement to VA OGC.
---

# The 21-22a and the fee agreement (pass 1, stage 2)

Both documents are signed by the veteran's own click on a Sign card. You can't sign; you prepare,
show and explain.

## 1. VA Form 21-22a (appoints the firm's attorney)

1. `request_secure_info` for what the form needs and the secure form doesn't have yet (see
   "secure form on file" in your context): first_name, last_name, ssn, date_of_birth, branch,
   address.line1, address.city, address.state, address.zip; also middle_initial,
   va_file_number, phone and email. Say why in `purpose`. Never ask for these in chat.
2. Wait for the `[event] secure_form_submitted`. If values were rejected, open a new form for
   those fields.
3. Ask the veteran's own choice on two items, in plain words:
   - Item 20: may the attorney see VA records about treatment for drug or alcohol use, HIV or
     sickle cell anemia?
   - Item 22: may the attorney change the veteran's address with VA?
4. `fill_pdf(form="21-22a", fields={"authorize_7332_records": ..., "authorize_address_change": ...})`.
   The veteran sees the preview. Ask them to check it.
5. A correction: `update_draft(form="21-22a", changes=...)` (ID numbers only by a new secure form).
6. After a clear yes: `get_signature(form="21-22a")`. The first time it opens the signature pad;
   after the `[event] signature_saved`, call it again to show the Sign card.

## 2. The fee agreement and conditions of costs

1. After the 21-22a is signed (`[event] signed`), `fill_pdf(form="fee_agreement", fields={})`.
   The fee % comes from the firm's rules (your context's "Fee" line).
2. Explain it in plain words, from the document: the fee is a percentage of past-due benefits
   only if VA awards them (no win, no fee); at 20% or less VA withholds the fee and pays the
   attorney, above 20% the veteran pays the firm directly; costs are asked first; the veteran can
   end the representation at any time; nothing is guaranteed. For anything else, `kb_search`.
3. Ask for an explicit yes to the terms. Only then `get_signature(form="fee_agreement")`.

## 3. Countersign

When both are signed, code puts the case in `waiting_on_attorney`. Tell the veteran the attorney
is reviewing both documents and you'll file as soon as they countersign. You still answer their
messages meanwhile. `submit_va` and `efax_ogc` are refused until the countersign.

## 4. After the `[event] countersigned`

In the same turn, in this order: `submit_va(form="21-22a")`, then `efax_ogc(doc="fee_agreement")`
(VA's Office of General Counsel must get the fee agreement within 30 days of signing, 38 CFR
14.636(g)), then `submit_va(form="itf")` last (see `intent-to-file`): filing the ITF ends pass 1. A deadline task tracks it until
it is sent. Tell the veteran what was filed and that the firm now requests their VA claims file.
