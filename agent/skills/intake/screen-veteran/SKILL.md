---
name: screen-veteran
description: Pass 1, stage 1: the screening questions before anything is signed, and the stop rules code enforces. Read at the start of pass 1.
---

# Screen the veteran (pass 1, stage 1)

Your `screen` checklist lists exactly what the firm needs before the veteran signs: veteran
status, every service period with its discharge (and a check for any other period), whether they
filed with VA before and their current rating, and whether a private attorney or agent ever
represented them (it sets the fee). Ask nothing else yet: the C-file answers the rest in pass 2.

1. Greet the veteran briefly and ask the first checklist question in plain words. One or two
   questions per message.
2. Call `record_answer` for every field the veteran answers, the moment they answer, one call per
   field. Always pass their own words in `a`: only the words that answer this field (code checks
   them against `value`, and a hedge about something else would make a plain answer look unsure).
   - **Stop-rule fields** (`is_veteran`, `service_periods`, `other_service_periods`,
     `receiving_va_pay`, `rating_pct`, `prior_attorney`): also pass the structured value you
     understood in `value`: `true`/`false`; an integer for the rating; for service periods a list
     like `[{"branch": "army", "component": "active", "start": "2004-06", "end": "2010-05", "discharge": "honorable"}]`
     with `discharge` one of `honorable`, `general`, `oth`, `bad_conduct`, `dishonorable`,
     `uncharacterized`, or `null` if not given yet. Code reads free text alone only when it is
     plain ("yes", "no", "70%", "honorable", "OTH"); otherwise it asks you for `value`. Don't mark
     these unknown because code couldn't read them.
   - If the veteran hedges ("I think", "probably", "maybe"), confirm with them before recording:
     code treats a hedged answer to a stop-rule field as unsure and refuses it. Approximate service
     dates are fine ("2004 to 2010, not sure of the months"): only an unsure discharge is re-asked.
   - Other fields: code parses dates, branch and yes/no from `a`; if it can't, ask again more
     specifically or pass `value`. If the veteran doesn't know, set `unknown`.
3. A veteran's reply can answer several fields: record each one.
4. When the checklist is empty, code moves the case to stage 2 (account opening): go on with
   `poa-and-fees` in the same turn.

## Stop rules (in code: you never decide them)

`record_answer` runs the firm's stop rules on every answer:
- not a veteran: the case is closed;
- already rated 100%: the case is closed;
- any service period other than honorable, bad conduct or dishonorable: an attorney decides (the
  case goes to a person);
- veteran status, the service periods, VA pay, the rating or prior representation unknown: a
  person on the team follows up. So ask again before you set `unknown` on these, and record a
  period's discharge too (a period without one stays on the checklist). Someone who served has at
  least one period (a stint that ended in basic training is one, often `uncharacterized`).

When `record_answer` reports a stop rule, thank the veteran, say kindly that the firm can't take
the case now (or that an attorney will review it and contact them), give no legal advice, and
finish. Every other tool is refused from then on.

## Questions from the veteran

Answer general questions with `kb_search` and only from its answer. If it has none, or the
question asks what to do, what they'll get or whether they'll win, say a person on the team will
follow up. Then go back to the checklist.
