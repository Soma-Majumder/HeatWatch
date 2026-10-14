"""Quoted ETA from priors, falling back to coarser keys when a cell is thin."""
from dataclasses import dataclass
from datetime import datetime

from .priors import MIN_N, hour_bucket


@dataclass
class Eta:
    p50_h: float
    p75_h: float
    p90_h: float
    n: int
    key: str            # which prior level answered
    text: str


def lookup_eta(conn, scope: str, when: datetime) -> Eta | None:
    month = f"{when.month:02d}"
    for key in (f"{scope}|{month}|{hour_bucket(when.hour)}", f"{scope}|{month}|*",
                f"{scope}|*|*", "*|*|*"):
        r = conn.execute("SELECT * FROM priors WHERE key=? AND n>=? AND p50_close_h IS NOT NULL",
                         (key, MIN_N)).fetchone()
        if r:
            p50, p90 = round(r["p50_close_h"]), round(r["p90_close_h"])
            return Eta(r["p50_close_h"], r["p75_close_h"], r["p90_close_h"], r["n"], key,
                       f"Similar complaints are usually resolved in about {p50} hours, "
                       f"and 9 in 10 within {p90} hours.")
    return None
