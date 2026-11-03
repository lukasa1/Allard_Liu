---
name: screen-veteran
description: Pass 1: the eligibility screening before the 21-22a. Read to understand which questions pass 1 asks and why it stops.
---

# Screen the veteran (intake pass 1)

Ask only what the firm needs before the veteran signs: veteran status, service periods and
discharges (with a check for any other period), whether they filed before and their current
rating, and whether a private attorney or agent represented them (the fee).

Stop rules (code, `agent/intake/rules.py`): not a veteran -> close; rated 100% -> close; every
period other than honorable -> an attorney decides. The question order and wording are in
`agent/intake/data/questions.yaml` (stage `screen`); the controller asks them, the model only
reads answers and phrases questions. Everything the C-file can settle waits for pass 2.
