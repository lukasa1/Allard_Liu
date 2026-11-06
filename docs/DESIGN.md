# VA claims agent: design

How the system is built: architecture, guards, the demo and the evaluation in detail. To install
and run it, see the [README](../README.md).

A CS329Z class project: an AI system that helps a law firm (called "the law firm" here) represent
veterans before VA. An **orchestrator** keeps each case moving and hands it to one sub-agent at a
time:

| Sub-agent | What it does | Status |
|---|---|---|
| **Intake** (`agent/intake/`) | Pass 1: screens the veteran, gets VA Form 21-22a and the fee agreement signed, files them after the attorney countersigns. Pass 2: asks only what the C-file didn't settle. | built |
| **Claims prep** (`agent/claims_prep/`) | Reads the C-file, records typed facts with page citations, prefills intake, writes and verifies the face note. | built |
| **Customer support** (`agent/support/`) | Answers the veteran while nobody else is talking to them; read-only; flags changes to the orchestrator. | built |
| **Claims investigation** | 526EZ / 0995 / 0996 / 4142, attorney-approved filing. | not built |

Model: `openrouter/anthropic/claude-haiku-5.5` for every agent. `config/representative.json` holds
placeholders.

## Architecture

```
web chat / cards / staff panel ──▶ runtime (agent/runtime.py) ──▶ code checks on every message
                                     │                               (redact, crisis, a person, withdraw)
                                     ├─ route (code): intake if it owns the case, else support
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
to stage 4 (reopening intake for a new condition; earlier stages can't be reopened). That move
leaves a reopen item that pass 2 must resolve, and `claim_conditions` is asked again; code hands
the case to intake with the move's reason as the goal, so a move back never leaves it with nobody. Every
refused move is logged and its reason goes back to the model.

### Runtime protocol

- **One turn = one `dspy.ReAct` run** per message or event. A turn's `reply` output is the only
  way it talks to the veteran (this is `ask_veteran`); `result` (a `SubagentResult`) is kept only
  when the agent's stop rule holds.
- **Handoffs are asynchronous**: `run_intake(goal)` / `run_prep(goal)` set the owner and queue
  the sub-agent's first turn; its result later wakes the orchestrator as a `subagent_result`
  event. The orchestrator wakes only on `case_opened`, `subagent_result`, `support_flag`,
  `escalated` and staff events nobody owns; chat messages never wake it. It may send the veteran a
  short reply from any wake (not on a case a rule handed to a person), and `staff_task` is allowed
  after the wake's handoff.
- **One case-owning sub-agent at a time.** Support is read-only and may run while claims prep
  works in the background; a `support_flag` raised in stage 4 is held until prep returns.
- **Limits per turn**: orchestrator 6 steps / 90 s, intake 8 / 120 s, support 7 / 60 s, claims prep
  40 / 600 s. A chat turn at its limit sends a canned "please resend"; a claims-prep turn that
  stops early is continued up to 3 times from the recorded facts, then goes to a person. A
  malformed model output goes through DSPy's JSON adapter fallback, then one retry of the turn.
  An owner's turn that ends with no reply while the veteran waits is asked once more to answer
  (`[nudge]`); a second empty turn sends the canned reply.

### Agents and their tools

| Agent | Tools (all agents also have `read_skill`) |
|---|---|
| Orchestrator | `run_intake`, `run_prep`, `move_stage`, `staff_task` |
| Intake | `kb_search`, `crisis_to_person`, `to_person`, `get_case`, `record_answer`, `fill_pdf`, `request_secure_info`, `update_draft`, `get_signature`, `submit_va`, `efax_ogc` |
| Claims prep | `pull_cfile`, `list_docs`, `read_pages`, `search`, `record_facts`, `prefill`, `render`, `verify` |
| Support | `kb_search`, `crisis_to_person`, `get_case`, `log_event`, `flag_orchestrator`, `escalate` |

Context per turn: the orchestrator sees the case file and the last 10 events (never a transcript
or the C-file); intake sees its typed checklist of missing fields and its last 12 messages;
support a read-only snapshot and its last 8 messages; claims prep the fact table so far and the
pages it read this turn.

### Guards (code, not the model)

- **Every message, every state, before any model:** ID numbers and a typed date of birth are
  redacted; crisis language sends the Veterans Crisis Line text and an urgent task; a request for
  a person or to end the representation goes to a person by rule (ending it has legal effect, so a
  person confirms it first). The rule replies are in `agent/ingest.py`; the checks read curly
  quotes as straight ones ("don’t"). Code routes each message: to intake while it owns the case,
  otherwise to support.
- **Backstops for what the checks miss:** crisis language the check misses reaches intake or
  support, whose prompts tell them to call `crisis_to_person` (`agent/crisis.py`); a request for a
  person or to end the representation that reaches intake goes through `to_person` (support uses
  `escalate`). Both run the rule's own hand-off (its reply text from code, a staff task,
  `needs_human`, the orchestrator woken; a closed case stays closed, with the task) and hold back
  the turn's own reply. They run even after the turn lost the case (a non-veteran's case just closed).
- **Held replies:** after a crisis or a person request, the model reply of every turn that was
  running or queued before it is held back (logged as `reply_held`); the rule's message is the
  last thing the veteran gets.
- **The firm's stop rules** run in code (`agent/intake/checklist.stop_rule`): not a veteran and
  rated 100% go to `closed` before filing and `needs_human` after it. When **every** service
  period is non-honorable, the case goes to `needs_human` even before filing (an attorney
  decides); when only some are, intake goes on and a staff task names those periods. Most of these
  discharges need a VA character-of-discharge determination (38 CFR 3.12), so this is a review,
  not a rejection. Non-honorable means **other than honorable, bad conduct or dishonorable**
  (`schema.NON_HONORABLE`); general (under honorable conditions) and uncharacterized are neither.
  Veteran status, service periods, VA pay, rating or prior representation left unknown in pass 1
  also go to `needs_human` (`screen_unresolved`).
- **Stop-rule answers are structured:** for is_veteran, each period's discharge, receiving_va_pay,
  rating_pct and prior_attorney the model passes the value it understood (a bool, a discharge code,
  an integer) while the veteran's words are kept as the raw answer; code reads free text for them
  only when it is plain ("yes", "no", "70%", "honorable", "OTH") and re-asks a hedged answer. A
  qualified "honorable" ("less than", "not") reads as other than honorable. Service periods can't
  be empty for a veteran, and an answer hidden by a later answer is dropped from the record.
- **Answer sources are set by code** (`veteran, chat HH:MM UTC`; prefill writes `C-file p. N`):
  `record_answer` has no `source` argument, so the model can't mislabel where an answer came from.
- **Fee:** 30%, or 20% when a private attorney or agent represented the veteran before. In the
  C-file that is a private attorney's or agent's 21-22a, revoked or not (they represented the
  veteran before); a VSO (a 21-22) is recorded but never counts.
- **No legal advice beyond the KB** is enforced by instructions and kb_search's hand-off (the
  reply is model output a guard can't inspect).
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
  the DD-214 wins on discharge (with a staff task); any other conflict is recorded for pass 2 to
  confirm with the veteran and a staff task.
- **Documents:** a fee agreement with stale terms can't be signed; a secure-form or `update_draft`
  change re-renders stale drafts, and signing refuses a draft whose vault fingerprint changed; a
  vault change after signing, or a fee change after the fee agreement is signed, creates a staff task.
- **Untrusted text** (the veteran's words, C-file pages, search hits, kb answers; claims prep's
  intake answers and fact table; support's flag text, earlier Q&A and deadline tasks) is wrapped
  as data before it enters a context (`ingest.untrusted`); what a tool may do is still decided by
  the guards. C-file names, titles, conditions and form ids are recorded only as plain text of a
  capped length (letters in any script, digits and `.,'’&()/#-`; no markup).
- **SSNs never reach a context or a trace:** the simulated VBMS strips them at ingest, and trace
  lines are scrubbed again before they are written.
- **Support changes nothing:** it has no tool that moves a stage, files or signs. Its one exception
  is the crisis backstop (`crisis_to_person`), which hands the case to a person by the rule's own code.
- **Failures park the case for a person:** a crashed turn, a failed orchestrator or claims-prep turn,
  or claims prep running out of continuations moves the case to `needs_human` with a staff task
  listing any undecided support flags. A failed intake or support turn sends the canned "please
  resend" reply instead; a support crash sends it with a staff task. Either way the case stays where it is.
- **The handoff goal is an instruction:** the orchestrator writes it and may paraphrase flag text; it
  reaches the sub-agent unwrapped.

### Skills, memory, traces

- **Skills** (`agent/skills/<agent>/<skill>/SKILL.md`): the index (name and description) is in the
  prompt, and code preloads the skills a step needs from the case (intake by stage, the
  orchestrator's stage playbook, claims prep's two); the model loads any other with `read_skill`. Orchestrator: stage-playbook, routing, flags.
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

## Built on

The knowledge base is a web search limited to
official VA and federal sites plus `law.cornell.edu` for 38 CFR and 38 USC (`agent/qa.py`). Support
returns no typed result: its flags and escalations are events.

## The demo

How to run it and the steps are in the README; this section covers how it works.

- **One test veteran:** the demo, live or scripted, plays one persona, Hector Alvarez
  (`recent_decision`); all 20 run in the eval. **You are playing…** shows the facts the eval's
  simulated veteran plays from, and the secure form is filled in with them.
- **Scripted mode** replays the midpoint eval's `recent_decision` run. Every model call is answered
  with the text the model gave in that run (`agent/scripted/demo_story.json`, recorded by
  `agent/scripted/record.py` from the run's traces), through the real harness, parsers, tools and
  guards, on the clock and IDs the eval pinned, so the chat, dates and confirmation codes are the
  run's. The server takes only the veteran's next recorded line. One case at a time: Start case
  starts the story over.
- **Live mode:** whenever the agents are idle, the input box suggests a reply in grey (the eval's
  simulated veteran writes it from the chat so far, about $0.0005); **Tab** takes it. No suggestion
  while any turn is queued or running, claims prep in the background included.
- **Staff side:** countersigning is accepted only while the Attorney tab says it is waiting. The case panel shows the stage and owner, the orchestrator's decisions (refused moves
  included), filings, tasks, flags, every answer with its source, the face note, the documents,
  the event log and the cost per agent.

## Evaluation (`intake_eval/`)

Synthetic veterans (`agent/data/personas/`, 20: 14 `dev`, the ones the system was developed
against, and 6 `heldout`, not fixed against directly; both are optimistic, and the report shows
them apart) go through **whole cases on the same runtime** the demo uses. A model plays the veteran from a hidden record (`simulator.py`); the runner submits the
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
  stalled run) are counted beside the headline: it is read only together with zero critical
  errors and field accuracy held. It averages over completed runs, the personas that stop early
  included; field accuracy averages over every run. A persona whose scripted message (`asks`)
  was never sent doesn't pass, and the report counts those messages.
- **Customer support** (`support_eval.py`): 84 labeled messages through the real runtime (3 crisis
  messages are worded so code's check misses them, for support's backstop): flags, hand-offs to a
  person, status answers, no promised dates, cited kb answers (the source's page; a looser count
  takes its site, "va.gov"), every crisis caught, the case
  unchanged. `--core` selects the 50-message core set (30 questions, 10 status checks, 5
  complaints, 5 changes). The promised-date and status checks are keyword heuristics; check
  flagged replies by hand. kb_search's answers are checked for a cited source, not for accuracy.
- **Persona question** (`asks_question_mid_intake`): an LLM judge (`intake_eval/judge.py`) grades
  intake's answer against the persona's answer key.

The commands are in the README. Each run prints an estimated number of model calls first (about 270 per case; about 4 per
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

`uv run pytest -q`: the whole suite in about two minutes, no key and no network. `agent/scripted/lm.py` scripts
each agent's tool calls through the real harness, registry and guards; `agent/scripted/kb.py` stands
in for web search. They pin the guards and stage moves, stop rules, citations and `verify`, crisis /
withdraw / a person by rule, signing and countersign integrity, SSNs never in a context or trace,
untrusted wrapping, end-to-end flows (runtime, HTTP demo, eval) and the eval's scoring.

## The POA skill (`poa_skill/`)

The skill for VA Form 21-22a, generalized here to the fee agreement too: a secure form the
model never sees (encrypted vault, masked values), the filled PDF and an editable preview, and
click-to-sign with the exact consent text shown, a stamped signature, and an append-only audit log
without PII. There is deliberately no signing tool. Its own tests are `tests/test_form.py` and
`tests/test_workflow.py`. Intake calls `PoaService` directly (`agent/intake/documents.py`);
the skill's own generic tool layer (`poa_skill/tools.py`: `TOOLS`, `run_tool`, `openai_tools`)
covers the 21-22a only and is not used by the agents. Change the firm and attorney in `config/representative.json`.

## Code map

```
agent/        runtime, harness, orchestrator, stages, casefile, store, traces, ingest, crisis
              (the model's crisis / person backstops), clock (pinned eval time), personas, kb, qa
  intake/       agent.py, checklist.py, documents.py, parsing, rules, conditions, schema, questions
                (data/questions.yaml)
  claims_prep/  agent.py, facts.py (typed facts + cite map), verify.py, prefill.py
  support/      agent.py
  cfile/        vbms.py (simulated VBMS), synth.py (synthetic C-files), extract.py, facts.py, facenote.py
  skills/       SKILL.md files per agent
  data/personas/  the synthetic veterans
  scripted/     lm.py (scripted fake LM), kb.py (offline FAQ), prep.py (claims prep's correct reading),
                demo.py, demo_story.json, record.py (the scripted demo: a recorded run, replayed)
poa_skill/    21-22a and fee agreement: vault, documents, PDF fill and signing
demo/         app.py (FastAPI) and static/app.html
intake_eval/  simulator, runner, scoring, evaluate (report), judge (LLM judge), support eval
tests/        fixtures, tests
```

`poa_skill/pdf/` and the signature-pad trimming are adapted from an earlier form engine.
