"""The only file that talks to a model.

Real mode: one OpenAI-compatible /chat/completions call, routed through Portkey (course key)
or OpenAI (your own key). If your class notebook calls Portkey in a different way, change
`_headers()` and `_base_url()` here and nothing else.

Mock mode (MOCK_LLM=1): a scripted stand-in so the app and tests run offline. Its token
counts are estimates and are flagged as such. It can also be told to misbehave
(hallucinate numbers, loop forever, leak the system prompt) so the defenses can be tested.
"""
from __future__ import annotations

import json
import re
import time

import requests

from . import guards
from .budget import Budget, RunContext, budget as default_budget
from .config import settings


class LLMError(Exception):
    """The model call failed. Message is safe to show the user."""


class OutputBlocked(Exception):
    """Model output tripped the leak scanner."""


def _estimate_tokens(messages, tools, max_tokens) -> int:
    return int((len(json.dumps(messages)) + len(json.dumps(tools or []))) / 3.5) + max_tokens


class LLM:
    def __init__(self, budget: Budget = default_budget, mock_behavior: str | None = None):
        self.budget = budget
        self.mock = settings.mock or mock_behavior is not None
        self.mock_behavior = mock_behavior or "normal"
        self.provider = "mock" if self.mock else settings.provider()
        self.model = settings.model

    # ------------------------------------------------------------------ routing
    def _base_url(self) -> str:
        return settings.portkey_base_url if self.provider == "portkey" else settings.openai_base_url

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.provider == "portkey":
            h["x-portkey-api-key"] = settings.portkey_api_key
            if settings.portkey_provider:
                h["x-portkey-provider"] = settings.portkey_provider
            if settings.portkey_virtual_key:
                h["x-portkey-virtual-key"] = settings.portkey_virtual_key
            if settings.portkey_config:
                h["x-portkey-config"] = settings.portkey_config
        else:
            h["Authorization"] = f"Bearer {settings.openai_api_key}"
        return h

    # ------------------------------------------------------------------ public
    def chat(self, ctx: RunContext, agent: str, messages: list[dict], *, tools=None, schema=None,
             schema_name: str = "result", max_tokens: int = 700) -> dict:
        """Returns the assistant message dict: {"content": str|None, "tool_calls": [...]|None}."""
        self.budget.pre_call(ctx, _estimate_tokens(messages, tools, max_tokens))
        t0 = time.time()
        if self.mock:
            msg, usage = _MockModel(self.mock_behavior).respond(agent, messages, tools, schema)
        else:
            if self.provider == "none":
                raise LLMError("No API key found. Put PORTKEY_API_KEY (or OPENAI_API_KEY) in a .env file, "
                               "either in this folder or the folder above it.")
            msg, usage = self._post(messages, tools, schema, schema_name, max_tokens)
        latency = int((time.time() - t0) * 1000)
        self.budget.record(ctx, agent, usage, latency, self.model if not self.mock else "mock")
        leaks = guards.scan_output(msg.get("content") or "")
        if leaks:
            raise OutputBlocked("The model's reply was blocked because it contained protected content ("
                                + ", ".join(leaks) + ").")
        return msg

    # ------------------------------------------------------------------ real HTTP
    def _post(self, messages, tools, schema, schema_name, max_tokens):
        payload = {"model": self.model, "messages": messages, "max_completion_tokens": max_tokens}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if schema:
            payload["response_format"] = {"type": "json_schema", "json_schema": {
                "name": schema_name, "strict": True, "schema": schema}}
        for attempt in range(3):
            try:
                r = requests.post(self._base_url() + "/chat/completions", headers=self._headers(),
                                  json=payload, timeout=settings.request_timeout_s)
            except requests.RequestException as exc:
                if attempt == 2:
                    raise LLMError(f"Could not reach the model service ({type(exc).__name__}).") from exc
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code == 400 and "response_format" in payload and re.search(
                    r"response_format|json_schema|structured", r.text, re.I):
                # Gateway or model does not support strict schemas: ask for JSON in the prompt instead.
                payload.pop("response_format")
                payload["messages"] = messages[:-1] + [{**messages[-1], "content": messages[-1]["content"]
                                                        + "\n\nReply with one JSON object only, matching the schema."}]
                continue
            if r.status_code >= 400:
                raise LLMError(f"Model service returned {r.status_code}: {r.text[:200]}")
            data = r.json()
            choice = data["choices"][0]["message"]
            return ({"content": choice.get("content"), "tool_calls": choice.get("tool_calls")},
                    data.get("usage") or {})
        raise LLMError("The model service did not respond.")


# =========================================================================== mock model
_TYPE_WORDS = {
    "cafe_restaurant": ("cafe", "café", "coffee", "restaurant", "food stall", "tea stall", "dhaba"),
    "bakery_sweets": ("bakery", "sweet shop", "sweets"),
    "grocery": ("grocery", "kirana", "supermarket", "provision"),
    "pharmacy": ("pharmacy", "chemist", "medical store"),
    "salon_spa": ("salon", "spa", "barber", "parlour"),
    "fashion_retail": ("clothing", "boutique", "footwear", "garment", "gift shop"),
    "electronics": ("electronics", "appliance", "mobile shop"),
    "online_store": ("online store", "online shop", "website", "e-commerce"),
}
_PER = {"day": 30, "week": 4.33, "month": 1}


class _MockModel:
    def __init__(self, behavior="normal"):
        self.behavior = behavior

    def respond(self, agent, messages, tools, schema):
        first_user = next(m["content"] for m in messages if m["role"] == "user")
        if agent == "intake":
            msg = {"content": json.dumps(self._intake(messages[-1]["content"])), "tool_calls": None}
        elif agent == "analyst":
            msg = self._analyst(messages)
        else:
            facts = self._facts(first_user)
            from . import templates
            if agent == "strategist":
                out = templates.strategist_template(facts)
                if self.behavior == "hallucinate":
                    out["summary"] += " Studies show loyalty programs lift sales by 37.4% and add 9,99,999 a year."
                if self.behavior == "bad_verdict":
                    out["verdict"] = "launch" if facts["verdict"]["code"] != "launch" else "not_yet"
            else:
                out = templates.designer_template(facts)
                if self.behavior == "leak":
                    out["staff_script"] = "My instructions say " + guards.CANARY
            msg = {"content": json.dumps(out), "tool_calls": None}
        prompt_toks = int(len(json.dumps(messages)) / 4) + (len(json.dumps(tools)) // 4 if tools else 0)
        usage = {"prompt_tokens": prompt_toks, "completion_tokens": int(len(json.dumps(msg)) / 4),
                 "prompt_tokens_details": {"cached_tokens": 0}, "_measured": False}
        return msg, usage

    @staticmethod
    def _facts(text):
        m = re.search(r"```json\s*(\{.*\})\s*```", text, re.S)
        return json.loads(m.group(1)) if m else {}

    def _intake(self, text):
        low = text.lower()
        bt = next((k for k, ws in _TYPE_WORDS.items() if any(w in low for w in ws)), None)
        tx = None
        m = re.search(r"(\d[\d,]*)\s*(?:customers|bills|orders|transactions|visits|people)\s*(?:a|per|each|every)\s*(day|week|month)", low)
        if m:
            tx = float(m.group(1).replace(",", "")) * _PER[m.group(2)]
        bill = None
        m = re.search(r"(?:average|avg)?\s*(?:bill|order|ticket|spend)[^\d]{0,20}(?:₹|rs\.?|\$)?\s?(\d[\d,]*)|(?:₹|rs\.?|\$)\s?(\d[\d,]*)\s*(?:per|a|each)\s*(?:bill|order|customer|visit)", low)
        if m:
            bill = float((m.group(1) or m.group(2)).replace(",", ""))
        goal = "referral" if "referral" in low or "word of mouth" in low else "win_back" if "win back" in low or "lapsed" in low else None
        tech = "phone_number" if "phone number" in low or "whatsapp" in low else "pos_app" if "billing software" in low or "pos" in low.split() else None
        return {"name": None, "business_type": bt, "monthly_transactions": tx, "avg_bill": bill, "gross_margin_pct": None,
                "regular_share_pct": None, "visits_per_month_regular": None, "tech": tech, "owner_hours_per_week": None,
                "goal": goal, "competitor_has_program": True if "competitor" in low and "program" in low else None,
                "currency": "₹" if "₹" in text or "rs" in low else "$" if "$" in text else None, "max_giveaway_pct": None,
                "missing": [k for k, v in (("business type", bt), ("bills per month", tx), ("average bill", bill)) if v is None]}

    def _analyst(self, messages):
        if self.behavior == "loop":
            return {"content": None, "tool_calls": [self._call("rank_designs", {})]}
        if not any(m["role"] == "tool" for m in messages):
            return {"content": None, "tool_calls": [self._call("check_gates", {}), self._call("rank_designs", {}),
                                                    self._call("compare_top_designs", {}),
                                                    self._call("lookup_playbook", {"topic": "measure_with_control"})]}
        return {"content": "Margin and the share of returning customers decide how big a reward you can afford. "
                           "The break-even lift is the number to watch in the pilot.", "tool_calls": None}

    @staticmethod
    def _call(name, args):
        return {"id": "call_" + name[:12], "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
