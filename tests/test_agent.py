from types import SimpleNamespace

from poa_agent.agent import IntakeAgent, redact


def test_redact_hides_ssns_and_file_numbers_but_not_phones_or_zips():
    for s in ("my ssn is 123-45-6789", "123 45 6789", "123456789", "file 12345678"):
        assert redact(s)[1], s
    for s in ("call 414-555-0100", "zip 53202-1234", "born 04/09/1988"):
        assert not redact(s)[1], s


class FakeClient:
    """Plays a scripted model: first a tool call, then a text reply."""

    def __init__(self):
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        if len(self.calls) == 1:
            return SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        id="t1",
                        name="request_secure_info",
                        input={"fields": ["ssn"], "purpose": "For the form."},
                    )
                ]
            )
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="I've opened a secure form.")]
        )


def test_agent_runs_tools_returns_cards_and_never_sees_typed_ssn(svc):
    client = FakeClient()
    agent = IntakeAgent(svc, client=client, model="fake")
    out = agent.send("ok, my social is 123-45-6789")
    assert out["reply"] == "I've opened a secure form."
    assert out["cards"][0]["type"] == "secure_form"
    sent = str(client.calls[0]["messages"])
    assert "6789" not in sent and "hidden" in sent
    # history: user, assistant tool_use, user tool_result, assistant text
    assert agent.messages[2]["content"][0]["type"] == "tool_result"
