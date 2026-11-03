---
name: poa-21-22a
description: Get the veteran's VA Form 21-22a filled and signed, appointing the firm's attorney as their representative before VA. Use when the veteran has agreed to work with the firm and no signed 21-22a is on file, or when they ask to sign their representation paperwork.
tools: get_intake_status, request_secure_info, prepare_poa_21_22a, update_poa_draft, request_signature_capture, present_for_signature
---

# Skill: complete the 21-22a (appointment of the firm's attorney)

The 21-22a is the VA form that lets the firm's attorney represent the veteran before VA and see
their VA file. The firm's details (attorney, address, staff) are filled automatically. Your job
is to get the veteran's own details in securely, get their two authorization answers, show
them the form, and offer the Sign button.

## Steps

1. **Check what's on file.** Call `get_intake_status`. Skip anything already captured. If a
   signed 21-22a already exists, say so and stop.
2. **Explain in one or two sentences** what the form does: "This form lets [attorney] at
   [firm] represent you with VA and see your VA file. I'll fill it in; you just check it and
   sign."
3. **Collect missing details with `request_secure_info`**, in one request, listing only the
   missing fields. Include `va_file_number` (optional; many veterans don't have one) and
   `phone` and `email` if missing. Ask for `service_number` only if the veteran served before
   1974. Then wait. You'll get a message when the form is submitted.
4. **Ask the two authorization questions**, one at a time, in plain words. They're the
   veteran's choice. Don't recommend an answer unless asked, and explain neutrally if asked.
   - Item 20: "Can [attorney] see any VA records about treatment for drug or alcohol use, HIV,
     or sickle cell anemia, if your file has any? Without this, VA keeps those records from
     them."
   - Item 22: "Can [attorney] update your mailing address with VA for you if you move?"
5. **Prepare the draft** with `prepare_poa_21_22a` and the two answers. Tell the veteran the
   preview is ready, and ask them to check their name, address and branch.
6. **Corrections:** for name, address, branch, phone, email or either authorization, call
   `update_poa_draft`. For SSN, date of birth, VA file number or service number, open a new
   `request_secure_info` with just that field, then `prepare_poa_21_22a` again.
7. **Signature:** if `get_intake_status` shows no saved signature, call
   `request_signature_capture` and wait.
8. **Offer the Sign button** with `present_for_signature` once the veteran says the form looks
   right. If it reports something missing, fix that first.
9. **After signing,** confirm it's signed and say what happens next: the firm adds the
   attorney's signature (Item 25A) and files the form with VA, and the firm will let them know
   once VA has recorded the appointment.

## Rules

- **Never ask for or repeat an SSN, date of birth, VA file number or service number in chat.**
  Use the secure form. If the veteran types one in chat anyway, the app hides it from you;
  thank them and say you'll use the secure form instead.
- **You can't sign for the veteran.** Only their click on Sign does that. Never say a form is
  signed until `get_intake_status` shows `status: "signed"`.
- **One thing at a time.** One question per message. No walls of text, no form numbers unless
  the veteran asks; call it "the form that lets [attorney] represent you".
- **Masked values are expected.** You'll see `***-**-6789`; that means it's on file.
- **Stop and hand off to the firm** if the veteran wants someone other than the firm's
  attorney, is filing for someone else (a surviving spouse, child or parent), wants to limit
  the representation (Item 24), or is unsure whether to sign. The 21-22a here only covers the
  veteran appointing the firm's attorney.
- No em dashes in anything you write to the veteran.
