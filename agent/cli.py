"""Command line: `uv run intake <command>` (run `uv run intake <command> -h` for options).

serve      the web demo (http://localhost:8000)
simulate   watch one synthetic veteran go through a whole case
eval       the simulated-veteran evaluation across conditions; writes results/<name>/report.md
support-eval  the customer-support subagent on labeled messages (intake_eval/support_messages.yaml)
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
    "ask_no_probes | ask | fetch | fetch_confirm, comma-separated, or 'all'. ask = no VA records "
    "(every question in chat); fetch = trust VA's records; fetch_confirm = records + confirm with the veteran"
)


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
    bad = [c for c in wanted if c not in CONDITIONS]
    if bad:
        raise SystemExit(f"unknown condition(s) {bad}; choose from {list(CONDITIONS)}")
    return wanted


def _sim_factory(provider: str):
    if provider != "dspy":
        return None
    from intake_eval.simulator import DSPySimulator

    lm = config.make_lm(role="simulator")
    return lambda persona: DSPySimulator(persona, lm)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    print(f"Demo: http://{args.host}:{args.port}  (provider: {config.default_provider()}, "
          f"Lighthouse: {config.os.environ.get('LIGHTHOUSE_MODE', 'stub')})", flush=True)  # fmt: skip
    uvicorn.run("demo.app:app", host=args.host, port=args.port, reload=False)


def cmd_simulate(args: argparse.Namespace) -> None:
    from agent.personas import get_persona
    from intake_eval.runner import run_case
    from intake_eval.scoring import score_run

    provider = _provider(args)
    persona = get_persona(args.persona)
    factory = _sim_factory(provider)
    run = run_case(
        persona, args.condition, provider=provider, simulator=factory(persona) if factory else None
    )
    for turn in run.transcript:
        who = {"agent": "Agent  ", "veteran": "Veteran", "app": "App    "}[turn["role"]]
        print(f"{who}: {turn['text']}\n")
    case = run.case
    print("--- orchestrator decisions ---")
    for d in case.decisions:
        if d.action != "wait":
            print(f"  {d.event:<32} -> {d.action:<24} {d.reason}")
    print(f"--- case ended in phase: {case.phase} ---")
    if case.intake_outcome:
        print(case.intake_outcome.model_dump_json(indent=2))
    if case.face_note:
        print("--- face note ---")
        print(case.face_note)
    if case.tasks:
        print("--- staff tasks ---")
        for t in case.tasks:
            print(f"  [{t.kind}] {t.text}" + (f" (due {t.due})" if t.due else ""))
    score = score_run(persona, run)
    print(f"--- score: critical errors {score.critical_errors or 'none'} ---")


def cmd_eval(args: argparse.Namespace) -> None:
    from agent.personas import load_personas
    from intake_eval.evaluate import aggregate, headline_line, run_eval

    provider = _provider(args)
    personas = load_personas(args.personas)
    conditions = _conditions(args.conditions)
    print(
        f"Running {len(personas)} persona(s) x {len(conditions)} condition(s) x {args.trials} trial(s), provider={provider}"
    )
    out, scores = run_eval(
        personas,
        conditions,
        provider,
        args.name,
        make_sim=_sim_factory(provider),
        trials=args.trials,
    )
    agg = aggregate(scores)
    print("\nHeadline: structured questions per completed case (mean),")
    print("with runs with critical errors and field accuracy (the headline counts only with zero):")
    for cond in conditions:
        sub = [s for s in scores if s.condition == cond]
        if sub:
            print("  " + headline_line(cond, aggregate(sub)))
    print(f"Decision accuracy {agg['decision_accuracy']:.0%} · end state {agg['end_state_accuracy']:.0%} · "
          f"critical errors {agg['critical_errors']}")  # fmt: skip
    print(f"Report: {out / 'report.md'}")
    if args.strict and agg["critical_errors"]:
        sys.exit(1)


def cmd_support_eval(args: argparse.Namespace) -> None:
    import json

    from intake_eval.support_eval import misses, run_support_eval, summarize

    scores = run_support_eval()
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

    p = sub.add_parser("simulate", help="watch one synthetic veteran go through a whole case")
    provider_arg(p)
    p.add_argument("--persona", default="baseline_clean")
    p.add_argument("--condition", default="fetch_confirm", help=CONDITION_HELP)
    p.set_defaults(func=cmd_simulate)

    p = sub.add_parser("eval", help="run the evaluation and write a report")
    provider_arg(p)
    p.add_argument("--personas", default="all", help="comma-separated persona ids, or 'all'")
    p.add_argument("--conditions", default="all", help=CONDITION_HELP)
    p.add_argument(
        "--trials", type=int, default=1, help="trials per persona (pass^k); set DSPY_CACHE=0"
    )
    p.add_argument(
        "--name", default=None, help="results folder name (default: timestamp + provider)"
    )
    p.add_argument("--strict", action="store_true", help="exit 1 if any critical error")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("support-eval", help="score the customer-support subagent (offline)")
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
