"""Turn real usage logs into the tokenomics numbers for the report.

    python scripts/tokenomics.py                 # reads logs/usage.jsonl (and evidence/usage_log.jsonl)
    python scripts/tokenomics.py --runs-per-user 6

Only MEASURED rows count (rows from MOCK_LLM demo mode are ignored). Writes evidence/tokenomics.json,
which scripts/build_report.py reads. Prices come from pricing.json: if blank, tokens only.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES = [ROOT / "logs" / "usage.jsonl", ROOT / "evidence" / "usage_log.jsonl"]
OUT = ROOT / "evidence" / "tokenomics.json"


def load_rows():
    rows, seen = [], set()
    for path in SOURCES:
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                key = (r.get("run_id"), r.get("ts"), r.get("agent"), r.get("input_tokens"), r.get("output_tokens"))
                if r.get("measured") and key not in seen:
                    seen.add(key)
                    rows.append(r)
    return rows


def price(prices, inp, cached, out):
    if None in (prices.get("input_per_million"), prices.get("output_per_million")):
        return None
    cin = prices.get("cached_input_per_million")
    cin = prices["input_per_million"] if cin is None else cin
    return ((inp - cached) * prices["input_per_million"] + cached * cin + out * prices["output_per_million"]) / 1e6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs-per-user", type=float, default=6, help="ASSUMPTION: business checks per user per month")
    args = ap.parse_args()
    prices = json.loads((ROOT / "pricing.json").read_text())
    rows = load_rows()
    runs = defaultdict(list)
    for r in rows:
        if r["mode"] in ("agentic", "lean"):
            runs[r["run_id"]].append(r)
    # a "complete" run reached the designer, so it is a typical end-to-end check
    complete = {k: v for k, v in runs.items() if any(c["agent"] == "designer" for c in v)}
    result = {"measured_runs": len(complete), "runs_per_user_month_assumption": args.runs_per_user,
              "currency": prices.get("currency"), "priced": prices.get("input_per_million") is not None, "modes": {}}
    for mode in ("agentic", "lean"):
        mine = [v for v in complete.values() if v[0]["mode"] == mode]
        if not mine:
            continue
        tot = lambda key: [sum(c[key] for c in v) for v in mine]
        inp, cached, out, ms = tot("input_tokens"), tot("cached_tokens"), tot("output_tokens"), tot("latency_ms")
        n = len(mine)
        avg = lambda xs: sum(xs) / len(xs)
        per_agent = defaultdict(lambda: [0, 0, 0, 0])
        for v in mine:
            for c in v:
                a = per_agent[c["agent"]]
                a[0] += c["input_tokens"]; a[1] += c["cached_tokens"]; a[2] += c["output_tokens"]; a[3] += 1
        costs = [price(prices, i, c, o) for i, c, o in zip(inp, cached, out)]
        cost = None if costs[0] is None else avg(costs)
        entry = {
            "runs": n,
            "avg_input_tokens": round(avg(inp)), "avg_cached_tokens": round(avg(cached)), "avg_output_tokens": round(avg(out)),
            "cache_share_of_input_pct": round(100 * sum(cached) / max(1, sum(inp)), 1),
            "avg_model_calls": round(avg([len(v) for v in mine]), 1),
            "avg_model_time_s": round(avg(ms) / 1000, 1),
            "per_agent_avg": {a: {"input": round(x[0] / n), "cached": round(x[1] / n), "output": round(x[2] / n), "calls": round(x[3] / n, 1)}
                              for a, x in per_agent.items()},
            "cost_per_run": cost,
        }
        if cost is not None:
            m = args.runs_per_user
            entry["cost_per_user_month"] = cost * m
            entry["cost_100_users_month"] = cost * m * 100
            entry["cost_10000_users_month"] = cost * m * 10000
            entry["sensitivity_cost_per_user_month"] = {str(k): cost * k for k in (3, 6, 12, 30)}
        else:
            entry["note"] = "Set the three prices in pricing.json to get cost figures."
        result["modes"][mode] = entry
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    if not complete:
        print("\nNo measured runs found. Run the app with a real key and check a few outlets first (mock-mode rows are ignored).")


if __name__ == "__main__":
    main()
