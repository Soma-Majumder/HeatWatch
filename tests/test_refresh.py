import json
import unittest
from datetime import datetime, timezone
from unittest import mock

from app import db, loader, priors, refresh
from app.config import Settings

NOW = datetime(2026, 10, 14, 6, 0, tzinfo=timezone.utc)


def conn_with(rows):
    conn = db.connect(":memory:")
    db.init_db(conn)
    for i, (created, closed, addr) in enumerate(rows):
        conn.execute(
            "INSERT INTO hpd_complaints (unique_key, created_date, closed_date, status, descriptor,"
            " incident_address, loaded_at) VALUES (?,?,?,?,?,?,?)",
            (f"k{i}", created, closed, "Closed", "ENTIRE BUILDING", addr, "2026-10-01T00:00:00Z"))
    conn.commit()
    return conn


class RefreshTests(unittest.TestCase):
    def test_load_prune_rebuild_and_meta(self):
        conn = conn_with([("2026-09-01T10:00:00", "2026-09-03T10:00:00", "1 A STREET"),
                          ("2026-09-02T10:00:00", "2026-09-03T22:00:00", "1 A STREET"),
                          ("2024-01-01T10:00:00", "2024-01-02T10:00:00", "OLD STREET")])  # outside window
        with mock.patch.object(loader, "load", return_value=7):
            s = refresh.refresh(Settings(window_days=730), conn, NOW)
        self.assertEqual((s["loaded"], s["pruned"], s["total_rows"]), (7, 1, 2))
        self.assertEqual(s["address_stats"], 1)
        self.assertGreater(s["priors"], 0)
        meta = conn.execute("SELECT value FROM meta WHERE key='last_refresh'").fetchone()[0]
        self.assertEqual(json.loads(meta)["loaded"], 7)
        self.assertEqual(conn.execute("SELECT value FROM meta WHERE key='last_refresh_error'").fetchone()[0], "")

    def test_zero_rows_warns(self):
        conn = conn_with([("2026-09-01T10:00:00", None, "1 A STREET")])
        with mock.patch.object(loader, "load", return_value=0):
            s = refresh.refresh(Settings(), conn, NOW)
        self.assertTrue(s["warnings"])

    def test_failure_keeps_old_priors_and_records_error(self):
        conn = conn_with([("2026-09-01T10:00:00", "2026-09-02T10:00:00", "1 A STREET")])
        priors.rebuild_all(conn)
        before = conn.execute("SELECT COUNT(*) FROM priors").fetchone()[0]
        self.assertGreater(before, 0)
        with mock.patch.object(loader, "load", side_effect=RuntimeError("source down")):
            with self.assertRaises(RuntimeError):
                refresh.refresh(Settings(), conn, NOW)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM priors").fetchone()[0], before)
        err = conn.execute("SELECT value FROM meta WHERE key='last_refresh_error'").fetchone()[0]
        self.assertIn("source down", err)

    def test_rerun_is_idempotent(self):
        conn = conn_with([("2026-09-01T10:00:00", "2026-09-02T10:00:00", "1 A STREET")])
        with mock.patch.object(loader, "load", return_value=0):
            a = refresh.refresh(Settings(), conn, NOW)
            b = refresh.refresh(Settings(), conn, NOW)
        self.assertEqual((a["total_rows"], a["priors"]), (b["total_rows"], b["priors"]))

    def test_main_returns_exit_codes(self):
        with mock.patch.object(refresh, "refresh", side_effect=RuntimeError("x")):
            self.assertEqual(refresh.main([]), 1)
        ok = {"loaded": 1, "pruned": 0, "total_rows": 1, "address_stats": 1, "priors": 1, "warnings": []}
        with mock.patch.object(refresh, "refresh", return_value=ok):
            self.assertEqual(refresh.main([]), 0)


if __name__ == "__main__":
    unittest.main()
