"""Run personas x conditions x trials through whole cases, score each per agent, write a report.

Output (results/<run name>/):
  report.md      the headline, then intake, orchestrator, claims prep, cost and latency per
                 agent, per-persona tables, every critical error and field mismatch
  summary.json   the same data, machine-readable (every Score)
  transcripts/   each conversation (<condition>/<persona>.md) with the decisions, face note and score
  runs/          each case's store, traces (traces.jsonl) and documents
"""

from __future__ import annotations

import json
import re
import shutil
import traceback
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Any

from agent.config import REPO_ROOT
from agent.personas import Persona
from agent.runtime import Runtime
from intake_eval.runner import CaseRun, Veteran, run_case
from intake_eval.scoring import Score, asked_answer, crashed_score, score_run

RESULTS_DIR = REPO_ROOT / "results"
SPLITS = ("dev", "heldout")  # agent/personas.py Persona.split
# Model calls per case, a rough estimate (an eligible case: two intake passes, one claims-prep turn,
# four orchestrator wakes). A run's report has the real counts.
EST_CALLS = {"orchestrator": 12, "intake": 190, "claims_prep": 20, "support": 2, "kb_search": 1, "simulator": 45}
AGENTS = ("orchestrator", "intake", "claims_prep", "support", "simulator", "judge")


def estimated_calls(runs: int) -> str:
    per = sum(EST_CALLS.values())
    return f"about {per} model calls per case ({', '.join(f'{k} {v}' for k, v in EST_CALLS.items())}); {runs} case(s): about {per * runs}"


def _pct(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.0f}%"


def _num(x: float | None, digits: int = 1) -> str:
    return "–" if x is None else f"{x:.{digits}f}"


def _avg(xs: list[float | None]) -> float | None:
    xs = [x for x in xs if x is not None]
    return mean(xs) if xs else None


def judge_answer(score: Score, run: CaseRun, persona: Persona, judge: Callable[[str, str, list[str]], dict]) -> None:
    """The judge's verdict on intake's answer to the persona's question, and its cost."""
    v = judge(persona.asks["text"].strip(), asked_answer(run), list(persona.asks["answer_key"]))
    score.ask_answer = v
    score.by_agent["judge"] = {"calls": 1, "input_tokens": 0, "output_tokens": 0,
                               "cost_usd": v.get("cost_usd", 0.0), "latency_s": 0.0}  # fmt: skip
    score.cost_usd += v.get("cost_usd", 0.0)


def _score_and_render(persona: Persona, condition: str, run: CaseRun,
                      judge: Callable[[str, str, list[str]], dict] | None) -> tuple[Score, str]:  # fmt: skip
    """A finished run's score and transcript. A failing judge or transcript writer never turns a
    finished run into a crash: the judge's error is recorded as its verdict, the score kept."""
    try:
        score = score_run(persona, run)
    except Exception as exc:  # noqa: BLE001 - a scorer bug: recorded as such, the run's cost still counted
        score = crashed_score(persona, condition, exc)
        score.critical_errors = [f"scoring failed: {type(exc).__name__}"]
        score.cost_usd = run.cost()
        return score, f"# {persona.id} ({condition})\n\nScoring failed:\n\n```\n{traceback.format_exc()}```\n"
    if judge and persona.asks.get("answer_key") and run.asked_index is not None:
        try:
            judge_answer(score, run, persona, judge)
        except Exception as exc:  # noqa: BLE001 - e.g. an unparseable verdict, a rate limit
            score.ask_answer = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        text = render_transcript(persona, run, score)
    except Exception:  # noqa: BLE001
        text = f"# {persona.id} ({condition})\n\nTranscript failed:\n\n```\n{traceback.format_exc()}```\n"
    return score, text


def run_eval(personas: list[Persona], conditions: list[str], make_rt: Callable[[Path], Runtime],
             make_sim: Callable[[Persona], Veteran], run_name: str | None = None, trials: int = 1,
             max_cost: float | None = None, judge: Callable[[str, str, list[str]], dict] | None = None,
             ) -> tuple[Path, list[Score]]:  # fmt: skip
    """`make_rt(data_dir)`: a runtime per case. `max_cost`: stop once the traced cost passes it.
    `judge(question, answer, key)`: grades intake's answer to a persona's question (`asks.answer_key`)."""
    run_name = run_name or f"{datetime.now():%Y%m%d-%H%M%S}"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", run_name) or ".." in run_name:
        # a folder name under results/, never a path: a rerun clears the case folders under it
        raise ValueError(f"--name must be a plain folder name (letters, digits, . _ -), not {run_name!r}")
    out = RESULTS_DIR / run_name
    out.mkdir(parents=True, exist_ok=True)
    scores: list[Score] = []
    spent, stopped = 0.0, False
    for condition in conditions:
        (out / "transcripts" / condition).mkdir(parents=True, exist_ok=True)
        for persona in personas:
            for trial in range(trials):
                if stopped:
                    break
                name = f"{persona.id}-t{trial + 1}" if trials > 1 else persona.id
                data_dir = out / "runs" / condition / name
                try:
                    # a rerun under the same name starts clean: the case id is the same each run
                    # (agent/clock.py), and an old case file, vault or documents must not carry over
                    shutil.rmtree(data_dir, ignore_errors=True)
                    run = run_case(persona, condition, lambda d=data_dir: make_rt(d), make_sim(persona),
                                   max_cost=max_cost, spent=spent)  # fmt: skip
                except Exception as exc:  # noqa: BLE001 - e.g. the runtime couldn't be built: score it, go on
                    score = crashed_score(persona, condition, exc)
                    text = f"# {persona.id} ({condition})\n\nRun crashed:\n\n```\n{traceback.format_exc()}```\n"
                else:
                    spent += run.cost()
                    stopped = run.stopped_at_cost
                    score, text = _score_and_render(persona, condition, run, judge)
                    spent += score.by_agent.get("judge", {}).get("cost_usd", 0.0)
                scores.append(score)
                (out / "transcripts" / condition / f"{name}.md").write_text(text)
                print(f"  {condition:<14} {name:<28} {score.end_state:<16}{'OK ' if score.scenario_pass else 'XX '}"
                      f"fields={_pct(score.field_accuracy):>5} facenote={_pct(score.facenote_line_accuracy):>5} "
                      f"critical={len(score.critical_errors)} structured_q={score.structured_questions} "
                      f"cost=${score.cost_usd:.3f}")  # fmt: skip
                _write(out, run_name, conditions, scores, trials, max_cost, stopped)  # partial results survive
    if stopped:
        print(f"  stopped: the traced cost ${spent:.2f} passed --max-cost ${max_cost:.2f}")
    _write(out, run_name, conditions, scores, trials, max_cost, stopped)
    return out, scores


def _write(out: Path, run_name: str, conditions: list[str], scores: list[Score], trials: int,
           max_cost: float | None, stopped: bool) -> None:  # fmt: skip
    summary = {"conditions": conditions, "trials": trials, "max_cost": max_cost, "stopped_at_cost": stopped,
               "by_condition": {c: aggregate([s for s in scores if s.condition == c]) for c in conditions},
               "by_split": {f"{c}/{sp}": aggregate(sub) for c in conditions for sp in SPLITS
                            if (sub := [s for s in scores if s.condition == c and s.split == sp])},
               "scores": [s.to_dict() for s in scores]}  # fmt: skip
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (out / "report.md").write_text(render_report(run_name, conditions, scores, trials, stopped))


def pass_hat_k(scores: list[Score]) -> float | None:
    """τ-bench pass^k: the share of personas whose every trial passed with no critical error."""
    by_persona: dict[str, list[bool]] = {}
    for s in scores:
        by_persona.setdefault(s.persona_id, []).append(s.scenario_pass and not s.critical_errors)
    return mean(all(v) for v in by_persona.values()) if by_persona else None


def aggregate(scores: list[Score]) -> dict[str, Any]:
    done = [s for s in scores if s.completed]  # process means: a crash would look "cheap"
    labelled = [s for s in scores if s.flag_decision_correct is not None]
    prep = [s for s in scores if s.verify_passed is not None]
    refused: dict[str, int] = {}
    for s in scores:
        for agent, n in s.refused.items():
            refused[agent] = refused.get(agent, 0) + n
    per_agent = {}
    for agent in AGENTS:
        rows = [s.by_agent.get(agent) for s in scores if agent in s.by_agent]
        calls = sum(r["calls"] for r in rows)
        per_agent[agent] = {
            "calls_mean": calls / len(scores) if scores else 0, "cost_total": sum(r["cost_usd"] for r in rows),
            "cost_mean": sum(r["cost_usd"] for r in rows) / len(scores) if scores else 0,
            "latency_per_call": sum(r["latency_s"] for r in rows) / calls if calls else None,
        }  # fmt: skip
    return {
        "runs": len(scores),
        "completed_runs": len(done),
        "scenario_pass_rate": _avg([float(s.scenario_pass) for s in scores]),
        "runs_with_critical_errors": sum(bool(s.critical_errors) for s in scores),
        "critical_errors": sum(len(s.critical_errors) for s in scores),
        "pass_hat_k": pass_hat_k(scores),
        "field_accuracy": _avg([s.field_accuracy for s in scores]),
        "structured_questions": _avg([float(s.structured_questions) for s in done]),
        "clarifications": _avg([float(s.clarifications) for s in done]),
        "narrative_answers": _avg([float(s.narrative_answers) for s in done]),
        "veteran_messages": _avg([float(s.veteran_messages) for s in done]),
        "prefill_share": _avg([s.prefill_share for s in done]),
        "turns_to_signed_poa": _avg([float(s.turns_to_signed_poa) for s in done if s.turns_to_signed_poa is not None]),
        "kb_calls": sum(s.kb_calls for s in scores),
        "kb_sourced": sum(s.kb_sourced for s in scores),
        "resumed_after": _avg([float(s.resumed_after) for s in scores if s.resumed_after is not None]),
        "scripted_sent": f"{sum(bool(s.scripted_sent) for s in scores)}/{sum(s.scripted_sent is not None for s in scores)}",
        "asked": sum(bool(s.ask_answer) or s.resumed_after is not None for s in scores),
        # graded answers only; a judge error (a parse failure, a rate limit) is no verdict
        "ask_answer_ok": f"{sum(bool(s.ask_answer.get('ok')) for s in scores)}/"
                         f"{sum(bool(s.ask_answer) and 'error' not in s.ask_answer for s in scores)}"
                         + (f" ({n} judge errors)" if (n := sum('error' in s.ask_answer for s in scores)) else ""),
        "untested": sum(s.untested for s in scores),
        "flag_decisions_correct": f"{sum(bool(s.flag_decision_correct) for s in labelled)}/{len(labelled)}",
        "refused": refused,
        "facenote_line_accuracy": _avg([s.facenote_line_accuracy for s in prep]),
        "facenote_fact_checks": _avg([sum(s.facenote_checks.values()) / len(s.facenote_checks)
                                      for s in prep if s.facenote_checks]),
        "verify_passed": f"{sum(bool(s.verify_passed) for s in prep)}/{len(prep)}",
        "citation_precision": _avg([s.citation_precision for s in prep]),
        "uncertain_lines": sum(s.uncertain_lines for s in prep),
        "cost_total": sum(s.cost_usd for s in scores),
        "cost_mean": _avg([s.cost_usd for s in scores]),
        "model_failures": sum(s.model_failures for s in scores),
        "per_agent": per_agent,
    }


def headline_line(cond: str, a: dict[str, Any]) -> str:
    return (f"{cond:<14} {_num(a['structured_questions'])} structured questions per completed case "
            f"(n={a['completed_runs']}/{a['runs']}) · {a['runs_with_critical_errors']} of {a['runs']} runs with "
            f"critical errors · field accuracy {_pct(a['field_accuracy'])} · scenario pass {_pct(a['scenario_pass_rate'])}")  # fmt: skip


NOTES = {
    "split": (
        "`dev`: the 14 personas the system was developed against, so these numbers are optimistic. "
        "`heldout`: the 6 personas not fixed against directly; they are optimistic too, since earlier "
        "runs of them informed later changes, baseline_clean is the same veteran as dev's "
        "asks_question_mid_intake, and reserve_not_in_records shares two_service_periods' mechanism."
    ),
    "conditions": (
        "Conditions: `ask_no_probes` = intake without the verification probes and without C-file "
        "prefill; `ask` = with the probes, no prefill; `cfile` = probes, prefill from the C-file and a "
        "confirmation of each conflict (the default, and what the demo runs)."
    ),
    "headline": (
        "Structured intake questions settled from the veteran's chat answers (narratives and the secure "
        "form excluded), mean over **completed** runs. Fewer is better only with zero critical errors and "
        "field accuracy held, so they share the row."
    ),
    "intake": (
        "KB: kb_search calls and those with a sourced answer. Persona question (asks_question_mid_intake, "
        "sent alone, answering nothing): `resumed after` = veteran replies until intake recorded an "
        "answer again (1 = it answered and asked its question again at once); `answer ok` = the LLM "
        "judge (intake_eval/judge.py) found every point of the persona's answer key and nothing wrong."
    ),
    "orchestrator": (
        "Scenario pass: the run completed and the case ended where the persona's expected decision says. "
        "Flag decisions: labelled scenarios (a persona's `expected.flag_decision`). Refused: tool calls and "
        "moves the guards refused, per agent."
    ),
    "claims_prep": (
        "Face-note lines: the note's lines against the note rendered from the ground-truth facts. Fact "
        "checks: the share of fact groups (DOB, periods, MOS, ratings, decisions, prior reps) read right. "
        "Citation precision: facts whose cited page shows their values."
    ),
    "cost": (
        "From the traces (prices in agent/config.py). Calls and cost are means per case; latency is "
        "per model call. The simulated veteran is counted separately; kb_search's model call is counted "
        "to the agent that searched."
    ),
}


def _section(title: str, note: str) -> list[str]:
    return ["", f"## {title}", "", note, ""]


def _table(header: list[str], rows: list[list[Any]]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + [
        "| " + " | ".join(str(c) for c in r) + " |" for r in rows
    ]


def render_report(run_name: str, conditions: list[str], scores: list[Score], trials: int, stopped: bool = False) -> str:
    agg = {c: aggregate(sub) for c in conditions if (sub := [s for s in scores if s.condition == c])}
    lines = [f"# Case eval: {run_name}", "", f"Trials per persona: {trials} · runs: {len(scores)}"]
    if stopped:
        lines.append("\n**Stopped early: the traced cost passed --max-cost.** Later runs are missing.")
    lines += ["", NOTES["conditions"], *_section("Headline: structured questions settled in chat", NOTES["headline"])]
    by_split = {(c, sp): aggregate(sub) for c in conditions for sp in SPLITS
                if (sub := [s for s in scores if s.condition == c and s.split == sp])}  # fmt: skip
    lines += _table(["Condition", "Structured questions", "n", "Runs w/ critical errors", "Field acc.",
                     "Prefilled (share)", "Clarifications", "Turns to signed 21-22a", "pass^k"],
                    [[c, f"**{_num(a['structured_questions'])}**", f"{a['completed_runs']}/{a['runs']}",
                      f"{a['runs_with_critical_errors']} of {a['runs']}", _pct(a["field_accuracy"]), _pct(a["prefill_share"]),
                      _num(a["clarifications"]), _num(a["turns_to_signed_poa"]), _pct(a["pass_hat_k"])]
                     for c, a in agg.items()])  # fmt: skip
    if len({sp for _, sp in by_split}) > 1:
        lines += _section("By split", NOTES["split"])
        lines += _table(["Condition", "Split", "Runs", "Scenario pass", "Runs w/ critical errors", "Field acc.",
                         "Structured questions", "Face-note lines", "Cost / case"],
                        [[c, sp, a["runs"], _pct(a["scenario_pass_rate"]), f"{a['runs_with_critical_errors']} of {a['runs']}",
                          _pct(a["field_accuracy"]), _num(a["structured_questions"]), _pct(a["facenote_line_accuracy"]),
                          f"${_num(a['cost_mean'], 4)}"] for (c, sp), a in by_split.items()])  # fmt: skip
    lines += _section("Intake", NOTES["intake"])
    lines += _table(["Condition", "Narrative answers", "Veteran messages", "KB calls / sourced",
                     "Question: resumed after / answer ok", "Scripted messages sent", "Model failures"],
                    [[c, _num(a["narrative_answers"]), _num(a["veteran_messages"]), f"{a['kb_calls']} / {a['kb_sourced']}",
                      f"{_num(a['resumed_after'])} / {a['ask_answer_ok']}" if a["asked"] else "–",
                      f"{a['scripted_sent']}" + (f" ({a['untested']} untested)" if a["untested"] else ""),
                      a["model_failures"]] for c, a in agg.items()])  # fmt: skip
    lines += _section("Orchestrator", NOTES["orchestrator"])
    lines += _table(["Condition", "Scenario pass", "Flag decisions correct", "Refused (per agent)"],
                    [[c, _pct(a["scenario_pass_rate"]), a["flag_decisions_correct"],
                      ", ".join(f"{k} {v}" for k, v in sorted(a["refused"].items())) or "none"] for c, a in agg.items()])  # fmt: skip
    lines += _section("Claims prep", NOTES["claims_prep"])
    lines += _table(["Condition", "Face-note lines", "Fact checks", "Verify passed", "Citation precision", "Uncertain lines"],
                    [[c, _pct(a["facenote_line_accuracy"]), _pct(a["facenote_fact_checks"]), a["verify_passed"],
                      _pct(a["citation_precision"]), a["uncertain_lines"]] for c, a in agg.items()])  # fmt: skip
    lines += _section("Cost and latency per agent", NOTES["cost"])
    rows = []
    for c, a in agg.items():
        for agent, p in a["per_agent"].items():
            rows.append([c, agent, _num(p["calls_mean"]), f"${p['cost_mean']:.4f}", f"${p['cost_total']:.4f}",
                         "–" if p["latency_per_call"] is None else f"{p['latency_per_call']:.2f}s"])  # fmt: skip
        rows.append([c, "**all**", "", f"${_num(a['cost_mean'], 4)}", f"${a['cost_total']:.4f}", ""])
    lines += _table(["Condition", "Agent", "Calls / case", "Cost / case", "Cost total", "Latency / call"], rows)
    lines += ["", "## Per persona", ""]
    for c in agg:
        lines += [f"### {c}", ""]
        lines += _table(["Persona", "Expected end", "Got", "Fields", "Structured q", "Prefilled", "Face-note lines",
                         "Citations", "Critical", "Cost"],
                        [[s.persona_id, s.expected_end, f"{'✅' if s.scenario_pass else '❌'} {s.end_state}",
                          _pct(s.field_accuracy), s.structured_questions if s.completed else f"({s.structured_questions}, incomplete)",
                          s.cfile_prefilled, _pct(s.facenote_line_accuracy), _pct(s.citation_precision),
                          len(s.critical_errors), f"${s.cost_usd:.4f}"] for s in scores if s.condition == c])  # fmt: skip
        lines.append("")
    lines += ["## Critical errors", ""]
    lines += [f"- **{s.condition} / {s.persona_id}**: {e}" for s in scores for e in s.critical_errors] or ["None."]
    lines += ["", "## Field mismatches", ""]
    lines += [f"- **{s.condition} / {s.persona_id}** `{f.field}` ({f.status}, from {f.source or '?'}): "
              f"expected `{f.expected}`, got `{f.got}`"
              for s in scores for f in s.fields if f.status in ("wrong", "missing", "extra")] or ["None."]  # fmt: skip
    return "\n".join(lines) + "\n"


DECISIONS = ("handoff", "refused", "stage_changed", "side_state_changed", "task_created", "support_flag",
             "escalated", "subagent_result")  # fmt: skip


def render_transcript(persona: Persona, run: CaseRun, score: Score) -> str:
    case = run.case
    lines = [f"# {persona.id} ({run.condition})", "", persona.summary, "",
             f"Behaviours: {', '.join(persona.behaviors) or 'none'}", "", "## Conversation", ""]  # fmt: skip
    for t in run.transcript:
        who = {"agent": "**Agent**", "veteran": "**Veteran**", "app": "_App_"}[t["role"]]
        lines += [f"{who}: {t['text']}", ""]
    lines += ["## Decisions and moves", ""]
    lines += [f"- #{e.seq} `{e.type}` by {e.actor}: {json.dumps(e.data)[:300]}" for e in run.events if e.type in DECISIONS]
    lines += ["", "## Answers", "", "```json",
              json.dumps({k: {"value": a.value, "source": a.source, "unknown": a.unknown} for k, a in case.answers.items()},
                         indent=1, default=str), "```"]  # fmt: skip
    if case.prep.face_note:
        lines += ["", "## Face note", "", "```", case.prep.face_note, "```"]
    if case.tasks:
        lines += ["", "## Staff tasks", ""] + [f"- [{t.kind}] {t.text}" + (f" (due {t.due})" if t.due else "") for t in case.tasks]
    lines += ["", "## Score", "", "```json", json.dumps(score.to_dict(), indent=1, default=str), "```"]
    if run.error:
        lines += ["", "## Crash", "", "```", run.error.rstrip(), "```"]
    return "\n".join(lines) + "\n"
