import unittest
from datetime import datetime
from unittest import mock

from app import db, loader, refresh
from app.config import Settings
from app.intake.guard import detect_deletion_request
from app.replies import check_reply
from app.retention import deletion_request_reply, purge_expired
from tests.test_intake import reply, session

NOW = datetime(2026, 10, 14, 6, 0, 0)


def conn_with_tickets():
    conn = db.connect(":memory:")
    db.init_db(conn)
    for tid, created in (("HW-OLD", "2026-07-01T10:00:00"), ("HW-NEW", "2026-10-01T10:00:00")):
        conn.execute("INSERT INTO tickets (id, created_at, address_raw) VALUES (?,?,?)", (tid, created, "1 A ST"))
        conn.execute("INSERT INTO ticket_events (ticket_id, at, stage, actor) VALUES (?,?,?,?)",
                     (tid, created, "received", "system"))
        conn.execute("INSERT INTO escalations (ticket_id, rule, at) VALUES (?,?,?)", (tid, "r", created))
    conn.commit()
    return conn


class PurgeTests(unittest.TestCase):
    def test_deletes_only_expired_tickets_with_their_events_and_escalations(self):
        conn = conn_with_tickets()
        out = purge_expired(conn, 90, NOW)
        self.assertEqual(out, {"tickets": 1, "events": 1, "escalations": 1})
        self.assertEqual([r[0] for r in conn.execute("SELECT id FROM tickets")], ["HW-NEW"])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM ticket_events").fetchone()[0], 1)
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM escalations").fetchone()[0], 1)

    def test_nothing_deleted_inside_the_window(self):
        conn = conn_with_tickets()
        self.assertEqual(purge_expired(conn, 365, NOW)["tickets"], 0)

    def test_refresh_purges_even_when_the_data_pull_fails(self):
        conn = conn_with_tickets()
        with mock.patch.object(loader, "load", side_effect=RuntimeError("down")):
            with self.assertRaises(RuntimeError):
                refresh.refresh(Settings(retention_days=90), conn, NOW)
        self.assertEqual([r[0] for r in conn.execute("SELECT id FROM tickets")], ["HW-NEW"])

    def test_refresh_reports_purged_count(self):
        conn = conn_with_tickets()
        with mock.patch.object(loader, "load", return_value=0):
            s = refresh.refresh(Settings(retention_days=90), conn, NOW)
        self.assertEqual(s["purged_tickets"], 1)


class DeletionRequestTests(unittest.TestCase):
    def test_detects_requests_in_both_languages(self):
        for t in ("please delete my information", "Can you remove my data?", "erase my address",
                  "forget me", "I want my info deleted"):
            self.assertEqual(detect_deletion_request(t), "en", t)
        for t in ("por favor borre mis datos", "quiero eliminar mi información", "elimine mi dirección"):
            self.assertEqual(detect_deletion_request(t), "es", t)

    def test_ordinary_complaints_are_not_deletion_requests(self):
        for t in ("no heat at 1 Quiet St", "my apartment has no hot water for two days",
                  "the landlord removed the radiator"):
            self.assertIsNone(detect_deletion_request(t), t)

    def test_reply_states_90_days_and_passes_the_gate(self):
        for lang in ("en", "es"):
            text = deletion_request_reply(90, lang)
            self.assertIn("90", text)
            self.assertEqual(check_reply(text, None, False, False, lang), [])

    def test_agent_answers_without_calling_the_model_or_keeping_the_text(self):
        s, llm = session([])
        r = s.step("please delete my information")
        self.assertIn("within 90 days", r.message)
        self.assertFalse(r.done)
        self.assertEqual(s.description, "")

    def test_agent_answers_in_spanish(self):
        s, _ = session([])
        self.assertIn("dentro de 90 días", s.step("por favor borre mis datos").message)

    def test_conversation_continues_after_a_deletion_request(self):
        s, _ = session([reply({"address": "1 Quiet St", "scope": "apartment", "problem": "heat"}, "ok")])
        s.step("delete my data")
        s.step("no heat at 1 Quiet St")
        self.assertEqual(s.fields.get("address"), "1 Quiet St")


if __name__ == "__main__":
    unittest.main()
