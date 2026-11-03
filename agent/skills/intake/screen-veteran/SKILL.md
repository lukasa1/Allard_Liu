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
   field. Pass their words in `a`; code parses dates, branch, discharge and yes/no. If code can't
   read it, ask again more specifically, or pass the value as JSON (for service periods:
   `[{"branch": "army", "component": "active", "start": "2004-06", "end": "2010-05", "discharge": "honorable"}]`).
   If the veteran doesn't know, set `unknown`.
3. A veteran's reply can answer several fields: record each one.
4. When the checklist is empty, code moves the case to stage 2 (account opening): go on with
   `poa-and-fees` in the same turn.

## Stop rules (in code: you never decide them)

`record_answer` runs the firm's stop rules on every answer:
- not a veteran: the case is closed;
- already rated 100%: the case is closed;
- any service period other than honorable, bad conduct or dishonorable: an attorney decides (the
  case goes to a person);
- veteran status or the service periods unknown: a person on the team follows up. So ask again
  before you set `unknown` on these, and record a period's discharge too (a period without one
  stays on the checklist).

When `record_answer` reports a stop rule, thank the veteran, say kindly that the firm can't take
the case now (or that an attorney will review it and contact them), give no legal advice, and
finish. Every other tool is refused from then on.

## Questions from the veteran

Answer general questions with `kb_search` and only from its answer. If it has none, or the
question asks what to do, what they'll get or whether they'll win, say a person on the team will
follow up. Then go back to the checklist.
