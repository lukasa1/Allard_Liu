import json
from types import SimpleNamespace

from demo.host_agent import HostAgent
from poa_skill import load_skill, redact


def test_redact_hides_ssns_and_file_numbers_but_not_phones_or_zips():
    for s in ("my ssn is 123-45-6789", "123 45 6789", "123456789", "file 12345678"):
        assert redact(s)[1], s
    for s in ("call 414-555-0100", "zip 53202-1234", "born 04/09/1988"):
        assert not redact(s)[1], s


def test_skill_loads_as_a_mountable_unit():
    skill = load_skill()
    assert skill.name == "poa-21-22a"
    assert "secure form" in skill.instructions and not skill.instructions.startswith("---")
    assert skill.tool_names == {
        "get_intake_status",
        "request_secure_info",
        "prepare_poa_21_22a",
        "update_poa_draft",
        "request_signature_capture",
        "present_for_signature",
    }
    fn = skill.tools_openai[1]["function"]
    assert fn["name"] == "request_secure_info" and fn["parameters"]["required"] == [
        "fields",
        "purpose",
    ]


def _reply(content=None, tool_calls=None):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=tool_calls))]
    )


class FakeOpenRouter:
    """Plays a scripted model through the OpenAI-compatible API: a tool call, then text."""

    def __init__(self):
        self.calls = []
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw["messages"], default=str)))  # snapshot
        if len(self.calls) == 1:
            call = SimpleNamespace(
                id="c1",
                function=SimpleNamespace(
                    name="request_secure_info",
                    arguments=json.dumps({"fields": ["ssn"], "purpose": "For the form."}),
                ),
            )
            return _reply(tool_calls=[call])
        return _reply(content="I've opened a secure form.")


def test_host_mounts_skill_routes_tool_calls_and_never_sends_typed_ssn(svc):
    client = FakeOpenRouter()
    host = HostAgent(svc, client=client, model="fake")
    out = host.send("ok, my social is 123-45-6789")
    assert out["reply"] == "I've opened a secure form."
    assert out["cards"][0]["type"] == "secure_form"
    sent = json.dumps([m for m in client.calls[0] if m["role"] == "user"])
    assert "6789" not in sent and "hidden" in sent
    tool_msg = client.calls[1][-1]
    assert tool_msg["role"] == "tool" and json.loads(tool_msg["content"])["status"] == "pending"
