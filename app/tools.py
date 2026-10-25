"""Tools the analyst agent can call.

Read-only, bound to one business profile on the server, arguments validated. The model never retypes the
owner's numbers, cannot reach any other business's data, and cannot send or change anything.
"""
from __future__ import annotations

import json

from . import engine
from .config import ROOT

PLAYBOOK = json.loads((ROOT / "data" / "playbook.json").read_text())["entries"]
DESIGN_KEYS = list(engine.DESIGNS)
_GIVE = {"type": "number", "description": "What-if: cap on rewards as % of member spend (0.5 to 30). Omit to use the sized default."}


def _fn(name, desc, props=None, required=None):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props or {}, "required": required or [], "additionalProperties": False}}}


TOOL_SCHEMAS = [
    _fn("check_gates", "Readiness checks: returning customers, enough regulars, margin, reward size, recognising customers, owner time."),
    _fn("rank_designs", "Score the six program designs for this business, with what each one needs."),
    _fn("get_design_plan", "Exact parameters, rules and how it works for one design.",
        {"design_key": {"type": "string", "enum": DESIGN_KEYS}, "max_giveaway_pct": _GIVE}, ["design_key"]),
    _fn("run_economics", "Pessimistic, expected and optimistic monthly result for one design, with break-even lift.",
        {"design_key": {"type": "string", "enum": DESIGN_KEYS}, "max_giveaway_pct": _GIVE}, ["design_key"]),
    _fn("compare_top_designs", "Monthly result in the three scenarios for the three best-scoring designs."),
    _fn("lookup_playbook", "Look up a vetted practical principle. Topics: " + ", ".join(PLAYBOOK),
        {"topic": {"type": "string", "enum": list(PLAYBOOK)}}, ["topic"]),
]
TOOL_NAMES = [s["function"]["name"] for s in TOOL_SCHEMAS]


class ToolBox:
    def __init__(self, profile: dict):
        self.profile = profile

    def schemas(self):
        return TOOL_SCHEMAS

    def _cap(self, args):
        v = args.get("max_giveaway_pct")
        if v is None:
            return None
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0.5 <= v <= 30:
            raise ValueError("max_giveaway_pct must be a number between 0.5 and 30")
        return float(v)

    def _key(self, args):
        k = args.get("design_key")
        if k not in engine.DESIGNS:
            raise ValueError("design_key must be one of: " + ", ".join(DESIGN_KEYS))
        return k

    def call(self, name: str, args: dict | None) -> dict:
        args, p = args or {}, self.profile
        try:
            if name == "check_gates":
                return {"gates": engine.check_gates(p)}
            if name == "rank_designs":
                return {"ranking": [{k: r[k] for k in ("key", "label", "score", "needs")} for r in engine.score_designs(p)]}
            if name == "get_design_plan":
                return engine.design_plan(p, self._key(args), self._cap(args))
            if name == "run_economics":
                plan = engine.design_plan(p, self._key(args), self._cap(args))
                return {"design": plan["label"], **engine.economics(p, plan)}
            if name == "compare_top_designs":
                rows = []
                for r in engine.score_designs(p)[:3]:
                    plan = engine.design_plan(p, r["key"])
                    ec = engine.economics(p, plan)
                    rows.append({"design": r["label"], "score": r["score"], "reward_rate_pct": ec["reward_rate_pct"],
                                 "net_month": {k: v["net_month"] for k, v in ec["scenarios"].items()}})
                return {"designs": rows}
            if name == "lookup_playbook":
                t = args.get("topic")
                return {"topic": t, "fact": PLAYBOOK[t]} if t in PLAYBOOK else {"error": "unknown topic", "topics": list(PLAYBOOK)}
            return {"error": f"unknown tool '{name}'", "tools": TOOL_NAMES}
        except (ValueError, TypeError) as exc:
            return {"error": str(exc)}
