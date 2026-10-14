"""Deterministic urgency scoring (BUILD_PLAN.md section 4).

Weights are starting assumptions; app/backtest.py is how they get tuned.
The LLM never decides urgency: it only extracts fields and phrases replies.
"""
from dataclasses import dataclass, field
from datetime import datetime

WEIGHTS = {
    "building": 3, "apartment": 1,
    "heat_season": 2,
    "duration_24h": 2, "duration_48h": 3,
    "vulnerable": 3,
    "overnight": 1,
    "repeat_address": 2,
    "reopened": 2,
}
BANDS = [(8, "critical"), (5, "high"), (2, "normal"), (float("-inf"), "low")]


@dataclass
class Complaint:
    scope: str                      # 'building' | 'apartment'
    problem: str                    # 'heat' | 'hot_water' | 'both'
    created_at: datetime
    duration_hours: float | None = None
    vulnerable: bool = False
    safety_flag: bool = False
    repeat_address: bool = False
    reopened: bool = False


@dataclass
class TriageResult:
    priority: str
    score: float
    reasons: list[str] = field(default_factory=list)
    override: str | None = None     # which hard override fired, if any


def is_heat_season(when: datetime) -> bool:
    return when.month >= 10 or when.month <= 5       # Oct 1 to May 31


def is_overnight(when: datetime) -> bool:
    return when.hour >= 22 or when.hour < 6


def band_for(score: float) -> str:
    for floor, name in BANDS:
        if score >= floor:
            return name
    return "low"


def score_complaint(c: Complaint) -> TriageResult:
    pts = 0.0
    reasons: list[str] = []

    def add(key: str, why: str):
        nonlocal pts
        pts += WEIGHTS[key]
        reasons.append(f"+{WEIGHTS[key]} {why}")

    add(c.scope, "whole building affected" if c.scope == "building" else "single apartment affected")
    heat_season = is_heat_season(c.created_at)
    if heat_season:
        add("heat_season", "heat season (Oct 1 to May 31)")
    if c.duration_hours is not None:
        if c.duration_hours >= 48:
            add("duration_48h", "outage lasting 48+ hours")
        elif c.duration_hours >= 24:
            add("duration_24h", "outage lasting 24+ hours")
    if c.vulnerable:
        add("vulnerable", "vulnerable household member")
    if is_overnight(c.created_at):
        add("overnight", "reported overnight")
    if c.repeat_address:
        add("repeat_address", "repeat-offender address")
    if c.reopened:
        add("reopened", "ticket reopened")

    override = None
    if c.safety_flag:
        override = "safety_risk"
    elif c.vulnerable and heat_season and c.problem in ("heat", "both"):
        override = "vulnerable_no_heat_in_season"
    if override:
        reasons.insert(0, f"critical override: {override}")
        return TriageResult("critical", pts, reasons, override)
    return TriageResult(band_for(pts), pts, reasons)
