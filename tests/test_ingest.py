"""The input guards (agent/ingest.py) and the kb engine's rules (agent/qa.py), on hand-built inputs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.ingest import HIDDEN, Ingested, detect_crisis, ingest, redact_chat, wants_human
from agent.qa import WebSearchQA

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


class FakeOpenRouter:
    """The OpenAI-compatible client, scripted: one answer with these source URLs."""

    def __init__(self, content="An intent to file holds your start date.", urls=("https://www.va.gov/x",), usage=None):
        self.content, self.urls, self.usage, self.kwargs = content, urls, usage, None
        self.chat = SimpleNamespace(completions=self)

    def create(self, **kw):
        self.kwargs = kw
        anns = [{"type": "url_citation", "url_citation": {"url": u}} for u in self.urls]
        msg = SimpleNamespace(content=self.content, annotations=anns)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=self.usage)


def test_web_search_qa_restricts_domains_and_requires_official_sources():
    client = FakeOpenRouter(urls=["https://www.va.gov/x", "https://spam.example/y"])
    r = WebSearchQA(client=client, model="m")("What is an intent to file?")
    assert r.sources == ["https://www.va.gov/x"] and not r.handoff
    plugin = client.kwargs["extra_body"]["plugins"][0]
    assert plugin["id"] == "web" and "va.gov" in plugin["include_domains"]
    assert plugin["engine"] == "exa"  # not OpenAI's native search (price, domain filter)
    assert WebSearchQA(client=FakeOpenRouter(urls=["https://spam.example"]), model="m")("q?").handoff
    assert WebSearchQA(client=FakeOpenRouter("HANDOFF", []), model="m")("q?").handoff


@pytest.mark.parametrize("text", [
    "Will I win my case?", "How much do I owe VA?", "Do I owe VA money for an overpayment?",
    "I have a VA debt, what do I do?",
])  # fmt: skip
def test_case_specific_questions_and_va_debts_go_to_a_person_before_the_model(text):
    client = FakeOpenRouter()
    assert WebSearchQA(client=client, model="m")(text).handoff and client.kwargs is None


def test_web_search_qa_client_has_a_timeout(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    client = WebSearchQA().client  # constructing it makes no request
    assert client.timeout == 30 and client.max_retries == 1


def test_web_qa_records_usage():
    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=40, cost=0.0123)
    r = WebSearchQA(client=FakeOpenRouter(urls=["https://www.va.gov/disability/"], usage=usage), model="m")(
        "What is a supplemental claim?")  # fmt: skip
    assert r.usage == {"prompt_tokens": 120, "completion_tokens": 40, "cost": 0.0123}
    assert r.sources == ["https://www.va.gov/disability/"]
