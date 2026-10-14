import unittest
from datetime import datetime, timezone
from unittest import mock

from app import db, loader
from app.config import Settings


def row(key, created, **kw):
    base = {"unique_key": key, "created_date": created, "status": "Closed",
            "descriptor": "ENTIRE BUILDING", "incident_address": "1 TEST AVENUE",
            "incident_zip": "10032", "community_board": "12 MANHATTAN", "borough": "MANHATTAN",
            "latitude": "40.84", "longitude": "-73.94"}
    base.update(kw)
    return base


class SchemaTests(unittest.TestCase):
    def test_all_tables_created(self):
        conn = db.connect(":memory:")
        db.init_db(conn)
        names = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
        for t in ("hpd_complaints", "tickets", "ticket_events", "escalations",
                  "address_stats", "priors", "meta"):
            self.assertIn(t, names)

    def test_init_is_idempotent(self):
        conn = db.connect(":memory:")
        db.init_db(conn)
        db.init_db(conn)


class LoaderTests(unittest.TestCase):
    NOW = datetime(2026, 10, 14, tzinfo=timezone.utc)

    def test_load_and_upsert(self):
        conn = db.connect(":memory:")
        s = Settings(page_size=2, window_days=730)
        pages = {0: [row("1", "2026-10-01T00:00:00"), row("2", "2026-09-01T00:00:00")],
                 2: [row("3", "2026-08-01T00:00:00")]}
        calls = []

        def fake_get(url, token, tries=4):
            off = int(url.split("%24offset=")[1].split("&")[0]) if "%24offset=" in url \
                else int(url.split("$offset=")[1].split("&")[0])
            calls.append(off)
            return pages[off]

        with mock.patch.object(loader, "_get", fake_get):
            self.assertEqual(loader.load(s, conn, self.NOW), 3)
            self.assertEqual(calls, [0, 2])
            pages[0][0] = row("1", "2026-10-01T00:00:00", status="Open")
            loader.load(s, conn, self.NOW)
        self.assertEqual(conn.execute("select count(*) from hpd_complaints").fetchone()[0], 3)
        self.assertEqual(conn.execute("select status from hpd_complaints where unique_key='1'")
                         .fetchone()[0], "Open")
        self.assertIsNotNone(conn.execute("select value from meta where key='hpd_last_load'").fetchone())

    def test_cutoff_is_rolling_window(self):
        url = loader.build_url(Settings(window_days=730), "2024-10-14T00:00:00", 0)
        self.assertIn("2024-10-14", url)
        self.assertIn("MANHATTAN", url)


if __name__ == "__main__":
    unittest.main()
