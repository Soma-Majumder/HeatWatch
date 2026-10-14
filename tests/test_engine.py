import unittest
from datetime import datetime, timedelta

from app import db, priors
from app.engine import Intake, IntakeError, assess

NOW = datetime(2026, 1, 15, 19, 0)


def fresh():
    conn = db.connect(":memory:")
    db.init_db(conn)
    return conn


def add(conn, key, created, closed, desc, addr, status="Closed"):
    conn.execute(
        "INSERT INTO hpd_complaints (unique_key, created_date, closed_date, status, descriptor,"
        " incident_address, loaded_at) VALUES (?,?,?,?,?,?,?)",
        (key, created, closed, status, desc, addr, "2026-10-14T00:00:00Z"))


def seeded():
    conn = fresh()
    for d in range(40):                         # enough rows for a trusted prior
        c = datetime(2026, 1, 1 + d % 28, 19)
        add(conn, f"b{d}", c.isoformat(), (c + timedelta(hours=30 + d)).isoformat(),
            "ENTIRE BUILDING", "7 OTHER STREET")
    for d in range(12):                         # a repeat-offender address
        c = datetime(2025, 12, 1 + d)
        add(conn, f"r{d}", c.isoformat(), (c + timedelta(hours=40)).isoformat(),
            "ENTIRE BUILDING", "9 REPEAT AVENUE")
    for n in range(30):                         # many ordinary addresses, so repeat is a real outlier
        add(conn, f"o{n}", "2025-12-05T10:00:00", "2025-12-07T10:00:00", "APARTMENT ONLY", f"{n + 100} ORDINARY STREET")
    conn.commit()
    priors.rebuild_all(conn, repeat_threshold=10)
    return conn


class EngineTests(unittest.TestCase):
    def test_plain_whole_building_is_high_with_eta(self):
        a = assess(seeded(), Intake("1 Quiet St", "building", "heat"), NOW)
        self.assertEqual((a.in_scope, a.priority, a.score), (True, "high", 5))
        self.assertFalse(a.escalate)
        self.assertIsNone(a.duplicate)
        self.assertIn("about", a.eta.text)

    def test_repeat_address_escalates_and_is_critical_for_building(self):
        a = assess(seeded(), Intake("9 Repeat Ave.", "building", "heat"), NOW)
        self.assertTrue(a.repeat_address)
        self.assertEqual((a.priority, a.override), ("critical", "whole_building_aggravated"))
        self.assertTrue(a.escalate)
        self.assertIn("repeat_offender_address", a.escalation_rules)

    def test_open_hpd_complaint_is_reported_as_duplicate(self):
        conn = seeded()
        add(conn, "open1", "2026-01-14T08:00:00", None, "ENTIRE BUILDING", "1 QUIET STREET", "Open")
        priors.backfill_address_norm(conn)
        a = assess(conn, Intake("1 quiet st", "building", "heat"), NOW)
        self.assertEqual((a.duplicate.source, a.duplicate.ref), ("hpd", "open1"))

    def test_safety_flag_is_critical_and_escalated(self):
        a = assess(seeded(), Intake("1 Quiet St", "apartment", "heat", safety_flag=True), NOW)
        self.assertEqual((a.priority, a.override), ("critical", "safety_risk"))
        self.assertEqual(a.escalation_rules, ["safety_risk"])

    def test_reopened_escalates(self):
        a = assess(seeded(), Intake("1 Quiet St", "apartment", "heat", reopened=True), NOW)
        self.assertIn("reopened", a.escalation_rules)

    def test_out_of_area_is_not_scored(self):
        a = assess(seeded(), Intake("5 Main St", "building", "heat", zip="11101"), NOW)
        self.assertFalse(a.in_scope)
        self.assertIsNone(a.priority)
        self.assertEqual(a.escalation_rules, ["out_of_area"])

    def test_in_scope_zip_is_scored(self):
        a = assess(seeded(), Intake("1 Quiet St", "apartment", "heat", zip="10032"), NOW)
        self.assertTrue(a.in_scope)

    def test_validation(self):
        conn = fresh()
        for bad in (Intake("", "building", "heat"), Intake("1 A St", "house", "heat"),
                    Intake("1 A St", "building", "cold"),
                    Intake("1 A St", "building", "heat", duration_hours=-1)):
            with self.assertRaises(IntakeError):
                assess(conn, bad, NOW)

    def test_works_on_empty_database(self):
        a = assess(fresh(), Intake("1 A St", "apartment", "hot_water"), NOW)
        self.assertEqual(a.priority, "normal")
        self.assertIsNone(a.eta)

    def test_as_dict_is_json_friendly(self):
        import json
        json.dumps(assess(seeded(), Intake("1 Quiet St", "building", "heat"), NOW).as_dict(), default=str)


if __name__ == "__main__":
    unittest.main()
