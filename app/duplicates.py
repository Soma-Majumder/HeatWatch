"""Duplicate detection: link a new complaint to an already-active one at the same address."""
from dataclasses import dataclass
from datetime import datetime, timedelta

ACTIVE_DAYS = 7      # an HPD "Open" row older than this is treated as stale
CLOSED_STAGES = ("closed", "resolved")


@dataclass
class Duplicate:
    source: str          # 'ticket' | 'hpd'
    ref: str             # ticket id or 311 unique_key
    created: str


def find_duplicate(conn, address_norm: str, now: datetime, active_days: int = ACTIVE_DAYS) -> Duplicate | None:
    if not address_norm:
        return None
    marks = ",".join("?" * len(CLOSED_STAGES))
    t = conn.execute(
        f"SELECT id, created_at FROM tickets WHERE address_norm=? AND stage NOT IN ({marks})"
        " ORDER BY created_at DESC LIMIT 1",
        (address_norm, *CLOSED_STAGES),
    ).fetchone()
    if t:
        return Duplicate("ticket", t["id"], t["created_at"])
    cutoff = (now - timedelta(days=active_days)).strftime("%Y-%m-%dT%H:%M:%S")
    h = conn.execute(
        "SELECT unique_key, created_date FROM hpd_complaints"
        " WHERE address_norm=? AND status='Open' AND created_date>=?"
        " ORDER BY created_date DESC LIMIT 1",
        (address_norm, cutoff),
    ).fetchone()
    if h:
        return Duplicate("hpd", h["unique_key"], h["created_date"])
    return None
