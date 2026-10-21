"""Minimal input guard. Issue #15 owns hardening this (injection test suite, more rules).

Two jobs: clean tenant text before it reaches the model, and accept only
well-formed field values from the model.
"""
import re
import unicodedata

MAX_CHARS = 1000
MAX_HOURS = 24 * 30
SCOPES = ("building", "apartment")
PROBLEMS = ("heat", "hot_water", "both")
LANGS = ("en", "es")

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE = re.compile(r"\s+")
_SAFETY = re.compile(
    r"(smell(s|ed|ing)?\s+(of\s+|like\s+)?gas|gas\s+(smell|leak|odor|odour)|carbon\s+monoxide"
    r"|\bco\s+(alarm|detector)"
    # Spanish: "huele a gas", "olor a gas", "fuga de gas", "monoxido de carbono"
    r"|(huele|huelo|huelen|olor)\s+(a|de)\s+gas|huelo\s+gas|(fuga|escape)\s+de\s+gas"
    r"|mon[o\u00f3]xido\s+de\s+carbono)", re.I)

# A report like "no gas smell" or "I don't smell gas" is the tenant answering "no", not
# raising an alarm. A negator only counts when it sits right before the match (at most two
# filler words between), so "no heat but I smell gas" still triggers. When in doubt, trigger.
_NEGATED = re.compile(
    r"\b(no|not|never|without|sin|ni|nunca|(do|does|did|have|has)n'?t|(do|does|did)\s+not)\s+"
    r"(?:(?:any|a|an|the|really|ever|even|one|hay|ning[u\u00fa]n|ninguna|un|una|el|la)\s+){0,2}$", re.I)

# Common single-character look-alikes from other scripts (Cyrillic, Greek) for the
# Latin letters the safety words above are built from -- not the full Unicode
# confusables table, just enough that "gаs" (Cyrillic а) still reads as "gas".
_CONFUSABLES = str.maketrans({
    "а": "a", "А": "A", "е": "e", "Е": "E", "о": "o", "О": "O", "р": "p", "Р": "P",
    "с": "c", "С": "C", "х": "x", "Х": "X", "у": "y", "У": "Y", "і": "i", "І": "I",
    "ѕ": "s", "Ѕ": "S", "к": "k", "К": "K", "м": "m", "М": "M", "н": "n", "Н": "H",
    "т": "t", "Т": "T", "В": "B",
    "α": "a", "Α": "A", "β": "b", "Β": "B", "ο": "o", "Ο": "O", "ρ": "p", "Ρ": "P",
    "κ": "k", "Κ": "K", "ν": "v", "Ν": "N", "υ": "y", "Υ": "Y", "χ": "x", "Χ": "X",
    "τ": "t", "Τ": "T", "ι": "i", "Ι": "I",
})


def _strip_invisible_formatting(text: str) -> str:
    """Unicode 'format' characters -- zero-width space/joiner, the byte-order mark,
    bidi overrides like right-to-left-override -- are invisible to a person reading
    the text but the model still sees them. They cost nothing to strip and buy
    nothing by being there, so they never reach the model."""
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def sanitize_text(text: str | None) -> str:
    if not text:
        return ""
    text = _CONTROL.sub("", str(text))
    text = _strip_invisible_formatting(text)
    return _SPACE.sub(" ", text).strip()[:MAX_CHARS]


def detect_safety(text: str) -> bool:
    """Deterministic backstop: a gas smell must never depend on the model noticing it.

    Normalizes look-alike characters first so this can't be evaded by swapping a
    visually identical Cyrillic or Greek letter into a trigger word -- the whole
    point of this check is that it doesn't depend on the model, so it shouldn't
    be easy to slip past with character tricks either.

    A negated mention ("no gas smell", "I don't smell gas", "sin olor a gas") does not
    count, but any un-negated mention anywhere in the text still does.
    """
    t = (text or "").translate(_CONFUSABLES).replace("\u2019", "'")
    return any(not _NEGATED.search(t[:m.start()]) for m in _SAFETY.finditer(t))


_NUM_WORDS = (r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|"
              r"thirty|forty|forty-eight|an?|half\s+a|"
              # Spanish (issue #16: intake must work in Spanish, not just the replies)
              r"uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|veinte|"
              r"treinta|cuarenta|cuarenta\s+y\s+ocho|un|una|media")
_UNITS = r"(?:hours?|hrs?|h|days?|weeks?|horas?|d[ií]as?|semanas?)"
_EXPLICIT_DURATION = re.compile(
    rf"(?:\b\d+(?:\.\d+)?\s*{_UNITS}\b|\b(?:{_NUM_WORDS})\s+{_UNITS}\b)", re.I)


_UNSURE = re.compile(
    r"(not\s+sure|unsure|don'?t\s+know|do\s+not\s+know|no\s+idea|dunno|can'?t\s+(say|tell)|"
    r"cannot\s+(say|tell)|not\s+certain|"
    r"no\s+s[eé]|no\s+estoy\s+segur[oa]|ni\s+idea|no\s+puedo\s+decir)", re.I)


def is_unsure(text: str) -> bool:
    """The tenant says they do not know; stop asking."""
    return bool(_UNSURE.search(text or ""))


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


_DELETE_EN = re.compile(
    r"(delete|remove|erase|wipe)\s+(all\s+)?(of\s+)?(my|the)\s+(info|information|data|details|address|ticket|record|report)"
    r"|(my|the)\s+(info|information|data|details|address|record)\s+(deleted|removed|erased)"
    r"|(please\s+)?forget\s+(me|about\s+me)", re.I)
_DELETE_ES = re.compile(
    r"(borr(a|e|en|ar)|elimin(a|e|en|ar)|quit(a|e|en|ar))\s+(todos?\s+)?(mis|mi|los|las)\s+"
    r"(datos|informaci[oó]n|direcci[oó]n|ticket|registro|reporte)"
    r"|(mis|mi)\s+(datos|informaci[oó]n|direcci[oó]n)\s+(borrad|eliminad)", re.I)


def detect_deletion_request(text: str) -> str | None:
    """Deterministic check, so a deletion request never depends on the model.
    Returns the language the request was made in ('en' or 'es'), or None."""
    if _DELETE_ES.search(text):
        return "es"
    if _DELETE_EN.search(text):
        return "en"
    return None
