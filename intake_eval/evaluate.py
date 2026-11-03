"""Run personas x conditions through whole cases, score each, and write a report.

Output (results/<run name>/):
  report.md         per-condition summary, per-persona table, every critical error
  summary.json      the same data, machine-readable
  transcripts/      each conversation (<condition>/<persona>.md) with the record, outcome and face note
"""

from __future__ import annotations

import json
import os
import traceback
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from agent import config
from agent.config import REPO_ROOT
from agent.personas import Persona
from intake_eval.runner import CaseRun, run_case
from intake_eval.scoring import Score, score_run

RESULTS_DIR = REPO_ROOT / "results"


COST_FIELDS = ("lm_calls", "input_tokens", "output_tokens", "cost_usd")
ORCHESTRATOR_FIELDS = (
    "decisions", "single_option_decisions", "wait_only_decisions", "model_decisions", "fallbacks",
    "illegal_choices",
)  # fmt: skip


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.0f}%"


def _num(x: float | None, digits: int = 1) -> str:
    return "–" if x is None else f"{x:.{digits}f}"


def headline_line(cond: str, a: dict[str, Any]) -> str:
    """One line per condition for the CLI: the headline and what it only counts together with."""
    return (
        f"{cond:<14} {_num(a['mean_structured_questions'])} structured questions per completed case "
        f"(n={a['completed_runs']}/{a['runs']}) · {a['runs_with_critical_errors']} of {a['runs']} runs "
        f"with critical errors · field accuracy {_pct(a['mean_field_accuracy'])}"
    )


@contextmanager
def _independent_trials(enabled: bool):
    """With DSPy's cache on, trial 2+ would replay trial 1 (so pass^k == pass^1): turn it off."""
    if not enabled:
        yield
        return
    import dspy

    old_env, old_cache = os.environ.get("DSPY_CACHE"), dspy.cache
    os.environ["DSPY_CACHE"] = "0"  # LMs built from here on (agent.config.make_lm)
    dspy.configure_cache(enable_disk_cache=False, enable_memory_cache=False)  # LMs built earlier
    print("  note: --trials > 1 with DSPy: response cache disabled so trials are independent")
    try:
        yield
    finally:
        dspy.cache = old_cache
        if old_env is None:
            os.environ.pop("DSPY_CACHE", None)
        else:
            os.environ["DSPY_CACHE"] = old_env


def _with_rollout(lm: Any, trial: int) -> Any:
    """A per-trial copy of a DSPy LM (rollout_id is part of DSPy's cache key)."""
    return lm.copy(rollout_id=trial) if lm is not None and hasattr(lm, "copy") else lm


def _crashed_score(persona: Persona, condition: str, exc: BaseException) -> Score:
    name = type(exc).__name__
    return Score(
        persona_id=persona.id, condition=condition, expected_decision=persona.expected_decision,
        decision="crashed", decision_correct=False, end_phase="crashed", end_phase_correct=False,
        fee_expected=None, fee_got=None, flags_expected=[], flags_got=[],
        critical_errors=[f"run crashed: {name}"], error=name,
    )  # fmt: skip


def run_eval(
    personas: list[Persona],
    conditions: list[str],
    provider: str = "offline",
    run_name: str | None = None,
    make_sim=None,
    lm=None,
    trials: int = 1,
) -> tuple[Path, list[Score]]:
    run_name = run_name or f"{datetime.now():%Y%m%d-%H%M%S}-{provider}"
    out = RESULTS_DIR / run_name
    out.mkdir(parents=True, exist_ok=True)
    scores: list[Score] = []
    vary = provider == "dspy" and trials > 1
    with _independent_trials(vary):
        if vary and lm is None:
            lm = config.make_lm()  # built after the cache is off; one copy per trial below
        for condition in conditions:
            (out / "transcripts" / condition).mkdir(parents=True, exist_ok=True)
            for persona in personas:
                for trial in range(trials):
                    suffix = f"-t{trial + 1}" if trials > 1 else ""
                    path = out / "transcripts" / condition / f"{persona.id}{suffix}.md"
                    try:
                        sim = make_sim(persona) if make_sim else None
                        if vary and getattr(sim, "lm", None) is not None:
                            sim.lm = _with_rollout(sim.lm, trial)
                        run = run_case(
                            persona, condition, provider=provider, simulator=sim,
                            lm=_with_rollout(lm, trial) if vary else lm,
                        )  # fmt: skip
                        score = score_run(persona, run)
                        text = render_transcript(persona, run, score)
                    except Exception as exc:  # e.g. the session couldn't be built: score it, go on
                        score = _crashed_score(persona, condition, exc)
                        text = f"# {persona.id} ({condition})\n\nRun crashed:\n\n```\n{traceback.format_exc()}```\n"
                    scores.append(score)
                    path.write_text(text)
                    print(
                        f"  {condition:<14} {persona.id:<24} {score.decision:<16}{'OK ' if score.decision_correct else 'XX '}"
                        f"fields={_pct(score.field_accuracy):>5} facenote={_pct(score.facenote_accuracy):>5} "
                        f"critical={len(score.critical_errors)} structured_q={score.structured_questions} "
                        f"narrative={score.narrative_prompts}"
                    )
                    _write(
                        out, run_name, provider, conditions, scores, trials
                    )  # partial results survive
    _write(out, run_name, provider, conditions, scores, trials)
    return out, scores


def _write(
    out: Path, run_name: str, provider: str, conditions: list[str], scores: list[Score], trials: int
) -> None:
    summary = {"provider": provider, "conditions": conditions, "trials": trials, "scores": [s.to_dict() for s in scores]}  # fmt: skip
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (out / "report.md").write_text(render_report(run_name, provider, conditions, scores, trials))


def aggregate(scores: list[Score]) -> dict[str, Any]:
    def avg(xs: list[float]) -> float | None:
        return mean(xs) if xs else None

    done = [s for s in scores if s.completed]
    signed = [s.turns_to_signed_poa for s in done if s.turns_to_signed_poa is not None]
    return {
        "runs": len(scores),
        "completed_runs": len(done),
        "decision_accuracy": avg([float(s.decision_correct) for s in scores]),
        "end_state_accuracy": avg([float(s.end_phase_correct) for s in scores]),
        "mean_field_accuracy": avg(
            [s.field_accuracy for s in scores if s.field_accuracy is not None]
        ),
        "mean_facenote_accuracy": avg(
            [s.facenote_accuracy for s in scores if s.facenote_accuracy is not None]
        ),
        "runs_with_critical_errors": sum(bool(s.critical_errors) for s in scores),
        "critical_errors": sum(len(s.critical_errors) for s in scores),
        "mean_chat_questions": avg([float(s.chat_questions) for s in scores]),
        # Process means are over completed runs: a crash or give-up would look "cheap".
        "mean_structured_questions": avg([float(s.structured_questions) for s in done]),
        "mean_narrative_prompts": avg([float(s.narrative_prompts) for s in done]),
        "mean_clarifications": avg([float(s.clarifications) for s in done]),
        "mean_poa_chat_turns": avg([float(s.poa_chat_turns) for s in done]),
        "mean_turns_to_signed_poa": avg([float(x) for x in signed]),
        "runs_signed_poa": len(signed),
        "mean_records_prefilled": avg([float(s.records_prefilled) for s in scores]),
        "mean_cfile_prefilled": avg([float(s.cfile_prefilled) for s in done]),
        "mean_agent_messages": avg([float(s.agent_messages) for s in scores]),
        "veteran_questions_answered": sum(s.veteran_questions_answered for s in scores),
        "redundant_asks": sum(s.redundant_asks for s in scores),
        "model_failures": sum(s.model_failures for s in scores),
        "runs_hit_step_limit": sum(s.hit_step_limit for s in scores),
        "runs_gave_up": sum(s.gave_up for s in scores),
        "runs_crashed": sum(bool(s.error) for s in scores),
        "mean_narrative_coverage": avg(
            [s.narrative_coverage for s in scores if s.narrative_coverage is not None]
        ),
        # cost: totals over every run (a failed run still spent tokens), means per run
        **{f"total_{k}": sum(getattr(s, k) for s in scores) for k in COST_FIELDS},
        **{f"mean_{k}": avg([float(getattr(s, k)) for s in scores]) for k in COST_FIELDS},
        # orchestrator: totals over every run
        **{k: sum(getattr(s, k) for s in scores) for k in ORCHESTRATOR_FIELDS},
    }


def pass_hat_k(scores: list[Score]) -> float | None:
    """τ-bench pass^k: share of personas whose every trial is free of critical errors."""
    by_persona: dict[str, list[bool]] = {}
    for s in scores:
        by_persona.setdefault(s.persona_id, []).append(not s.critical_errors)
    return mean(all(v) for v in by_persona.values()) if by_persona else None


def render_report(
    run_name: str, provider: str, conditions: list[str], scores: list[Score], trials: int
) -> str:
    lines = [
        f"# Case eval: {run_name}",
        "",
        f"Provider: `{provider}` · trials per persona: {trials}",
        "",
    ]
    lines += [
        "## Headline: structured questions asked",
        "",
        (
            "Structured intake questions the veteran was asked in chat (narrative prompts excluded, "
            "clarifications included), mean over **completed** runs only (no crash, step limit or "
            "give-up); n = completed / total. Fewer is better, but it only counts together with "
            "**zero critical errors** and field accuracy held, so all three are in the same row."
        ),
        "",
        "| Condition | Structured questions (mean) | n | Runs w/ critical errors | Field acc. | Narrative prompts | Clarifications | From VA records | From C-file |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cond in conditions:
        sub = [s for s in scores if s.condition == cond]
        if sub:
            a = aggregate(sub)
            lines.append(
                f"| {cond} | **{_num(a['mean_structured_questions'])}** | {a['completed_runs']}/{a['runs']} "
                f"| {a['runs_with_critical_errors']} of {a['runs']} | {_pct(a['mean_field_accuracy'])} "
                f"| {_num(a['mean_narrative_prompts'])} | {_num(a['mean_clarifications'])} "
                f"| {_num(a['mean_records_prefilled'])} | {_num(a['mean_cfile_prefilled'])} |"
            )
    lines += [
        "",
        "## By condition (how VA's records are used)",
        "",
        "| Condition | Runs | Decision | End state | Field acc. | Face note | Runs w/ critical | Critical | Chat questions | Model failures | Step limit | Gave up | Crashed | pass^k |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cond in conditions:
        sub = [s for s in scores if s.condition == cond]
        if not sub:
            continue
        a = aggregate(sub)
        lines.append(
            f"| {cond} | {a['runs']} | {_pct(a['decision_accuracy'])} | {_pct(a['end_state_accuracy'])} "
            f"| {_pct(a['mean_field_accuracy'])} | {_pct(a['mean_facenote_accuracy'])} | {a['runs_with_critical_errors']} "
            f"| {a['critical_errors']} | {a['mean_chat_questions']:.1f} | {a['model_failures']} "
            f"| {a['runs_hit_step_limit']} | {a['runs_gave_up']} | {a['runs_crashed']} | {_pct(pass_hat_k(sub))} |"
        )
    lines += [
        "",
        "## POA step and veteran questions",
        "",
        (
            "POA chat turns: the veteran's chat messages while the case was in the 21-22a step. Turns to "
            "signed POA: veteran actions (chat messages and card actions) until the 21-22a was signed "
            "(means over completed runs that signed). Veteran questions: questions the veteran asked "
            "that the agent answered or routed to the team (total)."
        ),
        "",
        "| Condition | POA chat turns (mean) | Turns to signed POA (mean) | Runs signed | Veteran questions answered |",
        "|---|---|---|---|---|",
    ]
    for cond in conditions:
        sub = [s for s in scores if s.condition == cond]
        if sub:
            a = aggregate(sub)
            lines.append(
                f"| {cond} | {_num(a['mean_poa_chat_turns'])} | {_num(a['mean_turns_to_signed_poa'])} "
                f"| {a['runs_signed_poa']} | {a['veteran_questions_answered']} |"
            )
    lines += [
        "",
        "## Cost per case",
        "",
        (
            "LM calls, tokens and cost from each case's usage log; means per run and totals per condition. "
            "Offline runs make no model calls, so they cost 0. With DSPy, the response cache makes "
            "repeated runs of the same prompts cheaper (often free), so a re-run under-states what a "
            "fresh case costs."
        ),
        "",
        "| Condition | LM calls (mean / total) | Input tokens (mean / total) | Output tokens (mean / total) | Cost USD (mean / total) |",
        "|---|---|---|---|---|",
    ]
    for cond in conditions:
        sub = [s for s in scores if s.condition == cond]
        if sub:
            a = aggregate(sub)
            lines.append(
                f"| {cond} | {_num(a['mean_lm_calls'])} / {a['total_lm_calls']} "
                f"| {_num(a['mean_input_tokens'], 0)} / {a['total_input_tokens']} "
                f"| {_num(a['mean_output_tokens'], 0)} / {a['total_output_tokens']} "
                f"| ${_num(a['mean_cost_usd'], 4)} / ${a['total_cost_usd']:.4f} |"
            )
    lines += [
        "",
        "## Orchestrator",
        "",
        (
            "How the case orchestrator chose its actions (totals). Single-option: only one action was "
            "allowed (counting `wait`), so there was nothing to choose. Model: the DSPy policy chose. "
            "Fallback: the model failed or chose an action that was not allowed, and the deterministic "
            "policy decided instead. Illegal: the model's choice was not in the allowed list. Offline "
            "runs use the deterministic policy for every decision, so model, fallback and illegal are 0 "
            "there by construction."
        ),
        "",
        "| Condition | Decisions | Wait only | One real option | Model chose | Fallbacks | Illegal choices |",
        "|---|---|---|---|---|---|---|",
    ]
    for cond in conditions:
        sub = [s for s in scores if s.condition == cond]
        if sub:
            a = aggregate(sub)
            lines.append(
                f"| {cond} | {a['decisions']} | {a['wait_only_decisions']} | {a['single_option_decisions']} | {a['model_decisions']} "
                f"| {a['fallbacks']} | {a['illegal_choices']} |"
            )
    lines += ["", "## Per persona", ""]
    for cond in conditions:
        lines += [
            f"### {cond}",
            "",
            "| Persona | Expected | Got | End | Fee | Fields | Face note | Critical | Structured q | Narrative | Clarif. | POA turns | Vet. questions | Cost USD |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for s in [s for s in scores if s.condition == cond]:
            fee = "–" if s.fee_got is None else f"{s.fee_got}%"
            structured = (
                f"{s.structured_questions}"
                if s.completed
                else f"({s.structured_questions}, incomplete)"
            )
            lines.append(
                f"| {s.persona_id} | {s.expected_decision} | {'✅' if s.decision_correct else '❌'} {s.decision} "
                f"| {'✅' if s.end_phase_correct else '❌'} {s.end_phase} | {fee} | {_pct(s.field_accuracy)} "
                f"| {_pct(s.facenote_accuracy)} | {len(s.critical_errors)} | {structured} | {s.narrative_prompts} "
                f"| {s.clarifications} | {s.poa_chat_turns} | {s.veteran_questions_answered} | {s.cost_usd:.4f} |"
            )
        lines.append("")
    errors = [(s.condition, s.persona_id, e) for s in scores for e in s.critical_errors]
    lines += ["## Critical errors", ""]
    lines += [f"- **{c} / {pid}**: {e}" for c, pid, e in errors] or ["None."]
    wrong = [
        (s.condition, s.persona_id, f)
        for s in scores
        for f in s.fields
        if f.status in ("wrong", "missing", "extra")
    ]
    lines += ["", "## Field mismatches", ""]
    lines += [
        f"- **{c} / {pid}** `{f.field}` ({f.status}, from {f.source or '?'}): expected `{f.expected}`, got `{f.got}`"
        for c, pid, f in wrong
    ] or ["None."]
    return "\n".join(lines) + "\n"


def render_transcript(persona: Persona, run: CaseRun, score: Score) -> str:
    case = run.case
    lines = [f"# {persona.id} ({run.condition})", "", persona.summary, "",
             f"Behaviours: {', '.join(persona.behaviors) or 'none'}", "", "## Conversation", ""]  # fmt: skip
    for turn in run.transcript:
        who = {"agent": "**Agent**", "veteran": "**Veteran**", "app": "_App_"}[turn["role"]]
        lines += [f"{who}: {turn['text']}", ""]
    lines += ["## Orchestrator decisions", ""]
    lines += [
        f"- `{d.event}` → **{d.action}** ({d.policy}): {d.reason}"
        for d in getattr(case, "decisions", None) or []
        if d.action != "wait"
    ]
    lines += [
        "",
        "## Outcome",
        "",
        "```json",
        case.intake_outcome.model_dump_json(indent=2) if case.intake_outcome else "null",
        "```",
    ]
    lines += [
        "",
        "## Collected record",
        "",
        "```json",
        run.session.intake.record.model_dump_json(indent=2, exclude_defaults=True),
        "```",
    ]
    if case.face_note:
        lines += ["", "## Face note", "", "```", case.face_note, "```"]
    if case.tasks:
        lines += ["", "## Staff tasks", ""] + [
            f"- [{t.kind}] {t.text}" + (f" (due {t.due})" if t.due else "") for t in case.tasks
        ]
    lines += ["", "## Score", "", f"- decision correct: {score.decision_correct}; end state: {score.end_phase}",
              f"- field accuracy: {_pct(score.field_accuracy)}; face note: {_pct(score.facenote_accuracy)}",
              f"- critical errors: {score.critical_errors or 'none'}",
              f"- model failures: {run.model_failures}; steps: {run.steps}; hit step limit: {run.hit_step_limit}",
              (f"- questions: {score.structured_questions} structured, {score.narrative_prompts} narrative, "
              f"{score.clarifications} clarifications; pre-filled: {score.records_prefilled} from VA records, "
              f"{score.cfile_prefilled} from the C-file"),
              (f"- POA: {score.poa_chat_turns} chat turns; {score.turns_to_signed_poa} actions to signed; "
              f"veteran questions answered: {score.veteran_questions_answered}"),
              (f"- cost: {score.lm_calls} LM calls, {score.input_tokens} in / {score.output_tokens} out tokens, "
              f"${score.cost_usd:.4f}"),
              (f"- orchestrator: {score.decisions} decisions ({score.single_option_decisions} single-option, "
              f"{score.model_decisions} model, {score.fallbacks} fallbacks, {score.illegal_choices} illegal)")]  # fmt: skip
    if run.error:
        lines += ["", "## Crash", "", "```", run.error.rstrip(), "```"]
    return "\n".join(lines) + "\n"
