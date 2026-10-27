"use strict";
/* No framework. All text goes in through textContent, so text from the model can never inject markup. */

const $ = (id) => document.getElementById(id);
const LOCALE = { "₹": "en-IN", "$": "en-US", "£": "en-GB", "€": "de-DE" };
const num = (n) => new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }).format(Math.round(n));
let CUR = "₹";
const money = (n) => (n < 0 ? "−" : "") + CUR + new Intl.NumberFormat(LOCALE[CUR] || "en-IN", { maximumFractionDigits: Math.abs(n) < 100 ? 1 : 0 }).format(Math.abs(n));
const pct = (n, d = 1) => (n === null || n === undefined ? "n/a" : Number(n).toFixed(d).replace(/\.0+$/, "").replace(/(\.\d)0$/, "$1") + "%");

function el(tag, attrs = {}, ...kids) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v; else node.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

const TYPES = { cafe_restaurant: "Cafe, restaurant or food stall", bakery_sweets: "Bakery or sweet shop", grocery: "Grocery, kirana or supermarket",
  pharmacy: "Pharmacy", salon_spa: "Salon or spa", fashion_retail: "Clothing, footwear or gifts", electronics: "Electronics or appliances",
  online_store: "Online store", other_service: "Other service (repair, tuition, studio)" };
const DESIGNS = { punch_card: "Stamp card", points: "Points on spend", tiers: "Silver and Gold tiers", cashback: "Cashback wallet",
  referral: "Refer-a-friend rewards", paid_membership: "Paid membership" };
const VERDICT = { launch: "Launch it", pilot: "Pilot first", not_yet: "Not yet" };
const SCEN = { pessimistic: "Pessimistic", expected: "Expected", optimistic: "Optimistic" };
const COMP = { goal: "Matches your goal", frequency: "Suits how often people visit", regulars: "Enough returning customers", tech: "Fits your tools", margin: "Fits your margin", effort: "Fits your time" };
const COMP_COLOR = { goal: "#0f4c81", frequency: "#3d78ab", regulars: "#7ba4cb", tech: "#f2b01e", margin: "#1e7b57", effort: "#98aec3" };
const FIELD = { gross_margin_pct: "Profit margin on sales (%)", regular_share_pct: "Sales from returning customers (%)", visits_per_month_regular: "Visits a month, per regular",
  owner_hours_per_week: "Your hours a week", setup_cost: "One-time setup cost", tool_cost_month: "Software cost a month", hourly_value: "Value of an hour of your time",
  tech: "How you recognise customers", goal: "Main goal", max_giveaway_pct: "Most you would give back (% of sales)" };
const EXAMPLES = [
  ["Cafe", "I run a small cafe in New Haven. About 100 customers a day, average bill $25. We save phone numbers. I want people to come back more often."],
  ["Grocery store", "Neighborhood grocery store with about 200 customers a day and an average bill of $40. Our profit margin is around 18%. We only use paper bills."],
  ["Salon", "Hair salon with 10 customers a day, average bill $90. We save phone numbers. I mostly want friends of my customers to come."],
  ["Phone shop", "Mobile phone and electronics shop, 4 customers a day, average bill $1,500. People rarely come back."],
];

for (const [k, v] of Object.entries(TYPES)) $("business_type").append(el("option", { value: k }, v));
for (const [k, v] of Object.entries(DESIGNS)) $("design_key").append(el("option", { value: k }, v));
for (const [label, text] of EXAMPLES) {
  const chip = el("button", { type: "button", class: "chip" }, label);
  chip.onclick = () => { $("text").value = text; $("text").focus(); };
  $("chips").append(chip);
}
fetch("/api/health").then((r) => r.json()).then((h) => {
  const b = $("banner");
  if (h.mock) { b.textContent = "Demo mode: no AI model is being called. Token counts are estimates, not measurements."; b.hidden = false; }
  else if (!h.ready) { b.textContent = "No API key found. Put PORTKEY_API_KEY in a .env file (in the repo folder or one folder above) and restart."; b.className = "banner bad"; b.hidden = false; }
}).catch(() => {});

const NUMERIC = ["monthly_transactions", "avg_bill", "gross_margin_pct", "regular_share_pct", "visits_per_month_regular", "owner_hours_per_week",
  "max_giveaway_pct", "setup_cost", "tool_cost_month", "hourly_value"];
function formPayload() {
  const fields = { currency: $("currency").value };
  for (const k of NUMERIC) fields[k] = $(k).value === "" ? null : Number($(k).value);
  for (const k of ["business_type", "goal", "tech"]) fields[k] = $(k).value || null;
  if ($("competitor_has_program").checked) fields.competitor_has_program = true;
  return { text: $("text").value, fields, design_key: $("design_key").value || undefined, mode: $("mode").value || undefined };
}

/* ------------------------------------------------------------------ agent log */
const AGENTS = ["Guard", "Intake", "Analyst", "Strategist", "Designer"];
const BLURB = { Guard: "Checks your text for tricks before any AI sees it", Intake: "Reads your description and fills in the numbers",
  Analyst: "Picks extra checks to run on your numbers", Strategist: "Answers: should you do this at all?", Designer: "Turns the best design into a launch kit" };
let rows = {};
function buildLog() {
  rows = {};
  const ul = el("ol", { class: "log", "aria-label": "What each agent is doing" });
  for (const a of AGENTS) {
    const detail = el("div", { class: "detail" }, BLURB[a]), sub = el("ul", { class: "sub" });
    const li = el("li", { class: "pending" }, el("span", { class: "dot" }), el("div", {}, el("div", { class: "name" }, a), detail, sub));
    rows[a] = { li, detail, sub };
    ul.append(li);
  }
  return ul;
}
const setState = (a, s, d) => { const r = rows[a]; if (!r) return; r.li.className = s; if (d) r.detail.textContent = d; };
const addSub = (a, n) => rows[a] && rows[a].sub.append(el("li", {}, n));

function handleEvent(ev, ctx) {
  switch (ev.type) {
    case "step": setState(ev.agent, ev.status === "start" ? "running" : ev.status === "done" ? "done" : ev.status === "skipped" ? "skipped" : "blocked", ev.detail); break;
    case "tool": {
      const who = ev.agent === "Code" ? "Analyst" : ev.agent;
      const a = ev.args && Object.keys(ev.args).length ? " " + JSON.stringify(ev.args) : "";
      addSub(who, [el("code", {}, ev.tool + a), ev.status === "ok" ? "" : " (" + ev.status + ")"]);
      break;
    }
    case "note": addSub(ev.agent, ev.detail); break;
    case "guard": addSub(ev.agent || (ev.name === "loop_cap" ? "Analyst" : ev.name === "output_leak" ? "Designer" : "Guard"), el("span", { class: "warn" }, "Safety check: " + ev.detail)); break;
    case "blocked":
      setState("Guard", "blocked", "Stopped: this text was not sent to the AI");
      ctx.out.append(el("div", { class: "alert bad" }, el("h3", {}, "Request blocked"), el("p", {}, ev.message))); break;
    case "need_info": ctx.out.append(el("div", { class: "alert info" }, el("h3", {}, "One more detail needed"), el("p", {}, ev.message))); break;
    case "error": ctx.out.append(el("div", { class: "alert bad" }, el("h3", {}, ev.kind === "budget" ? "Limit reached" : "Something went wrong"), el("p", {}, ev.message))); break;
    case "final": CUR = ev.profile.currency; ctx.final = ev; renderFinal(ev, ctx.out); break;
  }
}

async function runCheck(e) {
  e.preventDefault();
  const btn = $("run");
  btn.disabled = true; btn.textContent = "Checking…";
  const results = $("results");
  results.replaceChildren();
  results.append(el("div", { class: "panel" }, el("h2", {}, "What the agents are doing"), buildLog()));
  const out = el("div", { id: "out" });
  results.append(out);
  const ctx = { out };
  try {
    const res = await fetch("/api/check", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(formPayload()) });
    const reader = res.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) !== -1) {
        const chunk = buf.slice(0, i); buf = buf.slice(i + 2);
        if (chunk.startsWith("data: ")) handleEvent(JSON.parse(chunk.slice(6)), ctx);
      }
    }
  } catch (err) {
    out.append(el("div", { class: "alert bad" }, el("h3", {}, "Could not reach the app"), el("p", {}, "Check that the server is still running.")));
  } finally { btn.disabled = false; btn.textContent = "Check my business"; }
}
$("form").addEventListener("submit", runCheck);

/* ------------------------------------------------------------------ results */
const list = (items) => el("ul", {}, items.map((x) => el("li", {}, x)));
const section = (title, ...kids) => el("div", { class: "panel memo" }, el("h2", {}, title), ...kids);

function renderFinal(f, out) {
  const a = f.analysis, v = a.verdict, p = f.profile, s = f.strategy, b = f.blueprint, ec = a.economics, plan = a.plan;
  const exp = ec.scenarios.expected;
  const safe = (flag) => flag.fallback ? el("span", { class: "tag safe" }, "Safe template: AI text failed a check") : null;

  out.append(el("div", { class: "pass tone-" + v.code },
    el("div", { class: "band" }),
    el("div", { class: "main" },
      el("small", {}, p.name + " · " + TYPES[p.business_type] + " · about " + num(p.monthly_transactions) + " bills a month"),
      el("div", { class: "verdict" }, VERDICT[v.code]),
      el("div", { class: "headline" }, s.headline)),
    el("div", { class: "stub" },
      el("div", { class: "stat" }, el("small", {}, "Best fit: " + plan.label), el("b", {}, pct(ec.reward_rate_pct) + " back")),
      el("div", { class: "stat" }, el("small", {}, plan.kind === "spend" ? "Members must spend this much more to break even" : "Break-even"), el("b", {}, plan.kind === "spend" ? pct(ec.break_even_lift_pct, 2) : "per member")),
      el("small", {}, "Expected: " + money(exp.net_month) + " a month"))));

  const strat = section("Should you do it?", safe(f.flags.strategist), el("p", { class: "summary", style: "margin-top:8px" }, s.summary),
    el("h3", {}, "Why"), list(s.reasons), el("h3", {}, "Watch out for"), list(s.risks));
  if (s.alternatives.length) strat.append(el("h3", {}, v.code === "launch" ? "Also consider" : "Try instead, or first"), list(s.alternatives));
  strat.append(el("h3", {}, "Next step"), el("p", {}, s.next_step));
  out.append(strat);

  out.append(el("div", { class: "panel" }, el("h2", {}, "Readiness checks"), el("div", { style: "margin-top:8px" },
    a.gates.map((g) => el("div", { class: "gate" }, el("b", { class: g.status }, g.status === "pass" ? "Good" : g.status === "warn" ? "Careful" : "Problem"), el("span", {}, g.text))))));

  out.append(blueprintPanel(f, safe));
  out.append(economicsPanel(f));
  out.append(rankingPanel(a, p));
  out.append(kpiPanel(a));
  out.append(section("12-week launch plan", safe(f.flags.designer),
    el("ol", { class: "timeline" }, b.launch_plan.map((st) => el("li", {}, el("b", {}, st.when), st.action)))));
  out.append(assumptionsPanel(f));
  out.append(meterPanel(f));
  out.append(el("button", { class: "btn secondary wide", type: "button", onclick: () => downloadPlan(f) }, "Download my plan (.md)"));
}

function blueprintPanel(f, safe) {
  const a = f.analysis, plan = a.plan, b = f.blueprint, pr = plan.params;
  const labels = { stamps_needed: "Stamps for a reward", reward_value: "Reward worth", reward_rate_pct: "Cost as % of member spend", spend_per_point: "Spend per point", points_for_reward: "Points for a reward",
    silver_from_yearly_spend: "Silver from (yearly spend)", gold_from_yearly_spend: "Gold from (yearly spend)", base_cashback_pct: "Base cashback %", silver_cashback_pct: "Silver cashback %", gold_cashback_pct: "Gold cashback %",
    cashback_pct: "Cashback %", credit_expires_days: "Credit expires (days)", minimum_credit_to_use: "Minimum credit to use", reward_each: "Reward to each person", reward_total_per_referral: "Total reward per referral",
    first_year_profit_per_new_customer: "New customer's first-year profit", monthly_fee: "Monthly fee", member_discount_pct: "Member discount %", typical_monthly_discount_value: "Typical monthly discount" };
  const moneyKeys = new Set(["reward_value", "spend_per_point", "silver_from_yearly_spend", "gold_from_yearly_spend", "minimum_credit_to_use", "reward_each", "reward_total_per_referral", "first_year_profit_per_new_customer", "monthly_fee", "typical_monthly_discount_value"]);
  const grid = el("div", { class: "params" });
  for (const [k, v] of Object.entries(pr)) {
    if (!labels[k]) continue;
    grid.append(el("div", { class: "param" }, el("small", {}, labels[k]), el("b", {}, moneyKeys.has(k) ? money(v) : /pct/.test(k) ? pct(v) : num(v))));
  }
  return section("Your program: " + b.program_name, safe(f.flags.designer), el("p", { class: "summary", style: "margin-top:8px" }, b.one_line_pitch),
    grid, el("h3", {}, "How it works"), list(plan.how_it_works), el("h3", {}, "Rules"), list(plan.rules),
    el("h3", {}, "What to say"), el("div", { class: "quote" }, el("small", {}, "To a customer"), b.customer_pitch),
    el("div", { class: "quote" }, el("small", {}, "Staff briefing"), b.staff_script),
    el("h3", {}, "Tailored to your business"), list(b.tailoring_tips));
}

function economicsPanel(f) {
  const ec = f.analysis.economics, p = f.profile;
  const names = ["members", "extra_profit_month", "reward_cost_month", "running_cost_month", "net_month", "net_12_months"];
  const head = { members: f.analysis.plan.kind === "referral" ? "People taking part" : "Members", extra_profit_month: "Extra profit a month", reward_cost_month: "Reward cost a month", running_cost_month: "Running cost a month", net_month: "Result a month", net_12_months: "Result over 12 months" };
  const t = el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, ""), Object.keys(SCEN).map((k) => el("th", { class: "n" }, SCEN[k] + (ec.scenarios[k].uplift_pct ? " (" + ec.scenarios[k].uplift_pct + "% more spend)" : ""))))));
  const body = el("tbody");
  for (const n of names) {
    body.append(el("tr", { class: n === "net_month" ? "pos" : "" }, el("td", {}, head[n]),
      Object.keys(SCEN).map((k) => { const v = ec.scenarios[k][n]; return el("td", { class: "n" + (n.startsWith("net") ? (v >= 0 ? " ok" : " bad") : ""), style: n.startsWith("net") ? "font-weight:650;color:" + (v >= 0 ? "var(--go)" : "var(--hold)") : "" }, n === "members" ? num(v) : money(v)); })));
  }
  t.append(body);
  return el("div", { class: "panel" }, el("h2", {}, "The numbers"),
    el("p", { class: "hint" }, "About " + num(p.regular_customers) + " regular customers. The extra-spend percentages are planning assumptions, not measurements. Your pilot replaces them."),
    el("div", { style: "overflow-x:auto;margin-top:8px" }, t),
    el("p", { class: "hint", style: "margin-top:8px" }, f.analysis.plan.kind === "spend"
      ? "Break-even: members must spend " + pct(ec.break_even_lift_pct, 2) + " more than before. Below that, the rewards cost more than the extra sales earn." + (ec.payback_months ? " Setup pays back in about " + ec.payback_months + " months." : "")
      : "This design has its own break-even rule, so there is no single spend lift to hit."));
}

function rankingPanel(a, p) {
  const body = el("tbody");
  a.ranking.forEach((r, i) => body.append(el("tr", {}, el("td", {}, el("b", {}, r.label), i === 0 ? el("span", { class: "tag safe", style: "background:var(--go-soft);color:var(--go)" }, "Best fit") : null,
    el("div", { class: "hint" }, r.needs.length ? "Watch: " + r.needs.join("; ") : r.tagline)),
    el("td", { class: "n" }, el("b", {}, r.score)),
    el("td", {}, el("div", { class: "score", role: "img", "aria-label": "Score breakdown" }, Object.entries(r.points).map(([k, v]) => el("i", { title: COMP[k] + ": " + v, style: `width:${v}%;background:${COMP_COLOR[k]}` })))))));
  return el("details", { class: "panel" }, el("summary", { style: "cursor:pointer;font-weight:650" }, "Why this design? All six, scored"),
    el("p", { class: "hint", style: "margin:8px 0" }, "Score out of 100: goal (30), visit pattern (20), returning customers (15), tools (15), margin (10), your time (10). Hover a segment to see which."),
    el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Design"), el("th", { class: "n" }, "Score"), el("th", {}, "Breakdown"))), body),
    el("div", { class: "legend" }, Object.entries(COMP).map(([k, v]) => el("span", {}, el("i", { style: "background:" + COMP_COLOR[k] }), v))));
}

function kpiPanel(a) {
  const body = el("tbody");
  for (const k of a.kpis) body.append(el("tr", {}, el("td", {}, el("b", {}, k.name), el("div", { class: "hint" }, k.how)), el("td", {}, k.target), el("td", { style: "color:var(--hold)" }, k.red_flag)));
  return section("How you will know it works", el("div", { style: "overflow-x:auto" }, el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "What to track"), el("th", {}, "Aim for"), el("th", {}, "Red flag"))), body)),
    el("h3", {}, "When to stop"), list(a.stop_rules));
}

function assumptionsPanel(f) {
  const d = el("details", { class: "panel" }, el("summary", { style: "cursor:pointer;font-weight:650" }, "Numbers we assumed for you (" + f.assumptions.length + ")"));
  if (!f.assumptions.length) { d.append(el("p", { class: "hint", style: "margin-top:8px" }, "Everything came from you.")); return d; }
  const body = el("tbody");
  for (const a of f.assumptions) body.append(el("tr", {}, el("td", {}, FIELD[a.field] || a.field), el("td", { class: "n" }, String(a.value)), el("td", { class: "muted" }, a.basis)));
  d.append(el("p", { class: "hint", style: "margin:8px 0" }, "Change any of these under the form and run again."),
    el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Number"), el("th", { class: "n" }, "Used"), el("th", {}, "Where it comes from"))), body));
  return d;
}

function meterPanel(f) {
  const u = f.usage, t = u.total;
  const body = el("tbody");
  for (const [agent, s] of Object.entries(u.by_agent)) body.append(el("tr", {}, el("td", {}, agent), el("td", { class: "n" }, s.calls), el("td", { class: "n" }, num(s.input)), el("td", { class: "n" }, num(s.cached)), el("td", { class: "n" }, num(s.output)), el("td", { class: "n" }, (s.ms / 1000).toFixed(1) + " s")));
  body.append(el("tr", {}, el("td", {}, el("b", {}, "Total")), el("td", { class: "n" }, el("b", {}, t.calls)), el("td", { class: "n" }, el("b", {}, num(t.input))), el("td", { class: "n" }, el("b", {}, num(t.cached))), el("td", { class: "n" }, el("b", {}, num(t.output))), el("td", { class: "n" }, el("b", {}, u.wall_s + " s"))));
  const flags = [];
  for (const [who, fl] of Object.entries(f.flags)) {
    if (fl.cache_hit) flags.push(who + " reused a saved answer");
    if (fl.grounding_retries) flags.push(who + ": " + fl.grounding_retries + " grounding rewrite(s)");
    if (fl.fallback) flags.push(who + ": template used");
  }
  return el("details", { class: "panel meter" }, el("summary", { style: "cursor:pointer;font-weight:650" }, "Run meter: " + num(t.input + t.output) + " tokens · " + t.calls + " model calls"),
    el("p", { class: "hint", style: "margin:8px 0" }, f.measured ? "Measured from the model's own usage report. " : el("span", { class: "est" }, "Estimated (demo mode). "),
      "Run " + u.run_id + " · " + f.provider + " · " + f.model + " · mode " + u.mode + (flags.length ? " · " + flags.join(", ") : "")),
    el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Agent"), el("th", { class: "n" }, "Calls"), el("th", { class: "n" }, "Input tokens"), el("th", { class: "n" }, "of which cached"), el("th", { class: "n" }, "Output tokens"), el("th", { class: "n" }, "Time"))), body));
}

function downloadPlan(f) {
  const a = f.analysis, s = f.strategy, b = f.blueprint, ec = a.economics, plan = a.plan;
  const L = [`# Loyalty plan for ${f.profile.name}`, "", `**Verdict: ${VERDICT[a.verdict.code]}.** ${s.headline}`, "", s.summary, "", "## Why", ...s.reasons.map((x) => "- " + x),
    "", "## Watch out for", ...s.risks.map((x) => "- " + x)];
  if (s.alternatives.length) L.push("", "## Try instead, or first", ...s.alternatives.map((x) => "- " + x));
  L.push("", `## Program: ${b.program_name}`, b.one_line_pitch, "", "### How it works", ...plan.how_it_works.map((x) => "- " + x), "", "### Rules", ...plan.rules.map((x) => "- " + x),
    "", "### Say to customers", "> " + b.customer_pitch, "", "### Staff briefing", "> " + b.staff_script, "", "### Tailored tips", ...b.tailoring_tips.map((x) => "- " + x),
    "", "## Numbers", "| | Pessimistic | Expected | Optimistic |", "|---|---|---|---|");
  for (const [k, lab] of [["members", "Members"], ["extra_profit_month", "Extra profit a month"], ["reward_cost_month", "Reward cost a month"], ["net_month", "Result a month"], ["net_12_months", "Result over 12 months"]])
    L.push(`| ${lab} | ` + ["pessimistic", "expected", "optimistic"].map((x) => (k === "members" ? num(ec.scenarios[x][k]) : money(ec.scenarios[x][k]))).join(" | ") + " |");
  if (ec.break_even_lift_pct !== null) L.push("", `Break-even: members must spend ${pct(ec.break_even_lift_pct, 2)} more than before.`);
  L.push("", "## 12-week launch plan", ...b.launch_plan.map((x) => `- **${x.when}:** ${x.action}`), "", "## How you will know it works",
    ...a.kpis.map((k) => `- **${k.name}:** aim for ${k.target}. Red flag: ${k.red_flag}. (${k.how})`), "", "## When to stop", ...a.stop_rules.map((x) => "- " + x),
    "", "## Assumptions", ...f.assumptions.map((x) => `- ${FIELD[x.field] || x.field} = ${x.value}: ${x.basis}`), "", "_Decision support, not financial advice. The lift figures are planning assumptions until your pilot replaces them._");
  const url = URL.createObjectURL(new Blob([L.join("\n")], { type: "text/markdown" }));
  const link = el("a", { href: url, download: "loyalty-plan.md" });
  document.body.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
}
