"""Backtest triage bands on historical complaints.

Only signals recoverable from the public record are used: scope, season,
overnight, and repeat-offender address. Duration, vulnerability and safety
flags are not in the data, so those weights cannot be checked here.

Caveat: repeat_flag comes from counts over the full window, so it uses
information that would not have been known at report time.

Run:  python -m app.backtest
"""
import statistics
from collections import defaultdict

from .db import connect, init_db
from .priors import SCOPE, parse_ts, percentile, rebuild_all
from .triage import Complaint, score_complaint


def run(conn) -> dict:
    repeat = {r["address_norm"]: bool(r["repeat_flag"]) for r in conn.execute(
        "SELECT address_norm, repeat_flag FROM address_stats")}
    bands = defaultdict(lambda: {"n": 0, "close": [], "access": 0, "dup": 0})
    for r in conn.execute(
        "SELECT created_date, closed_date, descriptor, address_norm, resolution_description"
        " FROM hpd_complaints"
    ):
        scope = SCOPE.get((r["descriptor"] or "").upper())
        if not scope:
            continue
        created = parse_ts(r["created_date"])
        res = score_complaint(Complaint(scope, "heat", created,
                                        repeat_address=repeat.get(r["address_norm"], False)))
        b = bands[res.priority]
        b["n"] += 1
        text = (r["resolution_description"] or "").lower()
        b["access"] += int("not able to gain access" in text)
        b["dup"] += int("duplicate of a building-wide" in text)
        if r["closed_date"]:
            h = (parse_ts(r["closed_date"]) - created).total_seconds() / 3600
            if h >= 0:
                b["close"].append(h)
    return bands


def report(bands: dict) -> str:
    lines = [f"{'band':9}{'n':>8}{'median_h':>10}{'p90_h':>8}{'>72h':>8}{'no_access':>11}{'dup':>7}"]
    for name in ("critical", "high", "normal", "low"):
        b = bands.get(name)
        if not b:
            continue
        c = sorted(b["close"])
        over72 = sum(h > 72 for h in c) / len(c) if c else 0
        lines.append(f"{name:9}{b['n']:>8}{(statistics.median(c) if c else 0):>10.1f}"
                     f"{(percentile(c, .9) or 0):>8.1f}{over72:>8.1%}"
                     f"{b['access'] / b['n']:>11.1%}{b['dup'] / b['n']:>7.1%}")
    return "\n".join(lines)


if __name__ == "__main__":
    conn = connect()
    init_db(conn)
    print(rebuild_all(conn))
    print(report(run(conn)))
