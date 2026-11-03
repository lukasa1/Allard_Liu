"""The input guards (agent/ingest.py), the support subagent's rules (agent/legacy_support.py) and the
offline QA's routing (agent/qa.py), tested directly on hand-built inputs (no CaseSession)."""

from __future__ import annotations

import pytest

from agent.ingest import HIDDEN, Ingested, detect_crisis, ingest, redact_chat, wants_human
from agent.qa import OfflineQA, WebSearchQA

# ------------------------------------------------------------------------------ crisis

CRISIS = [
    "I've been having thoughts of hurting myself",
    "I keep thinking about ending things",
    "I'm planning to end it tonight",
    "i wanna end it",
    "I feel like ending it",
    "everyone would be better off without me",
    "I don't see the point in living",
    "no point living anymore",
    "I tried to overdose",
    "I've been cutting myself",
    "I just want it all to be over",
    "I want to kill myself",
    "I'm suicidal",
    "I've thought about suicide",
    "I attempted suicide last year",
    "I don't want to be here anymore",
    "Some days I think about killing myself.",
    "Honestly I don't want to live anymore",
    "I don't want to be here anymore. I've been thinking about ending it.",
    "My buddy overdosed last year and now I want to die",
]
NOT_CRISIS = [
    "I hurt myself lifting a crate in Iraq",
    "I fell and hurt myself on the ship",
    "The suicide of my friend triggered my PTSD",
    "I was on suicide watch duty",
    "his suicide still haunts me",
    "makes me want to die laughing",
    "suicide prevention training",
    "I cut myself shaving",
    "I want to diet",
    "My buddy died of an overdose in 2009",
]


@pytest.mark.parametrize("text", CRISIS)
def test_crisis_is_caught(text):
    assert detect_crisis(text), text


@pytest.mark.parametrize("text", NOT_CRISIS)
def test_injury_and_ptsd_narratives_are_not_a_crisis(text):
    assert not detect_crisis(text), text


def test_brains_still_exports_the_guards():
    from agent.intake.brains import _WANTS_HUMAN
    from agent.intake.brains import detect_crisis as brains_detect

    assert brains_detect is detect_crisis and _WANTS_HUMAN.search("Call me")


# ------------------------------------------------------------------------------ wants a person

WANTS_HUMAN = [
    "Can I speak to my attorney?",
    "I want to talk to my lawyer",
    "Call me",
    "Please call me at 555-0100",
    "Can you call me back?",
    "I moved. Call me.",
    "Can I talk to a person?",
    "I'd like to speak with someone",
    "Have someone call me",
]
NOT_WANTS_HUMAN = [
    "I never could talk to someone about it",
    "Yes. I never could talk to someone about what happened over there.",
    "Do I need to talk to someone at VA?",
    "Does a human read this?",
    "Yes - I'm a veteran, my wife told me to speak with someone",
    "They never call me back",
]


@pytest.mark.parametrize("text", WANTS_HUMAN)
def test_wants_human(text):
    assert wants_human(text), text


@pytest.mark.parametrize("text", NOT_WANTS_HUMAN)
def test_not_wants_human(text):
    assert not wants_human(text), text


# ------------------------------------------------------------------------------ redaction


@pytest.mark.parametrize(
    "text, dob",
    [
        ("I was born March 14th, 1985", "March 14th, 1985"),
        ("born on 1985/03/14", "1985/03/14"),
        ("born 1985.03.14", "1985.03.14"),
        ("My birthday is the 14th of March 1985", "14th of March 1985"),
        ("born 03/14/1985", "03/14/1985"),
        ("DOB: 1985-03-14", "1985-03-14"),
        ("Date of birth is 14 March 1985", "14 March 1985"),
    ],
)
def test_typed_date_of_birth_is_hidden(text, dob):
    clean, redacted = redact_chat(text)
    assert redacted and dob not in clean and HIDDEN in clean


@pytest.mark.parametrize(
    "text",
    ["I served from 2004-06 to 2010-05", "I was born in 1985 and served from 2004-06 to 2010-05",
     "Discharged on March 14th, 2010"],
)  # fmt: skip
def test_service_dates_stay_readable(text):
    assert redact_chat(text) == (text, False)


def test_ingest_runs_every_guard_on_the_redacted_text():
    got = ingest("My SSN is 123-45-6789. Call me, I want to kill myself")
    assert isinstance(got, Ingested)
    assert got.redacted and "123-45-6789" not in got.clean
    assert got.crisis and got.wants_human
    assert ingest("Thanks!") == Ingested(clean="Thanks!", redacted=False, crisis=False, wants_human=False)


# ------------------------------------------------------------------------------ QA


@pytest.mark.parametrize(
    "text",
    ["How much do I owe VA?", "Do I owe VA money for an overpayment?", "I have a VA debt, what do I do?"],
)
def test_va_debts_go_to_a_person_not_the_fee_answer(text):
    assert OfflineQA()(text).handoff


@pytest.mark.parametrize("text", ["Do I owe you anything?", "Do I have to pay you anything?", "What do I owe the firm?"])
def test_firm_fee_questions_get_the_fee_answer(text):
    r = OfflineQA()(text)
    assert not r.handoff and "up front" in r.text


def test_web_qa_records_usage():
    class _Usage:
        prompt_tokens, completion_tokens, cost = 120, 40, 0.0123

    class _Msg:
        content = "VA explains this on its site."
        annotations = [{"url_citation": {"url": "https://www.va.gov/disability/"}}]

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()

    class _Completions:
        def create(self, **kw):
            return _Resp()

    class _Client:
        class chat:
            completions = _Completions()

    r = WebSearchQA(client=_Client(), model="m")("What is a supplemental claim?")
    assert r.usage == {"prompt_tokens": 120, "completion_tokens": 40, "cost": 0.0123}
    assert r.sources == ["https://www.va.gov/disability/"]
