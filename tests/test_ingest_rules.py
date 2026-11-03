"""The input guards (agent/ingest.py), the support subagent's rules (agent/legacy_support.py) and the
offline QA's routing (agent/qa.py), tested directly on hand-built inputs (no CaseSession)."""

from __future__ import annotations

import pytest

from agent.ingest import HIDDEN, Ingested, detect_crisis, ingest, redact_chat, wants_human
from agent.qa import OfflineQA, WebSearchQA
from agent.legacy_support import FOR_A_PERSON, SupportAgent, status_text

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


# ------------------------------------------------------------------------------ support


def snap(phase="attorney_review", **kw):
    base = {
        "phase": phase, "decision": "proceed", "first_name": "Sam", "poa_signed": True,
        "poa_submitted": phase not in ("attorney_signoff",), "poa_status": None, "poa_countersigned": False,
        "itf_date": None, "face_note_ready": False, "cfile_requested": False, "cfile_received": False,
    }  # fmt: skip
    base.update(kw)
    return base


SUPPORT = SupportAgent(OfflineQA())

STATUS = [
    "Any news on my file?",
    "Where is my case at?",
    "Has the attorney looked at my file yet?",
    "Did you get my records?",
    "Have you filed the power of attorney yet?",
    "Did VA accept the 21-22a?",
    "Did VA get my form?",
    "When will I hear back?",
    "Is my claim approved yet?",
    "Can I get an update?",
]
NOT_STATUS = [
    "Is my progress note from the VA hospital needed?",
    "Where is the nearest VA hospital?",
    "Do I need to send an update on my meds?",
]


@pytest.mark.parametrize("text", STATUS)
def test_status_questions(text):
    r = SUPPORT.handle(snap(), text)
    assert r.answered == ["status"] and not r.for_a_person and not r.flags, (text, r)


@pytest.mark.parametrize("text", NOT_STATUS)
def test_not_status_questions_go_to_a_person(text):
    r = SUPPORT.handle(snap(), text)
    assert "status" not in r.answered and r.for_a_person and r.unanswered == [text], (text, r)


@pytest.mark.parametrize(
    "text, flags",
    [
        ("Can I add my wife as a dependent?", []),
        ("Can I also file for my wife's benefits?", []),
        ("Can you add my new email address to my file?", ["contact_change"]),
        ("Cancel the C&P exam?", []),
        ("I want to withdraw my old claim at VA for my back.", []),
        ("I need to cancel my appointment", []),
        ("I've moved on from that job.", []),
        ("My doctor said it's a terrible injury.", []),
        ("I'm upset about my divorce and it affects my sleep", []),
        ("My wife is frustrated with how I sleep", []),
        ("I have a new condition, diabetes", ["new_condition"]),
        ("I was diagnosed with sleep apnea last month", ["new_condition"]),
        ("My back has gotten worse since we talked", ["new_condition"]),
        ("Can I speak to my attorney?", ["wants_human"]),
        ("Call me", ["wants_human"]),
        ("I also want to claim my knees.", ["new_condition"]),
        ("I forgot to mention my tinnitus. Can we add that?", ["new_condition"]),
        ("Please cancel my case.", ["withdraw"]),
        ("I don't want you to represent me anymore.", ["withdraw"]),
        ("I want to revoke the power of attorney.", ["withdraw"]),
        ("I moved last week, my new address is 12 Oak St, Tulsa.", ["contact_change"]),
        ("This is ridiculous, nobody has called me in two weeks.", ["complaint"]),
        ("I'm frustrated, I haven't heard from anyone.", ["complaint"]),
        ("I'm unhappy with how my case is being handled.", ["complaint"]),
    ],
)
def test_support_flags(text, flags):
    r = SUPPORT.handle(snap(), text)
    assert sorted(r.flags) == sorted(flags), (text, r.flags)
    # every message is either answered or read by a person (a flag makes a task too)
    assert r.flags or r.answered or r.for_a_person


def test_withdrawing_a_va_claim_goes_to_a_person_not_a_withdraw_flag():
    r = SUPPORT.handle(snap(), "I want to withdraw my old claim at VA for my back.")
    assert r.flags == [] and r.for_a_person and FOR_A_PERSON in r.text


def test_a_flag_does_not_hide_the_other_question():
    r = SUPPORT.handle(snap(), "I moved to Tulsa. Will I get 70%?")
    assert r.flags == ["contact_change"]
    assert r.unanswered == ["Will I get 70%?"] and r.for_a_person
    assert "question" in r.text.lower() and "team" in r.text


def test_answered_message_needs_no_person():
    r = SUPPORT.handle(snap(), "Any news on my file? And do I owe you anything yet?")
    assert r.answered == ["status", "qa"] and not r.for_a_person and r.unanswered == []
    assert "nothing to pay up front" in r.text


@pytest.mark.parametrize(
    "text",
    ["Can you explain my C-file?", "Is my power of attorney valid?", "What is my effective date?"],
)
def test_faq_never_answers_a_question_about_this_case(text):
    r = SUPPORT.handle(snap(), text)
    assert "qa" not in r.answered and r.for_a_person, (text, r)


def test_general_faq_still_answered():
    r = SUPPORT.handle(snap(), "What is a C-file?")
    assert r.answered == ["qa"] and not r.for_a_person


# ------------------------------------------------------------------------------ status text


def test_status_text_attorney_signoff():
    text = status_text(snap("attorney_signoff", poa_submitted=False))
    assert "signed VA Form 21-22a" in text and "countersign" in text and "sent it to VA" not in text
    assert "can't predict VA's timing" in text
    text = status_text(snap("attorney_signoff", poa_submitted=False, poa_countersigned=True))
    assert "countersigned" in text and "sent it to VA" not in text


def test_status_text_case_prep():
    asked = status_text(snap("case_prep", cfile_requested=True))
    assert "asked VA for your claims file" in asked and "reading" not in asked
    reading = status_text(snap("case_prep", cfile_requested=True, cfile_received=True))
    assert "received your VA claims file" in reading
    assert "can't predict VA's timing" in asked and "can't predict VA's timing" in reading


def test_status_text_never_promises_dates():
    for phase in ("attorney_signoff", "case_prep", "attorney_review", "human_handoff", "intake"):
        text = status_text(snap(phase))
        assert "will be done by" not in text and "within" not in text.lower()


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


def test_asking_how_revoking_works_is_not_a_withdrawal():
    r = SUPPORT.handle(snap(), "Can I revoke the 21-22a later if I want?")
    assert r.flags == [] and r.answered == ["qa"]
    assert SUPPORT.handle(snap(), "Can I cancel my case?").flags == []
    assert SUPPORT.handle(snap(), "Can I cancel my case?").for_a_person
