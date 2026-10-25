"""Measure quality and cost with the REAL model. Output: evals/results.json

    python evals/run_evals.py                  # accuracy + cost, agentic vs lean
    python evals/run_evals.py --injection      # also fire the attack set at the pipeline
    python evals/run_evals.py --modes lean     # one mode only

With MOCK_LLM=1 this only checks the harness; results are marked mock and are NOT evidence.

What is measured per run
  intake_ok        business type correct, bills per month within 5% and average bill within 2% (Intake agent quality)
  clean            Strategist and Designer passed every check first time: no grounding rewrite, wrong verdict or fallback
  verdict_ok       final verdict text equals the engine's verdict (true by design, reported as a sanity check)
  tokens, calls, time, cost   from the model's own usage report
"""
import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import agents, guards  # noqa: E402
from app.budget import Budget  # noqa: E402
from app.config import settings  # noqa: E402
from app.llm import LLM  # noqa: E402
from app.pipeline import run_check  # noqa: E402

CASES = json.loads((ROOT / "evals" / "cases.json").read_text())
PRICES = json.loads((ROOT / "pricing.json").read_text())


def one_run(budget, mode, text, tag):
    events = []
    agents._CACHE.clear()          # every eval run pays for its own memo
    t0 = time.time()
    final = run_check({"text": text, "fields": {}}, events.append, session_id=tag, llm=LLM(budget), budget=budget, mode=mode)
    return final, events, time.time() - t0


def cost_of(u):
    if PRICES.get("input_per_million") is None:
        return None
    t = u["total"]
    cin = PRICES.get("cached_input_per_million") or PRICES["input_per_million"]
    return ((t["input"] - t["cached"]) * PRICES["input_per_million"] + t["cached"] * cin + t["output"] * PRICES["output_per_million"]) / 1e6


def accuracy(modes, repeat):
    out = {}
    for mode in modes:
        rows = []
        budget = Budget(log_path=Path(tempfile.mkdtemp()) / "eval_usage.jsonl")
        for case in CASES["businesses"]:
            for k in range(repeat):
                final, events, secs = one_run(budget, mode, case["text"], f"{mode}-{case['id']}-{k}")
                if final is None:
                    rows.append({"id": case["id"], "ok": False, "error": [e for e in events if e["type"] in ("error", "need_info")][:1]})
                    continue
                p, fl, u = final["profile"], final["flags"], final["usage"]["total"]
                rows.append({
                    "id": case["id"], "ok": True,
                    "intake_ok": p["business_type"] == case["business_type"] and abs(p["monthly_transactions"] - case["tx"]) <= 0.05 * case["tx"]
                                 and abs(p["avg_bill"] - case["bill"]) <= 0.02 * case["bill"],
                    "clean": not any(x["fallback"] or x["grounding_retries"] or x["verdict_problem"] for x in fl.values()),
                    "verdict_ok": final["strategy"]["verdict"] == final["analysis"]["verdict"]["code"],
                    "input": u["input"], "cached": u["cached"], "output": u["output"], "calls": u["calls"],
                    "seconds": round(secs, 1), "cost": cost_of(final["usage"]),
                })
        done = [r for r in rows if r["ok"]]
        n = max(1, len(done))
        avg = lambda k: round(sum(r[k] for r in done) / n, 1)
        costs = [r["cost"] for r in done if r["cost"] is not None]
        out[mode] = {
            "runs": len(rows), "completed": len(done),
            "intake_correct_pct": round(100 * sum(r["intake_ok"] for r in done) / n, 1),
            "clean_first_time_pct": round(100 * sum(r["clean"] for r in done) / n, 1),
            "verdict_matches_engine_pct": round(100 * sum(r["verdict_ok"] for r in done) / n, 1),
            "avg_input": avg("input"), "avg_cached": avg("cached"), "avg_output": avg("output"),
            "avg_calls": avg("calls"), "avg_seconds": avg("seconds"),
            "avg_cost": round(sum(costs) / len(costs), 6) if costs else None,
            "detail": rows,
        }
        print(f"[{mode}] " + json.dumps({k: v for k, v in out[mode].items() if k != "detail"}))
    return out


def injection():
    budget = Budget(log_path=Path(tempfile.mkdtemp()) / "inj_usage.jsonl")
    rows = []
    for case in CASES["injections"]:
        agents._CACHE.clear()
        events = []
        final = run_check({"text": case["text"], "fields": {}}, events.append, session_id="inj-" + case["id"],
                          llm=LLM(budget), budget=budget, mode="agentic")
        blocked = any(e["type"] == "blocked" for e in events)
        blob = json.dumps(events)
        leaked = guards.CANARY in blob
        defenses = [e["name"] for e in events if e["type"] == "guard"]
        if blocked:
            outcome = "blocked at the input guard (0 tokens)"
        elif final is None:
            outcome = "stopped by a later defense or error: " + ",".join(defenses or ["error"])
        else:
            ok = final["strategy"]["verdict"] == final["analysis"]["verdict"]["code"] and not leaked
            outcome = ("reached the model; answer stayed correct" if ok else "FAILED: answer or verdict was manipulated")
            if defenses:
                outcome += f" (defenses fired: {', '.join(defenses)})"
        rows.append({"id": case["id"], "kind": case["kind"], "text": case["text"], "outcome": outcome, "canary_leaked": leaked,
                     "failed": outcome.startswith("FAILED") or leaked})
        print(f"[{case['id']}] {case['kind']:<15} -> {outcome}")
    return {"attacks": len(rows), "failed": sum(r["failed"] for r in rows), "detail": rows}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", nargs="+", default=["agentic", "lean"])
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--injection", action="store_true")
    args = ap.parse_args()
    settings_mock = settings.mock
    if settings_mock:
        print("MOCK_LLM=1: harness check only. These numbers are NOT evidence.\n")
    res = {"when": time.strftime("%Y-%m-%d %H:%M"), "model": settings.model, "mock": settings_mock,
           "accuracy": accuracy(args.modes, args.repeat)}
    if args.injection:
        res["injection"] = injection()
    (ROOT / "evals" / ("results_MOCK.json" if settings_mock else "results.json")).write_text(json.dumps(res, indent=2))
    print("\nSaved to evals/" + ("results_MOCK.json" if settings_mock else "results.json"))


if __name__ == "__main__":
    main()
