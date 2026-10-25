"""Safety guards. Everything here is plain code: cheap, testable, and not fooled by clever prompts.

1. Input guard      - length cap, control-character strip, prompt-injection patterns.
2. Output guard     - canary + secret scan so a leaked system prompt or key never reaches the user.
3. Grounding guard  - every figure in the memo must come from a tool result, the profile or the
                      whitepaper playbook. Invented numbers are caught here.
4. Schema guard     - memo must have the right shape, lengths and the engine's verdict.
"""
from __future__ import annotations

import json
import re
import secrets
import unicodedata
from dataclasses import dataclass, field

from .config import settings

# A random marker placed in every system prompt. If it ever shows up in model output,
# the prompt leaked and the output is blocked.
CANARY = "CANARY-" + secrets.token_hex(6)


# --------------------------------------------------------------------------- input guard
INJECTION_PATTERNS = [
    (r"ignore (all |any |the |your )?(previous|prior|above|earlier|preceding) (instructions?|rules?|prompts?|messages?)", "override_instructions"),
    (r"disregard (all |any |the |your )?(previous|prior|above|earlier|system|safety)", "override_instructions"),
    (r"forget (all |everything |your )?(previous|prior|above|earlier|instructions?|rules?)", "override_instructions"),
    (r"(reveal|show|print|repeat|output|leak|display|tell me|give me)( me)? (your|the) (system|hidden|initial|developer|secret) (prompt|instructions?|message|rules)", "prompt_leak"),
    (r"what (is|are) your (system|initial|hidden) (prompt|instructions?)", "prompt_leak"),
    (r"you are now |act as (a|an|the) |pretend (to be|you are)|new (role|persona|instructions?) ?:", "role_change"),
    (r"(api[ _-]?key|portkey|openai_api|secret key|\.env\b|password|credentials)", "secret_request"),
    (r"(other|all|every|another) (merchants?|outlets?|concessionaires?|customers?|users?|shops?)('s)? (data|sales|revenue|numbers|records|details|figures)", "data_exfiltration"),
    (r"(data|sales|revenue|numbers|records|figures|details|information|performance)( numbers)? (of|for|from|about) (all |every |the |any )?(other|another) (merchants?|outlets?|concessionaires?|shops?|customers?|users?|stores?)", "data_exfiltration"),
    (r"</?(system|assistant|developer|tool)>|\[/?(system|inst)\]|#{2,}\s*(system|instructions?)", "fake_role_tag"),
    (r"jailbreak|dan mode|developer mode", "jailbreak"),
    (r"(set|change|mark|make|force|output|return) (the )?verdict (to|as|=)|always (say|answer|return|output|respond) .{0,20}(cleared|join|approve|launch|go ahead)", "verdict_manipulation"),
]
_COMPILED = [(re.compile(p, re.I), label) for p, label in INJECTION_PATTERNS]
_SQUASHED_KEYS = ("ignoreprevious", "ignoreallprevious", "ignoreyourinstructions", "ignoreabove", "ignoreinstructions",
                  "disregardprevious", "forgetprevious", "revealyoursystemprompt", "showyoursystemprompt",
                  "systemprompt", "apikey", "developermode", "jailbreak")
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff"), None)


@dataclass
class InputCheck:
    ok: bool
    text: str
    reasons: list = field(default_factory=list)


def check_user_text(text: str | None) -> InputCheck:
    """Clean the free-text field and decide whether it may reach a model at all."""
    if not text:
        return InputCheck(True, "")
    raw = unicodedata.normalize("NFKC", str(text)).translate(_ZERO_WIDTH)
    raw = "".join(ch for ch in raw if ch in "\n\t" or unicodedata.category(ch)[0] != "C")
    reasons = []
    if len(raw) > settings.max_input_chars:
        reasons.append("too_long")
        raw = raw[: settings.max_input_chars]
    flat = re.sub(r"\s+", " ", raw)
    for rx, label in _COMPILED:
        if rx.search(flat) and label not in reasons:
            reasons.append(label)
    # Letter-spaced or punctuated text ("i g n o r e", "i-g-n-o-r-e") dodges the patterns above.
    # When that signal is present, also look for key attack phrases in a letters-only copy.
    if re.search(r"\b(?:\w[ .\-_*]){4,}\w\b", flat):
        squashed = re.sub(r"[^a-z]", "", flat.lower())
        if any(k in squashed for k in _SQUASHED_KEYS) and "obfuscated_override" not in reasons:
            reasons.append("obfuscated_override")
    blocking = [r for r in reasons if r != "too_long"]
    return InputCheck(ok=not blocking, text=raw.strip(), reasons=reasons)


def explain_block(reasons: list[str]) -> str:
    return ("This text looks like an attempt to change the assistant's instructions or reach data that is not "
            "yours (" + ", ".join(r for r in reasons if r != "too_long") + "). It was not sent to the AI model. "
            "Describe your outlet in plain words, or fill in the fields below, and try again.")


# --------------------------------------------------------------------------- output guard
_KEY_LIKE = re.compile(r"(sk-[A-Za-z0-9_\-]{16,}|pk-[A-Za-z0-9_\-]{16,}|Bearer\s+[A-Za-z0-9._\-]{20,})")


def scan_output(text: str) -> list[str]:
    """Return a list of leak findings in model output (empty = clean)."""
    leaks = []
    if CANARY in text:
        leaks.append("system_prompt_marker")
    if _KEY_LIKE.search(text):
        leaks.append("key_like_string")
    for secret in (settings.portkey_api_key, settings.openai_api_key):
        if secret and len(secret) > 8 and secret in text:
            leaks.append("api_key")
    return leaks


# --------------------------------------------------------------------------- grounding guard
_NUM = re.compile(
    r"(?P<cur>₹|Rs\.?\s?|INR\s?|\$|£|€)?(?P<num>\d[\d,]*(?:\.\d+)?)(?P<suf>\s?(?:%|percent|lakhs?|crores?|cr\b|k\b))?",
    re.I,
)
_SUFFIX_FACTOR = {"lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7, "cr": 1e7, "k": 1e3}


def _numbers_in(obj) -> set[float]:
    """All numbers anywhere in a JSON-like object or string."""
    out: set[float] = set()
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        out.add(abs(float(obj)))
    elif isinstance(obj, str):
        for m in _NUM.finditer(obj):
            try:
                out.add(float(m.group("num").replace(",", "")))
            except ValueError:
                pass
    elif isinstance(obj, dict):
        for v in obj.values():
            out |= _numbers_in(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out |= _numbers_in(v)
    return out


def allowed_numbers(*sources) -> set[float]:
    allowed: set[float] = {0.0, 100.0, 12.0, 3.0}
    for s in sources:
        allowed |= _numbers_in(s)
    return allowed


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.06, 0.01 * max(abs(a), abs(b)))


def find_ungrounded(memo_text: str, allowed: set[float]) -> list[str]:
    """Figures in the memo that appear nowhere in the facts. Small plain integers are ignored."""
    bad = []
    for m in _NUM.finditer(memo_text):
        raw = m.group("num")
        value = float(raw.replace(",", ""))
        suf = (m.group("suf") or "").strip().lower()
        is_pct = suf in ("%", "percent")
        has_cur = bool(m.group("cur"))
        has_dec = "." in raw
        if not (is_pct or has_cur or has_dec or value >= 100 or suf):
            continue  # "3 reasons", "12 months": not a claim about the numbers
        candidates = [value]
        key = suf.rstrip(".")
        if key in _SUFFIX_FACTOR:
            candidates.append(value * _SUFFIX_FACTOR[key])
        if not any(_close(c, a) for c in candidates for a in allowed):
            bad.append(m.group(0).strip())
    return bad


# --------------------------------------------------------------------------- schema guard
def all_text(obj) -> str:
    """Every string inside a nested JSON-like object, joined. Used for the grounding check."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return "\n".join(all_text(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return "\n".join(all_text(v) for v in obj)
    return ""


def check_schema(obj, *, keys, lists=None, texts=None, verdict_code=None, item_keys=None) -> list[str]:
    """Shape, size and verdict checks for a model-written object. Returns a list of problems."""
    if not isinstance(obj, dict):
        return ["reply is not a JSON object"]
    problems = [f"missing {k}" for k in keys if k not in obj]
    if problems:
        return problems
    if verdict_code is not None and obj.get("verdict") != verdict_code:
        problems.append(f"verdict '{obj.get('verdict')}' does not match the engine ('{verdict_code}')")
    for k, (lo, hi) in (lists or {}).items():
        v = obj[k]
        if not isinstance(v, list):
            problems.append(f"{k} must be a list")
            continue
        if not lo <= len(v) <= hi:
            problems.append(f"{k} must have {lo}-{hi} items")
        ik = (item_keys or {}).get(k)
        for x in v:
            if ik and not (isinstance(x, dict) and all(isinstance(x.get(i), str) for i in ik)):
                problems.append(f"{k} items need text fields {ik}")
                break
            if not ik and not isinstance(x, str):
                problems.append(f"{k} must be a list of strings")
                break
    for k, limit in (texts or {}).items():
        if not isinstance(obj[k], str) or len(obj[k]) > limit:
            problems.append(f"{k} must be text of at most {limit} characters")
    return problems


def parse_json_loose(text: str):
    """Parse JSON that may be wrapped in a code fence or prose."""
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            return json.loads(text[start:end + 1])
        raise
