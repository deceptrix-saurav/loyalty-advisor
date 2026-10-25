"""One loyalty check, start to finish.

Guard (input) -> Intake -> fill defaults + validate -> Analyst (tools) -> Strategist -> Designer -> grounded output.
`run_check` never raises: every failure becomes an event the UI can show.
"""
from __future__ import annotations

import json
import re
import time

from . import agents, engine, guards, templates
from .budget import Budget, BudgetExceeded, RunContext, budget as default_budget
from .config import ROOT, settings
from .llm import LLM, LLMError, OutputBlocked
from .tools import ToolBox

SAFETY_LOG = ROOT / "logs" / "safety.jsonl"
_NUMERIC = list(engine.LIMITS)


def _log_safety(kind: str, detail: dict) -> None:
    try:
        SAFETY_LOG.parent.mkdir(parents=True, exist_ok=True)
        with SAFETY_LOG.open("a") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind, **detail}) + "\n")
    except OSError:
        pass


def clean_fields(raw: dict | None) -> dict:
    """Keep only known fields, coerce types, drop blanks. Range checks happen in engine.validate."""
    out: dict = {}
    raw = raw or {}
    for k in _NUMERIC:
        v = raw.get(k)
        if v in (None, ""):
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            raise engine.ProfileError([f"{k} must be a number"])
    for k, valid in (("business_type", engine.BUSINESS), ("tech", engine.TECH_LEVEL), ("goal", engine.GOALS), ("currency", engine.CURRENCIES)):
        if raw.get(k) in valid:
            out[k] = raw[k]
    if isinstance(raw.get("competitor_has_program"), bool):
        out["competitor_has_program"] = raw["competitor_has_program"]
    name = re.sub(r"[^\w &'.,\-]", "", str(raw.get("name") or ""))[:60].strip()
    if name:
        out["name"] = name
    return out


def run_check(payload: dict, emit, session_id: str = "local", llm: LLM | None = None,
              budget: Budget = default_budget, mode: str | None = None) -> dict | None:
    mode = mode if mode in ("agentic", "lean") else settings.mode
    llm = llm or LLM(budget)
    try:
        ctx = budget.start_run(session_id, mode)
    except BudgetExceeded as exc:
        emit({"type": "error", "kind": "budget", "message": str(exc)})
        return None
    emit({"type": "run", "run_id": ctx.run_id, "mode": mode, "provider": llm.provider, "model": llm.model})
    try:
        return _run(payload, emit, ctx, llm, budget, mode)
    except BudgetExceeded as exc:
        _log_safety("budget_stop", {"run_id": ctx.run_id, "message": str(exc)})
        emit({"type": "guard", "name": "budget", "detail": str(exc)})
        emit({"type": "error", "kind": "budget", "message": str(exc), "usage": ctx.summary()})
    except OutputBlocked as exc:
        _log_safety("output_blocked", {"run_id": ctx.run_id, "message": str(exc)})
        emit({"type": "guard", "name": "output_leak", "detail": str(exc)})
        emit({"type": "error", "kind": "blocked", "message": str(exc), "usage": ctx.summary()})
    except LLMError as exc:
        emit({"type": "error", "kind": "llm", "message": str(exc), "usage": ctx.summary()})
    except engine.ProfileError as exc:
        emit({"type": "error", "kind": "input", "message": "Please fix: " + "; ".join(exc.problems)})
    return None


def _step(emit, agent: str, status: str, **kw):
    emit({"type": "step", "agent": agent, "status": status, **kw})


def _run(payload, emit, ctx: RunContext, llm: LLM, budget: Budget, mode: str) -> dict | None:
    # 1. input guard
    _step(emit, "Guard", "start", detail="Checking your input")
    check = guards.check_user_text(payload.get("text"))
    if not check.ok:
        _log_safety("input_blocked", {"run_id": ctx.run_id, "reasons": check.reasons, "snippet": check.text[:160]})
        _step(emit, "Guard", "blocked", detail=", ".join(check.reasons))
        emit({"type": "blocked", "reasons": check.reasons, "message": guards.explain_block(check.reasons)})
        return None
    if "too_long" in check.reasons:
        emit({"type": "note", "agent": "Guard", "detail": f"Text was longer than {settings.max_input_chars} characters and was shortened."})
    fields = clean_fields(payload.get("fields"))
    _step(emit, "Guard", "done", detail="Input accepted")

    # 2. intake
    if check.text:
        _step(emit, "Intake", "start", detail="Reading your description")
        extracted = agents.run_intake(llm, ctx, check.text)
        from_text = clean_fields({k: v for k, v in extracted.items() if k != "missing"})
        _step(emit, "Intake", "done", detail=f"Found {len(from_text)} details", found=from_text)
    else:
        from_text = {}
        _step(emit, "Intake", "skipped", detail="Form filled in: no AI call needed")
    merged = {**from_text, **fields}   # form fields win over text
    need = [lbl for k, lbl in (("business_type", "what kind of business it is"), ("monthly_transactions", "how many bills or orders you get in a month"),
                               ("avg_bill", "the average bill")) if k not in merged]
    if need:
        emit({"type": "need_info", "message": "I still need " + ", ".join(need) + ". Add it to the description or the fields and run again."})
        return None
    profile, assumptions = engine.complete_profile(merged)
    emit({"type": "profile", "profile": profile, "assumptions": assumptions})

    # 3. numbers (code) + analyst (model chooses extra checks)
    analysis = engine.full_analysis(profile, payload.get("design_key"))
    toolbox = ToolBox(profile)
    if mode == "agentic":
        _step(emit, "Analyst", "start", detail="Choosing which checks to run")
        results, notes = agents.run_analyst(llm, ctx, toolbox, profile, [a["field"] for a in assumptions], emit,
                                            settings.max_agent_steps, settings.max_tool_calls)
    else:
        _step(emit, "Analyst", "start", detail="Lean mode: running the standard checks in code")
        results, notes = {"what_ifs": [], "playbook": []}, ""
        for name in ("check_gates", "rank_designs", "compare_top_designs"):
            toolbox.call(name, {})
            emit({"type": "tool", "agent": "Code", "tool": name, "args": {}, "status": "ok"})
    _step(emit, "Analyst", "done", detail=notes[:200] if notes else "Checks complete")

    # 4. writers
    facts = agents.build_facts(profile, assumptions, analysis, results, notes)
    allowed = agents.allowed_for(facts, profile)
    code = analysis["verdict"]["code"]
    _step(emit, "Strategist", "start", detail="Answering: should you do this at all?")
    strategy, f1 = agents.run_writer(llm, ctx, "strategist", agents.STRATEGIST_INSTRUCTIONS, agents.STRATEGY_SCHEMA,
                                     "strategy", agents.STRATEGY_CHECK, facts, allowed, emit,
                                     templates.strategist_template, code)
    _step(emit, "Strategist", "done", detail=strategy["headline"])
    _step(emit, "Designer", "start", detail="Writing your program blueprint")
    blueprint, f2 = agents.run_writer(llm, ctx, "designer", agents.DESIGNER_INSTRUCTIONS, agents.DESIGN_SCHEMA,
                                      "blueprint", agents.DESIGN_CHECK, facts, allowed, emit,
                                      templates.designer_template, None)
    _step(emit, "Designer", "done", detail=blueprint["program_name"])
    for who, f in (("strategist", f1), ("designer", f2)):
        if f["fallback"] or f["grounding_retries"] or f["verdict_problem"]:
            _log_safety("writer_defense", {"run_id": ctx.run_id, "agent": who, **f})

    final = {"type": "final", "profile": profile, "assumptions": assumptions, "analysis": analysis, "strategy": strategy,
             "blueprint": blueprint, "flags": {"strategist": f1, "designer": f2}, "usage": ctx.summary(),
             "budget": budget.remaining(ctx.session_id), "measured": all(c["measured"] for c in ctx.calls) if ctx.calls else True,
             "provider": llm.provider, "model": llm.model, "playbook_used": results.get("playbook", [])}
    emit(final)
    return final
