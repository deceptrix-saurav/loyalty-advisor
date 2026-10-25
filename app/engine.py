"""Deterministic loyalty-program maths. No LLM touches this file.

Question 1: should this business run a loyalty program at all?
Question 2: if yes, which design, with what numbers?

Spend-based designs (stamp card, points, tiers, cashback), per month:
    R        regular customers   = transactions * regular_share / visits_per_month_regular
    members  = R * enrolment% * scenario multiplier
    S0       monthly spend of one regular = visits_per_month * average_bill
    u        how much more members spend after joining (scenario)
    reward   = members * S0 * (1 + u) * reward_rate * (1 - breakage)      <- paid on ALL member spend
    extra GP = members * S0 * u * gross_margin                            <- only the extra spend earns this
    net      = extra GP - reward - tool cost - owner time
Break-even lift  u* = (c*N*S0 + F) / (N*S0*(m - c)),  c = reward_rate*(1-breakage), m = margin.
If m <= c the program can never pay for itself.

Referral and paid-membership designs have their own small models (see _econ_referral, _econ_paid).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
BENCH = json.loads((DATA_DIR / "benchmarks.json").read_text())
BUSINESS = BENCH["business_types"]
DESIGNS = BENCH["designs"]
SCEN = BENCH["scenarios"]
ENROLL = BENCH["enrollment_pct_of_regulars"]
WEIGHTS = BENCH["score_weights"]
TECH_LEVEL = {"none": 0, "phone_number": 1, "pos_app": 2}
TECH_LABEL = {"none": "paper only", "phone_number": "phone numbers at billing", "pos_app": "billing software or app"}
GOALS = ("frequency", "basket", "win_back", "referral", "data")
CURRENCIES = {"₹": "en-IN", "$": "en-US", "£": "en-GB", "€": "de-DE"}
MIN_REWARD = 0.015          # planning rule: rewards under ~1.5% of spend are rarely noticed by customers
SAFETY = 0.8                # size rewards at 80% of the break-even point so the expected case has headroom
REFERRAL_WINDOW_FACTOR = 78 / 144   # share of a referred customer's first-year profit earned inside a 12-month window

LIMITS = {
    "monthly_transactions": (10, 5_000_000), "avg_bill": (1, 10_000_000), "gross_margin_pct": (1, 95),
    "regular_share_pct": (0, 100), "visits_per_month_regular": (0.05, 40), "owner_hours_per_week": (0, 80),
    "max_giveaway_pct": (0.5, 30), "setup_cost": (0, 1e9), "tool_cost_month": (0, 1e8), "hourly_value": (0, 1e6),
}


class ProfileError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# --------------------------------------------------------------------------- formatting
def fmt(x: float, cur: str = "$") -> str:
    """Money with grouping suited to the currency. 12345.6 -> '₹12,346'."""
    n = round(x) if abs(x) >= 100 else round(x, 1)
    sign = "-" if n < 0 else ""
    n = abs(n)
    if cur == "₹" and n >= 1000:
        s = str(int(round(n)))
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        body = ",".join(parts + [tail])
    elif n >= 1000:
        body = f"{int(round(n)):,}"
    else:
        body = f"{n:g}"
    return f"{sign}{cur}{body}"


def nice(x: float) -> float:
    """Round to a friendly 1/2/5 x 10^k number."""
    if x <= 0:
        return 0
    k = 10 ** math.floor(math.log10(x))
    for m in (1, 2, 5, 10):
        if x <= m * k * 1.0001:
            return m * k if m * k >= 1 else round(m * k, 2)
    return 10 * k


def nice_down(x: float) -> float:
    """Largest friendly 1/2/5 x 10^k number that does not exceed x (so rounding never overshoots a budget)."""
    if x <= 0:
        return 0
    k = 10 ** math.floor(math.log10(x))
    best = k
    for m in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8):
        if m * k <= x * 1.0001:
            best = m * k
    return best if best >= 1 else round(best, 2)


# --------------------------------------------------------------------------- profile
def complete_profile(partial: dict) -> tuple[dict, list[dict]]:
    problems = []
    bt = partial.get("business_type")
    if bt not in BUSINESS:
        problems.append("business_type must be one of: " + ", ".join(BUSINESS))
    for k in ("monthly_transactions", "avg_bill"):
        if partial.get(k) is None:
            problems.append(f"{k} is required")
    if problems:
        raise ProfileError(problems)
    b = BUSINESS[bt]
    basis = BENCH["default_basis"]
    spec = {
        "gross_margin_pct": (b["gross_margin_pct"], basis),
        "regular_share_pct": (b["regular_share_pct"], basis),
        "visits_per_month_regular": (b["visits_per_month_regular"], basis),
        "owner_hours_per_week": (3, "Planning default: three hours a week of your own time"),
        "setup_cost": (0, "Assumed zero (cards printed or a notebook). Enter your real figure if different"),
        "tool_cost_month": (0, "Assumed zero. Enter the monthly fee if you use an app or software"),
        "hourly_value": (0, "Your time is not charged. Enter what an hour of your time is worth to include it"),
    }
    p = {"name": str(partial.get("name") or "Your business")[:60], "business_type": bt,
         "monthly_transactions": float(partial["monthly_transactions"]), "avg_bill": float(partial["avg_bill"]),
         "currency": partial.get("currency") if partial.get("currency") in CURRENCIES else "$",
         "competitor_has_program": bool(partial.get("competitor_has_program"))}
    assumed = []
    for f, (default, why) in spec.items():
        v = partial.get(f)
        if v is None:
            p[f] = float(default)
            assumed.append({"field": f, "value": p[f], "basis": why})
        else:
            p[f] = float(v)
    for f, valid, default, why in (
        ("tech", TECH_LEVEL, "none", "Assumed you can only use paper cards. Say if you capture phone numbers or use billing software"),
        ("goal", GOALS, "frequency", "Assumed your main goal is getting customers to come back more often"),
    ):
        v = partial.get(f)
        if v in valid:
            p[f] = v
        else:
            p[f] = default
            assumed.append({"field": f, "value": default, "basis": why})
    mg = partial.get("max_giveaway_pct")
    if mg is None:
        p["max_giveaway_pct"] = round(max(0.5, min(8.0, 0.15 * p["gross_margin_pct"])), 1)
        assumed.append({"field": "max_giveaway_pct", "value": p["max_giveaway_pct"],
                        "basis": "Cap on rewards as a share of sales: the smaller of 8% and 15% of your margin (never below 0.5%)"})
    else:
        p["max_giveaway_pct"] = float(mg)
    validate(p)
    p["monthly_revenue"] = p["monthly_transactions"] * p["avg_bill"]
    p["regular_customers"] = (p["monthly_transactions"] * p["regular_share_pct"] / 100) / p["visits_per_month_regular"]
    return p, assumed


def validate(p: dict) -> None:
    problems = []
    for f, (lo, hi) in LIMITS.items():
        v = p.get(f)
        if not isinstance(v, (int, float)) or v != v:
            problems.append(f"{f} must be a number")
        elif not lo <= v <= hi:
            problems.append(f"{f} must be between {lo:g} and {hi:g} (got {v:g})")
    if problems:
        raise ProfileError(problems)


# --------------------------------------------------------------------------- readiness gates
def check_gates(p: dict) -> list[dict]:
    m, rs, R = p["gross_margin_pct"], p["regular_share_pct"], p["regular_customers"]
    g = []

    def add(gid, status, text, hard=False):
        g.append({"id": gid, "status": status, "text": text, "hard": hard and status == "fail"})

    if rs >= 40:
        add("returning_customers", "pass", f"{rs:g}% of your sales come from returning customers, so there is someone to reward.")
    elif rs >= 25:
        add("returning_customers", "warn", f"Only {rs:g}% of sales come from returning customers. A program has a small base to work on.")
    else:
        add("returning_customers", "fail", f"Only {rs:g}% of sales come from returning customers. Rewards for repeat visits have almost nobody to reach.", True)
    if R >= 50:
        add("enough_regulars", "pass", f"About {round(R)} regular customers is enough to run and measure a program.")
    elif R >= 20:
        add("enough_regulars", "warn", f"About {round(R)} regular customers is thin. Results will be hard to measure, so keep it very simple.")
    else:
        add("enough_regulars", "fail", f"About {round(R)} regular customers is too few to measure whether a program works.", True)
    if m >= 20:
        add("margin", "pass", f"A {m:g}% margin leaves room to pay rewards.")
    elif m >= 8:
        add("margin", "warn", f"A {m:g}% margin is thin. Rewards must stay very small.")
    else:
        add("margin", "fail", f"A {m:g}% margin cannot carry rewards.", True)
    aff = affordable_rate(p)
    if aff >= MIN_REWARD:
        add("reward_size", "pass", f"At your margin you can afford rewards of up to about {aff * 100:.1f}% of member spend, enough to be noticed.")
    else:
        add("reward_size", "warn", f"At your margin the biggest affordable reward is about {aff * 100:.1f}% of member spend, which customers may barely notice.")
    lvl = TECH_LEVEL[p["tech"]]
    if lvl == 0:
        add("recognise_customers", "warn", "You cannot yet recognise customers by phone number or software. Paper cards work, but you will measure less.")
    else:
        add("recognise_customers", "pass", f"You can recognise customers ({TECH_LABEL[p['tech']]}), so you can measure results.")
    if p["owner_hours_per_week"] < 1:
        add("owner_time", "warn", "Under one hour a week of your time is available. Choose the lightest design.")
    else:
        add("owner_time", "pass", f"{p['owner_hours_per_week']:g} hours a week of your time is available.")
    return g


# --------------------------------------------------------------------------- ranking
def _fit_range(v, lo, hi):
    if lo <= v <= hi:
        return 1.0
    return max(0.0, v / lo) if v < lo else max(0.0, hi / v)


def score_designs(p: dict) -> list[dict]:
    out = []
    lvl = TECH_LEVEL[p["tech"]]
    for key, d in DESIGNS.items():
        comps = {
            "goal": d["goal_fit"][p["goal"]],
            "frequency": _fit_range(p["visits_per_month_regular"], *d["freq_range"]),
            "regulars": min(1.0, p["regular_share_pct"] / d["min_regular_share"]),
            "tech": 1.0 if lvl >= d["tech_need"] else (0.4 if d["tech_need"] - lvl == 1 else 0.1),
            "margin": min(1.0, p["gross_margin_pct"] / d["min_margin"]),
            "effort": min(1.0, p["owner_hours_per_week"] / d["admin_hours_week"]),
        }
        pts = {k: round(WEIGHTS[k] * v, 1) for k, v in comps.items()}
        needs = []
        if lvl < d["tech_need"]:
            need = [k for k, v in TECH_LEVEL.items() if v == d["tech_need"]][0]
            needs.append(f"needs {TECH_LABEL[need]}")
        if comps["margin"] < 1:
            needs.append(f"works best above a {d['min_margin']}% margin")
        if comps["effort"] < 1:
            needs.append(f"about {d['admin_hours_week']:g} hours a week of admin")
        if comps["regulars"] < 1:
            needs.append(f"works best when {d['min_regular_share']}% or more of sales are repeat")
        out.append({"key": key, "label": d["label"], "tagline": d["tagline"], "score": round(sum(pts.values())),
                    "points": pts, "needs": needs})
    out.sort(key=lambda r: -r["score"])
    return out


# --------------------------------------------------------------------------- design parameters
def affordable_rate(p: dict, breakage_pct: float = 20.0) -> float:
    """Biggest reward rate (share of member spend) that still pays off in the expected case, with headroom.

    From  margin*u - c*(1+u) >= 0  (per rupee of member spend) with c = rate*(1-breakage)."""
    u, m = SCEN["expected"]["uplift_pct"] / 100, p["gross_margin_pct"] / 100
    return SAFETY * m * u / (1 + u) / (1 - breakage_pct / 100)


def _rr(p: dict, breakage_pct: float, override=None) -> float:
    """Reward rate used by a design: what you can afford, within your cap, but never below the noticeable minimum."""
    if override is not None:
        return override / 100
    return max(MIN_REWARD, min(p["max_giveaway_pct"] / 100, affordable_rate(p, breakage_pct)))


def design_plan(p: dict, key: str, max_giveaway_pct: float | None = None) -> dict:
    d = DESIGNS[key]
    B, v, m, cur = p["avg_bill"], p["visits_per_month_regular"], p["gross_margin_pct"] / 100, p["currency"]
    r = _rr(p, d['breakage_pct'], max_giveaway_pct)
    params: dict = {}
    how: list[str] = []
    rules: list[str] = []
    if key == "punch_card":
        n = max(3, min(10, round(3 * v)))                      # about three months of visits to the first reward
        value = nice_down(r * (n + 1) * B)
        rr = value / ((n + 1) * B)
        params = {"stamps_needed": n, "reward_value": value, "reward_rate_pct": round(rr * 100, 1)}
        how = [f"Customer gets one stamp for every bill of at least {fmt(nice_down(B * 0.6), cur)}.",
               f"After {n} stamps, the next visit comes with a reward worth about {fmt(value, cur)} (a free small item or a discount).",
               f"A regular reaches the reward in about 3 months. Rewards cost you about {rr * 100:.1f}% of member spend."]
        rules = ["One stamp per bill, signed or initialled by staff.", "Cards carry a number and the customer's name or phone.", "Cards are valid for 12 months from the first stamp."]
    elif key == "points":
        per = nice(B / 5)
        thresh = max(10, round(4 * B / per / 5) * 5)
        value = nice_down(r * thresh * per)
        rr = value / (thresh * per)
        params = {"spend_per_point": per, "points_for_reward": thresh, "reward_value": value, "reward_rate_pct": round(rr * 100, 1)}
        how = [f"1 point for every {fmt(per, cur)} spent.", f"{thresh} points unlock a reward worth {fmt(value, cur)}.",
               f"A regular reaches the first reward in about 4 visits. Rewards cost about {rr * 100:.1f}% of member spend."]
        rules = ["Points expire after 12 months without a purchase, not on a fixed date.", "Points cannot be earned on the purchase paid for with points.", "Staff look the customer up by phone number at billing."]
    elif key == "tiers":
        S0 = v * B
        a = 12 * S0
        rr = r * 0.845
        params = {"silver_from_yearly_spend": nice(a), "gold_from_yearly_spend": nice(2 * a),
                  "base_cashback_pct": round(r * 0.7 * 100, 1), "silver_cashback_pct": round(r * 1.1 * 100, 1),
                  "gold_cashback_pct": round(r * 1.6 * 100, 1), "reward_rate_pct": round(rr * 100, 1)}
        how = [f"Everyone starts at Base and gets {params['base_cashback_pct']}% back as store credit.",
               f"Silver from {fmt(params['silver_from_yearly_spend'], cur)} spent in a year: {params['silver_cashback_pct']}% back.",
               f"Gold from {fmt(params['gold_from_yearly_spend'], cur)} spent in a year: {params['gold_cashback_pct']}% back plus one non-cash perk such as priority service.",
               f"With about 70% Base, 25% Silver and 5% Gold members, rewards cost about {rr * 100:.1f}% of member spend."]
        rules = ["Tier is reviewed every 12 months on spend in the last 12 months.", "Members who drop a tier get one month of grace.", "Perks must cost you little: priority booking, early access, a small gift."]
    elif key == "cashback":
        rr = r
        params = {"cashback_pct": round(rr * 100, 1), "credit_expires_days": 60, "minimum_credit_to_use": nice(B * 0.25)}
        how = [f"{rr * 100:.1f}% of every bill goes into the customer's store-credit balance.",
               f"Credit can be used on the next visit once it reaches {fmt(params['minimum_credit_to_use'], cur)}.",
               "Credit expires 60 days after it is earned, which nudges a quick return."]
        rules = ["Credit cannot be exchanged for cash.", "Credit is tied to the customer's phone number.", "Staff show the balance on the bill so it stays visible."]
    elif key == "referral":
        vn = max(0.3, 0.5 * v)
        gp_y1 = 12 * vn * B * m * 0.75
        total = nice(0.25 * gp_y1)
        each = round(total / 2, 2)
        rr = 0
        params = {"reward_each": each, "reward_total_per_referral": total, "first_year_profit_per_new_customer": round(gp_y1)}
        how = [f"Member shares a code or card. When the friend makes a first purchase, both get {fmt(each, cur)} off their next bill.",
               f"A new customer is worth about {fmt(gp_y1, cur)} of profit in the first year, so the reward is capped at 25% of that.",
               "Each member can earn at most 5 referral rewards a year."]
        rules = ["Reward is paid only after the friend's first completed purchase.", "A friend must be a new customer (new phone number).", "Maximum 5 referral rewards per member per year."]
    else:  # paid_membership
        S0 = v * B
        disc = min(0.15, max(0.05, round(r * 1.5, 2)))
        fee = nice(disc * S0)
        rr = 0
        params = {"monthly_fee": fee, "member_discount_pct": round(disc * 100), "typical_monthly_discount_value": round(disc * S0)}
        how = [f"Members pay {fmt(fee, cur)} a month and get {round(disc * 100)}% off every bill.",
               f"A typical regular spends about {fmt(S0, cur)} a month, so the discount is worth about {fmt(disc * S0, cur)}. The fee is set to cover it.",
               "Members can cancel any month. Extra visits are your profit."]
        rules = ["Fee is paid monthly in advance.", "Discount does not stack with other offers.", "Review the fee after 3 months using real visit counts."]
    return {"key": key, "label": d["label"], "tagline": d["tagline"], "kind": d["kind"], "reward_rate": rr,
            "breakage_pct": d["breakage_pct"], "admin_hours_week": d["admin_hours_week"],
            "params": params, "how_it_works": how, "rules": rules}


# --------------------------------------------------------------------------- economics
def _fixed(p: dict, plan: dict) -> float:
    return p["tool_cost_month"] + plan["admin_hours_week"] * 4.33 * p["hourly_value"]


def _members(p: dict, sc: dict) -> float:
    return p["regular_customers"] * ENROLL[p["tech"]] / 100 * sc["enroll_mult"]


def _econ_spend(p: dict, plan: dict, sc: dict) -> dict:
    N, S0, m = _members(p, sc), p["visits_per_month_regular"] * p["avg_bill"], p["gross_margin_pct"] / 100
    u = sc["uplift_pct"] / 100
    c = plan["reward_rate"] * (1 - plan["breakage_pct"] / 100)
    gp, cost, F = N * S0 * u * m, N * S0 * (1 + u) * c, _fixed(p, plan)
    return {"members": round(N), "extra_revenue_month": round(N * S0 * u), "extra_profit_month": round(gp),
            "reward_cost_month": round(cost), "running_cost_month": round(F), "net_month": round(gp - cost - F)}


def _econ_referral(p: dict, plan: dict, sc: dict) -> dict:
    N = _members(p, sc)
    refs = N * sc["referral_pct"] / 100
    gp12 = refs * 12 * plan["params"]["first_year_profit_per_new_customer"] * REFERRAL_WINDOW_FACTOR
    cost12 = refs * 12 * plan["params"]["reward_total_per_referral"]
    F = _fixed(p, plan)
    return {"members": round(N), "new_customers_per_month": round(refs, 1), "extra_revenue_month": 0,
            "extra_profit_month": round(gp12 / 12), "reward_cost_month": round(cost12 / 12),
            "running_cost_month": round(F), "net_month": round((gp12 - cost12) / 12 - F)}


def _econ_paid(p: dict, plan: dict, sc: dict) -> dict:
    N = p["regular_customers"] * sc["paid_enroll_pct"] / 100
    S0, m = p["visits_per_month_regular"] * p["avg_bill"], p["gross_margin_pct"] / 100
    u, d, fee = sc["paid_uplift_pct"] / 100, plan["params"]["member_discount_pct"] / 100, plan["params"]["monthly_fee"]
    gp, disc, F = N * S0 * u * m, N * S0 * (1 + u) * d, _fixed(p, plan)
    return {"members": round(N), "extra_revenue_month": round(N * S0 * u), "extra_profit_month": round(gp),
            "reward_cost_month": round(disc - N * fee), "running_cost_month": round(F),
            "net_month": round(gp + N * fee - disc - F)}


def economics(p: dict, plan: dict) -> dict:
    fn = {"spend": _econ_spend, "referral": _econ_referral, "paid": _econ_paid}[plan["kind"]]
    rows = {name: fn(p, plan, sc) for name, sc in SCEN.items()}
    for name, r in rows.items():
        r["uplift_pct"] = SCEN[name]["uplift_pct"] if plan["kind"] == "spend" else None
        r["net_12_months"] = r["net_month"] * 12 - round(p["setup_cost"])
        r["pays_off"] = r["net_month"] >= 0
    be = None
    if plan["kind"] == "spend":
        N, S0, m = _members(p, SCEN["expected"]), p["visits_per_month_regular"] * p["avg_bill"], p["gross_margin_pct"] / 100
        c = plan["reward_rate"] * (1 - plan["breakage_pct"] / 100)
        if m > c and N > 0:
            be = round(((c * N * S0 + _fixed(p, plan)) / (N * S0 * (m - c))) * 100, 2)
    exp = rows["expected"]
    payback = None
    if p["setup_cost"] > 0 and exp["net_month"] > 0:
        payback = round(p["setup_cost"] / exp["net_month"], 1)
    return {"scenarios": rows, "break_even_lift_pct": be, "payback_months": payback,
            "reward_rate_pct": round(plan["reward_rate"] * 100, 1)}


# --------------------------------------------------------------------------- verdict, KPIs, launch plan
VERDICT_LABEL = {"launch": "Launch it", "pilot": "Pilot first", "not_yet": "Not yet"}


def verdict(gates: list[dict], econ: dict) -> dict:
    sc = econ["scenarios"]
    hard = [g["id"] for g in gates if g["hard"]]
    if hard:
        code = "not_yet"
    elif sc["pessimistic"]["pays_off"]:
        code = "launch"
    elif sc["expected"]["pays_off"]:
        code = "pilot"
    else:
        code = "not_yet"
    return {"code": code, "label": VERDICT_LABEL[code], "blocked_by": hard}


def kpis(p: dict, plan: dict, econ: dict) -> list[dict]:
    cur, sc = p["currency"], econ["scenarios"]
    exp, pes = sc["expected"], sc["pessimistic"]
    out = [{"name": "Members signed up in 90 days", "target": f"{max(1, round(exp['members'] * 0.5))} members",
            "red_flag": f"under {max(1, round(pes['members'] * 0.5))} members", "how": "Count cards issued or phone numbers saved."}]
    if plan["kind"] == "spend":
        be = econ["break_even_lift_pct"]
        out += [{"name": "Members' extra spend versus before they joined", "target": f"{exp['uplift_pct']}% or more",
                 "red_flag": "below " + (f"{be}%" if be is not None else "any level (costs exceed margin)"),
                 "how": "Compare each member's monthly spend before and after joining, against similar non-members."},
                {"name": "Rewards given as a share of sales", "target": f"at most {p['max_giveaway_pct']:g}%",
                 "red_flag": f"above {p['max_giveaway_pct']:g}%", "how": "Value of rewards redeemed divided by total sales for the month."},
                {"name": "Share of earned rewards claimed", "target": f"about {100 - plan['breakage_pct']}%",
                 "red_flag": "under 10% (too hard) or over 95% (too easy)", "how": "Rewards claimed divided by rewards earned."}]
    elif plan["kind"] == "referral":
        out.append({"name": "New customers from referrals each month", "target": f"{exp['new_customers_per_month']}",
                    "red_flag": f"under {pes['new_customers_per_month']}", "how": "Count first purchases that used a referral code."})
    else:
        out.append({"name": "Paying members", "target": f"{exp['members']} members", "red_flag": f"under {pes['members']} members",
                    "how": "Count members who paid this month."})
    out.append({"name": "Net result each month", "target": f"{fmt(exp['net_month'], cur)} or better by month 4",
                "red_flag": f"below {fmt(pes['net_month'], cur)}", "how": "Extra profit minus rewards minus running cost."})
    return out


def launch_plan(p: dict, plan: dict) -> list[dict]:
    tech = p["tech"]
    prep = {"none": "Print numbered cards and agree the rules on one page.",
            "phone_number": "Set up a simple sheet or WhatsApp list for phone numbers and balances. Write the rules on one page.",
            "pos_app": "Configure the program in your billing software or app and test it with three dummy bills."}[tech]
    return [
        {"when": "Week 0", "action": prep},
        {"when": "Week 1", "action": "Soft launch with 20 regular customers. Ask them what is unclear."},
        {"when": "Weeks 2 to 4", "action": "Offer sign-up at the counter on every bill. Record the number of sign-ups each week."},
        {"when": "Week 6", "action": "Check rewards given as a share of sales. Fix anything staff or customers find confusing."},
        {"when": "Week 8", "action": "Compare members' spend with non-members' spend, before and after joining."},
        {"when": "Week 12", "action": "Decision day: scale it, adjust the numbers, or stop. Use the red flags in the KPI table."},
    ]


def stop_rules(p: dict, plan: dict, econ: dict) -> list[str]:
    cur = p["currency"]
    rules = [f"Stop or redesign if after 12 weeks the net result is below {fmt(econ['scenarios']['pessimistic']['net_month'], cur)} a month.",
             "Pause rewards if staff report cheating you cannot fix with a simpler rule."]
    if plan["kind"] == "spend" and econ["break_even_lift_pct"] is not None:
        rules.insert(0, f"Stop if members' extra spend stays below {econ['break_even_lift_pct']}% after 12 weeks.")
    return rules


def full_analysis(p: dict, design_key: str | None = None, max_giveaway_pct: float | None = None) -> dict:
    gates = check_gates(p)
    ranking = score_designs(p)
    key = design_key if design_key in DESIGNS else ranking[0]["key"]
    plan = design_plan(p, key, max_giveaway_pct)
    econ = economics(p, plan)
    return {"gates": gates, "ranking": ranking, "design_key": key, "plan": plan, "economics": econ,
            "verdict": verdict(gates, econ), "kpis": kpis(p, plan, econ), "launch_plan": launch_plan(p, plan),
            "stop_rules": stop_rules(p, plan, econ)}
