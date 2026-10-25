# Loyalty Advisor

**Should your business run a loyalty program, and if so, exactly which one?**
An AI agent app for small business owners (cafe, kirana store, salon, boutique, online shop). You describe your business in plain words. It answers honestly: *launch it*, *pilot it first*, or *not yet*. Then it designs the program: type, earn and reward numbers, rules, staff script, KPIs, red flags and a 12-week launch plan.

Live link (if hosted): _add here_

## Run it (about 3 minutes)

Needs Python 3.10 or newer.

```bash
git clone <this repo> loyalty-advisor
cd loyalty-advisor
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then put your key in .env
python run.py
```

Open http://localhost:8000.

**API key:** put `PORTKEY_API_KEY=...` (course key, model `gpt-5.6-luna`) or `OPENAI_API_KEY=...` in `.env`. The app looks for `.env` first in this folder, then in the folder above it. No key yet? `MOCK_LLM=1 python run.py` runs an offline demo (a banner says so, and its token counts are estimates).

If your Portkey setup needs a provider, virtual key or config, set the optional `PORTKEY_*` lines in `.env.example`. All model HTTP code is in `app/llm.py`.

## Try it
Click an example chip (Cafe, Grocery store, Salon, Phone shop) and press **Check my business**. The examples use US dollars by default and give four different answers.

## How it works
```
text -> Guard (code) -> Intake (AI) -> Engine (code) -> Analyst (AI + tools) -> Strategist (AI) -> Designer (AI) -> grounding check (code) -> UI
```
* **Engine (`app/engine.py`)** does all maths: readiness checks, design scoring, reward sizing, three scenarios, break-even lift. The AI never calculates.
* **Intake** turns free text into numbers. **Analyst** picks extra checks with read-only tools. **Strategist** answers "should I?". **Designer** writes scripts and the launch plan.
* **Guard** blocks prompt injection, caps spending, and rejects any figure in AI text that is not in the verified facts. If the AI fails twice, a plain template built from verified numbers is shown.

The core idea: a loyalty program pays only if the *extra* profit from changed behaviour beats *all* rewards given. The app sizes rewards to what your margin can afford and shows the break-even lift.

## Tests and evidence
```bash
python -m unittest discover tests -v          # 40 tests, no key needed
python evals/run_evals.py --injection         # real model: Intake accuracy, agentic vs lean cost, attack set
python scripts/tokenomics.py                  # token and cost figures from real runs (fill pricing.json first)
python scripts/capture_evidence.py            # screenshots of real runs into evidence/
python report/build_report.py                 # builds report.html and slides.html
```

## Files
| Path | What |
|---|---|
| `app/engine.py` | deterministic loyalty maths |
| `app/agents.py`, `app/tools.py`, `app/pipeline.py` | agents, tools, orchestration |
| `app/guards.py`, `app/budget.py` | injection, grounding, token and rate limits |
| `app/templates.py` | safe fallbacks |
| `data/benchmarks.json`, `data/playbook.json` | defaults (each with its basis) and practical principles |
| `static/` | web UI |
| `tests/`, `evals/`, `scripts/`, `report/` | tests, measurements, evidence, report builder |

## Honest limits
Lift figures (how much more members spend) are **planning assumptions**, not measurements; the app says so and the 12-week pilot replaces them. Defaults come from `data/benchmarks.json`. This is decision support, not financial advice.
