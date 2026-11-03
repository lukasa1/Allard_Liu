# Allard_Liu: intake agent skill for VA Form 21-22a

CS329Z class project. An intake subagent skill that gets a veteran's **VA Form 21-22a**
(*Appointment of Individual as Claimant's Representative*) filled and signed, appointing a law
firm's attorney to represent them before VA.

When the agent decides the veteran needs to sign the 21-22a, it:

1. **Captures sensitive data securely.** It opens a form outside the chat. SSN and date of birth
   go into an encrypted vault, and the agent only ever sees masked values (`***-**-6789`).
2. **Fills the form.** The veteran's data comes from the vault and the firm's attorney, address,
   staff and standard authorizations come from `config/representative.json`.
3. **Lets the user review and edit** the draft before signing.
4. **Signs on click.** The veteran draws a signature once. Clicking **Sign** stamps it into
   Item 23A, dates 23B, and writes an ESIGN/UETA audit record.

## Security model

| Rule | How it's enforced |
|---|---|
| The model never sees an SSN or date of birth | The secure form posts to the host (`demo/server.py`), not the chat. Tools return masked values only (`vault.masked()`). A test checks that no tool output contains raw PII. |
| PII typed into chat anyway is hidden | `agent.redact()` strips SSN and file-number patterns before a message reaches the model. |
| The agent can't sign | No signing tool exists. `PoaService.sign()` is reachable only from the user's click, which must echo the e-sign consent text the user was shown. |
| The agent can't request arbitrary data | Secure forms can only ask for fields in the `vault.FIELDS` catalog. A submission only stores the fields that form asked for. |
| Data at rest is encrypted | The vault and filled PDFs are Fernet-encrypted (key: `POA_VAULT_KEY`, or `.data/vault.key`). |
| Every step is auditable | `.data/audit.jsonl` is append-only and holds no PII: events, field names, content hashes, IP and user agent at signing. |
| Signed forms are frozen | Edits to a signed document are rejected; changes need a new draft. |

**Use synthetic data only.** This demo is not a production deployment: no KMS, no auth, and a
local file store. Real veteran data needs a BAA-covered model (`POA_LLM_BACKEND=bedrock`) and a
KMS-backed vault.

## Agent tools (`poa_agent/tools.py`)

Defined in Claude's tool-use format (`TOOLS`), executed by `run_tool()`.

| Tool | What it does |
|---|---|
| `get_intake_status` | Masked data on file, what's missing, signature on file, documents |
| `request_secure_info` | Opens the secure form for specific fields |
| `prepare_poa_21_22a` | Fills a draft from the vault and firm config with the veteran's Item 20/22 answers, and shows the preview |
| `update_poa_draft` | Corrects non-secret fields or authorizations on the draft |
| `request_signature_capture` | Shows the signature pad (one-time; the signature is reused) |
| `present_for_signature` | Shows the Sign button once the draft is complete |

The skill instructions the subagent follows are in `poa_agent/skills/poa_21_22a/SKILL.md`.

## Run it

```bash
uv sync
uv run pytest                      # 19 tests: form mapping, security properties, HTTP flow
uv run uvicorn demo.server:app     # open http://localhost:8000
```

- **With an API key** (`export ANTHROPIC_API_KEY=...`), Claude drives the conversation.
  Optional: `POA_AGENT_MODEL` sets the model; `POA_LLM_BACKEND=bedrock` uses AWS Bedrock.
- **Without a key**, the page shows a panel that calls the same tools the agent would, so the
  whole flow can be clicked through.

## Layout

```
poa_agent/
  form_21_22a.py      field mapping for the VA blank (JUL 2023 edition), draft + sign
  vault.py            encrypted PII + signature store, field catalog, validation, masking
  documents.py        encrypted PDF store + audit log
  service.py          workflow: capture requests, prepare, edit, sign (host-only)
  tools.py            agent tool definitions + dispatcher
  agent.py            minimal Claude tool-use loop with chat PII redaction
  skills/poa_21_22a/  SKILL.md for the intake subagent
  pdf/                fill.py, sign.py, transforms.py (ported from the Shire form engine)
  forms/              VA blank 21-22a
config/representative.json   the appointed attorney and firm (Tabak Law)
demo/                 FastAPI host + single-page UI (secure form, signature pad, preview)
tests/
```

## Provenance

`poa_agent/pdf/` and the signature-pad trimming in the demo UI are adapted from the Shire
claims-prep platform's form engine, written by Lukas Allard. The 21-22a mapping, vault, tools,
skill and demo are new for this project.
