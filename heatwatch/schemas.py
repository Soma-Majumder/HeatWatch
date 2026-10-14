"""One pydantic model per tool. These validate every call and, from Day 2 on,
produce the JSON schemas sent to Claude, so the model and the gate always agree
on what a valid call looks like."""
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

AreaLevel = Literal["city", "borough", "council_district", "community_board", "incident_zip"]
GroupBy = Literal["none", "borough", "council_district", "community_board", "incident_zip"]

MAX_RANGE_DAYS = 365 * 2
MAX_REASON_WORDS = 25


def _check_reason(value: str) -> str:
    if len(value.split()) > MAX_REASON_WORDS:
        raise ValueError(f"reason must be {MAX_REASON_WORDS} words or less")
    return value


class Area(BaseModel):
    level: AreaLevel
    value: str = Field(description="e.g. BROOKLYN, 36, 03 BROOKLYN, 11233; empty for city")

    @model_validator(mode="after")
    def value_required_unless_city(self) -> "Area":
        if self.level != "city" and not self.value.strip():
            raise ValueError("value is required unless level is 'city'")
        return self


class DateRange(BaseModel):
    start: date
    end: date

    @model_validator(mode="after")
    def start_before_end_within_limit(self) -> "DateRange":
        if self.start > self.end:
            raise ValueError("start must not be after end")
        if (self.end - self.start).days > MAX_RANGE_DAYS:
            raise ValueError(f"range may not exceed {MAX_RANGE_DAYS} days")
        return self


class CheckCoverageArgs(BaseModel):
    area: Area
    ranges: list[DateRange] = Field(min_length=1, max_length=2)
    reason: str

    _validate_reason = field_validator("reason")(_check_reason)


class ComparePeriodsArgs(BaseModel):
    area: Area
    period_a: DateRange
    period_b: DateRange
    group_by: GroupBy
    reason: str

    _validate_reason = field_validator("reason")(_check_reason)


class CountBuildingsArgs(BaseModel):
    area: Area
    period_a: DateRange
    period_b: DateRange
    top_n: int = Field(default=10, ge=1, le=25)
    reason: str

    _validate_reason = field_validator("reason")(_check_reason)


class GetTemperatureArgs(BaseModel):
    period_a: DateRange
    period_b: DateRange
    reason: str

    _validate_reason = field_validator("reason")(_check_reason)
