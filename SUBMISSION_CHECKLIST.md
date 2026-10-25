# What is left for you before Monday 6 PM

The code, tests and report builder are done. The rubric gives full credit only for **evidence from your real app**, which needs your key and a real person.

1. [ ] Put your key in `.env`. Run `python run.py` and click all four examples once.
2. [ ] Fill the three prices in `pricing.json` (course pricing page). Do not guess.
3. [ ] `python evals/run_evals.py --injection`  (about 24 real runs plus 10 attacks; saves `evals/results.json`)
4. [ ] `pip install playwright && playwright install chromium`, then `python scripts/capture_evidence.py`
5. [ ] `cp logs/usage.jsonl evidence/usage_log.jsonl`, then `python scripts/tokenomics.py`
6. [ ] **Real user (worth the most points):** ask one real shop owner (family, neighbour) to try it for 15 minutes. Also time yourself or them doing the same decision in a spreadsheet. Save `evidence/impact.json`:
   ```json
   {"user": "Aunt Meena, runs a bakery", "quote": "...", "manual_minutes": 40, "app_minutes": 5, "what_changed": "..."}
   ```
7. [ ] Edit the three TODO lines at the top of `report/build_report.py` (your name, repo URL, app URL).
8. [ ] `python report/build_report.py`, open `report.html` and `slides.html`, search for the yellow "TODO" boxes. Every one must be gone or removed.
9. [ ] Verify the competitor comparison in section 3 yourself (open each product's site and adjust the table to what you see).
10. [ ] Dry run: clone into a new folder, put `.env` one folder up, follow the README, use the app.
11. [ ] Submit on Canvas: repo link, `report.html`, `slides.html` (and an optional 2 to 3 minute video).
