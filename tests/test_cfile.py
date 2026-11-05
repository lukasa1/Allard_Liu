"""The C-file helpers and the face-note template: triage, SSN stripping, dates, deadlines."""

from datetime import date

from agent.cfile.extract import triage
from agent.cfile.facenote import cond_name, render, service_era
from agent.cfile.facts import truth_facts
from agent.personas import get_persona


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


def test_helpers():
    assert cond_name("ptsd") == "PTSD" and cond_name("left knee condition") == "Left knee condition"
    assert service_era("2004-06") == "Gulf War" and service_era("1968-01") == "Vietnam Era"
    assert service_era("1990-06", "1994-06") == "Gulf War"  # entered before 1990-08, served into it
    assert service_era("1976-01", "1980-01") == "Peacetime (post-Vietnam)" and service_era("1970-01", "1978-01") == "Vietnam Era"


def test_ssns_are_stripped_in_every_format_but_dates_dobs_and_zips_stay():
    from agent.cfile.extract import strip_ssns

    assert strip_ssns("SSN: 495-54-3022 / 495543022") == "SSN: [SSN removed] / [SSN removed]"
    assert strip_ssns("DATE OF BIRTH (YYYYMMDD): 19850407") == "DATE OF BIRTH (YYYYMMDD): 19850407"
    assert strip_ssns("SSN: 123-45-6789  DOB: 19850407\n4. GRADE") == "SSN: [SSN removed]  DOB: 19850407\n4. GRADE"
    assert strip_ssns("DOE, JOHN ARMY/RA 123 45 6789 19850407 1").endswith("[SSN removed] 19850407 1")
    assert strip_ssns("SSN: none\nDOB 1985 04 07\n2. ITEM") == "SSN: none\nDOB 1985 04 07\n2. ITEM"
    assert strip_ssns("ZIP 94305-1234") == "ZIP 94305-1234"
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


def test_prior_rep_is_the_newest_form_without_revocation_details():
    from agent.cfile.facts import CfileFacts, PriorRep

    facts = CfileFacts(prior_reps=[
        PriorRep(name="Newer Firm", kind="attorney", signed="2024-05-01"),
        PriorRep(name="Older Firm", kind="attorney", signed="2019-01-01"),
        PriorRep(name="A VSO", kind="vso", signed="2025-01-01", revoked="2025-06-01"),
    ])  # fmt: skip
    note = render(facts, fee_pct=20, itf_date=None, intake_dob=None)
    assert note.lines[0].text == "FA 20%; Prior rep Newer Firm"
    assert note.lines[0].sources == ("case:fee_agreement", "prior_reps.0")
    revoked = CfileFacts(prior_reps=[facts.prior_reps[2]])
    head = render(revoked, fee_pct=30, itf_date=None, intake_dob=None).lines[0]
    assert (head.text, head.sources) == ("FA 30%; No prior rep", ("case:fee_agreement", "prior_reps.0", "none:poa_form:prior_representative"))
    # a VSO is never a prior rep, even a current one and the newest
    vso = CfileFacts(prior_reps=[PriorRep(name="Older Firm", kind="attorney", signed="2019-01-01", revoked="2020-01-01"),
                                 PriorRep(name="DAV", kind="vso", signed="2025-01-01")])  # fmt: skip
    assert render(vso, fee_pct=30, itf_date=None, intake_dob=None).lines[0].text == "FA 30%; No prior rep"


def test_a_veteran_with_no_rating_decision_gets_a_plain_sc_line():
    """Live run 1: "SC (0%)|" with nothing after it read as garbled to the orchestrator."""
    note = render(truth_facts(get_persona("baseline_clean")), fee_pct=30, itf_date=None, intake_dob=None, firm="Law Firm")
    assert "SC at time of signing Law Firm - 0% (no rating decision in the C-file)" in note.text
    assert "SC (0%)| none" in note.text


def test_someone_who_never_served_has_no_c_file():
    from agent.cfile.synth import build_documents

    assert build_documents(get_persona("not_a_veteran")) == []
