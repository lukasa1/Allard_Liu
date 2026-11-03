"""Command line: `uv run intake <command>` (run `uv run intake <command> -h` for options).

serve      the web demo (http://localhost:8000)
simulate   watch one synthetic veteran go through a whole case on the runtime (needs the key)
eval       the simulated-veteran evaluation across conditions; writes results/<name>/report.md (needs the key)
support-eval  the customer-support sub-agent on labeled messages (intake_eval/support_messages.yaml)
personas   list the synthetic veterans
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from agent import config

CONDITION_HELP = (
    "ask_no_probes | ask | cfile, comma-separated, or 'all' (L32). ask_no_probes = no verification "
    "probes, no C-file prefill; ask = probes, no prefill; cfile = probes + C-file prefill + confirmation"
)
NO_KEY = ("This needs OPENROUTER_API_KEY (in your shell or the repo's .env): the agents and the simulated "
          "veteran run on Claude Haiku 5.5 through OpenRouter. There are no offline agents (D7).")  # fmt: skip


def _conditions(text: str) -> list[str]:
    from intake_eval.runner import CONDITIONS

    if text == "all":
        return list(CONDITIONS)
    wanted = [c.strip() for c in text.split(",") if c.strip()]
    if bad := [c for c in wanted if c not in CONDITIONS]:
        raise SystemExit(f"unknown condition(s) {bad}; choose from {list(CONDITIONS)}")
    return wanted


def unpriced(simulator: bool = True) -> list[str]:
    """The configured model slugs with no price in config.PRICES: their calls are traced at $0."""
    from agent.qa import DEFAULT_QA_MODEL

    env = config.os.environ
    agent = env.get("DSPY_MODEL") or config.DEFAULT_DSPY_MODEL
    models = {agent, env.get("QA_MODEL", DEFAULT_QA_MODEL)} | ({env.get("DSPY_SIM_MODEL") or agent} if simulator else set())
    return sorted(m for m in models if m not in config.PRICES)


def check_prices(max_cost: float | None, simulator: bool = True) -> None:
    """--max-cost can't hold for a model it can't price: refuse. Without --max-cost, warn."""
    if not (bad := unpriced(simulator)):
        return
    if max_cost is not None:
        raise SystemExit(f"--max-cost can't be enforced: no price in agent/config.py PRICES for {bad}, so "
                         "their calls would count as $0. Add their prices, or run without --max-cost.")  # fmt: skip
    print(f"WARNING: no price in agent/config.py PRICES for {bad}: the reported cost leaves their calls out.",
          file=sys.stderr, flush=True)  # fmt: skip


def _live(trials: int = 1, max_cost: float | None = None):
    """(make_rt, make_sim) on the live model, or exit with NO_KEY. Trials > 1 turn DSPy's response
    cache off, so trial 2 doesn't replay trial 1 (pass^k)."""
    if not config.os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit(NO_KEY)
    check_prices(max_cost)
    if trials > 1:
        config.os.environ["DSPY_CACHE"] = "0"
    from agent.runtime import make_runtime
    from intake_eval.simulator import DSPySimulator

    lm, sim_lm = config.make_lm(), config.make_lm(role="simulator")
    return (lambda data_dir: make_runtime(data_dir, lm)), (lambda persona: DSPySimulator(persona, sim_lm))


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    key = "set" if config.os.environ.get("OPENROUTER_API_KEY") else "NOT set: the page will say so"
    print(f"Demo: http://{args.host}:{args.port}  (OPENROUTER_API_KEY {key})", flush=True)
    uvicorn.run("demo.app:app", host=args.host, port=args.port, reload=False)


def cmd_simulate(args: argparse.Namespace) -> None:
    from agent.personas import get_persona
    from intake_eval.evaluate import estimated_calls, render_transcript
    from intake_eval.runner import run_case
    from intake_eval.scoring import score_run

    persona, conditions = get_persona(args.persona), _conditions(args.condition)
    if len(conditions) != 1:
        raise SystemExit("simulate runs one condition: ask_no_probes, ask or cfile")
    condition = conditions[0]
    make_rt, make_sim = _live(max_cost=args.max_cost)
    print(f"{persona.id} ({condition}): {estimated_calls(1)}", flush=True)
    data_dir = Path(tempfile.mkdtemp(prefix="simulate-"))
    run = run_case(persona, condition, lambda: make_rt(data_dir), make_sim(persona), max_cost=args.max_cost)
    print(render_transcript(persona, run, score_run(persona, run)))
    print(f"Case data and traces: {data_dir}")


def cmd_eval(args: argparse.Namespace) -> None:
    from agent.personas import load_personas
    from intake_eval.evaluate import aggregate, estimated_calls, headline_line, run_eval

    personas, conditions = load_personas(args.personas), _conditions(args.conditions)
    make_rt, make_sim = _live(args.trials, args.max_cost)
    runs = len(personas) * len(conditions) * args.trials
    print(f"{len(personas)} persona(s) x {len(conditions)} condition(s) x {args.trials} trial(s): "
          f"{estimated_calls(runs)}" + (f"; stops past ${args.max_cost:.2f}" if args.max_cost else ""), flush=True)  # fmt: skip
    out, scores = run_eval(personas, conditions, make_rt, make_sim, args.name, args.trials, args.max_cost)
    print("\nHeadline (counts only with zero critical errors and field accuracy held):")
    for cond in conditions:
        if sub := [s for s in scores if s.condition == cond]:
            print("  " + headline_line(cond, aggregate(sub)))
    agg = aggregate(scores)
    print(f"Critical errors {agg['critical_errors']} · cost ${agg['cost_total']:.2f}\nReport: {out / 'report.md'}")
    if args.strict and agg["critical_errors"]:
        sys.exit(1)


def cmd_support_eval(args: argparse.Namespace) -> None:
    import json

    from intake_eval.support_eval import (
        estimated_calls,
        load_messages,
        misses,
        run_support_eval,
        summarize,
    )

    if not config.os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit(NO_KEY)
    check_prices(args.max_cost, simulator=False)
    messages = load_messages(luke_only=args.luke)
    print(estimated_calls(len(messages)) + (f"; stops past ${args.max_cost:.2f}" if args.max_cost else ""), flush=True)
    scores = run_support_eval(messages, max_cost=args.max_cost)
    print(json.dumps(summarize(scores), indent=2))
    wrong = misses(scores)
    print("\nMisses:" if wrong else "\nNo misses.")
    for line in wrong:
        print(f"  {line}")
    if args.strict and wrong:
        sys.exit(1)


def cmd_personas(args: argparse.Namespace) -> None:
    from agent.personas import load_personas

    for p in load_personas():
        print(
            f"{p.id:<24} {p.display_name:<18} expected={p.expected_decision:<16} {p.summary[:90]}"
        )


def main(argv: list[str] | None = None) -> None:
    config.load_env()
    parser = argparse.ArgumentParser(
        prog="intake", description="VA claims agent: orchestrator, intake, claims prep, support (synthetic data only)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="run the web demo")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    def max_cost_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--max-cost", type=float, default=None,
                       help="stop when the traced cost (USD, every model call) passes this; checked between "
                            "steps, so one step may overshoot. Refused if a configured model has no price")  # fmt: skip

    p = sub.add_parser("simulate", help="watch one synthetic veteran go through a whole case (live model)")
    p.add_argument("--persona", default="baseline_clean")
    p.add_argument("--condition", default="cfile", help="ask_no_probes | ask | cfile")
    max_cost_arg(p)
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("eval", help="run the evaluation and write a report (live model)")
    p.add_argument("--personas", default="all", help="comma-separated persona ids, or 'all'")
    p.add_argument("--conditions", default="all", help=CONDITION_HELP)
    p.add_argument("--trials", type=int, default=1, help="trials per persona (pass^k); > 1 turns the cache off")
    p.add_argument("--name", default=None, help="results folder name (default: a timestamp)")
    p.add_argument("--strict", action="store_true", help="exit 1 if any critical error")
    max_cost_arg(p)
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("support-eval", help="score the customer-support sub-agent (live model)")
    p.add_argument("--luke", action="store_true", help="only the subset matching Luke's 50 messages")
    p.add_argument("--strict", action="store_true", help="exit 1 if any message is mishandled")
    max_cost_arg(p)
    p.set_defaults(func=cmd_support_eval)

    p = sub.add_parser("personas", help="list the synthetic veterans")
    p.set_defaults(func=cmd_personas)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
