"""Build address_stats and priors from the cached HPD complaints.

Prior keys are "scope|month|hour_bucket"; coarser fallbacks use "*":
  building|01|night -> building|01|* -> building|*|* -> *|*|*
"""
from datetime import datetime

from .address import normalize_address
from .config import get_settings

MIN_N = 30            # minimum sample for a prior to be trusted
SCOPE = {"ENTIRE BUILDING": "building", "APARTMENT ONLY": "apartment"}


def hour_bucket(hour: int) -> str:
    if hour >= 22 or hour < 6:
        return "night"
    if hour < 12:
        return "morning"
    if hour < 18:
        return "afternoon"
    return "evening"


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s[:19])


def percentile(sorted_vals: list[float], p: float) -> float | None:
    if not sorted_vals:
        return None
    k = (len(sorted_vals) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (k - lo)


def is_duplicate(resolution: str | None) -> bool:
    return bool(resolution) and "duplicate of a building-wide" in resolution.lower()


def backfill_address_norm(conn) -> int:
    rows = conn.execute(
        "SELECT unique_key, incident_address FROM hpd_complaints WHERE address_norm IS NULL"
    ).fetchall()
    with conn:
        conn.executemany(
            "UPDATE hpd_complaints SET address_norm=? WHERE unique_key=?",
            [(normalize_address(r["incident_address"]), r["unique_key"]) for r in rows],
        )
    return len(rows)


def build_address_stats(conn, threshold: int | None = None) -> int:
    """Flag repeat offenders: addresses with at least `threshold` complaints in the window.

    Defaults to Settings.repeat_min (200). Counts come from the cached 2-year window.
    """
    threshold = get_settings().repeat_min if threshold is None else threshold
    backfill_address_norm(conn)
    rows = conn.execute(
        "SELECT address_norm, COUNT(*) n, MAX(created_date) last FROM hpd_complaints"
        " WHERE address_norm != '' GROUP BY address_norm"
    ).fetchall()
    with conn:
        conn.execute("DELETE FROM address_stats")
        conn.executemany(
            "INSERT INTO address_stats(address_norm, complaints_2y, last_complaint_at, repeat_flag)"
            " VALUES (?,?,?,?)",
            [(r["address_norm"], r["n"], r["last"], int(r["n"] >= threshold)) for r in rows],
        )
    return len(rows)


def build_priors(conn) -> int:
    groups: dict[str, dict] = {}
    for r in conn.execute(
        "SELECT created_date, closed_date, descriptor, resolution_description FROM hpd_complaints"
    ):
        scope = SCOPE.get((r["descriptor"] or "").upper())
        if not scope:
            continue
        created = parse_ts(r["created_date"])
        close_h = None
        if r["closed_date"]:
            close_h = (parse_ts(r["closed_date"]) - created).total_seconds() / 3600
            if close_h < 0:
                close_h = None
        dup = is_duplicate(r["resolution_description"])
        month = f"{created.month:02d}"
        bucket = hour_bucket(created.hour)
        for key in (f"{scope}|{month}|{bucket}", f"{scope}|{month}|*", f"{scope}|*|*", "*|*|*"):
            g = groups.setdefault(key, {"n": 0, "close": [], "dup": 0})
            g["n"] += 1
            g["dup"] += int(dup)
            if close_h is not None:
                g["close"].append(close_h)
    out = []
    for key, g in groups.items():
        c = sorted(g["close"])
        out.append((key, g["n"], percentile(c, 0.5), percentile(c, 0.75), percentile(c, 0.9),
                    g["dup"] / g["n"]))
    with conn:
        conn.execute("DELETE FROM priors")
        conn.executemany(
            "INSERT INTO priors(key,n,p50_close_h,p75_close_h,p90_close_h,dup_rate) VALUES (?,?,?,?,?,?)",
            out,
        )
    return len(out)


def rebuild_all(conn, repeat_threshold: int | None = None) -> dict:
    return {"address_stats": build_address_stats(conn, repeat_threshold), "priors": build_priors(conn)}
