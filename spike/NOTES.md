# Day 1 feasibility spike

Run against live NYC Open Data (`erm2-nwe9`) and Open-Meteo on 2026-10-14. All queries below
are reproducible SoQL/HTTP calls; exact numbers will drift as new 311 records arrive.

## "To confirm" items (from CLAUDE.md)

### How far back do HEAT/HOT WATER records go?

Back to **2020-01-01** at minimum, with substantial volume every year since:

```
$select=min(created_date), max(created_date), count(*)
$where=complaint_type='HEAT/HOT WATER'
-> earliest 2020-01-01, latest 2026-10-12, n=1,659,492
```

Per-year counts (same `$where`, grouped by `date_extract_y(created_date)`):

| Year | Count |
|---|---|
| 2020 | 165,016 |
| 2021 | 199,618 |
| 2022 | 264,390 |
| 2023 | 229,509 |
| 2024 | 264,750 |
| 2025 | 315,946 |
| 2026 (through Oct 12) | 220,263 |

2026's partial-year count (220,263 through Oct 12) is consistent with the 216,699 figure already
confirmed on Oct 8 in CLAUDE.md. This comfortably covers the "need at least Oct 2025 to May 2026"
requirement, with 5+ full extra years available if the eval suite or a future feature wants them.

### Is `council_district` filled in on heat records?

Checked on a year of recent heat records (Oct 1 2025 - Oct 12 2026, n=363,969):

| Field | Filled | Rate |
|---|---|---|
| `council_district` | 363,949 | 99.99% |
| `bbl` | 362,707 | 99.65% (matches the 99.6% already confirmed city-wide on Oct 8) |
| `community_board` | 363,969 | 100% |

All three fields are reliable enough to group on without a large "unknown" bucket.

### Reporting lag on recent days

Latest record on file as of this check: **2026-10-12 23:48:55** (today is 2026-10-14, so about a
2-day lag). Daily counts for the last 16 days show no gradual fade-in -- the last available day
(Oct 12: 370) is in the same range as the days before it (Oct 9-11: 359, 256, 266), not a partial
count trailing toward zero:

```
Sep 27-Oct 5: 306,253,256,209,229,209,212,287,381 (normal range)
Oct 6-7: 960, 978   <- spike, not investigated further, possibly a cold snap
Oct 8-12: 375,359,256,266,370
```

**Conclusion:** the lag is a flat ~2 days, not a multi-day drop-off. `check_coverage`'s
`possibly_incomplete` flag (threshold: ends within 2 days of the latest record) matches this
exactly -- no adjustment needed.

### Weather source

**Open-Meteo historical archive API** (`archive-api.open-meteo.com/v1/archive`), Central Park
(40.7829, -73.9654), confirmed working:

- Both full past heat seasons (Oct 1 2024 - Jan 15 2025, and Oct 1 2025 - Jan 15 2026) returned
  107 days of complete daily data each, in well under 1 second.
- `temperature_unit=fahrenheit` returns daily mean/min/max directly in °F -- no manual C-to-F
  conversion needed in `tools.py`.
- No API key required.

## Three real questions, three different follow-up paths

All three ran through the actual `check_coverage` -> `compare_periods` -> (`get_temperature` and/or
`count_buildings`) pipeline now in `heatwatch/baseline.py`, not hand-waved.

### 1. Brooklyn, live season so far (Oct 1-12, 2026 vs same dates 2025) -- even spread, no drill-down

1,096 -> 1,494 complaints (+36.3%). Top 2 of ~18 districts hold only 39% of the change -- spread
across many districts, not a few. **Path: coverage, compare, temperature. No building drill-down.**
Weather was also up slightly (+3.0% heating degree days), nowhere near enough to explain a 36% rise
on its own.

### 2. Staten Island, full past season (Oct 1 2025 - Jan 14 2026 vs same dates prior year) -- decline, no drill-down

1,393 -> 1,549 complaints (**-10.1%**, note: originally computed as -10.8% against a slightly
different window before the coverage fix below). **Path: coverage, compare. No weather check, no
building drill-down** -- a decline answers itself.

### 3. Bronx, full past season (same windows as #2) -- concentrated, building drill-down

57,845 -> 55,229 complaints (+4.7% overall, a small rise), but **top 2 of 12 districts hold 70% of
the change**. Drilling into those two districts surfaced a genuine standout: one building in
district 14 (`bbl 2033150044`) went from 51 complaints last season to **761 this season**
(+710) -- almost certainly a real, ongoing building-specific heat failure, not noise. **Path:
coverage, compare, count_buildings (no temperature check needed since the overall change was
small and clearly building-driven).**

## Two things the spike changed in the design

### `check_coverage` was wrong about zero vs. missing

First pass at Staten Island's full-season check flagged 3 days as "missing" (2025-10-01,
2025-10-07, 2025-11-09). Checked directly: each of those days had 280-450 *other* 311 complaint
types in Staten Island, and exactly 0 HEAT/HOT WATER complaints. The feed was live; there were
just no heat complaints that day. CLAUDE.md already states the rule for this ("an empty result is
not zero... unless coverage passed") but the first implementation checked day-coverage using the
HEAT/HOT WATER filter itself, which is circular for low-volume areas.

**Fix:** `check_coverage` now checks for *any* 311 complaint type in the area that day
(`soql.coverage_where_clause`), not just heat complaints. `compare_periods` and `count_buildings`
still filter to HEAT/HOT WATER only, which is correct for them. Re-running Staten Island after the
fix: both periods fully covered, 0 missing days.

### The skill's "top quarter of districts" concentration rule needs the real denominator

`baseline.py`'s fixed pipeline checks a simpler "top 2 districts" share against 67%, which is what
the Blueprint's worked example uses. Testing against Manhattan (11 districts) showed top 2 holding
62% -- just under the threshold -- while top 3 (closer to the skill's actual "top quarter of
however many districts exist" rule) held 72%, clearly concentrated. The fixed baseline's simpler
"always top 2" rule misses this case; a smarter rule that scales with the group count would not.
**This is deliberate**, not a bug to fix in the baseline: it's a concrete example of where Day 2's
skill-driven agent should out-perform the baseline, which is exactly what Day 3's comparison is
for.

## Operational notes for `tools.py`

- Unfiltered or loosely-filtered aggregate queries can take 15-30s, and hit transient `503`s under
  load (`SOURCE_ERROR`, two cases encountered this session). Area- and date-scoped queries are fast
  (1-5s). `soql.fetch` retries once after 2s on a transient 5xx/connection error, and raises a
  distinct `SourceTimeout` for true timeouts, per CLAUDE.md hard rule #8.
- A 20s per-call timeout is occasionally tight for a 100+ day grouped query on a large borough
  (one Manhattan full-season query timed out once, succeeded on retry). Not changed for Day 1;
  worth watching once the real agent is making these calls unsupervised in Day 2.

## Exit check

`python -m heatwatch.cli --baseline "Are Brooklyn heat complaints up this winter compared to last
winter?"` prints real numbers (see Day 1 done-when output). Every "to confirm" item above is
answered.
