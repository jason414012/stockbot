import os
import sqlite3
import tempfile
import unittest

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("FUGLE_API_KEY", "test-key")

import db  # noqa: E402


class DbTransactionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        db.DB_FILE = os.path.join(self.tmp.name, "test.db")
        db.init_db()

    def test_trade_and_position_are_written_together(self):
        db.add_transaction_and_upsert_position(
            1, "2330", "buy", 100, 1000, "2026-06-05", 142, 0, 100.142, 1000, 0
        )

        transactions = db.list_transactions(1, "2330")
        position = db.get_position(1, "2330")

        self.assertEqual(len(transactions), 1)
        self.assertEqual(position["shares"], 1000)

    def test_trade_insert_rolls_back_if_position_write_fails(self):
        with self.assertRaises(sqlite3.IntegrityError):
            db.add_transaction_and_upsert_position(
                1, "2330", "buy", 100, 1000, "2026-06-05", 142, 0, None, 1000, 0
            )

        self.assertEqual(db.list_transactions(1, "2330"), [])
        self.assertIsNone(db.get_position(1, "2330"))


if __name__ == "__main__":
    unittest.main()
