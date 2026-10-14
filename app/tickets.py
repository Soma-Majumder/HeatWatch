"""Ticket store: create tickets from an Assessment, log events, look them up.

Only harness code calls these functions. The model never gets a handle on them
(see docs/security-layer.md, requirement 2).
"""
import json
import secrets
from dataclasses import dataclass
from datetime import datetime

from .engine import Assessment, Intake

STAGES = ("received", "triaged", "escalated", "awaiting_access", "reopened", "resolved", "closed")
CLOSED_STAGES = ("resolved", "closed")           # matches duplicates.CLOSED_STAGES
ACTORS = ("agent", "tenant", "reviewer", "system")
_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"     # no 0/O/1/I/L: easy to read aloud
_ID_LEN = 8


class TicketError(Exception):
    pass


@dataclass
class Ticket:
    id: str
    created_at: str
    address_raw: str | None
    address_norm: str | None
    zip: str | None
    scope: str | None
    problem: str | None
    duration_hours: float | None
    vulnerable: bool
    safety_flag: bool
    description: str | None
    priority: str | None
    score: float | None
    score_reasons: list[str]
    stage: str
    eta_hours: float | None          # the 90th-percentile window we quoted; used to judge "overdue"
    linked_311_key: str | None
    duplicate_of: str | None
    lang: str


@dataclass
class Event:
    at: str
    stage: str
    actor: str
    note: str | None


def _now_iso(now: datetime | None) -> str:
    return (now or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")


def new_ticket_id() -> str:
    return "HW-" + "".join(secrets.choice(_ALPHABET) for _ in range(_ID_LEN))


def _row_to_ticket(r) -> Ticket:
    return Ticket(
        id=r["id"], created_at=r["created_at"], address_raw=r["address_raw"],
        address_norm=r["address_norm"], zip=r["zip"], scope=r["scope"], problem=r["problem"],
        duration_hours=r["duration_hours"], vulnerable=bool(r["vulnerable"]),
        safety_flag=bool(r["safety_flag"]), description=r["description"], priority=r["priority"],
        score=r["score"], score_reasons=json.loads(r["score_reasons"] or "[]"), stage=r["stage"],
        eta_hours=r["eta_hours"], linked_311_key=r["linked_311_key"],
        duplicate_of=r["duplicate_of"], lang=r["lang"],
    )


def create_ticket(conn, intake: Intake, assessment: Assessment, now: datetime | None = None) -> Ticket:
    if not assessment.in_scope:
        raise TicketError("out-of-area complaints do not get a ticket")
    at = _now_iso(now)
    stage = "escalated" if assessment.escalate else "triaged"
    dup = assessment.duplicate
    for _ in range(10):                                   # retry on the (very unlikely) id clash
        tid = new_ticket_id()
        if not conn.execute("SELECT 1 FROM tickets WHERE id=?", (tid,)).fetchone():
            break
    else:
        raise TicketError("could not allocate a ticket id")
    with conn:
        conn.execute(
            "INSERT INTO tickets (id, created_at, address_norm, address_raw, zip, scope, problem,"
            " duration_hours, vulnerable, safety_flag, description, priority, score, score_reasons,"
            " stage, eta_hours, linked_311_key, duplicate_of, lang)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (tid, at, assessment.address_norm, intake.address, intake.zip, intake.scope,
             intake.problem, intake.duration_hours, int(intake.vulnerable), int(intake.safety_flag),
             intake.description, assessment.priority, assessment.score,
             json.dumps(assessment.reasons), stage,
             assessment.eta.p90_h if assessment.eta else None,
             dup.ref if dup and dup.source == "hpd" else None,
             dup.ref if dup and dup.source == "ticket" else None,
             intake.lang),
        )
        _insert_event(conn, tid, "received", "agent", "Complaint received", at)
        # Notes are visible to tenants, so keep internal rule names in the escalations table only.
        _insert_event(conn, tid, stage, "system",
                      "Escalated for review" if assessment.escalate else "Triaged", at)
        for rule in assessment.escalation_rules:
            conn.execute(
                "INSERT INTO escalations (ticket_id, rule, reason, at) VALUES (?,?,?,?)",
                (tid, rule, "; ".join(assessment.reasons[:3]), at))
    return get_ticket(conn, tid)


def _insert_event(conn, ticket_id, stage, actor, note, at):
    conn.execute("INSERT INTO ticket_events (ticket_id, at, stage, actor, note) VALUES (?,?,?,?,?)",
                 (ticket_id, at, stage, actor, note))


def get_ticket(conn, ticket_id: str) -> Ticket | None:
    r = conn.execute("SELECT * FROM tickets WHERE id=?", (ticket_id.strip().upper(),)).fetchone()
    return _row_to_ticket(r) if r else None


def history(conn, ticket_id: str) -> list[Event]:
    return [Event(r["at"], r["stage"], r["actor"], r["note"]) for r in conn.execute(
        "SELECT at, stage, actor, note FROM ticket_events WHERE ticket_id=? ORDER BY id",
        (ticket_id.strip().upper(),))]


def add_event(conn, ticket_id: str, stage: str, actor: str, note: str | None = None,
              now: datetime | None = None) -> Ticket:
    if stage not in STAGES:
        raise TicketError(f"unknown stage {stage!r}")
    if actor not in ACTORS:
        raise TicketError(f"unknown actor {actor!r}")
    if get_ticket(conn, ticket_id) is None:
        raise TicketError("no such ticket")
    tid = ticket_id.strip().upper()
    with conn:
        _insert_event(conn, tid, stage, actor, note, _now_iso(now))
        conn.execute("UPDATE tickets SET stage=? WHERE id=?", (stage, tid))
    return get_ticket(conn, tid)


def reopen(conn, ticket_id: str, note: str | None = None, now: datetime | None = None) -> Ticket:
    """Tenant says it is still broken: reopen and flag for a person."""
    t = add_event(conn, ticket_id, "reopened", "tenant", note or "Tenant reports the problem continues", now)
    with conn:
        conn.execute("INSERT INTO escalations (ticket_id, rule, reason, at) VALUES (?,?,?,?)",
                     (t.id, "reopened", note, _now_iso(now)))
    return t


def mask_address(address_norm: str | None) -> str | None:
    """Hide the house number so a leaked ticket number does not expose a home address."""
    if not address_norm:
        return None
    parts = address_norm.split(" ", 1)
    return ("*** " + parts[1]) if len(parts) == 2 and any(ch.isdigit() for ch in parts[0]) else address_norm


def public_view(conn, ticket_id: str) -> dict | None:
    """What a tenant sees when they look up a ticket by number. No reviewer notes, masked address."""
    t = get_ticket(conn, ticket_id)
    if not t:
        return None
    events = []
    for e in history(conn, t.id):
        note = e.note if e.actor != "reviewer" else None
        events.append({"at": e.at, "stage": e.stage, "actor": e.actor, "note": note})
    return {
        "ticket_id": t.id,
        "stage": t.stage,
        "priority": t.priority,
        "created_at": t.created_at,
        "address": mask_address(t.address_norm),
        "quoted_window_hours": t.eta_hours,
        "linked_to_existing_report": bool(t.linked_311_key or t.duplicate_of),
        "history": events,
    }
