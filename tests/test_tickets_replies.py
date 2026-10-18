import unittest
from datetime import datetime

from app import duplicates, priors
from app.engine import Intake, assess
from app.replies import (DISCLAIMER, DISCLAIMER_ES, ReplyViolation, build_out_of_area_reply,
                         build_reply, check_reply, gate)
from app.tickets import (TicketError, add_event, create_ticket, get_ticket, history,
                         mask_address, new_ticket_id, public_view, reopen)
from test_engine import add, fresh, seeded

NOW = datetime(2026, 1, 15, 19, 0)


def make(conn, **kw):
    base = dict(address="1 Quiet St", scope="building", problem="heat", zip="10032")
    base.update(kw)
    intake = Intake(**base)
    a = assess(conn, intake, NOW)
    return intake, a, create_ticket(conn, intake, a, NOW)


class TicketTests(unittest.TestCase):
    def test_id_format_and_uniqueness(self):
        ids = {new_ticket_id() for _ in range(500)}
        self.assertEqual(len(ids), 500)
        for i in ids:
            self.assertRegex(i, r"^HW-[2-9A-HJKMNP-Z]{8}$")

    def test_create_triaged_ticket(self):
        conn = seeded()
        intake, a, t = make(conn, description="No heat since last night")
        self.assertEqual((t.stage, t.priority, t.scope), ("triaged", "high", "building"))
        self.assertEqual(t.description, "No heat since last night")
        self.assertIsNotNone(t.eta_hours)
        self.assertEqual([e.stage for e in history(conn, t.id)], ["received", "triaged"])
        self.assertEqual(conn.execute("select count(*) from escalations").fetchone()[0], 0)

    def test_escalated_ticket_logs_rules(self):
        conn = seeded()
        _, _, t = make(conn, safety_flag=True, scope="apartment")
        self.assertEqual(t.stage, "escalated")
        rules = [r["rule"] for r in conn.execute("select rule from escalations where ticket_id=?", (t.id,))]
        self.assertEqual(rules, ["safety_risk"])
        self.assertNotIn("safety_risk", str(public_view(conn, t.id)))

    def test_out_of_area_has_no_ticket(self):
        conn = seeded()
        intake = Intake("5 Main St", "building", "heat", zip="11101")
        with self.assertRaises(TicketError):
            create_ticket(conn, intake, assess(conn, intake, NOW), NOW)

    def test_duplicate_links_and_new_ticket_is_found_by_duplicate_check(self):
        conn = seeded()
        _, _, first = make(conn)
        _, a2, second = make(conn)
        self.assertEqual(a2.duplicate.ref, first.id)
        self.assertEqual(second.duplicate_of, first.id)
        d = duplicates.find_duplicate(conn, first.address_norm, NOW)
        self.assertEqual(d.source, "ticket")

    def test_hpd_duplicate_sets_311_key(self):
        conn = seeded()
        add(conn, "open1", "2026-01-14T08:00:00", None, "ENTIRE BUILDING", "1 QUIET STREET", "Open")
        priors.backfill_address_norm(conn)
        _, _, t = make(conn)
        self.assertEqual(t.linked_311_key, "open1")

    def test_add_event_updates_stage_and_validates(self):
        conn = seeded()
        _, _, t = make(conn)
        t2 = add_event(conn, t.id, "awaiting_access", "reviewer", "internal note", NOW)
        self.assertEqual(t2.stage, "awaiting_access")
        with self.assertRaises(TicketError):
            add_event(conn, t.id, "nonsense", "agent")
        with self.assertRaises(TicketError):
            add_event(conn, t.id, "closed", "robot")
        with self.assertRaises(TicketError):
            add_event(conn, "HW-NOPE0000", "closed", "agent")

    def test_closed_ticket_no_longer_a_duplicate_target(self):
        conn = seeded()
        _, _, t = make(conn)
        add_event(conn, t.id, "closed", "reviewer", None, NOW)
        self.assertIsNone(duplicates.find_duplicate(conn, t.address_norm, NOW))

    def test_reopen_escalates(self):
        conn = seeded()
        _, _, t = make(conn)
        add_event(conn, t.id, "resolved", "tenant", "fixed", NOW)
        t = reopen(conn, t.id, "Cold again", NOW)
        self.assertEqual(t.stage, "reopened")
        rules = [r["rule"] for r in conn.execute("select rule from escalations where ticket_id=?", (t.id,))]
        self.assertIn("reopened", rules)

    def test_lookup_is_case_and_space_insensitive(self):
        conn = seeded()
        _, _, t = make(conn)
        self.assertEqual(get_ticket(conn, " " + t.id.lower() + " ").id, t.id)
        self.assertIsNone(get_ticket(conn, "HW-ZZZZZZZZ"))

    def test_public_view_hides_reviewer_notes_and_masks_address(self):
        conn = seeded()
        _, _, t = make(conn)
        add_event(conn, t.id, "awaiting_access", "reviewer", "SECRET internal note", NOW)
        v = public_view(conn, t.id)
        self.assertEqual(v["address"], "*** QUIET STREET")
        self.assertNotIn("SECRET", str(v))
        self.assertIsNone(public_view(conn, "HW-ZZZZZZZZ"))

    def test_mask_address(self):
        self.assertEqual(mask_address("21-34 45 ROAD"), "*** 45 ROAD")
        self.assertEqual(mask_address("BROADWAY"), "BROADWAY")
        self.assertIsNone(mask_address(None))


class ReplyTests(unittest.TestCase):
    def test_standard_reply_has_required_parts(self):
        conn = seeded()
        intake, a, t = make(conn)
        text = build_reply(a, t.id, scope=intake.scope)
        self.assertIn(t.id, text)
        self.assertIn(DISCLAIMER, text)
        self.assertIn("estimate based on past complaints", text)
        self.assertNotIn("911", text)

    def test_reply_does_not_imply_heatwatch_will_phone_the_tenant(self):
        conn = seeded()
        _, a, t = make(conn, safety_flag=False, scope="building", duration_hours=30)
        text = build_reply(a, t.id, scope="building")
        self.assertNotIn("be reachable by phone", text)
        self.assertIn("if you report this to 311, give them a phone number", text)
        self.assertIn("come back with your ticket number", text)
        self.assertIn("will review it. Please keep your ticket number", text)

    def test_safety_reply_leads_with_emergency(self):
        conn = seeded()
        intake, a, t = make(conn, scope="apartment", safety_flag=True)
        text = build_reply(a, t.id, safety_flag=True, scope="apartment")
        self.assertIn("911", text)
        self.assertLess(text.index("911"), text.index("urgent"))
        self.assertIn("neighbors", text)

    def test_vulnerable_reply(self):
        conn = seeded()
        _, a, t = make(conn, scope="apartment", vulnerable=True)
        text = build_reply(a, t.id, scope="apartment")
        self.assertIn("vulnerable", text)

    def test_duplicate_reply_mentions_link(self):
        conn = seeded()
        make(conn)
        _, a, t = make(conn)
        self.assertIn("already an open HeatWatch ticket", build_reply(a, t.id))

    def test_acknowledges_frustration_before_explaining_policy(self):
        conn = seeded()
        _, a, t = make(conn)
        text = build_reply(a, t.id, scope="building")
        self.assertTrue(text.startswith("I'm really sorry you're dealing with this"))
        self.assertLess(text.index("frustrating"), text.index("does not file complaints with the city"))
        out = build_out_of_area_reply()
        self.assertLess(out.index("I'm sorry"), out.index("cannot create a ticket"))
        self.assertLess(out.index("frustrating"), out.index("does not file"))

    def test_out_of_area_reply(self):
        text = build_out_of_area_reply()
        self.assertIn("Washington Heights and Inwood", text)
        self.assertIn(DISCLAIMER, text)

    def test_gate_blocks_filing_claims_and_promises(self):
        tid = "HW-ABCDEFGH"
        for bad in ("We have filed your complaint with HPD.", "I've submitted this to the city.",
                    "Your heat will be fixed by tomorrow.", "We guarantee a fast repair."):
            with self.assertRaises(ReplyViolation, msg=bad):
                gate(f"{tid} {bad} {DISCLAIMER}", tid)

    def test_gate_blocks_requests_for_personal_information(self):
        """The intake prompt already says not to ask for these; this is the code-level
        backstop in case the model asks anyway."""
        tid = "HW-ABCDEFGH"
        for bad in ("Could you tell me your name?", "What's your phone number?",
                    "Can I get your email address?", "Please share your social security number."):
            with self.assertRaises(ReplyViolation, msg=bad):
                gate(f"{tid} {bad} {DISCLAIMER}", tid)
        # The real reply's own wording is never flagged: "a phone number", not "your phone number".
        self.assertEqual(check_reply(
            f"{tid} if you report this to 311, give them a phone number where you can be reached. {DISCLAIMER}",
            tid), [])

    def test_gate_blocks_links_other_than_the_approved_311_one(self):
        tid = "HW-ABCDEFGH"
        for bad in ("Verify your ticket at http://heatwatch-verify.com/claim now",
                    "Check status at scam-site.net for updates",
                    "See www.not-the-real-site.org for details",
                    "visit nyc-gov-311.com for help"):
            with self.assertRaises(ReplyViolation, msg=bad):
                gate(f"{tid} {bad} {DISCLAIMER}", tid)
        # The one link HeatWatch's own fixed wording actually uses is never flagged.
        self.assertEqual(check_reply(f"{tid} {DISCLAIMER}", tid), [])

    def test_gate_requires_ticket_disclaimer_and_emergency(self):
        self.assertIn("missing ticket number", check_reply(DISCLAIMER, "HW-ABCDEFGH"))
        self.assertIn("missing 'we do not file with the city' notice", check_reply("hello HW-ABCDEFGH", "HW-ABCDEFGH"))
        self.assertIn("missing emergency instruction", check_reply(f"HW-ABCDEFGH {DISCLAIMER}", "HW-ABCDEFGH", True))

    def test_spanish_reply_has_required_parts_and_passes_its_own_gate(self):
        conn = seeded()
        intake, a, t = make(conn, lang="es")
        text = build_reply(a, t.id, scope=intake.scope, lang="es")
        self.assertIn(t.id, text)
        self.assertIn(DISCLAIMER_ES, text)
        self.assertNotIn(DISCLAIMER, text)          # the English disclaimer is not also present
        self.assertIn("estimado basado en quejas anteriores", text)

    def test_spanish_safety_reply_leads_with_911(self):
        conn = seeded()
        intake, a, t = make(conn, scope="apartment", safety_flag=True, lang="es")
        text = build_reply(a, t.id, safety_flag=True, scope="apartment", lang="es")
        self.assertIn("911", text)
        self.assertIn("vecinos", text)

    def test_spanish_out_of_area_reply(self):
        text = build_out_of_area_reply(lang="es")
        self.assertIn("Washington Heights e Inwood", text)
        self.assertIn(DISCLAIMER_ES, text)

    def test_gate_requires_the_spanish_disclaimer_for_a_spanish_reply(self):
        """The required-notice check has to actually look for the Spanish phrase when
        lang='es' -- not just pass because *some* disclaimer-shaped text is present."""
        tid = "HW-ABCDEFGH"
        self.assertIn("missing 'we do not file with the city' notice",
                      check_reply(f"{tid} {DISCLAIMER}", tid, lang="es"))   # English text, Spanish lang
        self.assertEqual(check_reply(f"{tid} {DISCLAIMER_ES}", tid, lang="es"), [])

    def test_gate_blocks_spanish_filing_claims_promises_and_pii_requests(self):
        tid = "HW-ABCDEFGH"
        for bad in ("Ya hemos presentado su queja con HPD.", "Se lo reparará mañana.",
                    "Garantizamos una reparación rápida.", "¿Cuál es su número de teléfono?",
                    "¿Me puede dar su nombre completo?"):
            with self.assertRaises(ReplyViolation, msg=bad):
                gate(f"{tid} {bad} {DISCLAIMER_ES}", tid, lang="es")
        # The real reply's own Spanish wording is never falsely flagged.
        self.assertEqual(check_reply(
            f"{tid} déles un número de teléfono donde puedan localizarlo/a. {DISCLAIMER_ES}",
            tid, lang="es"), [])

    def test_out_of_area_assessment_rejected_by_builder(self):
        conn = seeded()
        a = assess(conn, Intake("5 Main St", "building", "heat", zip="11101"), NOW)
        with self.assertRaises(ValueError):
            build_reply(a, "HW-ABCDEFGH")


if __name__ == "__main__":
    unittest.main()
