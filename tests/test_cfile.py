"""C-file -> face note: synthetic documents, extraction, the template and its deadlines."""

from datetime import date
from io import BytesIO

from agent.cfile import (
    DocumentsStub,
    OfflineExtractor,
    build_documents,
    extract_cfile,
    render,
    truth_facts,
)
from agent.cfile.extract import triage
from agent.cfile.facenote import cond_name, service_era
from agent.personas import get_persona, load_personas


def test_offline_extraction_recovers_the_truth_for_every_persona():
    for p in load_personas():
        facts, _, skipped = extract_cfile([d[2] for d in build_documents(p)], OfflineExtractor())
        assert facts.model_dump() == truth_facts(p).model_dump(), p.id
        assert skipped == 1  # the treatment record is triaged out


def test_letters_are_not_mistaken_for_rating_decisions():
    assert (
        triage(
            "DEPARTMENT OF VETERANS AFFAIRS\nDate of this letter: May 1, 2026\nThe rating decision dated"
        )
        == "notification_letter"
    )
    assert triage("DEPARTMENT OF VETERANS AFFAIRS - RATING DECISION") == "rating_decision"


def test_face_note_template_and_deadlines():
    p = get_persona("recent_decision")
    note = render(
        truth_facts(p),
        fee_pct=30,
        itf_date="2026-11-03",
        intake_dob=p.identity["dob"],
        firm="Law Firm",
        as_of=date(2026, 11, 3),
    )
    lines = note.text.splitlines()
    assert lines[0] == "FA 30%; No prior rep"
    assert "SC (40%)| PTSD 30% | Tinnitus 10%" in lines
    assert "Law Firm Filed 0966 Intent on 11/03/26" in lines
    i = lines.index("1. Tinnitus; Left knee condition")
    assert lines[i + 2 : i + 4] == [
        "   R.D. 03/13/26",
        "   DEADLINE TO FILE AMA APPEAL 03/13/27",
    ]  # from the notification letter
    assert "OLD CLAIMS" in lines and "1. PTSD R.D. 04/16/21" in lines
    assert note.deadlines == [
        {
            "deadline": "2027-03-13",
            "decision_date": "2026-03-13",
            "conditions": ["tinnitus", "left knee condition"],
        }
    ]


def test_flags_dob_mismatch_and_bad_discharge():
    p = get_persona("dob_swapped")
    note = render(truth_facts(p), fee_pct=30, itf_date=None, intake_dob=p.identity["dob_typed"])
    assert any("DOB mismatch" in f and "swapped" in f for f in note.flags)
    assert not any("85" in f for f in note.flags)  # no dates in flags (they reach prompts and tasks)
    q = get_persona("oth_one_of_two")
    note = render(truth_facts(q), fee_pct=30, itf_date=None, intake_dob=None)
    assert "FLAG: non-qualifying discharge" in note.text


def test_prior_private_rep_is_named():
    p = get_persona("prior_attorney")
    note = render(truth_facts(p), fee_pct=20, itf_date=None, intake_dob=None)
    assert note.text.startswith("FA 20%; Prior rep Alan Smith")


def test_documents_stub_round_trip(tmp_path):
    p = get_persona("baseline_clean")
    stub = DocumentsStub(tmp_path)
    stub.ensure(p)
    docs = stub.search(p.icn)
    assert docs and stub.download(p.icn, docs[0]["documentId"]).startswith(b"%PDF")
    assert stub.search("other") == []


def test_helpers():
    assert cond_name("ptsd") == "PTSD" and cond_name("left knee condition") == "Left knee condition"
    assert service_era("2004-06") == "Gulf War" and service_era("1968-01") == "Vietnam Era"


def test_ssns_are_stripped_before_extraction_but_dates_stay():
    from agent.cfile.extract import strip_ssns

    assert strip_ssns("SSN: 495-54-3022 / 495543022") == "SSN: [SSN removed] / [SSN removed]"
    assert strip_ssns("DATE OF BIRTH (YYYYMMDD): 19850407") == "DATE OF BIRTH (YYYYMMDD): 19850407"


def test_llm_dates_are_normalised_or_dropped():
    from agent.cfile.extract import DocumentFacts

    f = DocumentFacts(doc_type="dd214", dob="03/12/1975", decision_date="March 3, 2026", filed="soon")
    assert (f.dob, f.decision_date, f.filed) == ("1975-03-12", "2026-03-03", None)


def test_ssn_formats_are_stripped():
    from agent.cfile.extract import strip_ssns

    for text in [
        "123-45 6789",
        "123.45.6789",
        "123 - 45 - 6789",
        "123–45–6789",  # en dash
        "123  45  6789",
        "123-45-\n6789",
        "123\n45\n6789",
    ]:
        assert "6789" not in strip_ssns(f"x {text} y"), text
    one_per_line = "3. SOCIAL SECURITY NUMBER:\n" + "\n".join("123456789") + "\n5. DATE OF BIRTH"
    assert strip_ssns(one_per_line) == "3. SOCIAL SECURITY NUMBER:\n[SSN removed]\n5. DATE OF BIRTH"
    assert strip_ssns("SSN: 12 345 6 789") == "SSN: [SSN removed]"
    # Not SSNs: dates, and the DOB field right after a masked SSN.
    for text in ["Decided 2021-03-04 and 03/04/2021", "DOB 19850407", "Received 2021 03 04"]:
        assert strip_ssns(text) == text
    dd214 = "3. SOCIAL SECURITY NUMBER: 495-54-3022\n5. DATE OF BIRTH (YYYYMMDD): 19850407"
    assert strip_ssns(dd214).endswith("19850407") and "3022" not in strip_ssns(dd214)


def test_model_style_values_are_mapped_not_rejected():
    from agent.cfile.extract import DocumentFacts

    f = DocumentFacts.model_validate({
        "doc_type": "Rating Decision",
        "decision_date": "2021-03-04T00:00:00",
        "service_period": {"branch": "U.S. Army", "component": "Active Duty", "start": "2004-06-01",
                           "end": "200806", "discharge": "General (Under Honorable Conditions)"},
        "issues": [{"condition": "Tinnitus", "outcome": "Granted", "pct": "10%"},
                   {"condition": "PTSD", "outcome": "Denied.", "pct": None}],
        "combined_rating": "70%",
        "sc_conditions": [{"name": "Tinnitus", "rating_pct": "10 percent"}],
        "rep_kind": "Claims Agent",
        "mos": "88M Motor Transport Operator",
    })  # fmt: skip
    sp = f.service_period
    assert (f.doc_type, f.decision_date, f.combined_rating) == ("rating_decision", "2021-03-04", 70)
    assert (sp.branch, sp.component, sp.start, sp.end, sp.discharge) == ("army", "active", "2004-06", "2008-06", "general")
    assert [(i.outcome, i.pct) for i in f.issues] == [("granted", 10), ("denied", None)]
    assert f.sc_conditions[0].rating_pct == 10 and f.rep_kind == "agent"
    assert f.mos == ["88M Motor Transport Operator"]
    hon = DocumentFacts.model_validate({"service_period": {"discharge": "Honorable", "component": "Army Reserve"}})
    assert (hon.service_period.discharge, hon.service_period.component) == ("honorable", "reserve")


def test_dspy_extractor_normalizes_and_skips_the_disk_cache(monkeypatch):
    from dspy.clients import execution
    from dspy.utils.dummies import DummyLM

    from agent.cfile import make_dspy_extractor

    p = get_persona("recent_decision")
    decision = next(d[2] for d in build_documents(p) if d[0] == "rating_decision")
    lm = DummyLM([{"facts": {
        "doc_type": "rating_decision", "decision_date": "2021-04-16T00:00:00",
        "issues": [{"condition": "Post-traumatic stress disorder", "outcome": "Granted", "pct": "30%"}],
        "combined_rating": "30%", "sc_conditions": [{"name": "PTSD", "rating_pct": "30%"}],
    }}])  # fmt: skip
    seen, prepare = [], execution.prepare

    def spy(*args, **kwargs):
        call = prepare(*args, **kwargs)
        seen.append(call.kwargs.get("cache"))  # what decides the cache on a real dspy.LM
        return call

    monkeypatch.setattr(execution, "prepare", spy)
    facts, per_doc, _ = extract_cfile([decision], make_dspy_extractor(lm))
    assert per_doc[0].issues[0].condition == "ptsd" and per_doc[0].sc_conditions[0].name == "ptsd"
    assert facts.decisions[0].decision_date == "2021-04-16" and facts.combined_rating == 30
    assert seen == [False]  # no on-disk cache for C-file text


def test_one_bad_document_does_not_lose_the_note():
    from agent.cfile.extract import DocumentFacts

    p = get_persona("recent_decision")
    pdfs = [d[2] for d in build_documents(p)]

    class FailsOnLetters:
        def extract(self, text, doc_type):
            if doc_type == "notification_letter":
                raise ValueError("model output did not parse")
            return OfflineExtractor().extract(text, doc_type)

    corrupt = b"%PDF-1.4\n1 0 obj << /Length 99 >> stream\ngarbage"
    facts, per_doc, skipped = extract_cfile(pdfs + [corrupt, b"not a pdf"], FailsOnLetters())
    n_letters = sum(1 for d in build_documents(p) if d[0] == "notification_letter")
    assert skipped == 1 + n_letters + 2 and facts.decisions  # the rest still read
    note = render(facts, fee_pct=30, itf_date=None, intake_dob=None, as_of=date(2026, 11, 3))
    unread = [f for f in note.flags if f.startswith("Could not read")]
    assert len(unread) == n_letters + 2 and any("document " in f for f in unread)
    assert isinstance(per_doc[0], DocumentFacts)


def test_encrypted_pdf_is_flagged_not_fatal():
    from pypdf import PdfReader, PdfWriter

    p = get_persona("baseline_clean")
    docs = build_documents(p)
    w = PdfWriter(clone_from=PdfReader(BytesIO(docs[0][2])))
    w.encrypt(user_password="secret", algorithm="RC4-128")
    buf = BytesIO()
    w.write(buf)
    facts, _, skipped = extract_cfile([buf.getvalue(), docs[-1][2]], OfflineExtractor(), ["dd214.pdf", "str.pdf"])
    assert skipped == 2 and facts.problems == ["Could not read dd214.pdf (FileNotDecryptedError). Read it by hand."]


def test_undated_or_empty_key_documents_are_flagged_not_dropped():
    from agent.cfile.extract import DocumentFacts, merge

    request_letter = "We need more evidence. Please send a copy of your DD Form 214."
    assert triage(request_letter) == "dd214"  # the keyword triage is fooled ...
    empty = OfflineExtractor().extract(request_letter, "dd214")
    undated = DocumentFacts(doc_type="rating_decision", decision_date="sometime",
                            issues=[{"condition": "tinnitus", "outcome": "granted", "pct": 10}])  # fmt: skip
    blank = DocumentFacts(doc_type="rating_decision")
    facts = merge([empty, undated, blank], ["letter.pdf", "rd1.pdf", "rd2.pdf"])
    assert facts.service_periods == []  # ... but no "? ? - ?, Discharge unknown" line
    assert facts.decisions == []
    assert facts.problems == [
        "DD-214 unreadable (no key facts found): letter.pdf. Read it by hand.",
        (
            "Rating decision with no readable decision date: rd1.pdf. Its appeal deadline is not"
            " on the note; check it by hand."
        ),
        "Rating decision unreadable (no key facts found): rd2.pdf. Read it by hand.",
    ]
    note = render(facts, fee_pct=30, itf_date=None, intake_dob=None)
    assert "?" not in note.text.split("Service Era")[1].split("MOS")[0]
    assert note.flags == facts.problems


def test_iso_accepts_datetimes_and_us_dates():
    from agent.cfile.extract import _iso

    assert _iso("2021-03-04T00:00:00") == _iso("2021-03-04 00:00:00Z") == "2021-03-04"
    assert _iso("03/04/2021") == _iso("March 4, 2021") == _iso("4 March 2021") == "2021-03-04"
    assert _iso("2021-03-04T") is None and _iso("soon") is None


def test_deadline_today_is_current_across_a_leap_year():
    from agent.cfile.facts import CfileFacts, Decision, Issue

    facts = CfileFacts(decisions=[Decision(decision_date="2027-02-25", notified="2027-03-01",
                                           issues=[Issue(condition="tinnitus", outcome="denied")])])  # fmt: skip
    note = render(facts, fee_pct=30, itf_date=None, intake_dob=None, as_of=date(2028, 3, 1))
    assert note.deadlines and note.deadlines[0]["deadline"] == "2028-03-01"
    assert "OLD CLAIMS" not in note.text
    later = render(facts, fee_pct=30, itf_date=None, intake_dob=None, as_of=date(2028, 3, 2))
    assert not later.deadlines and "OLD CLAIMS" in later.text


def test_prior_rep_is_the_newest_signed():
    from agent.cfile.facts import CfileFacts, PriorRep

    facts = CfileFacts(prior_reps=[
        PriorRep(name="Newer Firm", kind="attorney", signed="2024-05-01"),
        PriorRep(name="Older Firm", kind="attorney", signed="2019-01-01"),
        PriorRep(name="A VSO", kind="vso", signed="2025-01-01"),
    ])  # fmt: skip
    note = render(facts, fee_pct=20, itf_date=None, intake_dob=None)
    assert note.text.startswith("FA 20%; Prior rep Newer Firm")


def test_documents_stub_regenerates_when_the_persona_changes(tmp_path):
    p = get_persona("baseline_clean")
    stub = DocumentsStub(tmp_path)
    stub.ensure(p)
    before = {d["documentId"] for d in stub.search(p.icn)}
    from dataclasses import replace

    changed = replace(p, cfile={**p.cfile, "pending_filings": [
        {"form": "0995", "filed": "2026-09-01", "conditions": ["tinnitus"]}]})  # fmt: skip
    stub.ensure(changed)
    after = stub.search(p.icn)
    assert len(after) == len(before) + 1
    assert len(list((tmp_path / p.icn).glob("*.pdf"))) == len(after)  # no stale PDFs left
    stub.ensure(changed)
    assert stub.search(p.icn) == after


def test_review4_ssn_dob_outcomes_forms_and_scans():
    from agent.cfile.extract import DocumentFacts, extract_cfile, merge, strip_ssns

    # the DOB next to a masked SSN stays (the replacement text is not a new "SSN" label)
    assert strip_ssns("SSN: 123-45-6789  DOB: 19850407\n4. GRADE") == "SSN: [SSN removed]  DOB: 19850407\n4. GRADE"
    assert strip_ssns("DOE, JOHN ARMY/RA 123 45 6789 19850407 1").endswith("[SSN removed] 19850407 1")
    assert strip_ssns("SSN: none\nDOB 1985 04 07\n2. ITEM") == "SSN: none\nDOB 1985 04 07\n2. ITEM"
    assert strip_ssns("ZIP 94305-1234") == "ZIP 94305-1234"
    # routine outcomes are read; an unreadable one is dropped and flagged, not the whole decision
    d = DocumentFacts.model_validate({
        "doc_type": "rating_decision", "decision_date": "2025-01-02", "evidence_form": "VA Form 21-526EZ",
        "issues": [{"condition": "PTSD", "outcome": "Increased", "pct": "70%"},
                   {"condition": "knee", "outcome": "Continued"}, {"condition": "x", "outcome": None}],
    })  # fmt: skip
    assert [(i.condition, i.outcome) for i in d.issues] == [("PTSD", "granted"), ("knee", "denied")]
    assert d.evidence_form == "526EZ"
    assert any("could not read the decision on x" in p for p in merge([d]).problems)
    # a scan (no text layer) is flagged, not silently triaged out
    import io

    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(612, 792)
    buf = io.BytesIO()
    w.write(buf)
    facts, _, skipped = extract_cfile([buf.getvalue()], None, ["DD-214 scan"])
    assert skipped == 1 and any("no text layer" in p for p in facts.problems)
