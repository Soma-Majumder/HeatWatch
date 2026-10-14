"""One call from a structured complaint to a full triage assessment.

    assessment = assess(conn, Intake(address="516 W 156th St", scope="building", problem="heat"))

This is the seam between the engine and the intake agent: the agent collects an
`Intake`, the engine returns an `Assessment`. No model is involved here, and
nothing is written to the database; creating tickets is a later phase.
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime

from .address import normalize_address
from .duplicates import Duplicate, find_duplicate
from .eta import Eta, lookup_eta
from .triage import Complaint, score_complaint

IN_SCOPE_ZIPS = ("10032", "10033", "10034", "10040")    # Community Board 12
SCOPES = ("building", "apartment")
PROBLEMS = ("heat", "hot_water", "both")


class IntakeError(ValueError):
    """The intake is missing or has an invalid required field."""


@dataclass
class Intake:
    address: str
    scope: str                          # 'building' | 'apartment'
    problem: str                        # 'heat' | 'hot_water' | 'both'
    zip: str | None = None
    duration_hours: float | None = None
    vulnerable: bool = False
    safety_flag: bool = False
    reopened: bool = False
    description: str | None = None      # tenant's own words, kept for the reviewer (shown quoted)
    lang: str = "en"
    created_at: datetime | None = None


@dataclass
class Assessment:
    in_scope: bool
    address_norm: str
    priority: str | None                # None when out of scope
    score: float | None
    reasons: list[str] = field(default_factory=list)
    override: str | None = None
    repeat_address: bool = False
    address_complaints_2y: int = 0
    duplicate: Duplicate | None = None
    eta: Eta | None = None
    escalate: bool = False
    escalation_rules: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def _validate(i: Intake) -> None:
    if not (i.address or "").strip():
        raise IntakeError("address is required")
    if i.scope not in SCOPES:
        raise IntakeError(f"scope must be one of {SCOPES}")
    if i.problem not in PROBLEMS:
        raise IntakeError(f"problem must be one of {PROBLEMS}")
    if i.duration_hours is not None and i.duration_hours < 0:
        raise IntakeError("duration_hours cannot be negative")


def assess(conn, intake: Intake, now: datetime | None = None) -> Assessment:
    _validate(intake)
    now = now or datetime.now()
    when = intake.created_at or now
    address_norm = normalize_address(intake.address)

    if intake.zip and intake.zip.strip() not in IN_SCOPE_ZIPS:
        return Assessment(False, address_norm, None, None,
                          reasons=["address is outside Washington Heights/Inwood"],
                          escalate=True, escalation_rules=["out_of_area"])

    stats = conn.execute(
        "SELECT complaints_2y, repeat_flag FROM address_stats WHERE address_norm=?", (address_norm,)
    ).fetchone()
    repeat = bool(stats["repeat_flag"]) if stats else False

    result = score_complaint(Complaint(
        scope=intake.scope, problem=intake.problem, created_at=when,
        duration_hours=intake.duration_hours, vulnerable=intake.vulnerable,
        safety_flag=intake.safety_flag, repeat_address=repeat, reopened=intake.reopened,
    ))

    rules: list[str] = []
    if result.override:
        rules.append(result.override)
    if intake.reopened:
        rules.append("reopened")
    if repeat:
        rules.append("repeat_offender_address")

    return Assessment(
        in_scope=True,
        address_norm=address_norm,
        priority=result.priority,
        score=result.score,
        reasons=result.reasons,
        override=result.override,
        repeat_address=repeat,
        address_complaints_2y=stats["complaints_2y"] if stats else 0,
        duplicate=find_duplicate(conn, address_norm, now),
        eta=lookup_eta(conn, intake.scope, when),
        escalate=bool(rules),
        escalation_rules=rules,
    )
