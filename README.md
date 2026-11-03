# POA skill: VA Form 21-22a for an intake agent

CS329Z class project. This repo is a **skill**, not an agent: a set of instructions plus tools
that any intake agent can mount to complete one task, getting a veteran's **VA Form 21-22a**
(*Appointment of Individual as Claimant's Representative*) filled and signed so a law firm's
attorney can represent them before VA.

The agent decides *when* the task applies. The skill handles *how*:

1. Capture the veteran's identity details, including SSN, through a secure form the model
   never sees.
2. Fill the 21-22a from those details plus the firm's details.
3. Let the veteran review and edit the draft.
4. Sign on one click, placing the veteran's saved signature.

## How it works

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

## Mounting the skill in an agent

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

`demo/host_agent.py` is a complete example: about 100 lines, using an OpenAI-compatible client
pointed at OpenRouter.

### What the host must provide

| Card | The host renders | And calls |
|---|---|---|
| `secure_form` | A form with the listed fields (`input_type`: text, ssn, date, select, tel, email) | `PoaService.complete_capture_request(request_id, values)`, then tells the model "form submitted" |
| `signature_pad` | A drawing pad (export a PNG data URI, trimmed to the ink) | `PoaService.save_signature(data_uri)` |
| `document_preview` | The PDF (`PoaService.document_pdf(id)`) plus an optional edit panel | `PoaService.edit(id, changes, actor="user")` |
| `sign_button` | `consent_text` and a Sign button | `PoaService.sign(id, consent_text=..., ip=..., user_agent=...)` |

`demo/server.py` (FastAPI) and `demo/static/index.html` implement all four.

## Run it

```bash
uv sync
uv run pytest                                    # 20 tests
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
demo/                 example host: host_agent.py, server.py, static/index.html
tests/                form mapping, security properties, host-agent loop, HTTP flow
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
  - Submitting to VA.
  - Real authentication. The demo session is just a cookie.

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
