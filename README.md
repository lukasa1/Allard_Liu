# VA claims agent

A CS329Z class project: an AI system that helps a law firm (called "the law firm" here) represent
veterans before VA. An **orchestrator** keeps each case moving and hands it to one sub-agent at a
time:

| Sub-agent | What it does | Status |
|---|---|---|
| **Intake** (`agent/intake/`) | Pass 1: screens the veteran, gets VA Form 21-22a and the fee agreement signed, files them after the attorney countersigns. Pass 2: asks only what the C-file didn't settle. | built |
| **Claims prep** (`agent/claims_prep/`) | Reads the C-file, records typed facts with page citations, prefills intake, writes and verifies the face note. | built |
| **Customer support** (`agent/support/`) | Answers the veteran while nobody else is talking to them; read-only; flags changes to the orchestrator. | built |
| **Claims investigation** | 526EZ / 0995 / 0996 / 4142, attorney-approved filing. | not built (after the midpoint) |

Every agent runs on **Claude Haiku 5.5 through OpenRouter** (`openrouter/anthropic/claude-haiku-5.5`).
VA, filing, eFax and the attorney are simulated. **Synthetic data only**: every veteran, C-file
and number in the repo is made up, and `config/representative.json` holds placeholders.

## Quick start

```bash
uv sync
uv run pytest -q                 # about a minute, no key, no network (scripted fake model)
cp .env.example .env             # set OPENROUTER_API_KEY for anything live
uv run intake serve              # the web demo: http://localhost:8000
uv run intake serve --scripted   # the same demo with no model: no key, no cost (D26)
uv run intake --help             # serve | simulate | eval | support-eval | personas
```

Without `OPENROUTER_API_KEY` the server still starts and the page says to set it; `simulate`,
`eval` and `support-eval` exit with the same message. There are no offline agents (D7), except
the scripted demo (D26).

## Architecture

```
web chat / cards / staff panel ──▶ runtime (agent/runtime.py) ──▶ code checks on every message
                                     │                               (redact, crisis, a person, withdraw)
                                     ├─ route (D1): intake if it owns the case, else support
                                     ├─ wakes ──▶ orchestrator ── run_intake / run_prep / move_stage / staff_task
                                     └─ queued turns: one worker per case (+ a background worker for claims prep)
   every agent turn = one dspy.ReAct run (agent/harness.py), tools via the guarded registry
   every change ──▶ store.update_case (patch, under a lock) ──▶ stages.settle (derive the stage)
   every reply and card ──▶ outbox ──▶ the page polls GET /api/cases/<id>/updates?since=<seq>
```

### Stage table (`agent/stages.py`)

| Stage | Owner | Reached when (checked in code) |
|---|---|---|
| 1 Screening (pass 1) | intake | case created |
| 2 Account opening (pass 1) | intake | every screening field answered or unknown, no stop rule fired |
| 3 Filed (pass 1 ends) | intake → orchestrator | 21-22a submitted **and** intent to file filed (the fee agreement goes to OGC in the same turn; a 30-day task tracks it) |
| 4 C-file requested | claims prep, then intake pass 2 | only by the orchestrator's `run_prep` handoff |
| 5 Gaps closed: **ready for attorney review** (the demo's end) | attorney | claims prep done and every pass-2 field filled or unknown |
| 6 File review done | — | not reachable yet (needs claims investigation) |

Side states, entered only through the guard: `waiting_on_veteran`, `waiting_on_attorney` (the
owner keeps the case), `waiting_on_va`, `needs_human` and `closed`. Code derives the stage after
every tool call and event. Moves inside one owner's stages are automatic; a move to another owner
only by a handoff; the orchestrator's `move_stage` covers side states and one move back, from stage 5
to stage 4 (D11, D20). That move leaves a reopen item that pass 2 must resolve. Every
refused move is logged and its reason goes back to the model.

### Runtime protocol

- **One turn = one `dspy.ReAct` run** per message or event. A turn's `reply` output is the only
  way it talks to the veteran (this is `ask_veteran`); `result` (a `SubagentResult`) is kept only
  when the agent's stop rule holds.
- **Handoffs are asynchronous** (D9): `run_intake(goal)` / `run_prep(goal)` set the owner and queue
  the sub-agent's first turn; its result later wakes the orchestrator as a `subagent_result`
  event. The orchestrator wakes only on `case_opened`, `subagent_result`, `support_flag`,
  `escalated` and staff events nobody owns; chat messages never wake it.
- **One case-owning sub-agent at a time** (A3). Support is read-only and may run while claims prep
  works in the background; a `support_flag` raised in stage 4 is held until prep returns.
- **Limits per turn**: orchestrator 6 steps / 90 s, intake 8 / 120 s, support 5 / 60 s, claims prep
  40 / 600 s. A chat turn at its limit sends a canned "please resend"; a claims-prep turn that
  stops early is continued up to 3 times from the recorded facts, then goes to a person. A
  malformed model output goes through DSPy's JSON adapter fallback, then one retry of the turn.

### Agents and their tools

| Agent | Tools (all agents also have `read_skill`) |
|---|---|
| Orchestrator | `run_intake`, `run_prep`, `move_stage`, `staff_task` |
| Intake | `kb_search`, `get_case`, `record_answer`, `fill_pdf`, `request_secure_info`, `update_draft`, `get_signature`, `submit_va`, `efax_ogc` |
| Claims prep | `pull_cfile`, `list_docs`, `read_pages`, `search`, `record_facts`, `prefill`, `render`, `verify` |
| Support | `kb_search`, `get_case`, `log_event`, `flag_orchestrator`, `escalate` |

Context per turn: the orchestrator sees the case file and the last 10 events (never a transcript
or the C-file); intake sees its typed checklist of missing fields and its last 12 messages;
support a read-only snapshot and its last 8 messages; claims prep the fact table so far and the
pages it read this turn.

### Guards (code, not the model)

- **Every message, every state, before any model:** ID numbers and a typed date of birth are
  redacted; crisis language sends the Veterans Crisis Line text and an urgent task (D3); a request
  for a person or to end the representation goes to a person by rule (D2). The rule replies are in
  `agent/ingest.py`.
- **The firm's stop rules** run in code (A1, `agent/intake/checklist.stop_rule`): not a veteran
  and rated 100% go to `closed` before filing and `needs_human` after it; a non-honorable period
  goes to `needs_human` always, even before filing (an attorney decides; D16). Non-honorable
  means a period whose discharge is **other than honorable, bad conduct or dishonorable**
  (`schema.NON_HONORABLE`); general (under honorable conditions) and uncharacterized discharges
  do not stop the case.
- **Signing is the veteran's click** in the host; no tool can sign. The SSN goes only through the
  secure form into the encrypted vault, and the model sees masked values. `submit_va` is refused
  until the 21-22a is countersigned, `efax_ogc` until the fee agreement is signed and
  countersigned. One staff action countersigns both; the stamp is saved as a new PDF version, and
  the version the veteran signed keeps its hash.
- **Citations:** `render` returns each face-note line with the facts it came from, and `verify`
  checks every cited page shows the value where its label puts it (the DOB after "date of birth",
  a decision's date after "decision date" and its filing after "received", a letter's date after
  "date of this letter"; a service period as one match, the DD-214's branch field and dates or one
  narrative "{branch} from {start} to {end}"; the whole MOS, or one whole entry of a MOS list, and
  representative name; every condition a decision decides), with dates, percentages and condition
  names normalized; a service period's component must show in the DD-214's branch field (or match
  one a narrative names). A coverage check in `verify` catches omissions: every DD-214 needs a
  service period, a discharge (when it shows one) and a MOS (when its specialty is filled in),
  every rating decision a decision, every notification letter a letter fact and every 21-22 or
  21-22a (the firm's own too) a representative fact recorded from it;
  every claim form needs a decision listing it as filed or a pending filing; every condition on the
  newest code sheet's SERVICE CONNECTED list needs a rated condition; the combined rating and the
  rated conditions must cite the newest rating decision (or its letter); and no fact may be left
  unlinked. No persona has a pending filing, so the claim-form check is tested only by removing
  a decision's filing date; it can't tell a pending filing from a decided claim whose decision
  doesn't list its form. A line or coverage item that fails goes back to the model, or is
  escalated as `[UNCERTAIN]` (a staff task, closed again once a later verify passes). The stored face note shows each line's pages (`[p. 2, 5]`, or `[firm record]`).
  Prefill is refused until `verify` has passed or every failing line is escalated as uncertain,
  and it writes only facts whose cited page holds them. When the C-file conflicts with an answer,
  the DD-214 wins on discharge; any other conflict is recorded for pass 2 and a staff task (A2).
- **Untrusted text** (the veteran's words, C-file pages, search hits, kb answers; claims prep's
  intake answers and fact table; support's flag text, earlier Q&A and deadline tasks) is wrapped
  as data before it enters a context (`ingest.untrusted`); what a tool may do is still decided by
  the guards. C-file names, titles, conditions and form ids are recorded only as plain text of a
  capped length (letters in any script, digits and `.,'’&()/#-`; no markup).
- **SSNs never reach a context or a trace:** the simulated VBMS strips them at ingest, and trace
  lines are scrubbed again before they are written.
- **Support changes nothing:** it has no tool that moves a stage, files or signs.
- **Failures park the case for a person:** a crashed turn, a failed orchestrator or claims-prep turn,
  or claims prep running out of continuations moves the case to `needs_human` with a staff task
  listing any undecided support flags. A failed intake or support turn sends the canned "please
  resend" reply instead; a support crash sends it with a staff task. Either way the case stays where it is.
- **The handoff goal is an instruction:** the orchestrator writes it and may paraphrase flag text; it
  reaches the sub-agent unwrapped.

### Skills, memory, traces

- **Skills** (`agent/skills/<agent>/<skill>/SKILL.md`): only the index (name and description) is in
  a prompt; the model loads one with `read_skill`. Orchestrator: stage-playbook, routing, flags.
  Intake: screen-veteran, poa-and-fees, intent-to-file, close-gaps. Claims prep: face-note-format,
  cite-check. Support: answer-questions, case-status, hand-to-a-person.
- **Memory store** (`agent/store.py`, SQLite): the `cases` table holds the case file as JSON plus
  flat columns (stage, owner, side state); `events` is the append-only event log; the outbox holds
  every reply and card. Changes are patches under a per-case lock; no model call holds the lock.
  After a restart, an intake conversation resumes from the store (the next message rebuilds the
  turn's context from the case file); queued and running turns (a wake, claims prep's background
  turn or its continuation) are in memory and do not survive a restart.
- **Traces** (`agent/traces.py`): DSPy callbacks write one JSON line per model call and per tool
  call (case, agent, turn, tokens, cost, the tool's guard decision and result) to `traces.jsonl`.
  Cost uses the price table in `agent/config.py`.

## How it maps to the lead's design

The structure follows the project lead's architecture: an orchestrator with a guarded stage table
and typed sub-agent results, the sub-agents with their own tools, skills, context and stop rules,
a shared harness, a tool registry with a guard hook, an event log and traces. The 21-22a tools wrap
the lead's POA skill (`poa_skill/`). Where we differ:

| # | Deviation | Reason |
|---|---|---|
| D1 | Code routes chat messages (the owner, else support), not the orchestrator's model | The routing rule is fixed; code gets it right every time and saves a call per message |
| D2 | Ending the representation or asking for a person goes to a person by rule, in every state | It has legal effect and needs an attorney |
| D3 | The crisis check runs in code on every message, in every stage | A crisis can come up mid-intake, not only in support |
| D6 | A `waiting_on_attorney` side state and one staff action that countersigns both documents | The demo and the eval need a way to simulate the attorney |
| D7 | No offline agents: tests use a scripted fake LM through the real code | One implementation; the demo and eval are paid |
| D8 | Haiku 5.5 through OpenRouter; the KB is our own web search on official sites, plus `law.cornell.edu` (`agent/qa.py`) | The lead's document library stays out of the public repo; Cornell LII serves 38 CFR and 38 USC as readable pages |
| D9 | `run_*` starts the sub-agent; its result arrives later as an event | A chat turn waits for the veteran's next HTTP request |
| D10 | Claims prep keeps every page read within one turn (no stubbing of old reads) | The synthetic C-files are small |
| D11 | An orchestrator `move_stage(to, reason)` tool | The design allows moves back and side states but has no tool for them |
| D12 | An extra intake skill, `close-gaps` | Pass 2 needs written directions |
| D13 | An orchestrator `staff_task(text)` tool | The flag decision "or a staff task" needs a tool |

Candidate deviations from the build, for the lead to confirm:
- **D14:** "no legal advice beyond the KB" is enforced by instructions and kb_search's hand-off,
  not by code: the reply is a model output a guard can't inspect.
- **D15:** a prior representative is a private attorney or agent on a 21-22a in the C-file without
  revocation details; a VSO (a 21-22) is recorded but never counts (Max confirmed 2026-11-03, as
  intake's question already said). Fee: 20% with a prior rep, else 30%.
- **D16:** a non-honorable period stops to `needs_human` even before filing; the plan (§2) says
  `closed`. An attorney decides, since most of these discharges need a VA character-of-discharge
  determination (38 CFR 3.12) rather than a rejection.
- **D17:** `record_answer` has no `source` argument: code sets the source (`veteran, chat HH:MM
  UTC`; prefill writes `C-file p. N`), so the model can't mislabel where an answer came from.
- **D18:** prefill runs once `verify` has passed **or** every failing line is escalated as
  uncertain (it writes only facts whose cites hold), not only after a clean pass.
- **D24:** the orchestrator may reply on any wake (the design describes it at a handoff), except on a
  case a rule handed to a person; `staff_task` is allowed after the wake's handoff.
- **D25:** `run_intake` at stage 4 after a new-condition flag also reopens `claim_conditions`, so pass
  2 can't end before the condition is recorded.
- **D27:** the skills a step needs are put in the agent's context, chosen in code from the case
  (intake by stage, the orchestrator's stage playbook, claims prep's two). The design loads skills on
  demand; the first live run spent one model call (about 3 s) per turn re-reading them.
- **D28:** an owner's turn that ends with no reply while the veteran waits is asked once more to
  answer (`[nudge]`); a second empty turn sends the canned reply. `record_answer(unknown=true)` needs
  the veteran's words. The first live run stalled when intake marked an unasked question unknown.
- **D26:** a scripted demo (`intake serve --scripted`) plays one case with no model: the agents'
  turns come from `agent/scripted/demo.py`; the runtime, tools, guard, documents and `verify` are the
  real code. It shows the flow without a key; it says nothing about the agents' quality.
- **D23:** `verify` also checks coverage (no DD-214, rating decision or letter left out, nor a
  DD-214's discharge or MOS, nor a claim or appointment form; every service-connected condition on the newest
  code sheet; the combined rating and rated conditions from the newest rating decision or its
  letter; no unlinked fact). What it can't see is listed under Citations above. Its
  items are numbered after the face-note lines and, like a line, can be escalated as uncertain.
- **D19:** kb_search's answer accuracy is not evaluated yet: the support eval checks that a kb
  answer cites its source, not that it is right.
- **D22:** veteran status, service periods, VA pay, rating or prior representation left unknown in pass 1
  (unknown prior representation sets no fee) stop the case to
  `needs_human` (`screen_unresolved`). Stop-rule fields (is_veteran, each period's discharge,
  receiving_va_pay, rating_pct, prior_attorney) take a structured value from the model (a JSON bool,
  a discharge code, an integer) while the veteran's words are kept as the raw answer; code reads free
  text for them only when it is plain ("yes", "no", "70%", "honorable", "OTH") and re-asks a
  hedged answer. A fee agreement with stale terms can't be signed; a vault change after signing
  creates a staff task. A qualified "honorable" ("less than", "not") reads as other than honorable.
  A secure-form or `update_draft` change re-renders stale drafts, and signing refuses a draft whose
  vault fingerprint changed.
  Service periods can't be empty for a veteran; when the veteran's own words are plain they must
  match the model's value; a vault change (secure form or `update_draft`) after signing, or a fee
  change after the fee agreement is signed, creates a staff task; an answer hidden by a later answer
  is dropped from the record.
- **D20:** the only move back is from stage 5 to stage 4 (reopening intake for a new condition).
  Moves back to earlier stages are future work (F9).
- **D21:** after a crisis or a person request, the model reply of every turn that was running or
  queued before it is held back (logged as `reply_held`); the rule message is the last thing the
  veteran gets.
- Support returns no typed result: its flags and escalations are events.
- The eval headline counts structured questions settled from chat, not questions asked (the
  model's wording can't be counted); citation precision uses `verify`'s own page check.

Answers to the lead's open design questions (not deviations): **A1** the firm's stop rules are
enforced in code; **A2** a C-file conflict: the DD-214 wins on discharge, everything else is asked
in pass 2 and becomes a staff task; **A3** at most one case-owning sub-agent at a time, with
read-only support alongside.

## The demo

`uv run intake serve` (needs the key), then http://localhost:8000:

**One test veteran:** the demo, live or scripted, currently plays one persona, Hector Alvarez
(`recent_decision`). The other 17 personas run in the eval (`intake simulate`, `intake eval`).

**No key:** `uv run intake serve --scripted` (D26) plays the same case with no model. Press **Tab**
to take the line the input box suggests and **Enter** to send it, submit the secure form (its test
values are filled in), sign (draw, or choose Type for your name in a script font), and countersign
as the cards appear. The agents follow the script, so typing something else won't change their
answers; the box then suggests nothing rather than a line that no longer fits. One case at a time:
Start case starts the story over.

1. Press **Start case** (the test veteran's synthetic C-file is what claims prep pulls). The left
   side is the **veteran's screen** (the chat and its cards, documents shown in the card); above
   it, **You are playing…** lists who you play (the same facts and condition stories the eval's
   simulated veteran plays from), and the secure form is filled in
   with them. The right side is the **firm's, internal**: Attorney (countersign, the documents),
   Case, Answers, Face note, Event log. You type as the veteran; whenever the agents are idle the
   input box suggests a reply in grey (the eval's simulated veteran writes it from the chat so far,
   about $0.0005), and **Tab** takes it. No suggestion while any turn is queued or running, claims
   prep in the background included.
2. Intake screens you, then shows the **secure form** for the ID numbers, the **21-22a preview**, a
   signature pad and a **Sign** card, then the **fee agreement** preview and its Sign card.
3. You also play the attorney: **Countersign both documents** in the staff box (refused at any
   other time). Intake files the 21-22a and the intent to file and faxes the fee agreement to OGC;
   the chat shows the simulated confirmation numbers.
4. Claims prep reads the C-file in the background while support answers your messages. Pass 2
   then asks only the gaps, a confirmation of each C-file conflict, and the narrative prompts. The
   case ends at stage 5, ready for attorney review.
5. The case panel shows the stage and owner, the orchestrator's decisions (refused moves
   included), filings, tasks, flags, every answer with its source, the face note, the documents,
   the event log and the cost per agent.

## Evaluation (`intake_eval/`)

Synthetic veterans (`agent/data/personas/`, 18) go through **whole cases on the same runtime** the
demo uses. A model plays the veteran from a hidden record (`simulator.py`); the runner submits the
secure form, signs, countersigns as the attorney and waits for the runtime to go idle between
steps (`runner.py`).

- **Conditions** (`--conditions`): `ask_no_probes` (no verification probes, no C-file prefill),
  `ask` (probes, no prefill), `cfile` (probes, prefill from the C-file and a confirmation of each
  conflict: the default and the demo's flow). The agents never see the condition.
- **Metrics** (`scoring.py`), per agent: intake (fields vs the answer key, structured questions
  settled from chat as the headline, the share prefilled, turns to a signed 21-22a, kb calls);
  orchestrator (scenario pass rate, flag decisions, refused moves); claims prep (face-note line
  accuracy, `verify` passed, citation precision); cost and latency per agent from the traces;
  pass^k with `--trials`. **Critical errors** (a wrong end state or stop decision, a missed
  service period, prior claim, crisis or DOB mismatch, a mistyped value left on the signed
  21-22a, a wrong fee, unfinished prep, a new condition never sent back to intake, a crashed or
  stalled run) void the headline.
- **Customer support** (`support_eval.py`): 81 labeled messages through the real runtime: flags,
  hand-offs to a person, status answers, no promised dates, cited kb answers, every crisis
  caught, the case unchanged. `--luke` selects the 50-message subset matching the lead's set.

```bash
uv run intake simulate --persona baseline_clean --max-cost 1    # one case, printed
uv run intake eval --personas baseline_clean --conditions cfile --name smoke --max-cost 1
uv run intake eval --name full --max-cost 20                    # 18 personas x 3 conditions
uv run intake support-eval --max-cost 1
```

Each run prints an estimated number of model calls first (about 270 per case; about 4 per
support message), and **`--max-cost`** (USD, from the traces: agents, kb_search and the simulated
veteran) stops the run once it is passed. It is checked between steps (a case step, or a support
message), so the step that crosses it finishes first. A model slug with no price in
`agent/config.py` would count as $0, so `--max-cost` is refused for it, and without `--max-cost`
the command warns. Output: `results/<name>/report.md`, `summary.json`, transcripts and each case's
traces.

**Reruns come from the cache.** Each case (and each support message) runs on a pinned clock and
seeded IDs (`agent/clock.py`): every timestamp is the same fixed instant (2026-11-03 17:00 UTC,
not the wall clock), and case ids, document ids and confirmation codes come from a generator
seeded with the case's name (dates are local, so a machine whose local date at 17:00 UTC is not
11-03, e.g. at UTC+8, gets its own cache entries). A rerun on the same code then sends the model the same prompts and
DSPy's response cache (`~/.dspy_cache`) answers them: no cost, and minutes instead of an hour.
After a change, only the calls from the first prompt it alters are paid. kb_search (OpenRouter's
web search, called directly, not through DSPy) keeps its answers in the same cache while pinned,
since its answer is part of the agent's next prompt; the live demo always searches. A rerun can
still differ where wall time matters (a turn's time limit; the message `new_condition_during_prep`
sends while claims prep runs), and the run goes on from there, paid. So `intake simulate` and
`intake eval` replay a case they have run before: for fresh samples set `DSPY_CACHE=0`, or use
`--trials` > 1 (pass^k), which turns the cache off. `tests/test_eval.py` checks that two runs of a
case send identical prompts; `tests/test_runtime.py` that nothing else reads the wall clock.

## Tests

`uv run pytest -q`: the whole suite in about a minute, no key and no network. `agent/scripted/lm.py` scripts
each agent's tool calls through the real harness, registry and guards; `agent/scripted/kb.py` stands
in for web search. They pin the guards and stage moves, stop rules, citations and `verify`, crisis /
withdraw / a person by rule, signing and countersign integrity, SSNs never in a context or trace,
untrusted wrapping, end-to-end flows (runtime, HTTP demo, eval) and the eval's scoring.

## Pending the live key

Nothing has run against the real model yet. Waiting on the key: a smoke test of each agent,
checking that `reasoning_effort` reaches OpenRouter (L9) and that the model slug and prices are
right, cost and latency per agent, and the full eval. The README has no eval numbers until then.

## The POA skill (`poa_skill/`)

The lead's skill for VA Form 21-22a, generalized here to the fee agreement too: a secure form the
model never sees (encrypted vault, masked values), the filled PDF and an editable preview, and
click-to-sign with the exact consent text shown, a stamped signature, and an append-only audit log
without PII. There is deliberately no signing tool. Its own tests are `tests/test_form.py` and
`tests/test_workflow.py`. Intake calls `PoaService` directly (`agent/intake/documents.py`);
the skill's own generic tool layer (`poa_skill/tools.py`: `TOOLS`, `run_tool`, `openai_tools`)
covers the 21-22a only and is not used by the agents. Change the firm and attorney in `config/representative.json`.

## Code map

```
agent/        runtime, harness, orchestrator, stages, casefile, store, traces, ingest, kb, qa
  intake/       agent.py, checklist.py, documents.py, questions.yaml, parsing, rules
  claims_prep/  agent.py, facts.py (typed facts + cite map), verify.py, prefill.py
  support/      agent.py
  cfile/        vbms.py (simulated VBMS), synth.py (synthetic C-files), facts.py, facenote.py
  skills/       SKILL.md files per agent
  data/personas/  the synthetic veterans
  scripted/     lm.py (scripted fake LM), kb.py (offline FAQ), prep.py (claims prep's correct reading),
                demo.py (the scripted demo's story)
poa_skill/    21-22a and fee agreement: vault, documents, PDF fill and signing
demo/         app.py (FastAPI) and static/app.html
intake_eval/  simulator, runner, scoring, report, support eval
tests/        fixtures, tests
```

`poa_skill/pdf/` and the signature-pad trimming are adapted from an earlier form engine by the
project lead.
