"""Host-side chat guard that ships with the skill. A host agent should run every user message
through redact() before it reaches the model, so an SSN typed into chat never lands in the
model's context (the skill's secure form is the only intake path for those numbers)."""

import re

# SSNs (123-45-6789, 123 45 6789, 123456789) and 7- or 8-digit VA file numbers (older C-file
# numbers have 7). The separator must repeat, so ZIP+4 (53202-1234) and phone numbers pass through;
# an unseparated 7-digit phone number is hidden too, which is the safe side. Decimals (a cost
# of 0.0001234 in a trace) are not ID numbers.
_ID_NUMBER = re.compile(r"(?<!\d)(?<!\d\.)(?:\d{3}([- .])\d{2}\1\d{4}|\d{7,9})(?!\d)")

REDACTION_NOTE = "[app note: the user typed an ID number in chat; it was hidden from you]"


def redact(text: str) -> tuple[str, bool]:
    clean, n = _ID_NUMBER.subn("[number hidden for your privacy]", text)
    return clean, n > 0
