"""Command line: `uv run intake <command>` (run `uv run intake <command> -h` for options).

serve      the web demo (http://localhost:8000)
simulate   watch one synthetic veteran go through a whole case on the runtime (needs the key)
eval       the simulated-veteran evaluation across conditions; writes results/<name>/report.md (needs the key)
support-eval  the customer-support sub-agent on labeled messages (intake_eval/support_messages.yaml)
facenote   run the C-file -> face note pipeline on a persona's synthetic C-file or a folder of PDFs
personas   list the synthetic veterans
lighthouse-record  save a VA sandbox test user's responses for LIGHTHOUSE_MODE=recorded
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from datetime import date
from pathlib import Path

from agent import config

CONDITION_HELP = (
    "ask_no_probes | ask | cfile, comma-separated, or 'all' (L32). ask_no_probes = no verification "
    "probes, no C-file prefill; ask = probes, no prefill; cfile = probes + C-file prefill + confirmation"
)
NO_KEY = ("This needs OPENROUTER_API_KEY (in your shell or the repo's .env): the agents and the simulated "
          "veteran run on Claude Haiku 5.5 through OpenRouter. There are no offline agents (D7).")  # fmt: skip


def _provider(args: argparse.Namespace) -> str:
    provider = args.provider or config.default_provider()
    if provider == "dspy" and not (
        config.os.environ.get("OPENROUTER_API_KEY") or config.os.environ.get("DSPY_MODEL")
    ):
        raise SystemExit(
            "--provider dspy needs OPENROUTER_API_KEY in .env (or DSPY_MODEL for another LiteLLM provider)."
        )
    return provider


def _conditions(text: str) -> list[str]:
    from intake_eval.runner import CONDITIONS

    if text == "all":
        return list(CONDITIONS)
    wanted = [c.strip() for c in text.split(",") if c.strip()]
    if bad := [c for c in wanted if c not in CONDITIONS]:
        raise SystemExit(f"unknown condition(s) {bad}; choose from {list(CONDITIONS)}")
    return wanted


def _live(trials: int = 1):
    """(make_rt, make_sim) on the live model, or exit with NO_KEY. Trials > 1 turn DSPy's response
    cache off, so trial 2 doesn't replay trial 1 (pass^k)."""
    if not config.os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit(NO_KEY)
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
    make_rt, make_sim = _live()
    print(f"{persona.id} ({condition}): {estimated_calls(1)}", flush=True)
    data_dir = Path(tempfile.mkdtemp(prefix="simulate-"))
    run = run_case(persona, condition, lambda: make_rt(data_dir), make_sim(persona), max_cost=args.max_cost)
    print(render_transcript(persona, run, score_run(persona, run)))
    print(f"Case data and traces: {data_dir}")


def cmd_eval(args: argparse.Namespace) -> None:
    from agent.personas import load_personas
    from intake_eval.evaluate import aggregate, estimated_calls, headline_line, run_eval

    personas, conditions = load_personas(args.personas), _conditions(args.conditions)
    make_rt, make_sim = _live(args.trials)
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

    from intake_eval.support_eval import load_messages, misses, run_support_eval, summarize

    if not config.os.environ.get("OPENROUTER_API_KEY"):
        raise SystemExit(NO_KEY)
    scores = run_support_eval(load_messages(luke_only=args.luke))
    print(json.dumps(summarize(scores), indent=2))
    wrong = misses(scores)
    print("\nMisses:" if wrong else "\nNo misses.")
    for line in wrong:
        print(f"  {line}")
    if args.strict and wrong:
        sys.exit(1)


def cmd_facenote(args: argparse.Namespace) -> None:
    from agent.cfile import (
        DocumentsStub,
        OfflineExtractor,
        extract_cfile,
        make_dspy_extractor,
        render,
    )
    from agent.cfile.extract import _iso

    provider = _provider(args)
    if args.cfile:
        folder = Path(args.cfile)
        # VBMS exports and scanners write .PDF as often as .pdf.
        paths = sorted(p for p in folder.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf")
        pdfs = [p.read_bytes() for p in paths]
        names = [str(p.relative_to(folder)) for p in paths]
        if not pdfs:
            raise SystemExit(f"no PDFs under {folder}")
        if provider != "dspy":
            print(
                "[offline extractor: it only reads the synthetic layout. Use --provider dspy for real-shaped C-files.]\n"
            )
        # Compared as ISO dates: "11/20/1972" is the same DOB as "1972-11-20", not a mismatch.
        intake_dob = _iso(args.dob) if args.dob else None
        if args.dob and not intake_dob:
            raise SystemExit(f"--dob: unrecognised date {args.dob!r}; use YYYY-MM-DD or MM/DD/YYYY")
    else:
        from agent.personas import get_persona

        persona = get_persona(args.persona)
        stub = DocumentsStub(Path(tempfile.mkdtemp(prefix="cfile-")))
        stub.ensure(persona)
        listing = stub.search(persona.icn)
        pdfs = [stub.download(persona.icn, d["documentId"]) for d in listing]
        names = [d["subject"] for d in listing]
        intake_dob = persona.identity.get("dob_typed") or persona.identity.get("dob")
    extractor = make_dspy_extractor(config.make_lm()) if provider == "dspy" else OfflineExtractor()
    facts, per_doc, skipped = extract_cfile(pdfs, extractor, names)
    note = render(facts, fee_pct=args.fee, itf_date=args.itf, intake_dob=intake_dob,
                  as_of=date.fromisoformat(args.as_of) if args.as_of else None)  # fmt: skip
    print(f"[{len(pdfs)} documents, {skipped} skipped (triage or unreadable), {len(per_doc)} read]\n")
    print(note.text)
    for flag in note.flags:
        print(f"\nFLAG: {flag}")


def cmd_personas(args: argparse.Namespace) -> None:
    from agent.personas import load_personas

    for p in load_personas():
        print(
            f"{p.id:<24} {p.display_name:<18} expected={p.expected_decision:<16} {p.summary[:90]}"
        )


def cmd_lighthouse_record(args: argparse.Namespace) -> None:
    from agent.lighthouse.client import record_sandbox

    folder = record_sandbox(args.icn, args.label)
    print(f"Saved to {folder}. Set LIGHTHOUSE_MODE=recorded to replay it.")


def main(argv: list[str] | None = None) -> None:
    config.load_env()
    parser = argparse.ArgumentParser(
        prog="intake", description="Veteran intake agent (synthetic data only)."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def provider_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--provider", choices=list(config.PROVIDERS), default=None,
                       help="offline = rule-based, no key; dspy = DSPy on DSPY_MODEL (default: dspy if "
                            "OPENROUTER_API_KEY is set, else offline)")  # fmt: skip

    p = sub.add_parser("serve", help="run the web demo")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=cmd_serve)

    def max_cost_arg(p: argparse.ArgumentParser) -> None:
        p.add_argument("--max-cost", type=float, default=None,
                       help="stop when the traced cost (USD, agents + simulated veteran) passes this")  # fmt: skip

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
    p.set_defaults(func=cmd_support_eval)

    p = sub.add_parser("facenote", help="C-file -> face note")
    provider_arg(p)
    src = p.add_mutually_exclusive_group()
    src.add_argument(
        "--persona", default="recent_decision", help="use this persona's synthetic C-file"
    )
    src.add_argument("--cfile", help="a folder of C-file PDFs (e.g. Ben's samples)")
    p.add_argument("--fee", type=int, default=30)
    p.add_argument("--itf", default=None, help="the firm's intent-to-file date, YYYY-MM-DD")
    p.add_argument(
        "--dob",
        default=None,
        help="DOB from intake, checked against the DD-214: YYYY-MM-DD, MM/DD/YYYY or 'November 20, 1972'",
    )
    p.add_argument("--as-of", default=None, help="today's date for deadlines, YYYY-MM-DD")
    p.set_defaults(func=cmd_facenote)

    p = sub.add_parser("personas", help="list the synthetic veterans")
    p.set_defaults(func=cmd_personas)

    p = sub.add_parser("lighthouse-record", help="save sandbox responses for recorded mode")
    p.add_argument("--icn", required=True)
    p.add_argument("--label", required=True, help="display name for the recorded test user")
    p.set_defaults(func=cmd_lighthouse_record)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
