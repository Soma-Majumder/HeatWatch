"""Minimal input guard. Issue #15 owns hardening this (injection test suite, more rules).

Two jobs: clean tenant text before it reaches the model, and accept only
well-formed field values from the model.
"""
import re

MAX_CHARS = 1000
MAX_HOURS = 24 * 30
SCOPES = ("building", "apartment")
PROBLEMS = ("heat", "hot_water", "both")
LANGS = ("en", "es")

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE = re.compile(r"\s+")
_SAFETY = re.compile(
    r"(smell(s|ed|ing)?\s+(of\s+|like\s+)?gas|gas\s+(smell|leak|odor|odour)|carbon\s+monoxide"
    r"|\bco\s+(alarm|detector))", re.I)


def sanitize_text(text: str | None) -> str:
    if not text:
        return ""
    text = _CONTROL.sub("", str(text))
    return _SPACE.sub(" ", text).strip()[:MAX_CHARS]


def detect_safety(text: str) -> bool:
    """Deterministic backstop: a gas smell must never depend on the model noticing it."""
    return bool(_SAFETY.search(text or ""))


_NUM_WORDS = (r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|"
              r"thirty|forty|forty-eight|an?|half\s+a")
_UNITS = r"(?:hours?|hrs?|h|days?|weeks?)"
_EXPLICIT_DURATION = re.compile(
    rf"(?:\b\d+(?:\.\d+)?\s*{_UNITS}\b|\b(?:{_NUM_WORDS})\s+{_UNITS}\b)", re.I)


def has_explicit_duration(text: str) -> bool:
    """True only if the tenant gave a number plus a unit, like '10 hours' or 'two days'.

    Vague phrases ('since last night', 'yesterday') do not count, so the agent asks.
    """
    return bool(_EXPLICIT_DURATION.search(text or ""))


def validate_fields(raw) -> dict:
    """Keep only known fields with valid values. Everything else is dropped silently."""
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    addr = raw.get("address")
    if isinstance(addr, str):
        addr = sanitize_text(addr)[:200]
        if len(addr) >= 3:
            out["address"] = addr
    z = raw.get("zip")
    if isinstance(z, str) and re.fullmatch(r"\d{5}", z.strip()):
        out["zip"] = z.strip()
    for key, allowed in (("scope", SCOPES), ("problem", PROBLEMS), ("lang", LANGS)):
        v = raw.get(key)
        if isinstance(v, str) and v.strip().lower() in allowed:
            out[key] = v.strip().lower()
    d = raw.get("duration_hours")
    if isinstance(d, (int, float)) and not isinstance(d, bool) and 0 <= d <= MAX_HOURS:
        out["duration_hours"] = float(d)
    for key in ("vulnerable", "safety_flag"):
        if isinstance(raw.get(key), bool):
            out[key] = raw[key]
    return out
