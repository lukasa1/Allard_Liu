"""`prefill`: write the intake answers the C-file settles, and record where it disagrees.

For each question the C-file can answer, the value is built in code from the recorded facts (in
the shapes `parsing.coerce` gives intake's own answers), with the source "C-file p. N" from the
facts' cites. Against an answer already on file:
  - none, unknown, or itself from the C-file: the C-file's value is written;
  - the same value: the veteran's answer stays;
  - a different character of discharge on a DD-214: the DD-214 wins, written straight to the
    answer (with a staff task), so the firm's stop rules see it at once;
  - anything else: a Conflict. The veteran's answer stays until pass 2 asks them to confirm, and
    a staff task is created.
The checklist is rebuilt (and the stop rules run) in the same patch. In the eval conditions `ask`
and `ask_no_probes` (casefile.EvalCondition) prefill writes nothing: pass 2 asks every question.
"""

from __future__ import annotations

from typing import Any, Literal

from agent.casefile import Answer, CaseFile, Conflict, Task
from agent.cfile.facts import CfileFacts, newest_private_rep, same_period
from agent.claims_prep.facts import Fact
from agent.intake import checklist
from agent.intake.conditions import normalize_condition
from agent.intake.schema import ServicePeriod

Prefillable = Literal["service_periods", "filed_before", "rating_pct", "sc_conditions", "prior_attorney",
                      "prior_attorney_name", "mos"]  # fmt: skip
QUESTIONS: tuple[str, ...] = Prefillable.__args__


def _source(facts: list[Fact]) -> str:
    pages = sorted({f.cite.page for f in facts})
    return f"C-file p. {pages[0]}" if len(pages) == 1 else f"C-file pp. {', '.join(map(str, pages))}"


def _paths(cites: dict[str, Fact], prefix: str) -> list[Fact]:
    return [f for p, f in cites.items() if p == prefix or p.startswith(prefix + ".")]


def values(cf: CfileFacts, cites: dict[str, Fact]) -> dict[str, tuple[Any, list[Fact]]]:
    """question -> (value, the facts it came from), for what the fact table settles."""
    out: dict[str, tuple[Any, list[Fact]]] = {}
    if cf.service_periods:
        out["service_periods"] = ([p.model_dump() for p in cf.service_periods], _paths(cites, "service_periods"))
    if cf.decisions:
        out["filed_before"] = (True, [cites[f"decisions.{i}"] for i in range(len(cf.decisions))])
    if cf.combined_rating is not None:
        out["rating_pct"] = (cf.combined_rating, [cites["combined_rating"]])
    if cf.sc_conditions:
        out["sc_conditions"] = ([c.model_dump() for c in cf.sc_conditions], _paths(cites, "sc_conditions"))
    if rep := newest_private_rep(cf):
        i = cf.prior_reps.index(rep)
        out["prior_attorney"] = (True, [cites[f"prior_reps.{i}"]])
        out["prior_attorney_name"] = (rep.name, [cites[f"prior_reps.{i}"]])
    if cf.mos:
        out["mos"] = (list(cf.mos), _paths(cites, "mos"))
    return out


def _holder(case: CaseFile, q: str) -> str:
    """The question whose answer the intake record reads for q's field. A probe shares its field
    with the question it double-checks (prior_claim_probe -> filed_before), and the last one
    answered in the bank's order wins, so that is the answer to fill or to confirm."""
    field = checklist.BANK.by_id[q].field
    answered = [x.id for x in checklist.BANK.structured
                if x.field == field and x.id in case.answers and x.type != "service_periods_append"]  # fmt: skip
    return answered[-1] if answered else q


def _same(q: str, a: Any, b: Any) -> bool:
    if q == "sc_conditions":
        return {(normalize_condition(c["name"]), c.get("rating_pct")) for c in a} == {
            (normalize_condition(c["name"]), c.get("rating_pct")) for c in b}  # fmt: skip
    if q == "mos":
        return {m.lower().split()[0] for m in a if m.strip()} == {m.lower().split()[0] for m in b if m.strip()}
    if q == "prior_attorney_name":
        return a.lower() in b.lower() or b.lower() in a.lower()
    return a == b


def _conflict(case: CaseFile, q: str, on_file: Any, cfile: Any, cite: str) -> None:
    case.conflicts = [c for c in case.conflicts if c.question != q or c.resolved_at]
    case.conflicts.append(Conflict(question=q, on_file=on_file, cfile=cfile, cite=cite))
    _task(case, f"C-file vs intake on {q} ({cite}): pass 2 asks the veteran to confirm. Review the difference.")


def _task(case: CaseFile, text: str) -> None:
    if not any(t.text == text and not t.done_at for t in case.tasks):
        case.tasks.append(Task(kind="staff", text=text))


def _periods(case: CaseFile, cfile: list[dict], source: str) -> list[str]:
    """Service periods: the DD-214's discharge replaces the veteran's for the same period; a period
    the veteran didn't list is a conflict on `other_service_periods`."""
    c_periods = [ServicePeriod.model_validate(c) for c in cfile]
    on_file = checklist.record(case).service_periods
    out = []
    for key in ("service_periods", "other_service_periods"):
        ans = case.answers.get(key)
        if not ans or ans.unknown or not ans.value:
            continue
        for p in ans.value:
            match = next((c for c in c_periods if same_period(c, ServicePeriod.model_validate(p))), None)
            if match and match.discharge and p.get("discharge") != match.discharge:
                p["discharge"] = match.discharge
                case.answers[key] = ans.model_copy(update={"source": f"{ans.source}; discharge: DD-214, {source}"})
                out.append("discharge_from_dd214")
            # "2004 to May 2010": the veteran gave a year, the DD-214 has the month: take the month
            dated = [e for e in ("start", "end") if match and (getattr(match, e) or "").startswith(f"{p.get(e)}-")
                     and len(str(p.get(e) or "")) == 4]  # fmt: skip
            for e in dated:
                p[e] = getattr(match, e)
            if dated:
                ans = case.answers[key]
                case.answers[key] = ans.model_copy(update={"source": f"{ans.source}; months: DD-214, {source}"})
                out.append("months_from_dd214")
    if "discharge_from_dd214" in out:  # months alone ("2007 to 2015") are no conflict
        _task(case, f"The DD-214 ({source}) shows a different discharge than the veteran gave; the record now follows the DD-214.")
    new = [c.model_dump() for c in c_periods if not any(same_period(c, p) for p in on_file)]
    if new:
        held = case.answers.get("other_service_periods")
        _conflict(case, "other_service_periods", held.value if held else [], new, source)
        out.append("conflicts")
    return sorted(set(out)) or ["kept"]


def apply(case: CaseFile, questions: list[str], cf: CfileFacts, cites: dict[str, Fact]) -> dict[str, list[str]]:
    """Mutates `case`; returns what happened to each question."""
    if case.eval_condition != "cfile":
        case.prep.prefill_done = True
        checklist.refresh(case)
        return {"skipped": list(questions)}
    settled = values(cf, cites)
    out: dict[str, list[str]] = {"written": [], "kept": [], "conflicts": [], "discharge_from_dd214": [],
                                 "months_from_dd214": [], "no_facts": []}  # fmt: skip
    for q in questions:
        if q not in settled:
            out["no_facts"].append(q)
            continue
        value, facts = settled[q]
        source = _source(facts)
        key = _holder(case, q)
        stale = {key, "other_service_periods"} if q == "service_periods" else {key}
        case.conflicts = [c for c in case.conflicts if c.question not in stale or c.resolved_at]  # rebuilt below
        held = case.answers.get(key)
        if held is None or held.unknown or held.source.startswith("C-file"):
            case.answers[key] = Answer(value=value, source=source)
            out["written"].append(key)
        elif q == "service_periods":
            for what in _periods(case, value, source):
                out[what].append("other_service_periods" if what == "conflicts" else q)
        elif _same(q, held.value, value):
            out["kept"].append(key)
        else:
            _conflict(case, key, held.value, value, source)
            out["conflicts"].append(key)
    case.prep.prefill_done = True
    checklist.refresh(case)
    return {k: v for k, v in out.items() if v}
