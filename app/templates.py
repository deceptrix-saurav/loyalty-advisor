"""Plain-code fallbacks. If an AI answer fails the grounding or schema checks twice, these are shown instead.
They are built only from verified figures, so they are always safe, just less personal."""
from __future__ import annotations

from . import engine


def strategist_template(facts: dict) -> dict:
    v, d, e, b = facts["verdict"], facts["design"], facts["economics"], facts["business"]
    cur = b["currency"]
    sc = e["scenarios"]
    f = lambda x: engine.fmt(x, cur)
    be = e["break_even_lift_pct"]
    headline = {"launch": "A loyalty program should pay off for you",
                "pilot": "Worth a small pilot, not a full launch yet",
                "not_yet": "A loyalty program does not pay off for you yet"}[v["code"]]
    if be is not None:
        first = (f"A {d['label'].lower()} that gives back about {e['reward_rate_pct']:g}% of member spend breaks even "
                 f"if members spend {be:g}% more than before.")
    else:
        first = f"A {d['label'].lower()} has its own break-even rule (it does not depend on one spend lift)."
    summary = (f"{first} Expected result: {f(sc['expected']['net_month'])} a month. "
               f"Pessimistic case: {f(sc['pessimistic']['net_month'])} a month.")
    reasons = [first,
               f"Expected case: {f(sc['expected']['net_month'])} a month and {f(sc['expected']['net_12_months'])} over 12 months.",
               f"Pessimistic case: {f(sc['pessimistic']['net_month'])} a month, so the result depends on how much members really change their behaviour."]
    risks = [g["text"] for g in facts["gates"] if g["status"] != "pass"][:2]
    risks.append("The lift in spending is a planning assumption, not a measurement. Only a pilot will show the real number.")
    alts = []
    ids = {g["id"] for g in facts["gates"] if g["status"] in ("warn", "fail")}
    if v["code"] != "launch":
        if "returning_customers" in ids:
            alts.append("Focus first on giving first-time customers a reason to return once: a small voucher on the next visit.")
        if "margin" in ids or "reward_size" in ids:
            alts.append("Protect margin first: small price rise, bundles, or rewards paid for by a supplier.")
        alts.append("Try a one-off offer such as bring a friend this month, and measure the result before building a program.")
    nxt = {"launch": "Follow the 12-week plan below and check the red flags at week 6.",
           "pilot": "Run the plan below with your 20 best regular customers for 12 weeks, then decide.",
           "not_yet": "Fix the blocking points above, or try one of the alternatives, then run this check again."}[v["code"]]
    return {"verdict": v["code"], "headline": headline, "summary": summary, "reasons": reasons,
            "risks": risks[:3], "alternatives": alts[:3], "next_step": nxt}


def designer_template(facts: dict) -> dict:
    d, b = facts["design"], facts["business"]
    how = d["how_it_works"]
    owner = "Our" if b["name"] == "Your business" else b["name"]
    return {
        "program_name": f"{owner} {d['label']}",
        "one_line_pitch": d["tagline"],
        "customer_pitch": f"Join our {d['label'].lower()}. " + " ".join(how[:2]),
        "staff_script": "At billing, ask: 'Would you like to join our rewards? It is free and takes ten seconds.' Then explain: " + how[0],
        "launch_plan": facts["launch_plan"],
        "tailoring_tips": ["Capture a phone number at billing, with the customer's consent, so you can measure results.",
                           "Keep the rules on one printed page and give the same page to every member of staff."],
    }
