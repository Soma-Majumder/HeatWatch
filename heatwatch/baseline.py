"""Fixed pipeline, no model choices (CLAUDE.md Decisions: Day 1 is the data side).
Area comes from matching a borough name in the question text; periods always mean
the current heat season versus the same calendar dates last season. The only
branch -- whether to drill into buildings -- is a fixed numeric threshold on the
concentration number `compare_periods` already computed, not a judgment call."""
import re
from datetime import date, timedelta

from heatwatch import config, tools
from heatwatch.schemas import (
    Area,
    CheckCoverageArgs,
    ComparePeriodsArgs,
    CountBuildingsArgs,
    DateRange,
    GetTemperatureArgs,
)

BOROUGHS = ["BROOKLYN", "QUEENS", "MANHATTAN", "BRONX", "STATEN ISLAND"]
CONCENTRATION_THRESHOLD = 0.67  # skill's "roughly two-thirds or more" rule, as a fixed constant


def parse_area(question: str) -> Area:
    upper = question.upper()
    for borough in BOROUGHS:
        if borough in upper:
            return Area(level="borough", value=borough)
    return Area(level="city", value="")


def heat_season_window(as_of: date) -> tuple[DateRange, DateRange]:
    season_start_this_year = date(as_of.year, 10, 1)
    season_start = season_start_this_year if as_of >= season_start_this_year else date(as_of.year - 1, 10, 1)
    season_end_cap = date(season_start.year + 1, config.HEAT_SEASON_END[0], config.HEAT_SEASON_END[1])
    period_a_end = min(as_of - timedelta(days=config.POSSIBLY_INCOMPLETE_DAYS), season_end_cap)

    period_a = DateRange(start=season_start, end=period_a_end)
    period_b = DateRange(
        start=date(season_start.year - 1, season_start.month, season_start.day),
        end=date(period_a_end.year - 1, period_a_end.month, period_a_end.day),
    )
    return period_a, period_b


def _fmt_pct(pct: float | None) -> str:
    return f"{pct:+.1f}%" if pct is not None else "n/a (base too small)"


def run_baseline(question: str, as_of: date | None = None) -> str:
    area = parse_area(question)
    period_a, period_b = heat_season_window(as_of or date.today())
    lines = [
        f"Question: {question}",
        f"Area: {area.level} {area.value or '(citywide)'}",
        f"This season:  {period_a.start} to {period_a.end}",
        f"Last season:  {period_b.start} to {period_b.end}",
        "",
    ]

    coverage = tools.check_coverage(
        CheckCoverageArgs(area=area, ranges=[period_a, period_b], reason="Baseline always checks coverage first")
    )
    lines.append(f"[check_coverage] latest record on file: {coverage['latest_record_date']}")
    for r in coverage["ranges"]:
        flag = " (possibly incomplete)" if r["possibly_incomplete"] else ""
        gap = f", MISSING {len(r['missing_days'])} day(s): {r['missing_days'][:5]}" if r["missing_days"] else ""
        lines.append(f"  {r['start']}..{r['end']}: {r['days_with_records']} days with records{gap}{flag}")

    if not coverage["complete"]:
        lines.append("")
        lines.append("STATUS: cannot_answer -- coverage gap in one of the periods above; no comparison run.")
        return "\n".join(lines)

    comparison = tools.compare_periods(
        ComparePeriodsArgs(
            area=area, period_a=period_a, period_b=period_b, group_by="council_district",
            reason="Baseline always compares by council district",
        )
    )
    total = comparison["total"]
    lines.append("")
    lines.append(
        f"[compare_periods by council_district] {total['a']} vs {total['b']} complaints "
        f"({_fmt_pct(total['pct'])})"
    )
    top_groups = sorted(comparison["groups"], key=lambda g: -g["change"])[:5]
    for g in top_groups:
        lines.append(f"  district {g['group']}: {g['count_a']} vs {g['count_b']} ({_fmt_pct(g['pct'])})")
    share = comparison["top_2_share_of_change"]
    # Districts whose own change is large enough to matter on its own, even when
    # the citywide net is too small to divide by (see tools.compare_periods).
    notable = sorted(
        (g for g in comparison["groups"] if abs(g["change"]) >= config.SMALL_BASE_THRESHOLD),
        key=lambda g: -abs(g["change"]),
    )[:2]
    if share is not None:
        lines.append(f"  top 2 districts hold {share * 100:.0f}% of the total change")
    elif notable:
        named = ", ".join(f"district {g['group']} ({g['change']:+d})" for g in notable)
        lines.append(
            f"  citywide change is too small to attribute a share to any district, but "
            f"{named} moved enough on their own to stand out -- other districts offset them"
        )

    temperature = tools.get_temperature(
        GetTemperatureArgs(period_a=period_a, period_b=period_b, reason="Baseline always checks weather")
    )
    lines.append("")
    lines.append(
        f"[get_temperature] heating degree days {temperature['period_a']['heating_degree_days']} "
        f"vs {temperature['period_b']['heating_degree_days']} "
        f"({_fmt_pct(temperature['heating_demand_pct_change'])})"
    )

    concentrated_by_share = share is not None and share >= CONCENTRATION_THRESHOLD and total["change"] > 0
    rising_notable = [g for g in notable if g["change"] > 0]
    offsetting = share is None and bool(rising_notable)

    if concentrated_by_share or offsetting:
        drill_districts = [g for g in top_groups[:2] if g["change"] > 0] if concentrated_by_share else rising_notable
        lines.append("")
        if concentrated_by_share:
            lines.append(f"Change is concentrated (>= {CONCENTRATION_THRESHOLD:.0%} in top 2 districts) -- drilling into buildings.")
        else:
            lines.append(
                "Citywide change is small, but specific districts moved enough on their own to be "
                "worth checking -- drilling into buildings there, not because of a share-of-change number."
            )
        for g in drill_districts:
            district_area = Area(level="council_district", value=g["group"])
            buildings = tools.count_buildings(
                CountBuildingsArgs(
                    area=district_area, period_a=period_a, period_b=period_b, top_n=5,
                    reason=f"District {g['group']} changed by {g['change']:+d}, worth a closer look",
                )
            )
            lines.append(
                f"  [count_buildings] district {g['group']}: {buildings['distinct_buildings_a']} "
                f"distinct buildings this season"
            )
            for b in buildings["top_buildings"][:3]:
                lines.append(f"    bbl {b['bbl']}: {b['count_a']} vs {b['count_b']} (change {b['change']:+d})")
    elif total["change"] <= 0:
        lines.append("")
        lines.append("Change is flat or a decline -- no building drill-down.")
    else:
        lines.append("")
        lines.append("Change is spread across districts, not concentrated -- no building drill-down.")

    lines.append("")
    lines.append("STATUS: answered")
    return "\n".join(lines)
