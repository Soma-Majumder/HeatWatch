"""Builds SoQL queries from validated, enum-checked parameters only (CLAUDE.md hard
rule #10: never from model free text) and fetches them from NYC Open Data."""
import time
from datetime import date

import httpx

from heatwatch import config
from heatwatch.schemas import Area

COMPLAINT_TYPE = "HEAT/HOT WATER"

AREA_COLUMN = {
    "borough": "borough",
    "council_district": "council_district",
    "community_board": "community_board",
    "incident_zip": "incident_zip",
}


class SourceTimeout(Exception):
    """The data source did not answer within the timeout. Narrow the query and retry."""


class SourceError(Exception):
    """The data source returned a server error after the automatic retry."""


def _escape(value: str) -> str:
    return value.replace("'", "''")


def area_clause(area: Area) -> str:
    if area.level == "city":
        return "1=1"
    column = AREA_COLUMN[area.level]
    return f"{column}='{_escape(area.value)}'"


def date_clause(start: date, end: date) -> str:
    return f"created_date >= '{start.isoformat()}T00:00:00' AND created_date <= '{end.isoformat()}T23:59:59'"


def where_clause(area: Area, start: date, end: date) -> str:
    return f"complaint_type='{COMPLAINT_TYPE}' AND {area_clause(area)} AND {date_clause(start, end)}"


def coverage_where_clause(area: Area, start: date, end: date) -> str:
    """Deliberately omits the complaint_type filter. A day can have zero HEAT/HOT
    WATER complaints and still be fully covered -- that's a true zero, not a gap
    (CLAUDE.md: "an empty result is not zero... unless coverage passed"). The
    only way to tell the two apart is to check whether 311 ingested *anything*
    for the area that day, confirmed against real Staten Island data during the
    Day 1 feasibility check (days with hundreds of other complaint types and
    zero heat complaints were initially misflagged as coverage gaps)."""
    return f"{area_clause(area)} AND {date_clause(start, end)}"


def fetch(params: dict) -> list[dict]:
    """GET against the Socrata endpoint. One retry after 2s on a transient 5xx or
    connection error, confirmed necessary during the Day 1 feasibility check. A
    timeout is raised distinctly so the caller can narrow the query instead of
    blindly retrying the same shape."""
    if config.SOCRATA_APP_TOKEN:
        params = {**params, "$$app_token": config.SOCRATA_APP_TOKEN}
    last_exc: Exception | None = None
    for attempt in range(config.SOCRATA_RETRYABLE_RETRIES + 1):
        try:
            response = httpx.get(config.SOCRATA_BASE_URL, params=params, timeout=config.SOCRATA_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise SourceTimeout(str(exc)) from exc
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < config.SOCRATA_RETRYABLE_RETRIES:
                time.sleep(2)
    raise SourceError(str(last_exc))
