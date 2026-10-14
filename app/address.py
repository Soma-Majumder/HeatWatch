"""Address normalization so tenant input and 311 rows compare equal.

"516 West  156 Street", "516 W 156th St." and "516 WEST 156 STREET" all
normalize to "516 WEST 156 STREET".
"""
import re

_SUFFIX = {
    "ST": "STREET", "STR": "STREET", "AVE": "AVENUE", "AV": "AVENUE", "BLVD": "BOULEVARD",
    "RD": "ROAD", "DR": "DRIVE", "PL": "PLACE", "PKWY": "PARKWAY", "TER": "TERRACE",
    "TERR": "TERRACE", "LN": "LANE", "CT": "COURT", "HWY": "HIGHWAY", "SQ": "SQUARE",
    "PLZ": "PLAZA", "CIR": "CIRCLE",
}
_DIR = {"W": "WEST", "E": "EAST", "N": "NORTH", "S": "SOUTH"}
_ORDINAL = re.compile(r"^(\d+)(ST|ND|RD|TH)$")
_UNIT = re.compile(r"\b(APT|APARTMENT|UNIT|STE|SUITE|FL|FLOOR|RM|ROOM)\b.*$")


def normalize_address(raw: str | None) -> str:
    if not raw:
        return ""
    s = raw.upper().split(",")[0]
    s = re.sub(r"#.*$", "", s)
    s = _UNIT.sub("", s)
    s = re.sub(r"[.']", "", s)
    tokens = s.split()
    out = []
    for i, tok in enumerate(tokens):
        last = i == len(tokens) - 1
        m = _ORDINAL.match(tok)
        if m:
            tok = m.group(1)
        elif tok == "ST":
            tok = "STREET" if last else "SAINT"
        elif tok in _SUFFIX:
            tok = _SUFFIX[tok]
        elif tok in _DIR and not last:
            tok = _DIR[tok]
        out.append(tok)
    return " ".join(out)
