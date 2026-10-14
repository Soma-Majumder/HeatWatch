"""Pull the rolling 2-year CB12 HEAT/HOT WATER window from NYC Open Data into SQLite.

Run:  python -m app.loader
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

from .config import Settings, get_settings
from .address import normalize_address
from .db import connect, init_db

FIELDS = [
    "unique_key", "created_date", "closed_date", "status", "descriptor",
    "incident_address", "incident_zip", "community_board", "borough",
    "resolution_description", "resolution_action_updated_date",
    "latitude", "longitude",
]


def _get(url: str, token: str | None, tries: int = 4) -> list[dict]:
    headers = {"X-App-Token": token} if token else {}
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.load(r)
            if isinstance(data, dict):  # Socrata returns an error object on transient failures
                raise RuntimeError(data.get("message", "source error"))
            return data
        except (urllib.error.URLError, RuntimeError, TimeoutError):
            if attempt == tries - 1:
                raise
            time.sleep(2 * (attempt + 1))
    return []


def build_url(settings: Settings, cutoff: str, offset: int) -> str:
    params = {
        "$select": ",".join(FIELDS),
        "$where": f"created_date>='{cutoff}' AND borough='MANHATTAN'",
        "$order": "created_date DESC, unique_key",
        "$limit": str(settings.page_size),
        "$offset": str(offset),
    }
    return settings.source_url + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)


def fetch_window(settings: Settings, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=settings.window_days)).strftime("%Y-%m-%dT00:00:00")
    offset = 0
    while True:
        page = _get(build_url(settings, cutoff, offset), settings.app_token)
        yield from page
        if len(page) < settings.page_size:
            return
        offset += settings.page_size


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def load(settings: Settings | None = None, conn=None, now: datetime | None = None) -> int:
    settings = settings or get_settings()
    own = conn is None
    conn = conn or connect(settings.db_path)
    init_db(conn)
    loaded_at = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for r in fetch_window(settings, now):
        if not r.get("unique_key") or not r.get("created_date"):
            continue
        rows.append((
            r["unique_key"], r["created_date"], r.get("closed_date"), r.get("status"),
            r.get("descriptor"), r.get("incident_address"), normalize_address(r.get("incident_address")),
            r.get("incident_zip"),
            r.get("community_board"), r.get("borough"), r.get("resolution_description"),
            r.get("resolution_action_updated_date"), _num(r.get("latitude")),
            _num(r.get("longitude")), loaded_at,
        ))
    with conn:
        conn.executemany(
            "INSERT INTO hpd_complaints (unique_key, created_date, closed_date, status, descriptor,"
            " incident_address, address_norm, incident_zip, community_board, borough, resolution_description,"
            " resolution_action_updated_date, latitude, longitude, loaded_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(unique_key) DO UPDATE SET"
            " closed_date=excluded.closed_date, status=excluded.status,"
            " address_norm=excluded.address_norm,"
            " resolution_description=excluded.resolution_description,"
            " resolution_action_updated_date=excluded.resolution_action_updated_date,"
            " loaded_at=excluded.loaded_at",
            rows,
        )
        conn.execute(
            "INSERT INTO meta(key,value) VALUES('hpd_last_load',?)"
            " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (loaded_at,),
        )
    if own:
        conn.close()
    return len(rows)


if __name__ == "__main__":
    n = load()
    print(f"loaded {n} complaints into {get_settings().db_path}")
