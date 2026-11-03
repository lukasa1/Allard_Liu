"""The LLM code paths, with scripted models (no network): QA web search, the DSPy POA agent,
the DSPy brain and the DSPy C-file extractor."""

import json
from types import SimpleNamespace

import dspy
from dspy.utils.dummies import DummyLM

from agent.case import CaseState
from agent.cfile import build_documents, extract_cfile, make_dspy_extractor
from agent.cfile.extract import DocumentFacts
from agent.intake.dspy_brain import DSPyBrain, ExtractAnswers
from agent.intake.questions import Ask, QuestionBank
from agent.legacy_orchestrator import DSPyPolicy, allowed_actions
from agent.personas import get_persona
from agent.poa import make_dspy_poa_step
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


def test_dspy_poa_agent_mounts_the_skill_and_never_sees_raw_pii(svc):
    lm = DummyLM([
        {"next_thought": "open the form", "next_tool_name": "request_secure_info",
         "next_tool_args": {"fields": ["ssn", "date_of_birth"], "purpose": "For the form."}},
        {"next_thought": "wait", "next_tool_name": "finish", "next_tool_args": {}},
        {"reasoning": "done", "reply": "I've opened a secure form."},
    ])  # fmt: skip
    step = make_dspy_poa_step(svc, lm)
    turn = step.start()
    assert turn.text == "I've opened a secure form."
    assert [c["type"] for c in turn.cards] == ["secure_form"]
    svc.complete_capture_request(
        turn.cards[0]["request_id"], {"ssn": "123-45-6789", "date_of_birth": "1988-04-09"}
    )
    lm2 = DummyLM([
        {"next_thought": "check", "next_tool_name": "get_intake_status", "next_tool_args": {}},
        {"next_thought": "ok", "next_tool_name": "finish", "next_tool_args": {}},
        {"reasoning": "r", "reply": "Thanks."},
    ])  # fmt: skip
    step2 = make_dspy_poa_step(svc, lm2)
    step2.event("secure_form_submitted")
    prompts = json.dumps([h["messages"] for h in lm2.history], default=str)
    assert "***-**-6789" in prompts and "123-45-6789" not in prompts and "1988-04-09" not in prompts


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


class _Pred:
    def __init__(self, action):
        self.action, self.reason = action, "r"


def test_dspy_policy_matches_the_action_name_as_a_token():
    policy = DSPyPolicy(lm=None)
    c = CaseState(case_id="c7")
    allowed = allowed_actions(c)  # ["request_va_sign_in"]
    for raw in ("request_va_sign_in.", "`request_va_sign_in`", "Action: request_va_sign_in"):
        policy.predict = lambda raw=raw, **kw: _Pred(raw)
        assert policy.choose(c, "case_opened", allowed) == ("request_va_sign_in", "r")
    policy.predict = lambda **kw: _Pred("request_va_sign_in_now")  # not a token match
    action, reason = policy.choose(c, "case_opened", allowed)
    assert action == "request_va_sign_in" and "fallback" in reason
    c.phase, c.va_consent = "va_sign_in", "granted"
    two = ["fetch_va_records", "wait"]
    policy.predict = lambda **kw: _Pred("fetch_va_records, then wait")  # ambiguous
    assert "fallback" in policy.choose(c, "e", two)[1]


def test_dspy_extractor_feeds_the_same_merge():
    p = get_persona("baseline_clean")
    pdfs = [d[2] for d in build_documents(p)][:1]  # the DD-214
    facts = DocumentFacts(doc_type="dd214", dob="1970-01-02", mos=["88M"])
    lm = DummyLM([{"facts": facts.model_dump()}])
    merged, per_doc, _ = extract_cfile(pdfs, make_dspy_extractor(lm))
    assert merged.dob == "1970-01-02" and merged.mos == ["88M"] and per_doc[0].doc_type == "dd214"
    assert isinstance(dspy.settings, object)


class _TextAwareVeteran:
    """Offline simulator, plus answers to the POA questions read from the agent's text (the DSPy
    POA agent doesn't expose what it's waiting for, unlike the scripted one)."""

    def __init__(self, persona):
        from intake_eval.simulator import OfflineSimulator

        self.inner = OfflineSimulator(persona)

    def respond(self, text, pending):
        low = text.lower()
        if pending is None or isinstance(pending, str):
            if "drug or alcohol" in low or "update your address" in low:
                return "Yes."
            if "look right" in low:
                return "Looks good."
        return self.inner.respond(text, pending)


def test_dspy_provider_runs_a_whole_case(tmp_path):
    """Every DSPy component (orchestrator policy, intake brain, POA ReAct agent mounting the skill,
    C-file extractor) wired into one case, with a rule-driven fake model."""
    from legacy_rule_lm import RuleLM

    from intake_eval.runner import run_case

    persona = get_persona("recent_decision")
    lm = RuleLM()
    run = run_case(
        persona,
        "fetch_confirm",
        provider="dspy",
        simulator=_TextAwareVeteran(persona),
        lm=lm,
        data_dir=tmp_path,
    )
    case = run.case
    assert not run.hit_step_limit
    assert case.phase == "attorney_review" and case.poa_signed and case.face_note
    # every orchestrator step with a real choice came from the model (no fallbacks); steps with
    # nothing to decide (only "wait") are labelled "rule" and skip the model
    assert {d.policy for d in case.decisions} <= {"dspy", "rule"}
    assert all(d.policy == "dspy" for d in case.decisions if d.allowed != ["wait"] and d.reason.startswith("[rule]") is False)
    assert {"react", "react_extract", "extract", "phrase", "orchestrator", "orchestrator_react", "cfile"} <= set(
        lm.signatures
    )
    prompts = json.dumps([h["messages"] for h in lm.history], default=str)
    assert persona.identity["ssn"] not in prompts  # the model never sees the SSN
