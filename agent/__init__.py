"""Veteran intake agent: an orchestrator over one case, with intake, claims-prep and support sub-agents.

agent/runtime.py       the runtime protocol (plan §3): routing, queued turns, the outbox
agent/harness.py       the shared ReAct turn every agent runs on
agent/orchestrator.py  the orchestrator agent: handoffs, flags, guarded stage moves
agent/stages.py        the stage table, derived from the case file (agent/casefile.py)
agent/intake/          the intake sub-agent: agent.py (its AgentSpec), checklist.py, documents.py,
                       plus the question bank, parsing and rules (the old controller and brains
                       are legacy, unused by the new intake)
agent/claims_prep/     the claims-prep sub-agent: the C-file -> cited facts -> prefill -> face note
agent/support/         the customer-support sub-agent (read-only; flags to the orchestrator)
agent/kb.py            kb_search, the knowledge-base tool shared by intake and support
agent/qa.py            answers veterans' questions (web search limited to official sites)
agent/cfile/           the simulated VBMS (synthetic C-files) and the face-note template
agent/lighthouse/      VA Lighthouse API tools (legacy; step 8 decides)
"""
