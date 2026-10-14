"""The four read-only data tools. Every number here is computed in code; the model
never does arithmetic (CLAUDE.md hard rule #2) -- it only reads what these return."""
from datetime import date, timedelta

import httpx

from heatwatch import config, soql
from heatwatch.schemas import (
    CheckCoverageArgs,
    ComparePeriodsArgs,
    CountBuildingsArgs,
    GetTemperatureArgs,
)


def _days_with_records(area, start: date, end: date) -> set[str]:
    """Any 311 complaint in the area counts, not just HEAT/HOT WATER -- a quiet day
    with zero heat complaints is a true zero, not a gap. See soql.coverage_where_clause."""
    rows = soql.fetch({
        "$select": "date_trunc_ymd(created_date) as day, count(*) as n",
        "$where": soql.coverage_where_clause(area, start, end),
        "$group": "day",
        "$order": "day",
        "$limit": 1000,
    })
    return {row["day"][:10] for row in rows}


def _latest_record_date(area) -> date | None:
    rows = soql.fetch({
        "$select": "max(created_date) as latest",
        "$where": f"complaint_type='{soql.COMPLAINT_TYPE}' AND {soql.area_clause(area)}",
    })
    latest = rows[0].get("latest") if rows else None
    return date.fromisoformat(latest[:10]) if latest else None


def check_coverage(args: CheckCoverageArgs) -> dict:
    results = []
    for date_range in args.ranges:
        have = _days_with_records(args.area, date_range.start, date_range.end)
        all_days = {
            (date_range.start + timedelta(days=i)).isoformat()
            for i in range((date_range.end - date_range.start).days + 1)
        }
        missing = sorted(all_days - have)
        results.append({
            "start": date_range.start.isoformat(),
            "end": date_range.end.isoformat(),
            "days_with_records": len(have),
            "missing_days": missing,
        })

    latest = _latest_record_date(args.area)
    for result in results:
        end = date.fromisoformat(result["end"])
        result["possibly_incomplete"] = bool(
            latest and (latest - end).days < config.POSSIBLY_INCOMPLETE_DAYS
        )

    return {
        "latest_record_date": latest.isoformat() if latest else None,
        "ranges": results,
        "complete": all(not r["missing_days"] for r in results),
    }


def _counts_by_group(args: ComparePeriodsArgs, date_range, group_by: str) -> dict[str, int]:
    where = soql.where_clause(args.area, date_range.start, date_range.end)
    if group_by == "none":
        rows = soql.fetch({"$select": "count(*) as n", "$where": where})
        return {"_total": int(rows[0]["n"])} if rows else {"_total": 0}

    column = soql.AREA_COLUMN[group_by]
    rows = soql.fetch({
        "$select": f"{column}, count(*) as n",
        "$where": f"{where} AND {column} IS NOT NULL",
        "$group": column,
        "$order": "n DESC",
        "$limit": 60,
    })
    return {row[column]: int(row["n"]) for row in rows}


def compare_periods(args: ComparePeriodsArgs) -> dict:
    counts_a = _counts_by_group(args, args.period_a, args.group_by)
    counts_b = _counts_by_group(args, args.period_b, args.group_by)
    groups = sorted(set(counts_a) | set(counts_b))

    rows = []
    for group in groups:
        count_a, count_b = counts_a.get(group, 0), counts_b.get(group, 0)
        change = count_a - count_b
        if count_b < config.SMALL_BASE_THRESHOLD:
            pct, small_base = None, True
        else:
            pct, small_base = round(change / count_b * 100, 1), False
        rows.append({
            "group": group,
            "count_a": count_a,
            "count_b": count_b,
            "change": change,
            "pct": pct,
            "small_base": small_base,
        })

    total_a, total_b = sum(counts_a.values()), sum(counts_b.values())
    total_change = total_a - total_b
    rows_by_change = sorted(rows, key=lambda r: -r["change"])

    # "Share of change" divides by the net total, which can be near zero even when
    # individual groups moved a lot, if gains and losses elsewhere happened to
    # offset (confirmed on real Bronx data: two districts rose by 65 and 51 while
    # the net citywide change was only 13, producing a nonsensical 892% share).
    # Below this threshold the ratio isn't a meaningful percentage of anything,
    # so it's withheld rather than reported, the same way a small per-group base
    # withholds that group's own percent change above.
    concentration_small_base = abs(total_change) < config.SMALL_BASE_THRESHOLD
    if concentration_small_base:
        top_2_share = None
    else:
        top_2_change = sum(r["change"] for r in rows_by_change[:2] if r["change"] > 0)
        top_2_share = round(top_2_change / total_change, 3)

    return {
        "total": {
            "a": total_a,
            "b": total_b,
            "change": total_change,
            "pct": round(total_change / total_b * 100, 1) if total_b >= config.SMALL_BASE_THRESHOLD else None,
        },
        "groups": rows,
        "top_2_share_of_change": top_2_share,
        "rest_of_area_pct": round(1 - top_2_share, 3) if top_2_share is not None else None,
        "concentration_small_base": concentration_small_base,
    }


def count_buildings(args: CountBuildingsArgs) -> dict:
    def buildings_in(date_range):
        where = soql.where_clause(args.area, date_range.start, date_range.end)
        rows = soql.fetch({
            "$select": "bbl, count(*) as n",
            "$where": f"{where} AND bbl IS NOT NULL",
            "$group": "bbl",
            "$order": "n DESC",
            "$limit": 1000,
        })
        return {row["bbl"]: int(row["n"]) for row in rows}

    buildings_a, buildings_b = buildings_in(args.period_a), buildings_in(args.period_b)
    all_bbls = set(buildings_a) | set(buildings_b)
    top = sorted(all_bbls, key=lambda b: -(buildings_a.get(b, 0) - buildings_b.get(b, 0)))[: args.top_n]

    return {
        "distinct_buildings_a": len(buildings_a),
        "distinct_buildings_b": len(buildings_b),
        "top_buildings": [
            {
                "bbl": bbl,
                "count_a": buildings_a.get(bbl, 0),
                "count_b": buildings_b.get(bbl, 0),
                "change": buildings_a.get(bbl, 0) - buildings_b.get(bbl, 0),
            }
            for bbl in top
        ],
    }


def _heating_demand(args: GetTemperatureArgs, date_range) -> dict:
    try:
        response = httpx.get(
            config.OPEN_METEO_URL,
            params={
                "latitude": config.CENTRAL_PARK_LAT,
                "longitude": config.CENTRAL_PARK_LON,
                "start_date": date_range.start.isoformat(),
                "end_date": date_range.end.isoformat(),
                "daily": "temperature_2m_mean,temperature_2m_min,temperature_2m_max",
                "temperature_unit": "fahrenheit",
                "timezone": "America/New_York",
            },
            timeout=config.OPEN_METEO_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise soql.SourceTimeout(str(exc)) from exc
    except (httpx.HTTPStatusError, httpx.TransportError) as exc:
        raise soql.SourceError(str(exc)) from exc

    daily = response.json()["daily"]
    means = daily["temperature_2m_mean"]
    hdd = sum(max(0.0, config.HDD_BASE_FAHRENHEIT - m) for m in means)
    return {
        "mean_f": round(sum(means) / len(means), 1),
        "low_f": round(min(daily["temperature_2m_min"]), 1),
        "high_f": round(max(daily["temperature_2m_max"]), 1),
        "heating_degree_days": round(hdd, 1),
        "days": len(means),
    }


def get_temperature(args: GetTemperatureArgs) -> dict:
    period_a, period_b = _heating_demand(args, args.period_a), _heating_demand(args, args.period_b)
    hdd_a, hdd_b = period_a["heating_degree_days"], period_b["heating_degree_days"]
    pct = round((hdd_a - hdd_b) / hdd_b * 100, 1) if hdd_b else None
    return {"period_a": period_a, "period_b": period_b, "heating_demand_pct_change": pct}
