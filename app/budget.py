"""Overspending defence: per-run, per-session and global token caps plus a rate limit.

Every LLM call goes through Budget, so a bug (infinite loop) or a bad actor
(scripted requests) hits a hard ceiling long before it burns the token budget.
Every call is also appended to logs/usage.jsonl: that file is the evidence
behind the tokenomics section of the report.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .config import ROOT, settings

LOG_PATH = ROOT / "logs" / "usage.jsonl"


class BudgetExceeded(Exception):
    """A spending or rate limit stopped the request. Message is safe to show the user."""


@dataclass
class RunContext:
    run_id: str
    session_id: str
    mode: str
    started: float = field(default_factory=time.time)
    calls: list = field(default_factory=list)
    tokens: int = 0

    def elapsed(self) -> float:
        return time.time() - self.started

    def summary(self) -> dict:
        by_agent: dict[str, dict] = {}
        for c in self.calls:
            a = by_agent.setdefault(c["agent"], {"calls": 0, "input": 0, "cached": 0, "output": 0, "ms": 0})
            a["calls"] += 1
            a["input"] += c["input_tokens"]
            a["cached"] += c["cached_tokens"]
            a["output"] += c["output_tokens"]
            a["ms"] += c["latency_ms"]
        tot = {k: sum(a[k] for a in by_agent.values()) for k in ("calls", "input", "cached", "output", "ms")}
        return {"run_id": self.run_id, "mode": self.mode, "by_agent": by_agent, "total": tot,
                "wall_s": round(self.elapsed(), 2)}


class Budget:
    def __init__(self, log_path: Path = LOG_PATH):
        self._lock = threading.Lock()
        self._day = date.today()
        self._global = 0
        self._session: dict[str, int] = {}
        self._starts: dict[str, list[float]] = {}
        self.log_path = log_path

    # ------------------------------------------------------------------ helpers
    def _roll_day(self):
        if date.today() != self._day:
            self._day, self._global, self._session = date.today(), 0, {}

    def remaining(self, session_id: str) -> dict:
        with self._lock:
            self._roll_day()
            return {
                "session_tokens_left": max(0, settings.max_tokens_per_session_day - self._session.get(session_id, 0)),
                "global_tokens_left": max(0, settings.max_tokens_global_day - self._global),
                "per_run_cap": settings.max_tokens_per_run,
            }

    # ------------------------------------------------------------------ run lifecycle
    def start_run(self, session_id: str, mode: str) -> RunContext:
        with self._lock:
            self._roll_day()
            now = time.time()
            recent = [t for t in self._starts.get(session_id, []) if now - t < 60]
            if len(recent) >= settings.max_runs_per_minute:
                raise BudgetExceeded("Too many requests. Wait a minute and try again.")
            if self._session.get(session_id, 0) >= settings.max_tokens_per_session_day:
                raise BudgetExceeded("You have used today's token allowance for this session. Try again tomorrow.")
            if self._global >= settings.max_tokens_global_day:
                raise BudgetExceeded("The app's daily token budget is used up. Try again tomorrow.")
            recent.append(now)
            self._starts[session_id] = recent
        return RunContext(run_id=uuid.uuid4().hex[:10], session_id=session_id, mode=mode)

    def pre_call(self, ctx: RunContext, est_tokens: int) -> None:
        """Called before every model call. Raises if this call could break a limit."""
        if len(ctx.calls) >= settings.max_llm_calls_per_run:
            raise BudgetExceeded("Stopped: this request made too many model calls.")
        if ctx.elapsed() > settings.run_timeout_s:
            raise BudgetExceeded("Stopped: this request took too long.")
        if ctx.tokens + est_tokens > settings.max_tokens_per_run:
            raise BudgetExceeded("Stopped: this request would use more tokens than the per-request limit.")
        with self._lock:
            self._roll_day()
            if self._global + est_tokens > settings.max_tokens_global_day:
                raise BudgetExceeded("The app's daily token budget is used up. Try again tomorrow.")
            if self._session.get(ctx.session_id, 0) + est_tokens > settings.max_tokens_per_session_day:
                raise BudgetExceeded("You have used today's token allowance for this session.")

    def record(self, ctx: RunContext, agent: str, usage: dict, latency_ms: int, model: str,
               cache_hit: bool = False) -> dict:
        details = usage.get("prompt_tokens_details") or {}
        row = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "run_id": ctx.run_id, "mode": ctx.mode, "agent": agent, "model": model,
            "input_tokens": int(usage.get("prompt_tokens", 0)),
            "cached_tokens": int(details.get("cached_tokens", 0) or 0),
            "output_tokens": int(usage.get("completion_tokens", 0)),
            "latency_ms": latency_ms, "cache_hit": cache_hit,
            "measured": bool(usage.get("_measured", True)),
        }
        total = row["input_tokens"] + row["output_tokens"]
        ctx.calls.append(row)
        ctx.tokens += total
        with self._lock:
            self._roll_day()
            self._global += total
            self._session[ctx.session_id] = self._session.get(ctx.session_id, 0) + total
            try:
                self.log_path.parent.mkdir(parents=True, exist_ok=True)
                with self.log_path.open("a") as fh:
                    fh.write(json.dumps(row) + "\n")
            except OSError:
                pass  # logging must never crash the app
        return row


budget = Budget()
