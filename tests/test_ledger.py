"""Credit guard and ledger rules (decision 0001). Fixture config, not the live one, so limits here are frozen."""
import json
import os
import tempfile
import unittest

from tools import ledger

CFG = {"credits": {"reserve_ai_film": 450, "media_cap": 120, "cost_per_generation": 9}}


def row(key, credits=9):
    return {"shot": "s", "model": "m", "route": "/v1/t2v", "idempotency_key": key, "credits": credits}


class GuardTest(unittest.TestCase):
    def test_refuses_when_balance_minus_cost_below_reserve(self):
        with self.assertRaises(ledger.GuardRefused):
            ledger.check_guard(458, 9, [], CFG)  # 449 left

    def test_accepts_exactly_at_reserve(self):
        self.assertEqual(ledger.check_guard(459, 9, [], CFG), 111)

    def test_refuses_when_spent_plus_cost_above_cap(self):
        rows = [{"status": "done", "credits": 9} for _ in range(13)]  # 117 spent
        with self.assertRaises(ledger.GuardRefused):
            ledger.check_guard(1000, 9, rows, CFG)

    def test_accepts_exactly_at_cap(self):
        rows = [{"status": "done", "credits": 9} for _ in range(12)] + [{"status": "done", "credits": 3}]  # 111
        self.assertEqual(ledger.check_guard(1000, 9, rows, CFG), 0)

    def test_refunded_and_balance_rows_do_not_count(self):
        rows = [{"status": "failed", "credits": 9, "refunded": True}, {"status": "me_only", "credits": 500}]
        self.assertEqual(ledger.spent(rows), 0)


class LedgerFileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.log = os.path.join(self.tmp.name, "generations.jsonl")

    def tearDown(self):
        self.tmp.cleanup()

    def test_row_has_schema_and_me_before(self):
        r = ledger.record_before_submit(row("k1"), 700, self.log, CFG)
        self.assertEqual(set(ledger.FIELDS) - set(r), set())
        self.assertEqual((r["status"], r["me_before"], r["credits"], r["refunded"]), ("submitted", 700.0, 9.0, False))

    def test_refused_guard_writes_nothing(self):
        with self.assertRaises(ledger.GuardRefused):
            ledger.record_before_submit(row("k1"), 455, self.log, CFG)
        self.assertEqual(ledger.read(self.log), [])

    def test_duplicate_key_is_refused(self):
        ledger.record_before_submit(row("k1"), 700, self.log, CFG)
        with self.assertRaises(ledger.InvalidRow):
            ledger.record_before_submit(row("k1"), 700, self.log, CFG)

    def test_update_changes_only_its_row(self):
        ledger.record_before_submit(row("k1"), 700, self.log, CFG)
        ledger.record_before_submit(row("k2"), 691, self.log, CFG)
        with open(self.log, encoding="utf-8") as f:
            first = f.readline()
        ledger.update("k2", {"status": "done", "me_after": 682}, self.log)
        with open(self.log, encoding="utf-8") as f:
            lines = f.readlines()
        self.assertEqual(lines[0], first)
        self.assertEqual(json.loads(lines[1])["me_after"], 682)

    def test_update_rejects_unknown_status(self):
        ledger.record_before_submit(row("k1"), 700, self.log, CFG)
        with self.assertRaises(ledger.InvalidRow):
            ledger.update("k1", {"status": "rendering"}, self.log)

    def test_record_me_spends_nothing(self):
        r = ledger.record_me(691, self.log)
        self.assertEqual((r["status"], r["credits"], r["me_before"]), ("me_only", 0.0, 691.0))
        self.assertEqual(ledger.spent(ledger.read(self.log)), 0)


if __name__ == "__main__":
    unittest.main()
