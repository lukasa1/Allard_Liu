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
