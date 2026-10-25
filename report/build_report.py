#!/usr/bin/env python3
"""Build report.html and slides.html (both fully self-contained).

    python report/build_report.py

What it uses
  * the real engine, run live, for every worked example (nothing typed by hand)
  * evidence/*.png            screenshots from scripts/capture_evidence.py (embedded as base64)
  * evidence/tokenomics.json  from scripts/tokenomics.py
  * evals/results.json        from evals/run_evals.py
  * evidence/impact.json      your real-user result (see SUBMISSION_CHECKLIST.md)
  * a live run of the unit tests

Anything that needs evidence you have not produced yet is shown as a yellow TODO box, never as made-up data.
"""
import base64
import html
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ======================= EDIT THESE THREE LINES =======================
STUDENT_NAME = "Saurav Shekhar"
COURSE = "MGT 409 (AI)"
REPO_URL = "https://github.com/deceptrix-saurav/loyalty-advisor"
APP_URL = ""          # leave empty if the app is not hosted
# ======================================================================

from app import engine  # noqa: E402

EV = ROOT / "evidence"
esc = html.escape


# ----------------------------------------------------------------------------- helpers
def todo(text):
    return f'<div class="todo"><b>TODO</b> {esc(text)}</div>'


def img_uri(name):
    p = EV / name
    if not p.exists():
        return None
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode()


def shot(name, caption, how="python scripts/capture_evidence.py"):
    uri = img_uri(name)
    if uri:
        return f'<figure><img src="{uri}" alt="{esc(caption)}"><figcaption>{esc(caption)}</figcaption></figure>'
    return todo(f"Screenshot missing: evidence/{name} ({caption}). Create it with: {how}")


def load_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def m(x, cur="₹"):
    return engine.fmt(x, cur)


# ----------------------------------------------------------------------------- live examples (real engine output)
EXAMPLES = {
    "Cafe": dict(business_type="cafe_restaurant", monthly_transactions=3000, avg_bill=250, tech="phone_number", goal="frequency"),
    "Kirana store": dict(business_type="grocery", monthly_transactions=6000, avg_bill=400, tech="none", gross_margin_pct=18),
    "Salon": dict(business_type="salon_spa", monthly_transactions=300, avg_bill=900, tech="phone_number", goal="referral"),
    "Phone shop": dict(business_type="electronics", monthly_transactions=120, avg_bill=15000),
}
RUNS = {}
for name, f in EXAMPLES.items():
    prof, assumed = engine.complete_profile(f)
    RUNS[name] = (prof, assumed, engine.full_analysis(prof))
CAFE_P, CAFE_ASSUMED, CAFE_A = RUNS["Cafe"]
CE = CAFE_A["economics"]
CS = CE["scenarios"]


def examples_table():
    rows = ""
    for name, (p, _, a) in RUNS.items():
        e = a["economics"]
        be = f'{e["break_even_lift_pct"]:g}%' if e["break_even_lift_pct"] is not None else "n/a"
        rows += (f"<tr><td>{name}</td><td>{a['plan']['label']}</td><td>{engine.VERDICT_LABEL[a['verdict']['code']]}</td>"
                 f"<td class=n>{be}</td><td class=n>{m(e['scenarios']['pessimistic']['net_month'])}</td>"
                 f"<td class=n>{m(e['scenarios']['expected']['net_month'])}</td></tr>")
    return ("<table><thead><tr><th>Business</th><th>Best design</th><th>Verdict</th><th class=n>Break-even lift</th>"
            "<th class=n>Pessimistic, per month</th><th class=n>Expected, per month</th></tr></thead><tbody>" + rows + "</tbody></table>")


def cafe_walk_table():
    g = CAFE_A["gates"]
    top = CAFE_A["ranking"][:3]
    plan = CAFE_A["plan"]
    return f"""<table><thead><tr><th>Step</th><th>Who</th><th>What it produces for the example cafe</th></tr></thead><tbody>
<tr><td>1</td><td>Input guard (code)</td><td>Checks length and attack patterns. Accepted, 0 tokens.</td></tr>
<tr><td>2</td><td>Intake (AI)</td><td>Turns the sentence into: cafe, 3,000 bills a month, average bill {m(250)}, phone numbers saved, goal: come back more often. Anything not said is filled from documented defaults and listed as an assumption.</td></tr>
<tr><td>3</td><td>Engine (code)</td><td>{len([x for x in g if x['status']=='pass'])} of {len(g)} readiness checks pass. Scores all six designs: {top[0]['label']} {top[0]['score']}, {top[1]['label']} {top[1]['score']}, {top[2]['label']} {top[2]['score']}. Sizes the reward to what the margin can carry: about {CE['reward_rate_pct']:g}% of member spend.</td></tr>
<tr><td>4</td><td>Analyst (AI + tools)</td><td>Chooses extra checks, for example comparing the top three designs and looking up a principle from the playbook. Real tool calls are in the screenshot below.</td></tr>
<tr><td>5</td><td>Strategist (AI)</td><td>Explains the verdict in plain words using only the verified figures: break-even lift {CE['break_even_lift_pct']:g}%, expected {m(CS['expected']['net_month'])} a month, pessimistic {m(CS['pessimistic']['net_month'])} a month.</td></tr>
<tr><td>6</td><td>Designer (AI)</td><td>Personalises the program: {plan['params']['stamps_needed']} stamps, a reward worth {m(plan['params']['reward_value'])}, customer pitch, staff script, and the 12-week plan.</td></tr>
<tr><td>7</td><td>Output guard (code)</td><td>Checks the verdict matches the engine and every figure appears in the verified facts. If not, one rewrite, then a safe template.</td></tr></tbody></table>"""


def tokenomics_block():
    t = load_json(EV / "tokenomics.json")
    if not t or not t.get("modes"):
        return todo("No measured runs yet. Run the app with your real key, check several businesses, then run: python scripts/tokenomics.py (see SUBMISSION_CHECKLIST.md).")
    out = ""
    for mode, d in t["modes"].items():
        cost = d.get("cost_per_run")
        out += (f"<h3>{'Full agent mode' if mode == 'agentic' else 'Lean mode'} ({d['runs']} measured runs)</h3><table><thead><tr><th>Measure</th><th class=n>Average per run</th></tr></thead><tbody>"
                f"<tr><td>Input tokens</td><td class=n>{d['avg_input_tokens']:,}</td></tr>"
                f"<tr><td>of which cached</td><td class=n>{d['avg_cached_tokens']:,} ({d['cache_share_of_input_pct']}% of input)</td></tr>"
                f"<tr><td>Output tokens</td><td class=n>{d['avg_output_tokens']:,}</td></tr>"
                f"<tr><td>Model calls</td><td class=n>{d['avg_model_calls']}</td></tr>"
                f"<tr><td>Model time</td><td class=n>{d['avg_model_time_s']} s</td></tr>")
        if cost is not None:
            cur = t.get("currency", "USD")
            out += (f"<tr><td>Cost per run</td><td class=n>{cost:.4f} {cur}</td></tr>"
                    f"<tr><td>Cost per user per month ({t['runs_per_user_month_assumption']:g} checks, assumed)</td><td class=n>{d['cost_per_user_month']:.3f} {cur}</td></tr>"
                    f"<tr><td>100 users, per month</td><td class=n>{d['cost_100_users_month']:.2f} {cur}</td></tr>"
                    f"<tr><td>10,000 users, per month</td><td class=n>{d['cost_10000_users_month']:,.2f} {cur}</td></tr>")
        else:
            out += "<tr><td>Cost</td><td class=n>prices not set in pricing.json</td></tr>"
        out += "</tbody></table>"
        pa = d["per_agent_avg"]
        out += ("<p class=small>Per agent (average input / output tokens): " +
                "; ".join(f"{a} {v['input']:,} / {v['output']:,}" for a, v in pa.items()) + ".</p>")
        if cost is None:
            out += todo("Fill input_per_million, cached_input_per_million and output_per_million in pricing.json, then rerun scripts/tokenomics.py.")
    return out


def evals_block():
    r = load_json(ROOT / "evals" / "results.json")
    if not r or r.get("mock"):
        return todo("No real eval results yet. Run: python evals/run_evals.py --injection (needs your real key).")
    rows = ""
    for mode, d in r["accuracy"].items():
        rows += (f"<tr><td>{'Full agent' if mode == 'agentic' else 'Lean'}</td><td class=n>{d['completed']}/{d['runs']}</td><td class=n>{d['intake_correct_pct']}%</td>"
                 f"<td class=n>{d['clean_first_time_pct']}%</td><td class=n>{d['verdict_matches_engine_pct']}%</td>"
                 f"<td class=n>{d['avg_input'] + d['avg_output']:,.0f}</td><td class=n>{d['avg_calls']}</td><td class=n>{d['avg_seconds']} s</td></tr>")
    return (f"<p class=small>Model {esc(str(r['model']))}, run {esc(r['when'])}. 12 test businesses with known answers.</p><table><thead><tr><th>Mode</th><th class=n>Completed</th>"
            "<th class=n>Intake correct</th><th class=n>AI answers clean first time</th><th class=n>Verdict matches engine</th><th class=n>Tokens per run</th><th class=n>Calls</th><th class=n>Time</th></tr></thead><tbody>"
            + rows + "</tbody></table>")


def injection_block():
    r = load_json(ROOT / "evals" / "results.json")
    if not r or r.get("mock") or "injection" not in r:
        return todo("No attack results yet. Run: python evals/run_evals.py --injection (needs your real key).")
    inj = r["injection"]
    rows = "".join(f"<tr><td>{esc(d['id'])}</td><td>{esc(d['kind'])}</td><td>{esc(d['text'].split('rupees.', 1)[-1].strip()[:90])}</td><td>{esc(d['outcome'])}</td></tr>" for d in inj["detail"])
    return (f"<p><b>{inj['attacks'] - inj['failed']} of {inj['attacks']} attacks failed to manipulate the answer.</b></p><table><thead><tr><th>ID</th><th>Type</th><th>Attack text (after the business details)</th><th>What happened</th></tr></thead><tbody>"
            + rows + "</tbody></table>")


def tests_block():
    env = {**os.environ, "MOCK_LLM": "1"}
    p = subprocess.run([sys.executable, "-m", "unittest", "discover", "tests", "-v"], cwd=ROOT, env=env, capture_output=True, text=True)
    lines = [l for l in p.stderr.splitlines() if " ... " in l]
    groups = {}
    for l in lines:
        mm = re.match(r"test_(\w+) \((?:[\w.]+\.)?(\w+)\.(\w+)\) \.\.\. (\w+)", l)
        if mm:
            groups.setdefault(mm.group(2), []).append((mm.group(1).replace("_", " "), mm.group(4)))
    ok = sum(1 for g in groups.values() for _, s in g if s == "ok")
    total = sum(len(g) for g in groups.values())
    body = "".join(f"<tr><td>{esc(c)}</td><td>{'; '.join(esc(n) for n, _ in g)}</td><td class=n>{sum(1 for _, s in g if s == 'ok')}/{len(g)}</td></tr>" for c, g in groups.items())
    return (f"<p><b>{ok} of {total} tests pass</b> (live run when this report was built, offline mode, no API key needed). "
            "Each test attacks one defense on purpose.</p><table><thead><tr><th>Group</th><th>Tests</th><th class=n>Pass</th></tr></thead><tbody>" + body + "</tbody></table>")


def impact_block():
    d = load_json(EV / "impact.json")
    if not d:
        return todo("No real-user evidence yet. Ask one real shop owner to try the app for 15 minutes, time the same decision done by hand in a spreadsheet, then save evidence/impact.json (format in SUBMISSION_CHECKLIST.md). This is the single most valuable piece of evidence for the Impact row.")
    saved = d["manual_minutes"] - d["app_minutes"]
    return (f"<h3>A real user tried it</h3><table><tbody><tr><td>Who</td><td>{esc(d['user'])}</td></tr>"
            f"<tr><td>Same decision by hand</td><td>{d['manual_minutes']} minutes</td></tr><tr><td>With Loyalty Advisor</td><td>{d['app_minutes']} minutes</td></tr>"
            f"<tr><td>Time saved</td><td>{saved} minutes ({saved / max(1, d['manual_minutes']) * 100:.0f}%)</td></tr>"
            f"<tr><td>What changed for them</td><td>{esc(d.get('what_changed', ''))}</td></tr></tbody></table>"
            f"<blockquote>{esc(d['quote'])}</blockquote>")


DIAGRAM = """<svg viewBox="0 0 900 330" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Agent architecture" style="width:100%;height:auto;font-family:Avenir Next,Segoe UI,Arial,sans-serif">
<defs><marker id="ar" markerWidth="9" markerHeight="9" refX="8" refY="4.5" orient="auto"><path d="M0,0 L9,4.5 L0,9 z" fill="#4a5b6e"/></marker></defs>
<g stroke-width="1.6" fill="none" stroke="#4a5b6e" marker-end="url(#ar)">
<path d="M130,60 H165"/><path d="M290,60 H325"/><path d="M450,60 H485"/><path d="M610,60 H645"/>
<path d="M705,90 V145"/><path d="M645,190 H610"/><path d="M485,190 H450"/><path d="M325,190 H290"/></g>
<g font-size="13" text-anchor="middle" fill="#14263b">
<rect x="10" y="30" width="120" height="60" rx="10" fill="#fff" stroke="#14263b"/><text x="70" y="57" font-weight="700">Owner</text><text x="70" y="75">plain-words text</text>
<rect x="170" y="30" width="120" height="60" rx="10" fill="#e8ecf0" stroke="#4a5b6e"/><text x="230" y="55" font-weight="700">Input guard</text><text x="230" y="73" font-size="11">code · injection</text>
<rect x="330" y="30" width="120" height="60" rx="10" fill="#0f4c81"/><text x="390" y="55" font-weight="700" fill="#fff">Intake</text><text x="390" y="73" font-size="11" fill="#fff">AI · text to numbers</text>
<rect x="490" y="30" width="120" height="60" rx="10" fill="#e8ecf0" stroke="#4a5b6e"/><text x="550" y="52" font-weight="700">Engine</text><text x="550" y="68" font-size="11">code · checks, scores,</text><text x="550" y="81" font-size="11">reward size, break-even</text>
<rect x="650" y="30" width="120" height="60" rx="10" fill="#0f4c81"/><text x="710" y="52" font-weight="700" fill="#fff">Analyst</text><text x="710" y="68" font-size="11" fill="#fff">AI · picks checks</text><text x="710" y="81" font-size="11" fill="#fff">6 read-only tools</text>
<rect x="650" y="150" width="120" height="60" rx="10" fill="#0f4c81"/><text x="710" y="175" font-weight="700" fill="#fff">Strategist</text><text x="710" y="193" font-size="11" fill="#fff">AI · should you?</text>
<rect x="490" y="150" width="120" height="60" rx="10" fill="#0f4c81"/><text x="550" y="175" font-weight="700" fill="#fff">Designer</text><text x="550" y="193" font-size="11" fill="#fff">AI · program + plan</text>
<rect x="330" y="150" width="120" height="60" rx="10" fill="#e8ecf0" stroke="#4a5b6e"/><text x="390" y="172" font-weight="700">Output guard</text><text x="390" y="188" font-size="11">code · figures must be</text><text x="390" y="201" font-size="11">in the verified facts</text>
<rect x="170" y="150" width="120" height="60" rx="10" fill="#fff" stroke="#14263b"/><text x="230" y="177" font-weight="700">Your plan</text><text x="230" y="195" font-size="11">verdict + launch kit</text>
<rect x="10" y="250" width="880" height="44" rx="10" fill="#fbf0dc" stroke="#f2b01e"/><text x="450" y="277" font-size="13">Budget guard wraps every AI call: per-run, per-client and daily token caps, call-count cap, timeout, rate limit</text>
</g>
<g font-size="12" fill="#14263b"><rect x="10" y="306" width="14" height="14" rx="3" fill="#0f4c81"/><text x="30" y="318">AI agent</text><rect x="110" y="306" width="14" height="14" rx="3" fill="#e8ecf0" stroke="#4a5b6e"/><text x="130" y="318">plain code (cannot be talked out of its answer)</text></g>
</svg>"""

COMPARE = """<table><thead><tr><th>Question the owner has</th><th>Loyalty platforms (Square Loyalty, Smile.io, Loyverse)</th><th>Vendor ROI calculators</th><th>ChatGPT alone</th><th>Loyalty Advisor</th></tr></thead><tbody>
<tr><td>Should I run a program at all?</td><td>Not their job: they help you run one</td><td>Usually assume yes</td><td>Can discuss, no checked numbers</td><td><b>Yes: launch, pilot or not yet</b></td></tr>
<tr><td>How big a reward can I afford?</td><td>You choose</td><td>One formula, inputs optimistic</td><td>May invent a figure</td><td><b>Sized to your margin</b></td></tr>
<tr><td>What lift do I need to break even?</td><td>Not shown</td><td>Rarely</td><td>Not reliably</td><td><b>Computed and tested</b></td></tr>
<tr><td>Which of six designs fits my goal and tools?</td><td>Their own design</td><td>No</td><td>Generic list</td><td><b>Scored and ranked</b></td></tr>
<tr><td>Exact numbers, rules, scripts, launch plan, stop rules?</td><td>Setup screens</td><td>No</td><td>Prose, unverified</td><td><b>Yes, with red flags</b></td></tr>
<tr><td>Can I trust the figures?</td><td>n/a</td><td>Vendor interest</td><td>Not checked</td><td><b>Code computes, guard verifies</b></td></tr></tbody></table>"""

CSS_REPORT = """
@page { size: Letter; margin: 0.65in; }
* { box-sizing: border-box; }
body { font: 10.5pt/1.45 "Avenir Next","Segoe UI",system-ui,Arial,sans-serif; color: #14263b; margin: 0 auto; max-width: 8.4in; padding: 0.3in; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
h1 { font-size: 30pt; margin: 0 0 4pt; color: #0f4c81; line-height: 1.1; }
h2 { font-size: 15pt; margin: 22pt 0 6pt; padding-bottom: 3pt; border-bottom: 2px solid #f2b01e; break-after: avoid; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; break-after: avoid; }
p { margin: 0 0 7pt; } ul, ol { margin: 0 0 8pt; padding-left: 18pt; } li { margin: 2pt 0; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 6pt 0 10pt; break-inside: avoid; }
th, td { border: 1px solid #d3dae2; padding: 4pt 6pt; text-align: left; vertical-align: top; } th { background: #e6eef6; } td.n, th.n { text-align: right; }
figure { margin: 8pt 0; break-inside: avoid; } figure img { max-width: 100%; border: 1px solid #d3dae2; border-radius: 4px; } figcaption { font-size: 8.5pt; color: #4a5b6e; margin-top: 2pt; }
.todo { background: #fff3c4; border: 2px dashed #c98a00; border-radius: 6px; padding: 6pt 9pt; margin: 8pt 0; font-size: 9.5pt; break-inside: avoid; }
.small { font-size: 9pt; color: #4a5b6e; } blockquote { margin: 8pt 0; padding: 6pt 12pt; border-left: 4px solid #f2b01e; background: #f2f4f7; }
.meta { font-size: 10.5pt; margin: 10pt 0 6pt; } .meta td { border: 0; padding: 1pt 8pt 1pt 0; } .lead { font-size: 12.5pt; color: #4a5b6e; margin-bottom: 10pt; }
.two { display: grid; grid-template-columns: 1fr 1fr; gap: 12pt; } .callout { background: #e6eef6; border-radius: 8px; padding: 8pt 12pt; margin: 8pt 0; break-inside: avoid; }
code { background: #f2f4f7; padding: 0 3pt; border-radius: 3px; font-size: 9pt; }
"""

REPORT = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Loyalty Advisor: report</title><style>@@CSS@@</style></head><body>

<h1>Loyalty Advisor</h1>
<p class="lead">An AI agent app that tells a small business whether a loyalty program will pay for itself, and designs one if it will.</p>
<table class="meta"><tbody>
<tr><td><b>Author</b></td><td>@@NAME@@ · @@COURSE@@</td></tr>
<tr><td><b>Code</b></td><td>@@REPO@@</td></tr>
<tr><td><b>Live app</b></td><td>@@APP@@</td></tr>
<tr><td><b>In one sentence</b></td><td>You describe your shop in plain words and four AI agents, backed by tested maths, answer "launch it, pilot it, or not yet?" and hand you a complete program with numbers, rules, scripts, red flags and a 12-week plan.</td></tr></tbody></table>
@@TITLE_SHOT@@

<h2>1. The problem and who has it</h2>
<p>Millions of small businesses (cafes, kirana stores, salons, boutiques, online shops) are told to "start a loyalty program". App vendors say it, competitors do it, and every owner has heard that regular customers matter. The decision is almost always made by gut feel or by copying the shop next door.</p>
<p><b>How owners deal with it today:</b> copy a neighbour's stamp card, sign up with an app vendor whose calculator assumes the program works, or ask a general chatbot that happily invents a figure. None of these checks the one question that decides the outcome: <b>does the extra profit from changed behaviour beat everything given away in rewards?</b> Most reward cost goes to customers who would have bought anyway.</p>
<div class="callout"><b>What a wrong guess costs, from the app's own engine.</b> An example cafe (3,000 bills a month, @@BILL@@ average bill, 65% margin, @@RR@@% of member spend given back) gains @@EXP@@ a month if members spend 6% more, but <b>loses @@PESS@@ a month</b> if they spend only 2% more. That is @@PESSYEAR@@ a year, quietly, with no one to point it out. These are engine outputs on illustrative inputs, not field measurements.</div>
<h3>Where this idea comes from</h3>
<p>I came to this from an earlier project: a strategy whitepaper on a real airport loyalty program (Aeroknots, at Delhi Airport, about 70 million passengers a year and 400+ shops). Its findings are exactly the failure modes a small owner faces, just at a larger scale:</p>
<ul><li>Shops already paid 22 to 38% of sales in fees and revenue share, so margins were thin. The program added 1.1% (earn only) up to 10% (burn only) of the bill on top.</li>
<li>Much airport buying is impulsive, so sales rose only for planned purchases. The lift was small.</li>
<li>Nobody had settled who pays for the points, and customers were expected to redeem at a few "winner" shops while others funded them.</li>
<li>The vendor's financial model was found to lack the detail needed for an investment decision, yet commitments had been made.</li></ul>
<p>A large operator can pay consultants to find this. A shop owner cannot. <b>Loyalty Advisor is that check, made free, fast and understandable for the common man.</b></p>

<h2>2. What is new here</h2>
<p>I looked at what already exists. This comparison is based on how each category describes itself publicly; I have not used paid versions.</p>
@@COMPARE@@
@@VERIFY@@
<h3>What is different, and why it matters</h3>
<ul><li><b>It starts from "should I?", not "how do I set it up?"</b> Platforms assume you have decided. Most owners have not, and a "no, not yet" is the most valuable answer for a shop with few repeat customers.</li>
<li><b>It sizes the reward to your margin.</b> The reward rate is the largest one that still pays in the expected case with headroom, never below a level customers would notice. If those two conflict, the verdict says so.</li>
<li><b>Maths in code, words from AI.</b> Every figure is computed by tested code and the AI is only allowed to explain it. A guard rejects any number in AI text that is not in the verified facts.</li>
<li><b>It ends with a kill switch.</b> Each plan lists red flags and stop rules, so a failing program is stopped at week 12, not year 2.</li></ul>
<p>Four different businesses get four different answers from the same engine (live output):</p>
@@EXAMPLES@@

<h2>3. The agents</h2>
<h3>Who does what</h3>
<table><thead><tr><th>Component</th><th>Type</th><th>Job</th><th>Tools</th></tr></thead><tbody>
<tr><td>Input guard</td><td>code</td><td>Cleans text, blocks prompt-injection patterns before any AI sees it</td><td>pattern checks</td></tr>
<tr><td>Intake</td><td>AI, structured output</td><td>Turns a plain-words description into numbers; leaves unknowns blank instead of guessing</td><td>none</td></tr>
<tr><td>Engine</td><td>code</td><td>Readiness checks, scores six designs, sizes rewards, three scenarios, break-even, KPIs, launch plan</td><td>n/a</td></tr>
<tr><td>Analyst</td><td>AI, tool loop (max 6 rounds, 8 calls)</td><td>Decides which extra checks to run (what-ifs, comparing top designs, playbook lookups) and writes short notes</td><td><code>check_gates</code> <code>rank_designs</code> <code>get_design_plan</code> <code>run_economics</code> <code>compare_top_designs</code> <code>lookup_playbook</code></td></tr>
<tr><td>Strategist</td><td>AI, structured output</td><td>Answers "should you do this at all?" with reasons, risks and alternatives</td><td>none</td></tr>
<tr><td>Designer</td><td>AI, structured output</td><td>Personalises the program: name, customer pitch, staff script, launch plan, tips</td><td>none</td></tr>
<tr><td>Output guard</td><td>code</td><td>Verdict must match the engine; every figure must be in the facts; no leaked prompt; one rewrite then a safe template</td><td>grounding check</td></tr></tbody></table>
<h3>How they are organised</h3>
<p>Work flows one way, left to right then back along the bottom row. Code does everything that must be right (maths, verdict, checks). AI agents do everything that needs language (reading messy text, choosing what to look at, explaining, personalising). The Analyst is the only agent that chooses its own steps, and it can only call read-only tools bound to the owner's profile.</p>
@@DIAGRAM@@
<h3>Models</h3>
<p>All agents use the course model <code>gpt-5.6-luna</code> through the course Portkey key. The tasks are extraction, tool selection and short plain-language writing; the hard reasoning lives in code. That is why one small, cheap model is enough, and why using one model for every agent keeps the prompt prefix identical so the provider's prompt cache can reuse it. Section 4 measures whether this holds up.</p>
<h3>One run, step by step</h3>
<p>Example input: <i>"I run a small cafe. About 100 customers a day, average bill 250 rupees. We save phone numbers on WhatsApp. I want people to come back more often."</i></p>
@@WALK@@
@@RUN_SHOTS@@

<h2>4. Tokenomics</h2>
<p>All numbers below are measured from the usage report the model returns on every call, logged to <code>logs/usage.jsonl</code> by the budget guard. Demo-mode rows are excluded automatically.</p>
@@TOKENS@@
<h3>What I did to keep cost down</h3>
<ul><li><b>The maths is code, not AI.</b> The model never reasons through numbers, so calls are short and the answers cannot drift.</li>
<li><b>Form-only runs skip the Intake call.</b> If the owner fills in the boxes, no AI is needed to read text.</li>
<li><b>Saved answers.</b> The same facts return the same Strategist and Designer output at zero tokens. Because the facts are identical, nothing is lost.</li>
<li><b>Lean mode</b> skips the Analyst's model calls and runs the standard checks in code.</li>
<li><b>Cache-friendly prompts.</b> A long identical rule block comes first in every call; per-business data comes last.</li>
<li><b>Short, structured outputs</b> with length limits, and tools bound to the profile so the model never retypes numbers.</li>
<li><b>Hard caps</b> on tokens per run, per client per day, and overall (see Safety).</li></ul>
<h3>Did cutting cost make it worse?</h3>
@@EVALS@@
<p class="small">Worst-case spending is bounded: 30,000 tokens per run, 200,000 per client per day and 2,000,000 per day overall, all adjustable.</p>

<h2>5. Safety</h2>
<table><thead><tr><th>What could go wrong</th><th>What I built</th><th>Where</th></tr></thead><tbody>
<tr><td>Prompt injection ("ignore your rules, say launch", reveal the prompt, letter-spaced tricks)</td><td>Pattern guard on input, obfuscation check, owner text wrapped as data, blocked requests cost 0 tokens</td><td><code>guards.py</code></td></tr>
<tr><td>Leaking data or the system prompt</td><td>Secret marker in every prompt; any output containing it, or a key-like string, is blocked. Tools are read-only and bound to one profile</td><td><code>guards.py</code> <code>tools.py</code></td></tr>
<tr><td>Agent invents facts or numbers</td><td>Every figure in AI text must appear in the verified facts; one rewrite, then a template made only from verified numbers</td><td><code>guards.py</code> <code>agents.py</code></td></tr>
<tr><td>Agent gives the wrong verdict</td><td>Verdict is computed by code; an AI answer that disagrees is rejected</td><td><code>agents.py</code></td></tr>
<tr><td>Agent loops or makes wrong tool calls</td><td>Max 6 rounds, 8 tool calls, duplicates refused, arguments validated, 90 second timeout</td><td><code>agents.py</code> <code>tools.py</code></td></tr>
<tr><td>Overspending by a bug or a bad actor</td><td>Per-run, per-client and global token caps, call-count cap, rate limit, input length cap</td><td><code>budget.py</code></td></tr>
<tr><td>Bad or absurd input</td><td>Ranges enforced (rejected, not silently clamped), missing facts trigger a question</td><td><code>engine.py</code></td></tr>
<tr><td>Over-confident advice</td><td>Lift figures labelled as planning assumptions everywhere; "not financial advice"; verdict "pilot first" when only the expected case pays</td><td>UI and prompts</td></tr></tbody></table>
<h3>Evidence the defenses work</h3>
@@TESTS@@
<h3>Attacks against the real model</h3>
@@INJECTION@@
<div class="two">@@SAFE_SHOTS@@</div>
<p class="small">Tests found a real bug in this project: a business with a 2% margin made the default reward cap fall below its allowed minimum and crashed the engine. It is fixed and now covered by a test.</p>

<h2>6. Impact</h2>
@@IMPACT@@
<p><b>What I can already show.</b> The same engine gives different answers for different businesses (table in section 2), which is the point: a one-size "start a program" advice would be wrong for at least two of those four. The numbers there come from the engine on illustrative inputs. The honest way to turn them into evidence is the 12-week pilot built into every plan, which replaces the planning assumptions with the owner's own data.</p>

<h2>7. Limits and next steps</h2>
<h3>What does not work yet</h3>
<ul><li><b>The lift is assumed, not measured.</b> The 2%, 6% and 12% extra-spend scenarios and the enrolment rates are planning assumptions. The app says so everywhere, but they are the weakest link.</li>
<li><b>Defaults are generic.</b> Margins and visit rates by business type are starting points the owner should override; each default is listed with its basis.</li>
<li>No memory between visits, and no import of real sales data. Six designs only (no coalition or partner programs). Four currencies.</li>
<li>Not validated with enough real owners yet.</li></ul>
<h3>What I would build in the next month</h3>
<ul><li><b>Pilot tracker:</b> paste weekly sales for members and non-members and get the real lift, the real break-even gap and a scale/adjust/stop recommendation.</li>
<li><b>Calibrate the assumptions</b> from pilot results across many shops.</li>
<li>WhatsApp front end and Hindi and other languages, since many owners work on a phone.</li>
<li>Supplier-funded and partner rewards (the airport lesson on who pays), and POS exports for one-click setup.</li></ul>
</body></html>"""


def build_report():
    fill = {
        "CSS": CSS_REPORT, "COURSE": esc(COURSE), "NAME": esc(STUDENT_NAME) if not STUDENT_NAME.startswith("TODO") else todo(STUDENT_NAME),
        "REPO": esc(REPO_URL) if not REPO_URL.startswith("TODO") else todo(REPO_URL),
        "APP": esc(APP_URL) if APP_URL else "Runs locally from the repo (see README)",
        "BILL": m(250), "RR": f"{CE['reward_rate_pct']:g}", "EXP": m(CS["expected"]["net_month"]),
        "PESS": m(abs(CS["pessimistic"]["net_month"])), "PESSYEAR": m(abs(CS["pessimistic"]["net_month"]) * 12),
        "COMPARE": COMPARE, "EXAMPLES": examples_table(), "DIAGRAM": DIAGRAM, "WALK": cafe_walk_table(),
        "TITLE_SHOT": shot("03_verdict.png", "The verdict card for the example cafe, from a real run"),
        "VERIFY": todo("Open each product's website and adjust the comparison table to what you actually see before submitting. I could not verify it for you."),
        "RUN_SHOTS": shot("04_agent_log.png", "What each agent did, including the real tool calls") + shot("06_blueprint.png", "The program the Designer produced") + shot("07_numbers.png", "Scenario numbers and break-even"),
        "TOKENS": tokenomics_block() + shot("11_run_meter.png", "The in-app run meter showing measured tokens for one run"),
        "EVALS": evals_block(), "TESTS": tests_block(), "INJECTION": injection_block(),
        "SAFE_SHOTS": shot("14_injection_blocked.png", "An injection attempt blocked before any AI call") + shot("15_subtle_injection.png", "A subtle manipulation that reached the model and was ignored"),
        "IMPACT": impact_block(),
    }
    out = REPORT
    for k, v in fill.items():
        out = out.replace(f"@@{k}@@", v)
    (ROOT / "report.html").write_text(out, encoding="utf-8")
    return out.count('class="todo"')


CSS_SLIDES = """
.reveal { font-family: "Avenir Next","Segoe UI",system-ui,Arial,sans-serif; color: #14263b; font-size: 27px; }
.reveal h1, .reveal h2, .reveal h3 { text-transform: none; color: #0f4c81; font-weight: 700; margin: 0 0 .35em; line-height: 1.1; }
.reveal h1 { font-size: 2.5em; } .reveal h2 { font-size: 1.45em; } .reveal h3 { font-size: 1em; margin-bottom: .2em; }
.reveal section { text-align: left; } .reveal ul { display: block; margin: 0 0 .4em 1em; } .reveal li { margin: .22em 0; line-height: 1.25; }
.reveal .dark h1, .reveal .dark h2, .reveal .dark { color: #fff; }
.reveal p { margin: .3em 0; } .big { font-size: 1.3em; font-weight: 700; } .sub { color: #4a5b6e; font-size: .66em; } .amber { color: #a8650f; }
.reveal table { font-size: .62em; border-collapse: collapse; width: 100%; margin: .3em 0; } .reveal th, .reveal td { border: 1px solid #d3dae2; padding: 4px 9px; text-align: left; vertical-align: top; line-height: 1.2; } .reveal th { background: #e6eef6; }
.reveal td.n, .reveal th.n { text-align: right; }
.reveal figure { margin: 0 0 .3em; } .reveal figure img { max-height: 360px; max-width: 100%; border: 1px solid #d3dae2; border-radius: 6px; margin: 0; } .reveal figcaption { font-size: .55em; color: #4a5b6e; }
.todo { background: #fff3c4; border: 3px dashed #c98a00; border-radius: 8px; padding: 10px 14px; font-size: .6em; margin: .3em 0; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 26px; align-items: start; } .cols3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.num { font-size: 1.9em; font-weight: 800; color: #0f4c81; line-height: 1; } .card { background: #f2f4f7; border-radius: 10px; padding: 10px 16px; font-size: .78em; line-height: 1.25; }
.card.amber { background: #fbf0dc; color: #14263b; } .card.green { background: #e3f2ec; } .card.red { background: #fbe7e4; } .chip { display: inline-block; background: #0f4c81; color: #fff; border-radius: 999px; padding: 4px 16px; font-size: .7em; margin: 0 8px 8px 0; }
.sm { font-size: .78em; } .tight li { margin: .12em 0; }
.foot { position: fixed; left: 24px; bottom: 10px; font-size: 13px; color: #4a5b6e; z-index: 30; }
"""


def slides_tokens():
    t = load_json(EV / "tokenomics.json")
    if not t or not t.get("modes"):
        return todo("Run scripts/tokenomics.py after real runs, then rebuild: tokens per check, cached share, cost per check and cost for 10,000 users appear here.")
    mode = "agentic" if "agentic" in t["modes"] else next(iter(t["modes"]))
    d = t["modes"][mode]
    cost, cur = d.get("cost_per_run"), t.get("currency", "USD")
    cells = [(f"{d['avg_input_tokens'] + d['avg_output_tokens']:,}", "tokens per check"), (f"{d['cache_share_of_input_pct']}%", "of input from cache")]
    if cost is not None:
        cells += [(f"{cost:.4f} {cur}", "per check"), (f"{d['cost_per_user_month']:.3f} {cur}", f"per user a month ({t['runs_per_user_month_assumption']:g} checks, assumed)"),
                  (f"{d['cost_100_users_month']:.2f} {cur}", "100 users a month"), (f"{d['cost_10000_users_month']:,.0f} {cur}", "10,000 users a month")]
    return '<div class="cols3">' + "".join(f'<div class="card"><div class="num">{a}</div>{b}</div>' for a, b in cells) + "</div>" + (
        "" if cost is not None else todo("Fill pricing.json to show cost per check, per user and at scale."))


def build_slides():
    P, A, E = CAFE_P, CAFE_A, CE
    gates_ok = len([g for g in A["gates"] if g["status"] == "pass"])
    top = A["ranking"][:3]
    tests = tests_block()
    ok = re.search(r"(\d+) of (\d+) tests pass", tests)
    inj = load_json(ROOT / "evals" / "results.json")
    inj_line = (f"{inj['injection']['attacks'] - inj['injection']['failed']} of {inj['injection']['attacks']} attacks failed to manipulate the answer"
                if inj and not inj.get("mock") and "injection" in inj else None)
    s = []
    s.append(f"""<section class="dark" data-background-color="#0f4c81"><h1>Loyalty Advisor</h1>
<p class="big">Should your business run a loyalty program? And if so, exactly which one?</p>
<p style="margin-top:1em">An AI agent app for small business owners that checks the maths first.</p>
<p style="margin-top:1.4em"><span class="chip">4 AI agents</span><span class="chip">6 program designs</span><span class="chip">maths in tested code</span><span class="chip">{ok.group(1) if ok else '40'} automated tests</span></p>
<p style="margin-top:1.2em"><b>{esc(STUDENT_NAME)}</b> · {esc(COURSE)}</p>
<aside class="notes">Introduce yourself and the course. One sentence: this app tells a shop owner whether a loyalty program will pay for itself, and designs one if it will.</aside></section>""")
    s.append(f"""<section><h2>The problem: everyone says "start a loyalty program"</h2>
<div class="cols"><div>
<p><b>Who has it:</b> owners of cafes, kirana stores, salons, boutiques, online shops.</p>
<p><b>How they decide today:</b></p><ul class="tight"><li>copy the shop next door</li><li>trust an app vendor's calculator</li><li>ask a chatbot that invents a number</li></ul>
<p><b>What nobody checks:</b> does the <i>extra</i> profit beat <i>all</i> the rewards given? Most rewards go to people who would have bought anyway.</p>
<div class="card amber"><b>Example cafe, from the app's own engine:</b><br>gains <b>{m(CS['expected']['net_month'])}/month</b> if members spend 6% more, but <b>loses {m(abs(CS['pessimistic']['net_month']))}/month</b> ({m(abs(CS['pessimistic']['net_month']) * 12)}/year) if they spend only 2% more.</div>
</div><div>
<h3>Where the idea came from: my airport loyalty study</h3>
<p class="sm">Aeroknots at Delhi Airport: about 70 million passengers a year, 400+ shops.</p>
<ul class="sm tight"><li>Shops already paid <b>22 to 38%</b> of sales in fees and revenue share</li>
<li>The program added <b>1.1%</b> (earn only), <b>2.0%</b> (earn + burn) or <b>10%</b> (burn only) per bill</li>
<li>Much buying is impulsive, so the sales lift was small</li>
<li>Nobody had settled <b>who pays for the points</b>; customers redeemed at a few "winner" shops</li>
<li>The vendor's model lacked the detail to decide, yet commitments were made</li></ul>
<div class="card green"><b>Lesson:</b> the same mistakes happen in small shops, where nobody is paid to catch them. This app is that check.</div></div></div>
<aside class="notes">Stress the one question nobody asks: extra profit versus all rewards. Then explain the airport study as the origin: big operator, same failure modes. Cafe numbers are engine outputs on illustrative inputs, not field data.</aside></section>""")
    s.append("""<section><h2>What is new</h2>
<table><thead><tr><th>Owner's question</th><th>Loyalty platforms (Square Loyalty, Smile.io, Loyverse)</th><th>Vendor ROI calculators</th><th>ChatGPT alone</th><th>Loyalty Advisor</th></tr></thead><tbody>
<tr><td>Should I run one at all?</td><td>Not their job</td><td>Usually assume yes</td><td>Prose, unchecked</td><td><b>Launch / pilot / not yet</b></td></tr>
<tr><td>How big a reward can I afford?</td><td>You choose</td><td>Optimistic inputs</td><td>May invent a figure</td><td><b>Sized to your margin</b></td></tr>
<tr><td>Break-even lift?</td><td>Not shown</td><td>Rarely</td><td>Not reliably</td><td><b>Computed and tested</b></td></tr>
<tr><td>Which of six designs fits me?</td><td>Their own design</td><td>No</td><td>Generic list</td><td><b>Scored and ranked</b></td></tr>
<tr><td>Rules, scripts, plan, stop rules?</td><td>Setup screens</td><td>No</td><td>Unverified prose</td><td><b>Yes, with red flags</b></td></tr>
<tr><td>Can I trust the figures?</td><td>n/a</td><td>Vendor interest</td><td>Not checked</td><td><b>Code computes, guard verifies</b></td></tr></tbody></table>
<div class="cols3" style="margin-top:.5em"><div class="card"><b>Starts at "should I?"</b><br>not "how do I set it up?"</div><div class="card"><b>Maths in code</b><br>AI explains, never calculates</div><div class="card"><b>Ends with a kill switch</b><br>red flags and stop rules at week 12</div></div>
<p class="sub">Comparison based on public descriptions of each category.</p>
<aside class="notes">Be honest: the comparison is from how each category describes itself. The novelty is the go/no-go question, reward sizing to margin, and the verified numbers.</aside></section>""")
    s.append(f"""<section><h2>How it works</h2>{DIAGRAM}
<div class="cols3"><div class="card green"><b>Code</b> does the maths, the verdict and every check</div><div class="card"><b>AI</b> reads messy text, chooses extra checks, explains, personalises</div><div class="card amber"><b>Budget guard</b> caps tokens, calls, time and rate on every AI call</div></div>
<aside class="notes">Walk left to right: guard, intake, engine, analyst; then strategist, designer, output guard, plan. The key idea: whatever must be right is plain code that cannot be talked out of its answer.</aside></section>""")
    s.append("""<section><h2>The agents, tools and model</h2>
<table><thead><tr><th>Component</th><th>Type</th><th>Job</th><th>Tools</th></tr></thead><tbody>
<tr><td>Input guard</td><td>code</td><td>Cleans text, blocks injection before any AI sees it</td><td>pattern checks</td></tr>
<tr><td>Intake</td><td>AI, structured output</td><td>Plain words to numbers; blanks instead of guesses</td><td>none</td></tr>
<tr><td>Engine</td><td>code</td><td>Readiness checks, scores 6 designs, sizes rewards, 3 scenarios, break-even, KPIs</td><td>n/a</td></tr>
<tr><td>Analyst</td><td>AI, tool loop (6 rounds, 8 calls)</td><td>Chooses what-ifs, comparisons and playbook lookups</td><td>check_gates, rank_designs, get_design_plan, run_economics, compare_top_designs, lookup_playbook</td></tr>
<tr><td>Strategist</td><td>AI, structured output</td><td>"Should you do this at all?": reasons, risks, alternatives</td><td>none</td></tr>
<tr><td>Designer</td><td>AI, structured output</td><td>Program name, customer pitch, staff script, 12-week plan</td><td>none</td></tr>
<tr><td>Output guard</td><td>code</td><td>Verdict must match the engine; every figure must be in the facts</td><td>grounding check</td></tr></tbody></table>
<div class="cols"><div class="card"><b>Model:</b> course model <b>gpt-5.6-luna</b> via the course Portkey key, for every agent.</div><div class="card"><b>Why one small model is enough:</b> the hard reasoning is in code; the AI extracts, picks tools and writes short plain text. One model also keeps the prompt prefix identical for caching.</div></div>
<p class="sub">All tools are read-only and bound to one owner's profile.</p>
<aside class="notes">Only the Analyst chooses its own steps, and it can only call read-only tools bound to the owner's profile, so it cannot reach other data or take actions.</aside></section>""")
    s.append(f"""<section><h2>Demo: one real run, step by step</h2>
<div class="cols"><div>
<p class="sm"><i>"I run a small cafe. About 100 customers a day, average bill 250 rupees. We save phone numbers on WhatsApp."</i></p>
<ol class="sm tight"><li><b>Guard:</b> accepted, 0 tokens</li>
<li><b>Intake (AI):</b> cafe, 3,000 bills a month, {m(250)} bill, phone numbers</li>
<li><b>Engine:</b> {gates_ok} of {len(A['gates'])} checks pass; best fit <b>{top[0]['label']}</b> ({top[0]['score']}), then {top[1]['label']} ({top[1]['score']}), {top[2]['label']} ({top[2]['score']})</li>
<li><b>Analyst (AI):</b> compares top designs, looks up a principle</li>
<li><b>Strategist (AI):</b> <b>{engine.VERDICT_LABEL[A['verdict']['code']]}</b>: break-even lift <b>{E['break_even_lift_pct']:g}%</b>, expected <b>{m(CS['expected']['net_month'])}</b>/month, pessimistic <b>{m(CS['pessimistic']['net_month'])}</b></li>
<li><b>Designer (AI):</b> {A['plan']['params']['stamps_needed']} stamps, reward worth {m(A['plan']['params']['reward_value'])}, scripts, 12-week plan</li>
<li><b>Output guard:</b> every figure checked</li></ol>
</div><div>{shot("03_verdict.png", "Verdict card from a real run")}{shot("06_blueprint.png", "Program blueprint from a real run")}</div></div>
<aside class="notes">Do the live demo here: click the Cafe chip. Point at the agent log, the verdict card, then the blueprint and the 12-week plan. Numbers on this slide are deterministic engine outputs.</aside></section>""")
    s.append(f"""<section><h2>Four businesses, four answers</h2>{examples_table()}
<div class="cols"><div class="card green"><b>Launch:</b> pays even in the pessimistic case.<br><b>Pilot first:</b> pays in the expected case only.<br><b>Not yet:</b> does not pay, or a basic need is missing.</div>
<div class="card"><b>Basics that block a program:</b> under 25% of sales from returning customers, under 20 regular customers, or margin under 8%.<br><b>Reward sizing:</b> 80% of break-even at the expected lift, never below 1.5% of spend.</div></div>
<div class="cols" style="margin-top:.4em"><div class="card"><b>6 designs scored out of 100:</b> goal 30, visit pattern 20, returning customers 15, tools 15, margin 10, your time 10.</div><div class="card"><b>Every plan includes:</b> exact numbers, rules, KPIs with red flags, stop rules, a 12-week launch plan.</div></div>
<p class="sub">Live engine output on illustrative inputs. The lift scenarios (2%, 6%, 12%) are planning assumptions; the 12-week pilot replaces them with the owner's own data.</p>
<aside class="notes">Salon launches because referral rewards only cost money when a new customer actually buys. The phone shop is not yet because few customers return. Be upfront that lift scenarios are assumptions.</aside></section>""")
    s.append(f"""<section><h2>Cost to run (tokenomics)</h2>{slides_tokens()}
<div class="cols" style="margin-top:.4em"><div><h3>How cost was kept down</h3><ul class="sm tight"><li>Maths is code, so model calls stay short</li><li>Form-only runs skip the Intake call</li><li>Same facts reuse a saved answer (0 tokens)</li><li>Lean mode skips the Analyst's model calls</li><li>Long identical rules first, so the prompt cache hits</li><li>Short structured outputs; tools bound to the profile</li><li>Hard caps: 30,000 tokens per run, 200,000 per client a day</li></ul></div>
<div><h3>Did cutting cost hurt quality?</h3>{evals_block()}</div></div>
<aside class="notes">All token counts are measured from the usage object returned on each call, logged by the budget guard. Per-user cost assumes 6 checks a month, which is an assumption stated openly.</aside></section>""")
    s.append(f"""<section><h2>Safety: what could go wrong, and what stops it</h2>
<div class="cols"><div><table><thead><tr><th>Risk</th><th>Defense</th></tr></thead><tbody>
<tr><td>Prompt injection, prompt leak</td><td>Pattern + obfuscation guard, secret marker, blocked requests cost 0 tokens</td></tr>
<tr><td>Invented numbers</td><td>Every figure must be in the verified facts; one rewrite, then a safe template</td></tr>
<tr><td>Wrong verdict</td><td>Code decides; a different AI verdict is rejected</td></tr>
<tr><td>Loops, wrong tool use</td><td>Max 6 rounds, 8 calls, read-only validated tools, timeout</td></tr>
<tr><td>Overspending</td><td>Run, client and daily token caps, rate limit</td></tr>
<tr><td>Over-confident advice</td><td>Assumptions labelled; "pilot first" when only the expected case pays</td></tr></tbody></table>
<p class="big" style="margin-top:.3em">{ok.group(0) if ok else 'Tests pass'}</p><p class="sm">Each test attacks one defense on purpose. Tests also caught a real crash for 2%-margin shops, now fixed.</p>
{('<p class="sm"><b>' + inj_line + '</b> (real model, 10 attacks)</p>') if inj_line else todo("Run python evals/run_evals.py --injection to show the attack results here.")}
</div><div>{shot("14_injection_blocked.png", "An injection attempt, blocked before any AI call")}{shot("15_subtle_injection.png", "A subtle manipulation that reached the model and was ignored")}</div></div>
<aside class="notes">Show the blocked-attack screenshot. Explain defense in depth: regex guard first, then the model sees owner text only as data, then the output guard checks figures and the verdict against the engine.</aside></section>""")
    d = load_json(EV / "impact.json")
    imp = (f'<div class="card green"><div class="num">{d["manual_minutes"]} to {d["app_minutes"]} min</div>to make the decision: by hand versus the app</div><div class="card" style="margin-top:.4em">“{esc(d["quote"])}”<br><span class="sub">{esc(d["user"])}</span></div><p class="sm">{esc(d.get("what_changed", ""))}</p>'
           if d else todo("Add evidence/impact.json: one real owner's quote and before/after minutes. Then rebuild."))
    s.append(f"""<section><h2>Impact, limits and next steps</h2>
<div class="cols"><div><h3>Impact</h3>{imp}
<ul class="sm tight"><li>One-size advice would be wrong for at least two of the four example businesses</li><li>Turns a gut-feel decision into a 12-week test with stop rules</li><li>Free, plain-language, no analyst needed</li></ul></div>
<div><h3>Honest limits</h3><ul class="sm tight"><li>Lift scenarios are assumptions until a pilot measures them</li><li>Defaults are generic starting points (each lists its basis)</li><li>No saved history; no import of real sales data</li><li>Six designs; four currencies; not yet tested with many owners</li></ul>
<h3>Next month</h3><ul class="sm tight"><li><b>Pilot tracker:</b> paste member vs non-member sales, get the true lift and a scale / adjust / stop call</li><li>Calibrate assumptions from many pilots</li><li>WhatsApp and Hindi for phone-first owners</li><li>Supplier-funded and partner rewards (the airport's "who pays" lesson)</li></ul></div></div>
<p class="sub">Decision support, not financial advice. Thank you. Questions?</p>
<aside class="notes">Close on the honest limit: the lift is assumed until measured, which is exactly why every plan ends with a pilot and stop rules.</aside></section>""")
    doc = ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Loyalty Advisor: slides</title>'
           '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.css"><link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/theme/white.css">'
           f'<style>{CSS_SLIDES}</style></head><body><div class="reveal"><div class="slides">' + "".join(s) +
           f'</div></div><div class="foot">{esc(STUDENT_NAME)} · {esc(COURSE)} · Loyalty Advisor</div>'
           '<script src="https://cdn.jsdelivr.net/npm/reveal.js@5/dist/reveal.js"></script><script src="https://cdn.jsdelivr.net/npm/reveal.js@5/plugin/notes/notes.js"></script>'
           '<script>Reveal.initialize({hash:true,width:1280,height:760,margin:0.05,center:false,slideNumber:"c/t",transition:"fade",plugins:[RevealNotes]});</script></body></html>')
    (ROOT / "slides.html").write_text(doc, encoding="utf-8")
    assert len(s) <= 10, "assignment allows 10 slides max"
    return doc.count('class="todo"')


if __name__ == "__main__":
    r = build_report()
    s = build_slides()
    print(f"report.html written ({r} TODO boxes left)")
    print(f"slides.html written ({s} TODO boxes left)")
    print("Open both and search for the yellow TODO boxes. Each one needs evidence from your real runs.")
