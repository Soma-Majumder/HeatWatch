"""Retention: tenant data is deleted automatically once it is older than the retention window.

The window is `retention_days` in app/config.py (90 by default, decision 4 in BUILD_PLAN.md).
A ticket and everything that hangs off it (events, escalations) go together. The public 311
data in `hpd_complaints` is not tenant data and is handled by the refresh window instead.
"""
from datetime import datetime, timedelta


def purge_expired(conn, retention_days: int, now: datetime) -> dict:
    """Delete tickets created more than `retention_days` ago, with their events and escalations."""
    cutoff = (now - timedelta(days=retention_days)).strftime("%Y-%m-%dT%H:%M:%S")
    old = "(SELECT id FROM tickets WHERE created_at < ?)"
    with conn:
        events = conn.execute(f"DELETE FROM ticket_events WHERE ticket_id IN {old}", (cutoff,)).rowcount
        escalations = conn.execute(f"DELETE FROM escalations WHERE ticket_id IN {old}", (cutoff,)).rowcount
        tickets = conn.execute("DELETE FROM tickets WHERE created_at < ?", (cutoff,)).rowcount
    return {"tickets": tickets, "events": events, "escalations": escalations}


def deletion_request_reply(retention_days: int, lang: str = "en") -> str:
    """What a tenant is told when they ask for their information to be deleted."""
    if lang == "es":
        return (f"Entiendo, y su privacidad es importante. Su información se eliminará automáticamente "
                f"dentro de {retention_days} días.")
    return (f"I understand, and your privacy matters. Your information will be deleted automatically "
            f"within {retention_days} days.")
