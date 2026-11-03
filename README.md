# Veteran intake agent

CS329Z class project: an **AI intake agent for a law firm that represents veterans before VA**.
An orchestrator keeps each veteran's case moving and hands it to one subagent at a time. The design
follows the project's architecture (orchestrator + intake, claims preparation, claims
investigation, customer support); claims investigation is not built yet.
- an **intake subagent** that runs twice: pass 1 screens the veteran and gets VA Form 21-22a
  signed (the POA skill); after the attorney countersigns, the firm files it and the intent to
  file, claims prep reads the C-file, and pass 2 asks only what the C-file and VA's records
  didn't settle;
- **claims prep** (C-file → cited facts → face note), which also pre-fills pass 2 and lists what
  the C-file contradicts;
- **VA Lighthouse API tools**, so service history, ratings and claims come from VA instead of
  questions;
- **web-search QA** for the veteran's questions;
- a read-only **customer-support subagent** that answers once the case is parked (status, questions)
  and flags anything that would change the case for a person;

**Everything runs offline with no API key** (rule-based agent, stubbed VA APIs, synthetic
C-files). Add an OpenRouter key to switch the agents to an LLM (DSPy). **Synthetic data only.**

| Status | Piece |
|---|---|
| ✅ | **Orchestrator** (`agent/orchestrator.py`): stage table (gates) + a policy (DSPy or deterministic) that picks among the allowed actions; one subagent handoff per wake |
| ✅ | **Intake subagent** (`agent/intake/`): 36 firm questions + 16 narrative prompts per condition, two stages around the 21-22a |
| ✅ | **POA skill** (`poa_skill/`): VA Form 21-22a, secure capture, click-to-sign (described below) |
| ✅ | **Lighthouse tools** (`agent/lighthouse/`): VSHE + Benefits Claims, stub / recorded / sandbox |
| ✅ | **QA** (`agent/qa.py`): OpenRouter web search limited to official sites; offline FAQ |
| ✅ | **Customer support** (`agent/support/`): read-only agent loop; status, kb_search, flags to the orchestrator |
| ✅ | **Memory**: the case and every subagent's working memory saved each turn; `CaseSession.resume` continues after a restart |
| ✅ prototype | **C-file → face note** (`agent/cfile/`): Benefits Documents stub, extraction, the firm's template |
| ✅ | **Evaluation** (`intake_eval/`): simulated veterans with hidden ground truth, 4 conditions, pass^k |
| ⏳ | Live sandbox credentials, real sample C-files, OAuth login flow, live-model eval runs |
| ⏳ later | Claims investigation (526EZ / 0995 / 0996 / 4142, attorney-approved filing), fee agreement + eFax to VA's OGC |

## Quick start (no keys needed)

```bash
uv sync
uv run intake serve              # web demo: http://localhost:8000 (needs OPENROUTER_API_KEY)
uv run pytest                    # ~290 tests, all offline (about 3 minutes)
uv run intake eval --name offline  # the evaluation; report in results/offline/report.md
```

With an LLM: `cp .env.example .env`, set `OPENROUTER_API_KEY`, and run the same commands. The
agents switch to DSPy on `openrouter/openai/gpt-6-luna` (change it with `DSPY_MODEL`). Every
setting is documented in `.env.example`. **With a key, everything runs live and costs money**
(gpt-6-luna is $0.10 / $0.50 per million tokens; QA web search about $0.007 per question). Start
small: `uv run intake simulate --persona baseline_clean`, then
`uv run intake eval --personas baseline_clean,two_service_periods --conditions fetch_confirm`
before the full 14 x 4 run. Set `INTAKE_PROVIDER=offline` to force offline mode with a key.

## Try the demo

The demo runs the real agents (orchestrator, intake, claims prep, support) on Claude Haiku 5.5
through OpenRouter, so it **needs `OPENROUTER_API_KEY`** (in your shell or in `.env`) and every
case costs money. There is no offline mode for the agents (tests use a scripted fake model). Without
the key the server still starts, and the page says to set it.

```bash
cp .env.example .env              # then set OPENROUTER_API_KEY
uv run intake serve               # http://localhost:8000
# or: uv run uvicorn demo.app:app --port 8000
```

1. Pick a **test veteran**. Each is a synthetic persona with its own synthetic C-file (the one
   claims prep pulls from the simulated VBMS). Then press **Start case**.
2. You play the veteran in the chat. Intake screens you, then opens a **secure form** for the ID
   numbers, shows the **21-22a preview**, a **signature pad** and a **Sign** card, then the **fee
   agreement** preview and its Sign card. The page polls the outbox every 1.5 s
   (`GET /api/cases/<id>/updates?since=<seq>`), so replies from background turns appear by
   themselves.
3. You also play the attorney. When both documents are signed, the **Staff** box in the case panel
   enables **Countersign both documents** (one action; it is refused at any other time). Intake
   then files the 21-22a and the intent to file and faxes the fee agreement to VA OGC. All three
   are simulated, and the chat shows their confirmation numbers.
4. Claims prep then reads the C-file in the background. Chat meanwhile and customer support
   answers. When it is done, intake's pass 2 asks only what is still missing, and the case ends
   at stage 5, ready for attorney review.
5. The right panel shows the **Case** (stage, owner, side state, the orchestrator's decisions
   including refused moves, filings, tasks, support's log, flags and escalations, the cost per
   agent from the traces, and every answer with its source), the **Face note** (lines verify
   couldn't cite are marked `[UNCERTAIN]`), the **Documents** (the latest PDF of each, the
   countersigned version after the countersign) and the **Event log**.

Command-line equivalents:

```bash
uv run intake personas                                   # the test veterans
uv run intake simulate --persona recent_decision         # one whole case, printed
uv run intake simulate --persona reserve_not_in_records --condition fetch
uv run intake facenote --persona recent_decision         # just the C-file -> face note step
uv run intake facenote --cfile path/to/pdfs --provider dspy   # on a folder of C-file PDFs
```

## How a case flows

```
 every event (a chat message, a card, the attorney's countersign, "C-file ready") wakes the orchestrator:
   allowed = stage table(case)  →  policy picks one  →  execute  →  … until one subagent handoff, or wait

 new ─▶ va_sign_in ─▶ screening ─▶ poa ─▶ attorney_signoff ─▶ case_prep ─▶ intake ─▶ attorney_review
        Lighthouse     intake       POA skill:  attorney          C-file arrives   intake
        VSHE + Claims  pass 1       secure form, countersigns,    (its own event); pass 2: only
        prefill        (eligibility, sign 21-22a then POST 2122  claims prep:     the gaps, a check
                       stop rules,               + ITF 0966      facts → face     of what the C-file
                       fee)                                       note, prefill,   contradicts, the
                                                                  conflicts        narratives
 terminal: closed (not a veteran, already 100%) · human_handoff (crisis, attorney review, no C-file, ...)
 while no subagent is talking with the veteran (attorney_signoff, case_prep, terminal), the read-only
 support subagent answers
```

With VA, the C-file comes weeks after signing (VA must record the 21-22a first); in the demo the
stub returns it at once, and the memory below is what lets a real case wait that long.

- **Code decides what may happen; the agents decide how.** The orchestrator only sees the actions
  the case's state allows (nothing filed before the attorney countersigns; no C-file before the
  21-22a and the intent to file are in; no pass 2 before claims prep; after a crisis, only the
  hand-off), so a model mistake can't skip a gate. Honestly put, the orchestrator is a gated
  workflow with model tie-breaking: most of the time exactly one action is allowed (the eval
  reports how often), and the open-ended work happens in the subagents. Every decision is logged on the case with its options and
  reason. Firm rules (fee %, who to stop with) are plain code in `agent/intake/rules.py`, each
  labelled `law` or `firm_policy`.
- **Collect once.** VA's records answer the history questions in pass 1; the C-file answers more
  before pass 2 (rated conditions, MOS, an earlier representative) and catches what the veteran
  forgot (a second service period, an old claim); the POA skill's secure form collects name and
  contact details; chat asks only the rest. Each answer records its source
  (chat | va_records | cfile | secure_form).
- **Subagents return typed results** (`SubagentResult`: status, the event it raises, what it
  wrote, what it needs next); the orchestrator reads those, never a transcript.
- **Trace log.** Every turn appends one JSON line to `.data/traces/<case>.jsonl`: the (redacted)
  input, the orchestrator's decisions with their options, the events and results, and the model
  calls, tokens and cost. Case totals are in `case.usage`.
- **Flags are the orchestrator's decision.** Support only reports them (`case.open_flags`); the
  orchestrator chooses `reopen_intake_for_new_condition` (intake asks which condition, then its
  narrative prompts, and the case returns to attorney review) or `pass_flags_to_staff`. A
  withdrawal or a request for a person is never a choice: it is escalated by rule, so nothing is
  filed (e.g. "cancel my power of attorney" before the countersign stops the filing). A stop found
  after filing (rated 100% discovered in pass 2) goes to a person, not to "closed".
- **Skills** (`agent/skills/<agent>/<skill>/SKILL.md`, plus `poa_skill`): only the index (name +
  description) is in a prompt; the DSPy orchestrator calls `read_skill` to load one. For the
  rule-based parts the skill is the spec the code implements (a test checks the stage playbook
  names every action).
- **Who answers the veteran.** While the intake subagent or the POA step is working the case, it
  answers questions itself (it has the conversation). Once the case is parked (with the attorney,
  handed off, closed), the **support subagent** answers from a read-only snapshot of the case: the
  status in plain words (never a promised VA date) and general questions through QA. Anything
  that would change the case (a new condition, ending representation, a new address, a
  complaint, a request for a person) comes back as a flag and becomes a staff task. Crisis
  language is checked first in every phase.
- **Memory.** A case lasts months, so nothing lives only in a running process: after every turn
  the case file (state, event log, decisions, staff tasks) is saved with each subagent's working
  memory (the pending question, answers and transcript; the POA step's position). After a
  restart, `CaseSession.resume(case_id)` continues mid-conversation, and the web demo resumes the
  case for the same browser. The eval checks this by restarting before every step
  (`run_case(..., restart_every_turn=True)`): every case ends the same.
- **PII:** the model never sees an SSN or DOB from the secure form (POA skill design), SSNs
  typed in chat are redacted, and SSNs are stripped from C-file text before extraction. The
  case file never holds an SSN; the DOB appears only inside the face note (the firm's template).

## Evaluation

Each persona is a synthetic veteran with a hidden true record, scripted behaviours (omits a
second service period, forgets an old claim, uses everyday words for conditions, discloses a
crisis) and a synthetic VA record and C-file. A simulated veteran (offline: rule-based; with a
key: an LLM via DSPy) goes through the **whole case** in the same `CaseSession` the demo uses,
including the cards. Scored: decision and end state, fee, field accuracy, face-note facts,
critical errors (anything that changes what the firm does next), questions asked, pass^k.

**Headline metric: questions asked in chat** (fewer is better), and it only counts together with
**zero critical errors** and field accuracy held; the report shows the three side by side, with
how many answers came from VA's records.

Conditions (how intake uses records): `ask_no_probes` (no records, no verification questions),
`ask` (no records), **`cfile`** (no VA sign-in; the C-file pre-fills pass 2 and pass 2 confirms
what it contradicts: **the default flow**), and, only if VA sign-in were approved, `fetch` (VA
records in pass 1 + C-file, trusted) and `fetch_confirm` (both, confirmed). Offline, 16 personas
(`uv run intake eval --name offline`):

| Condition | Structured questions (mean) | Runs w/ critical errors | Field acc. |
|---|---|---|---|
| ask_no_probes | 15.9 | 3 of 16 | 99% |
| ask | 17.8 | 0 of 16 | 100% |
| **cfile (default)** | **16.8** | 0 of 16 | 100% |
| fetch (VA sign-in, off by default) | 11.6 | 0 of 16 | 100% |
| fetch_confirm (VA sign-in, off by default) | 13.2 | 0 of 16 | 100% |

The C-file saves about one question on its own (rated conditions, MOS, an earlier
representative); its main value is catching what the veteran forgot or VA's records got wrong (a
second service period, an old claim, a wrong discharge), which ask_no_probes misses. VA sign-in in
pass 1 would save the most, but it collects VA records before representation, so it is **off by
default** (`INTAKE_VA_SIGN_IN=1` turns it on in the demo) until the firm decides. **Offline numbers
show the mechanics, not quality**: the rule-based simulator answers plainly and the synthetic
C-file is built from the truth. The persona set is a development set. The real comparison is
`uv run intake eval --provider dspy` (LLM agent and simulator; `DSPY_CACHE=0`, `--trials 3`),
not yet run.

**Orchestrator:** across the offline runs about 25% of decisions had nothing to decide (only
wait) and about 73% exactly one real option; the model's real choices are ordering, whether a
flag needs a person, and what a support flag means (reopen intake for a new condition, or pass
it to staff). The report counts model choices, fallbacks and illegal choices for live runs.

**Customer support** (`uv run intake support-eval`): 32 labeled messages sent to parked cases
(status checks, general and case-specific questions, new conditions, withdrawals, contact
changes, complaints, requests for a person, crisis). Scored: flag precision and recall, status
answers, whether a person gets a task exactly when needed, every crisis handed off, and the case
left unchanged. Offline: all 32 correct. This set was used while writing the rules, so it is a
development set, not a held-out test.

## The POA skill

The POA skill completes one task: getting a veteran's **VA Form 21-22a** (*Appointment of
Individual as Claimant's Representative*) filled and signed so the firm's attorney can represent
them before VA. The agent decides *when* the task applies. The skill handles *how*:

1. Capture the veteran's identity details, including SSN, through a secure form the model
   never sees.
2. Fill the 21-22a from those details plus the firm's details.
3. Let the veteran review and edit the draft.
4. Sign on one click, placing the veteran's saved signature.

## How the POA skill works

### The three parts

| Part | What it is | Where |
|---|---|---|
| **Skill instructions** | `SKILL.md`: when to use the skill, the steps, and the rules. The host loads it into the model's context. | `poa_skill/skills/poa_21_22a/SKILL.md` |
| **Tools** | Six tools the model calls. They return masked data plus **cards** (UI the host renders). | `poa_skill/tools.py` |
| **Service** | The workflow and storage behind the tools, plus the host-only actions: storing secure-form data, saving a signature, signing. | `poa_skill/service.py` |

### One run through the task

```
veteran       host app (UI + server)         model (host agent)          poa_skill
   |                 |                              |                         |
   |  "I want to work with the firm"                |                         |
   |---------------->|--- redact(), send ---------->|                         |
   |                 |                              |-- get_intake_status --->|  masked data, what's missing
   |                 |                              |-- request_secure_info ->|  creates request -> secure_form card
   |  secure form (rendered by host, outside chat)  |                         |
   |---------------->|--- PoaService.complete_capture_request() ------------->|  encrypted vault
   |                 |--- notify("form submitted")->|                         |
   |  Item 20? Item 22? (asked in chat)             |                         |
   |                 |                              |-- prepare_poa_21_22a -->|  fills PDF -> preview card
   |  edits (chat or the edit panel)                |-- update_poa_draft ---->|  refills -> preview card
   |                 |                              |-- request_signature_capture -> signature_pad card
   |  draws signature|--- PoaService.save_signature() ----------------------->|
   |                 |                              |-- present_for_signature>|  sign_button card
   |  clicks Sign    |--- PoaService.sign(consent_text, ip, user agent) ----->|  stamps 23A, dates 23B, audit
   |                 |--- notify("signed") -------->|  "Signed. The firm files it with VA next."
```

Two kinds of actions:
- **The model calls tools** (`run_tool`) to look, ask, fill, edit and offer.
- **The user's actions go straight from the host to `PoaService`**: typing PII, drawing a
  signature, clicking Sign. They never pass through the model, so the model can't see an SSN
  and can't sign for anyone.

### Tools

| Tool | What it does | Card it returns |
|---|---|---|
| `get_intake_status` | Masked data on file, what the 21-22a still needs, whether a signature is saved, existing documents | none |
| `request_secure_info` | Opens a secure form for specific fields from the catalog | `secure_form` |
| `prepare_poa_21_22a` | Fills a draft with the veteran's answers to Item 20 (sensitive records) and Item 22 (address changes) | `document_preview` |
| `update_poa_draft` | Changes non-secret fields or authorizations on the draft | `document_preview` |
| `request_signature_capture` | Draw-once signature pad; the signature is saved for reuse | `signature_pad` |
| `present_for_signature` | Checks the draft is complete, then offers the Sign button | `sign_button` |

There is deliberately **no signing tool**. Tools come in Anthropic format (`skill.tools`) and
OpenAI/OpenRouter format (`skill.tools_openai`).

### What the model sees

```json
{"captured": {"first_name": "Jordan", "ssn": "***-**-6789", "date_of_birth": "**/**/1988",
              "address.line1": "*** ***n St", "address.city": "Milwaukee"},
 "missing_for_21_22a": [], "signature_on_file": true, "documents": [...]}
```

Field sensitivity lives in `vault.FIELDS`:
- **secret** fields (SSN, date of birth, VA file number, service number) are masked and can
  only change through a new secure form.
- **private** fields (street, ZIP, phone, email) are partly masked.
- **plain** fields (name, city, state, branch) are shown in full.

## Mounting a skill in the agent

This is the contract the intake agent will use for every skill.

```python
from poa_skill import PoaService, load_skill, redact

skill = load_skill()

system_prompt = MY_AGENT_PROMPT + "\n\n" + skill.instructions   # or load it only when needed
tools = MY_TOOLS + skill.tools_openai                           # skill.tools for Anthropic SDK

# Every user chat message, before it goes to the model:
text, had_pii = redact(text)

# When the model calls a tool:
if call.name in skill.tool_names:
    out = skill.run_tool(PoaService(session_id), call.name, args)
    # out.result -> send back to the model as the tool result
    # out.cards  -> render in your UI
```

`demo/host_agent.py` is a working stand-in for the agent: about 110 lines, using an
OpenAI-compatible client pointed at OpenRouter. Start the real agent from its loop.

### What the host must provide

| Card | The host renders | And calls |
|---|---|---|
| `secure_form` | A form with the listed fields (`input_type`: text, ssn, date, select, tel, email) | `PoaService.complete_capture_request(request_id, values)`, then tells the model "form submitted" |
| `signature_pad` | A drawing pad (export a PNG data URI, trimmed to the ink) | `PoaService.save_signature(data_uri)` |
| `document_preview` | The PDF (`PoaService.document_pdf(id)`) plus an optional edit panel | `PoaService.edit(id, changes, actor="user")` |
| `sign_button` | `consent_text` and a Sign button | `PoaService.sign(id, consent_text=..., ip=..., user_agent=...)` |

`demo/server.py` (FastAPI) and `demo/static/index.html` implement all four.

## Run the POA-only demo

The original skill demo (no orchestrator) is still here:

```bash
uv run uvicorn demo.server:app                   # http://localhost:8000
```

- **With an agent:** `export OPENROUTER_API_KEY=...`. The model defaults to
  `anthropic/claude-sonnet-5.5`; set `POA_AGENT_MODEL` for any other OpenRouter model with tool
  support, or `POA_LLM_BASE_URL` for another OpenAI-compatible endpoint.
- **Without a key:** the page shows buttons that call the six tools directly, so the whole flow
  can be clicked through.

Runtime data (vault, PDFs, audit log, key) goes to `.data/`, which is gitignored. Change it with
`POA_DATA_DIR`, and set the key with `POA_VAULT_KEY`.

## Code map

```
poa_skill/
  __init__.py         load_skill(): the mounting surface (instructions, tools, run_tool)
  skills/poa_21_22a/  SKILL.md
  tools.py            tool definitions (Anthropic + OpenAI formats) and run_tool()
  service.py          PoaService: capture requests, prepare, edit, sign; ESIGN consent text
  vault.py            encrypted PII + signature store; field catalog, validation, masking
  documents.py        encrypted PDF store, document records, append-only audit log
  form_21_22a.py      field mapping for VA's blank (JUL 2023 edition); render_draft, sign_draft
  guard.py            redact(): strips SSNs and file numbers from chat
  pdf/                fill.py (AcroForm fill), sign.py (signature stamping), transforms.py
  forms/              VA's blank 21-22a
config/representative.json   the appointed attorney and firm (placeholders)
demo/                 stand-in host for testing skills: host_agent.py, server.py, static/
agent/
  orchestrator.py     the orchestrating agent: action gates, offline + DSPy policies, decision log
  session.py          one case end to end (used by the web demo, the CLI and the eval)
  case.py             persisted case state (JSON) and phases
  intake/             intake subagent: questions.yaml, controller, rules, brains (offline, DSPy)
  poa.py              the intake subagent's POA step: mounts poa_skill (DSPy ReAct, or scripted)
  lighthouse/         VA Lighthouse tools: stub (VA response shapes), recorded, sandbox
  qa.py               veteran questions: web search on official sites, offline FAQ
  support/            customer-support sub-agent (legacy_support.py: the old regex one)
  cfile/              synthetic C-files + Benefits Documents stub, extraction, face-note template
  personas.py, data/personas/   the synthetic test veterans
  cli.py              `uv run intake ...`
intake_eval/          simulator, case runner, scoring, report; support_eval.py + support_messages.yaml
demo/app.py, demo/static/app.html   the web demo, on agent/runtime.py
tests/                form mapping, security properties, host-agent loop, HTTP flow, intake,
                      Lighthouse, C-file, orchestrator, whole cases, LLM paths (scripted models)
```

## Security model

| Rule | Enforced by |
|---|---|
| The model never sees an SSN or date of birth | Secure-form data goes host -> vault. Tools return `vault.masked()` only. A test checks every tool output for raw PII. |
| PII typed into chat is hidden | `redact()` before the model. Tested. |
| Only the user can sign | No signing tool. `sign()` requires a complete draft, a saved signature, and the exact consent text the user was shown. |
| The model can't ask for arbitrary data | Secure forms only use fields in `vault.FIELDS`. A submission only stores the fields its form requested. |
| Encrypted at rest | The vault and PDFs are Fernet-encrypted. |
| Auditable | `.data/audit.jsonl` is append-only with no PII: events, field names, hashes of the signature and PDFs, IP and user agent at signing. |
| Signed forms are frozen | Edits are rejected; changes need a new draft, and the old draft is superseded. |

**Use synthetic data only.** OpenRouter isn't covered by a BAA, and the demo has no login,
no KMS, and a local file store.

## Building on it

- **The intake agent** lives in `agent/` (see "How a case flows"). It mounts this skill in
  `agent/poa.py` through `load_skill()`, runs `redact()` on every user message, and returns the
  skill's cards to the host (`demo/app.py`). Keep skills independent: each one is instructions +
  tools + its own service, and none of them talks to the model directly.

- **Different firm or attorney:** edit `config/representative.json`. It holds placeholders now
  (Attorney 1, "Law Firm"). Item 19's staff list is `affiliated_staff`.
- **Another form** (21-22, 21-4142, ...): add a mapping module like `form_21_22a.py`. Read the
  field names with `pypdf.PdfReader(blank).get_fields()`, and build with `fill_acroform(...,
  strict=True)` so a renamed field fails loudly. Then add a prepare tool and a SKILL.md.
- **New data fields:** add to `vault.FIELDS` with a sensitivity level and a validator. The
  secure form and masking pick them up automatically.
- **Production storage:** swap `Vault` and `DocumentStore` for KMS-backed versions with the
  same methods.
- **Not covered yet:**
  - Section II (a claimant other than the veteran: surviving spouse, child or parent).
  - Item 24 limitations.
  - The representative's own signature (25A).
  - Submitting to VA from the skill itself (the orchestrator does it: Lighthouse `POST /forms/2122`, stubbed).
  - Real authentication. The demo has no login: a case is addressed by its id.

### PDF gotchas already handled

These are in `pdf/fill.py`:
- **VA forms are XFA hybrids.** The XFA layer is dropped, or Chrome and Acrobat show the blank
  values.
- **Radio buttons** need `/V` stored as a name plus each widget's `/AS` set, or they render
  unselected.
- **`/NeedAppearances` is set** so filled values print.

## Provenance

`poa_skill/pdf/` and the signature-pad trimming in the demo UI are adapted from the Shire
claims-prep platform's form engine, written by Lukas Allard. The 21-22a mapping, vault, tools,
skill and demo are new for this project.
