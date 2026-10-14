"""Daily refresh: pull new 311 data, drop rows outside the rolling window, rebuild priors.

Run:  python3 -m app.refresh

Safe to re-run. If the data pull fails, priors and address stats are left
exactly as they were and the process exits with status 1.
"""
import json
import logging
import sys
from datetime import datetime, timedelta, timezone

from . import loader, priors
from .config import Settings, get_settings
from .db import connect, init_db

log = logging.getLogger("heatwatch.refresh")


def _set_meta(conn, key: str, value: str) -> None:
    with conn:
        conn.execute("INSERT INTO meta(key,value) VALUES(?,?)"
                     " ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def prune_window(conn, window_days: int, now: datetime) -> int:
    cutoff = (now - timedelta(days=window_days)).strftime("%Y-%m-%dT00:00:00")
    with conn:
        cur = conn.execute("DELETE FROM hpd_complaints WHERE created_date < ?", (cutoff,))
    return cur.rowcount


def refresh(settings: Settings | None = None, conn=None, now: datetime | None = None) -> dict:
    """Returns a summary dict. Raises whatever the loader raises; the caller decides what to do."""
    settings = settings or get_settings()
    own = conn is None
    conn = conn or connect(settings.db_path)
    init_db(conn)
    now = now or datetime.now(timezone.utc)
    started = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        loaded = loader.load(settings, conn, now)
        pruned = prune_window(conn, settings.window_days, now)
        built = priors.rebuild_all(conn)
        total = conn.execute("SELECT COUNT(*) FROM hpd_complaints").fetchone()[0]
        summary = {"started": started, "loaded": loaded, "pruned": pruned, "total_rows": total,
                   "address_stats": built["address_stats"], "priors": built["priors"], "warnings": []}
        if loaded == 0:
            summary["warnings"].append("source returned 0 rows; check the source and the date window")
        _set_meta(conn, "last_refresh", json.dumps(summary))
        _set_meta(conn, "last_refresh_error", "")
        return summary
    except Exception as exc:
        _set_meta(conn, "last_refresh_error", f"{started} {type(exc).__name__}: {exc}")
        raise
    finally:
        if own:
            conn.close()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        s = refresh()
    except Exception as exc:                      # report and signal failure to cron
        log.error("refresh failed: %s: %s", type(exc).__name__, exc)
        return 1
    log.info("loaded %d, pruned %d, %d rows in window; %d addresses, %d priors",
             s["loaded"], s["pruned"], s["total_rows"], s["address_stats"], s["priors"])
    for w in s["warnings"]:
        log.warning(w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
