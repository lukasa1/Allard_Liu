"""Agent tools for the intake subagent's 21-22a skill.

TOOLS is a list of tool definitions in Claude's tool-use format (name / description /
input_schema), so it plugs straight into `client.messages.create(tools=TOOLS)` or any agent
framework that accepts JSON-schema tools. `run_tool()` executes one call and returns:

  result  JSON-safe dict for the model (never raw PII: masked values only)
  cards   UI instructions for the host app (secure form, signature pad, preview, Sign button)

Deliberately missing: any tool that reads raw PII or signs. Signing happens only when the user
clicks Sign in the host UI (PoaService.sign).
"""

from dataclasses import dataclass, field

from poa_skill.service import EDITABLE, ESIGN_CONSENT, PoaService, WorkflowError
from poa_skill.vault import FIELDS

_EDITABLE_DOC = ", ".join(sorted(EDITABLE))

TOOLS: list[dict] = [
    {
        "name": "get_intake_status",
        "description": (
            "See what's on file for this veteran: masked identity fields, what the 21-22a still "
            "needs, whether a signature is saved, pending secure forms, and existing documents. "
            "Call this first, and again after the user submits a secure form or signs."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "request_secure_info",
        "description": (
            "Open a secure form OUTSIDE the chat for the user to type personal details. Use it "
            "for anything sensitive (SSN, date of birth, VA file number, service number) and "
            "for identity details in bulk. Never ask for these values in chat. Values go into an "
            "encrypted vault; you only ever see masked versions. Ask only for fields that are "
            "missing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fields": {
                    "type": "array",
                    "items": {"type": "string", "enum": list(FIELDS)},
                    "minItems": 1,
                },
                "purpose": {
                    "type": "string",
                    "description": "One plain sentence shown above the form: why you need it.",
                },
            },
            "required": ["fields", "purpose"],
        },
    },
    {
        "name": "prepare_poa_21_22a",
        "description": (
            "Fill VA Form 21-22a (appointing the firm's attorney as the veteran's "
            "representative) from the vault and the firm's details, and show the user a "
            "preview. Both authorizations are the veteran's own choice: ask them in plain words "
            "first and pass their answers. Item 20 lets the representative see records about "
            "drug or alcohol treatment, HIV, or sickle cell anemia. Item 22 lets the "
            "representative update the veteran's address with VA."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "authorize_7332_records": {"type": "boolean"},
                "authorize_address_change": {"type": "boolean"},
            },
            "required": ["authorize_7332_records", "authorize_address_change"],
        },
    },
    {
        "name": "update_poa_draft",
        "description": (
            "Change fields on an unsigned 21-22a draft when the user asks for a correction, then "
            "refresh the preview. Editable: " + _EDITABLE_DOC + ", authorize_7332_records, "
            "authorize_address_change. SSN, date of birth, VA file number and service number "
            "can't be edited here: use request_secure_info for those."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "changes": {
                    "type": "object",
                    "description": 'e.g. {"address.city": "Waukesha", "authorize_address_change": true}',
                },
            },
            "required": ["document_id", "changes"],
        },
    },
    {
        "name": "request_signature_capture",
        "description": (
            "Show a signature pad so the user can draw their signature once. It's saved and "
            "reused for this and later forms. Only needed when get_intake_status says no "
            "signature is on file."
        ),
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "present_for_signature",
        "description": (
            "When the draft is complete and the user has reviewed it, show the Sign button. "
            "The user signs by clicking it; their saved signature is placed in Item 23A and "
            "dated. You cannot sign for them. If something is missing, this says what."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"document_id": {"type": "string"}},
            "required": ["document_id"],
        },
    },
]


@dataclass
class ToolOutcome:
    result: dict
    cards: list[dict] = field(default_factory=list)
    is_error: bool = False


def _form_card(req: dict) -> dict:
    return {
        "type": "secure_form",
        "request_id": req["id"],
        "purpose": req["purpose"],
        "fields": [
            {
                "name": n,
                "label": FIELDS[n].label,
                "input_type": FIELDS[n].input_type,
                "options": list(FIELDS[n].options),
            }
            for n in req["fields"]
        ],
    }


def _preview_card(svc: PoaService, doc) -> dict:
    return {
        "type": "document_preview",
        "document_id": doc.id,
        "version": doc.version,
        "missing": doc.missing,
        "consents": doc.consents,
        "editable": {n: FIELDS[n].label for n in sorted(EDITABLE)},
        "current": {n: v for n, v in svc.vault.masked().items() if n in EDITABLE},
    }


def run_tool(svc: PoaService, name: str, args: dict) -> ToolOutcome:
    try:
        if name == "get_intake_status":
            return ToolOutcome(svc.status())

        if name == "request_secure_info":
            req = svc.create_capture_request(list(args["fields"]), str(args["purpose"]))
            return ToolOutcome(
                {
                    "request_id": req["id"],
                    "status": "pending",
                    "note": "The secure form is open for the user. Don't ask for these values "
                    "in chat. You'll be told when it's submitted.",
                },
                [_form_card(req)],
            )

        if name == "prepare_poa_21_22a":
            doc = svc.prepare(
                {
                    "authorize_7332_records": bool(args["authorize_7332_records"]),
                    "authorize_address_change": bool(args["authorize_address_change"]),
                }
            )
            return ToolOutcome(svc.describe(doc), [_preview_card(svc, doc)])

        if name == "update_poa_draft":
            doc = svc.edit(args["document_id"], dict(args["changes"]), actor="agent")
            return ToolOutcome(svc.describe(doc), [_preview_card(svc, doc)])

        if name == "request_signature_capture":
            return ToolOutcome(
                {"status": "pending", "note": "The signature pad is open. Wait for the user."},
                [{"type": "signature_pad"}],
            )

        if name == "present_for_signature":
            ok, why = svc.ready_to_sign(args["document_id"])
            if not ok:
                return ToolOutcome({"ready": False, "reason": why})
            return ToolOutcome(
                {"ready": True, "note": "The Sign button is showing. Wait for the user."},
                [
                    {
                        "type": "sign_button",
                        "document_id": args["document_id"],
                        "consent_text": ESIGN_CONSENT,
                    }
                ],
            )

        return ToolOutcome({"error": f"unknown tool {name}"}, is_error=True)
    except (WorkflowError, KeyError, TypeError) as e:
        return ToolOutcome({"error": str(e)}, is_error=True)


def openai_tools(tools: list[dict] = TOOLS) -> list[dict]:
    """The same tools in OpenAI function-calling format (OpenRouter, OpenAI, vLLM, etc.)."""
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]
