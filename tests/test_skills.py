"""Skills in the architecture's layout, and that they stay in sync with the code they describe."""

import re

from agent.orchestrator import ACTIONS
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


def test_the_stage_playbook_names_every_orchestrator_action():
    playbook = read_skill("orchestrator", "stage-playbook")
    named = set(re.findall(r"[a-z_]{6,}", playbook))
    missing = {a.name for a in ACTIONS} - named
    assert missing == set(), f"stage-playbook doesn't mention {missing}"


def test_the_dspy_policy_offers_read_skill():
    from agent.orchestrator import DSPyPolicy

    policy = DSPyPolicy(lm=None)
    assert "read_skill" in policy.predict.tools
