"""Veteran intake agent: an orchestrator agent over one case, with an intake subagent.

agent/orchestrator.py  the orchestrating agent: picks the next action among the ones the case's
                       phase allows (DSPy, or a deterministic policy offline)
agent/session.py       one case end to end: wires the orchestrator, the intake subagent, the POA
                       skill, Lighthouse, QA and the face-note pipeline; used by the web demo, the
                       CLI and the eval
agent/intake/          the intake sub-agent: agent.py (its AgentSpec), checklist.py, documents.py,
                       plus the question bank, parsing and rules (the old controller and brains
                       are legacy, unused by the new intake)
agent/kb.py            kb_search, the knowledge-base tool shared by intake and support
agent/poa.py           the intake subagent's POA step: mounts poa_skill (the 21-22a skill)
agent/lighthouse/      VA Lighthouse API tools (stub / recorded / sandbox)
agent/qa.py            answers veterans' questions (web search limited to official sites)
agent/cfile/           Benefits Documents stub (synthetic C-files) and the face-note pipeline
"""
