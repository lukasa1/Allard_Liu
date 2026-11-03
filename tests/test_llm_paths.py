"""The LLM code paths, with scripted models (no network): QA web search, the DSPy brain and the
DSPy C-file extractor."""

from types import SimpleNamespace

import dspy
from dspy.utils.dummies import DummyLM

from agent.cfile import build_documents, extract_cfile, make_dspy_extractor
from agent.cfile.extract import DocumentFacts
from agent.intake.dspy_brain import DSPyBrain, ExtractAnswers
from agent.intake.questions import Ask, QuestionBank
from agent.personas import get_persona
from agent.qa import OfflineQA, WebSearchQA


class FakeOpenRouter:
    def __init__(self, content, urls):
        self.content, self.urls, self.kwargs = content, urls, None
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.kwargs = kw
        anns = [{"type": "url_citation", "url_citation": {"url": u}} for u in self.urls]
        msg = SimpleNamespace(content=self.content, annotations=anns)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


def test_web_search_qa_restricts_domains_and_requires_official_sources():
    client = FakeOpenRouter(
        "An intent to file holds your start date.",
        ["https://www.va.gov/x", "https://spam.example/y"],
    )
    r = WebSearchQA(client=client, model="m")("What is an intent to file?")
    assert r.sources == ["https://www.va.gov/x"] and not r.handoff
    plugin = client.kwargs["extra_body"]["plugins"][0]
    assert plugin["id"] == "web" and "va.gov" in plugin["include_domains"]
    assert plugin["engine"] == "exa"  # not OpenAI's native search (price, domain filter)
    assert WebSearchQA(client=FakeOpenRouter("text", ["https://spam.example"]), model="m")(
        "q?"
    ).handoff
    assert WebSearchQA(client=FakeOpenRouter("HANDOFF", []), model="m")("q?").handoff
    assert WebSearchQA(client=client, model="m")(
        "Will I win my case?"
    ).handoff  # never reaches the model


def test_offline_qa():
    assert OfflineQA()("How much do you charge?").sources
    assert OfflineQA()("Should I appeal?").handoff


def test_dspy_brain_extracts_with_a_scripted_model():
    lm = DummyLM([{
        "answers": [{"question_id": "is_veteran", "value_json": "true"}],
        "pending_status": "answered", "clarify_hint": "", "escalate": False, "escalate_reason": "",
        "wants_human": False, "veteran_question": "",
    }])  # fmt: skip
    q = QuestionBank.load().by_id["is_veteran"]
    ext = DSPyBrain(lm).extract(
        pending=Ask(question=q), open_asks=[], transcript=[], user_text="yep, Army"
    )
    assert ext.values == {"is_veteran": True} and ext.pending_status == "answered"


def test_web_search_qa_client_has_a_timeout(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    client = WebSearchQA().client  # constructing it makes no request
    assert client.timeout == 30 and client.max_retries == 1


def _extract(lm, user_text="yes"):
    q = QuestionBank.load().by_id["is_veteran"]
    return DSPyBrain(lm).extract(
        pending=Ask(question=q), open_asks=[], transcript=[], user_text=user_text
    )


def test_dspy_brain_survives_out_of_shape_fields():
    # value_json as a raw JSON bool, a status outside the enum, most fields missing: the answer
    # is kept (coerce validates it later) and the unknown status reads as "unclear".
    lm = DummyLM([{
        "answers": [{"question_id": "is_veteran", "value_json": True}, "junk",
                    {"question_id": "rating_pct", "value": 40}],
        "pending_status": "partially_answered",
    }])  # fmt: skip
    ext = _extract(lm)
    assert ext.values == {"is_veteran": True, "rating_pct": 40}
    assert ext.pending_status == "unclear" and not ext.escalate and not ext.wants_human


def test_dspy_extract_signature_parses_offline_with_both_adapters():
    chat = (
        "[[ ## answers ## ]]\n"
        '[{"question_id": "is_veteran", "value_json": true}, {"question_id": "x", '
        '"value_json": ["a"]}]\n\n[[ ## pending_status ## ]]\nanswered\n\n[[ ## completed ## ]]'
    )
    out = dspy.ChatAdapter().parse(ExtractAnswers, chat)
    assert [a.value_json for a in out["answers"]] == [True, ["a"]]
    assert out["escalate"] is False and out["clarify_hint"] == ""
    out = dspy.JSONAdapter().parse(ExtractAnswers, '{"pending_status": "declined"}')
    assert out["answers"] == [] and out["pending_status"] == "declined"


def test_dspy_brain_still_decodes_json_strings_and_keeps_text():
    lm = DummyLM([{
        "answers": [{"question_id": "is_veteran", "value_json": "false"},
                    {"question_id": "branch", "value_json": "army, I think"}],
        "pending_status": "answered",
    }])  # fmt: skip
    assert _extract(lm).values == {"is_veteran": False, "branch": "army, I think"}


def test_dspy_extractor_feeds_the_same_merge():
    p = get_persona("baseline_clean")
    pdfs = [d[2] for d in build_documents(p)][:1]  # the DD-214
    facts = DocumentFacts(doc_type="dd214", dob="1970-01-02", mos=["88M"])
    lm = DummyLM([{"facts": facts.model_dump()}])
    merged, per_doc, _ = extract_cfile(pdfs, make_dspy_extractor(lm))
    assert merged.dob == "1970-01-02" and merged.mos == ["88M"] and per_doc[0].doc_type == "dd214"
    assert isinstance(dspy.settings, object)
