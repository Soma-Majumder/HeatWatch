import unittest
from datetime import datetime

from app import db, priors, triage
from app.address import normalize_address
from app.duplicates import find_duplicate
from app.eta import lookup_eta
from app.triage import Complaint, score_complaint

JAN_EVENING = datetime(2026, 1, 15, 19, 0)
JUL_NOON = datetime(2026, 7, 15, 12, 0)
JAN_3AM = datetime(2026, 1, 15, 3, 0)


class AddressTests(unittest.TestCase):
    def test_variants_match(self):
        want = "516 WEST 156 STREET"
        for raw in ("516 WEST  156 STREET", "516 W 156th St.", "516 west 156 st", "516 W 156 ST, NEW YORK"):
            self.assertEqual(normalize_address(raw), want, raw)

    def test_saint_vs_street(self):
        self.assertEqual(normalize_address("100 ST NICHOLAS AVE"), "100 SAINT NICHOLAS AVENUE")

    def test_unit_stripped_and_hyphen_kept(self):
        self.assertEqual(normalize_address("21-34 45 ROAD APT 3B"), "21-34 45 ROAD")
        self.assertEqual(normalize_address("139 Payson Ave #4C"), "139 PAYSON AVENUE")

    def test_empty(self):
        self.assertEqual(normalize_address(None), "")
        self.assertEqual(normalize_address(""), "")


class TriageTests(unittest.TestCase):
    def test_whole_building_winter_is_high(self):
        r = score_complaint(Complaint("building", "heat", JAN_EVENING, duration_hours=10))
        self.assertEqual(r.score, 5)
        self.assertEqual(r.priority, "high")

    def test_apartment_summer_is_low(self):
        r = score_complaint(Complaint("apartment", "hot_water", JUL_NOON))
        self.assertEqual(r.priority, "low")

    def test_long_outage_overnight_repeat_reaches_critical(self):
        r = score_complaint(Complaint("building", "heat", JAN_3AM, duration_hours=50, repeat_address=True))
        self.assertEqual(r.score, 3 + 2 + 3 + 1 + 2)
        self.assertEqual(r.priority, "critical")

    def test_safety_override(self):
        r = score_complaint(Complaint("apartment", "heat", JUL_NOON, safety_flag=True))
        self.assertEqual((r.priority, r.override), ("critical", "safety_risk"))

    def test_vulnerable_no_heat_in_season_override(self):
        r = score_complaint(Complaint("apartment", "heat", JAN_EVENING, vulnerable=True))
        self.assertEqual(r.override, "vulnerable_no_heat_in_season")
        self.assertEqual(r.priority, "critical")

    def test_vulnerable_hot_water_only_not_overridden(self):
        r = score_complaint(Complaint("apartment", "hot_water", JAN_EVENING, vulnerable=True))
        self.assertIsNone(r.override)

    def test_heat_season_bounds(self):
        self.assertTrue(triage.is_heat_season(datetime(2026, 10, 1)))
        self.assertTrue(triage.is_heat_season(datetime(2026, 5, 31)))
        self.assertFalse(triage.is_heat_season(datetime(2026, 6, 1)))
        self.assertFalse(triage.is_heat_season(datetime(2026, 9, 30)))


def seed(conn, rows):
    for i, (created, closed, desc, addr, status, res) in enumerate(rows):
        conn.execute(
            "INSERT INTO hpd_complaints (unique_key, created_date, closed_date, status, descriptor,"
            " incident_address, resolution_description, loaded_at) VALUES (?,?,?,?,?,?,?,?)",
            (str(i), created, closed, status, desc, addr, res, "2026-10-14T00:00:00Z"))
    conn.commit()


class PriorsTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        rows = []
        for d in range(1, 41):  # 40 building complaints in January, each closed after d hours
            created = f"2026-01-{(d % 28) + 1:02d}T19:00:00"
            closed = datetime(2026, 1, (d % 28) + 1, 19).replace() 
            from datetime import timedelta
            rows.append((created, (closed + timedelta(hours=d)).strftime("%Y-%m-%dT%H:%M:%S"),
                         "ENTIRE BUILDING", "1 TEST AVENUE" if d % 2 else "2 OTHER STREET", "Closed",
                         "This complaint is a duplicate of a building-wide condition already reported" if d <= 10 else "ok"))
        seed(self.conn, rows)

    def test_address_stats_and_backfill(self):
        n = priors.build_address_stats(self.conn)
        self.assertEqual(n, 2)
        row = self.conn.execute("SELECT * FROM address_stats WHERE address_norm='1 TEST AVENUE'").fetchone()
        self.assertEqual(row["complaints_2y"], 20)
        self.assertEqual(row["repeat_flag"], 1)

    def test_priors_and_eta_fallback(self):
        priors.build_priors(self.conn)
        r = self.conn.execute("SELECT * FROM priors WHERE key='building|*|*'").fetchone()
        self.assertEqual(r["n"], 40)
        self.assertAlmostEqual(r["dup_rate"], 0.25)
        self.assertAlmostEqual(r["p50_close_h"], 20.5)
        eta = lookup_eta(self.conn, "building", datetime(2026, 1, 20, 10))   # morning cell is empty
        self.assertEqual(eta.key, "building|01|*")
        self.assertIn("about", eta.text)

    def test_eta_none_when_no_data(self):
        db_empty = db.connect(":memory:")
        db.init_db(db_empty)
        self.assertIsNone(lookup_eta(db_empty, "building", JAN_EVENING))


class DuplicateTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        db.init_db(self.conn)
        self.now = datetime(2026, 10, 14, 12, 0)

    def test_recent_open_hpd_complaint_is_duplicate(self):
        seed(self.conn, [("2026-10-12T08:00:00", None, "ENTIRE BUILDING", "5 MAIN STREET", "Open", None)])
        priors.backfill_address_norm(self.conn)
        d = find_duplicate(self.conn, "5 MAIN STREET", self.now)
        self.assertEqual((d.source, d.ref), ("hpd", "0"))

    def test_stale_open_complaint_ignored(self):
        seed(self.conn, [("2026-08-01T08:00:00", None, "ENTIRE BUILDING", "5 MAIN STREET", "Open", None)])
        priors.backfill_address_norm(self.conn)
        self.assertIsNone(find_duplicate(self.conn, "5 MAIN STREET", self.now))

    def test_open_ticket_wins_and_closed_ignored(self):
        self.conn.execute("INSERT INTO tickets(id, created_at, address_norm, stage) VALUES ('HW-1','2026-10-13T09:00:00','5 MAIN STREET','closed')")
        self.assertIsNone(find_duplicate(self.conn, "5 MAIN STREET", self.now))
        self.conn.execute("INSERT INTO tickets(id, created_at, address_norm, stage) VALUES ('HW-2','2026-10-14T09:00:00','5 MAIN STREET','received')")
        d = find_duplicate(self.conn, "5 MAIN STREET", self.now)
        self.assertEqual((d.source, d.ref), ("ticket", "HW-2"))


if __name__ == "__main__":
    unittest.main()
