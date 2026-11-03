"""Skills in the architecture's layout, and that they stay in sync with the code they describe."""


from agent.skills import AGENTS, load_skills, read_skill, skill_index


def test_every_agent_has_skills_with_a_name_and_description():
    for agent in AGENTS:
        skills = load_skills(agent)
        assert skills
        for s in skills.values():
            assert s.name and len(s.description) > 20 and s.body.startswith("#")


def test_the_index_holds_only_names_and_descriptions():
    index = skill_index("orchestrator")
    assert "stage-playbook" in index and "## " not in index and "|" not in index


def test_read_skill_loads_one_and_names_the_others_on_a_miss():
    assert "new_condition" in read_skill("orchestrator", "flags")
    assert "Available: " in read_skill("orchestrator", "nope")


def test_the_orchestrator_skills_name_its_tools_and_the_stages():
    from agent import orchestrator
    from agent.harness import Turn

    playbook = read_skill("orchestrator", "stage-playbook")
    flags = read_skill("orchestrator", "flags")
    names = {t.name for t in orchestrator.tools(Turn(None, "c", "orchestrator", "", 1))}
    assert names == {"run_intake", "run_prep", "move_stage", "staff_task"}
    assert all(n in playbook for n in names)
    assert all(f"| {n} " in playbook for n in range(1, 7))
    assert "run_intake" in flags and "staff_task" in flags and "move_stage" in flags
    assert "closed" in playbook and "needs_human" in playbook


def test_the_routing_skill_matches_the_code_rules():
    routing = read_skill("orchestrator", "routing")
    assert "waiting for the attorney" in routing or "countersign" in routing
    assert "support" in routing and "Crisis" in routing and "held" in routing


def test_the_intake_skills_name_its_tools():
    from agent.intake import agent as intake
    from agent.harness import Turn

    text = "\n".join(s.body for s in load_skills("intake").values())
    names = {t.name for t in intake.tools(Turn(None, "c", "intake", "", 1))} - {"get_case"}
    assert set(load_skills("intake")) == {"screen-veteran", "poa-and-fees", "intent-to-file", "close-gaps"}
    assert all(n in text for n in names), names - {n for n in names if n in text}
    assert "waiting_on_attorney" in text and "stop rule" in text.lower() and "confirm" in text


def test_the_claims_prep_skills_name_its_tools_and_what_prefill_settles():
    from agent.claims_prep import agent as prep
    from agent.claims_prep.facts import FACT
    from agent.claims_prep.prefill import QUESTIONS
    from agent.harness import Turn

    text = "\n".join(s.body for s in load_skills("claims_prep").values())
    assert set(load_skills("claims_prep")) == {"face-note-format", "cite-check"}
    names = {t.name for t in prep.tools(Turn(None, "c", "claims_prep", "", 1))} - {"pull_cfile", "list_docs"}
    assert all(n in text for n in names), names - {n for n in names if n in text}
    kinds = set(FACT.json_schema()["discriminator"]["mapping"])
    assert all(f"`{k}`" in text for k in kinds), kinds - {k for k in kinds if f"`{k}`" in text}
    assert all(q in text for q in QUESTIONS) and "revocation" in text and "uncertain" in text


def test_the_support_skills_name_its_tools_and_never_promise_a_date():
    from agent.harness import Turn
    from agent.support import agent as support

    skills = load_skills("support")
    text = "\n".join(s.body for s in skills.values())
    assert set(skills) == {"answer-questions", "case-status", "hand-to-a-person"}
    names = {t.name for t in support.tools(Turn(None, "c", "support", "", 1))}
    assert all(n in text for n in names), names - {n for n in names if n in text}
    assert all(f"`{k}`" in text for k in ("new_condition", "contact_change", "complaint"))
    assert "Never promise a VA date" in skills["case-status"].body and "988" in text
    assert all(f"| stage {n}" in skills["case-status"].body for n in (3, 4, 5))
