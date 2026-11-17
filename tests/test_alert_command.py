import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

import _path  # noqa: F401

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("FUGLE_API_KEY", "test-key")

try:
    from stockbot import db
    from stockbot.bot_commands import alerts as alert_cmds
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime deps
    if exc.name in {"discord", "fugle_marketdata", "feedparser", "pandas"}:
        raise unittest.SkipTest(f"optional runtime dependency not installed: {exc.name}")
    raise


class FakeInteraction:
    def __init__(self, user_id=1):
        self.user = SimpleNamespace(id=user_id)
        self.deferred = False
        self.replies: list[str] = []

        async def defer():
            self.deferred = True

        async def send(content=None, **kwargs):
            self.replies.append(content)

        self.response = SimpleNamespace(defer=defer)
        self.followup = SimpleNamespace(send=send)


class AlertSetCommandTest(unittest.TestCase):
    """/alert set 必須在寫入 DB 前驗證目標價，否則非法警示會被存下或下一輪立即觸發。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for target, attr, value in [
            (db, "DB_FILE", os.path.join(self.tmp.name, "test.db")),
            (alert_cmds, "get_stock_info", lambda sym: {"price": 100.0}),
        ]:
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)
        db.init_db()

    def run_set(self, target) -> FakeInteraction:
        interaction = FakeInteraction()
        asyncio.run(alert_cmds.alert_set.callback(interaction, "2330", target))
        return interaction

    def test_target_equal_to_current_price_rejected(self):
        interaction = self.run_set(100.0)
        self.assertEqual(db.list_all_alerts(), [])
        self.assertEqual(len(interaction.replies), 1)
        self.assertIn("目標價不可等於現價", interaction.replies[0])

    def test_non_positive_target_rejected(self):
        interaction = self.run_set(0.0)
        self.assertEqual(db.list_all_alerts(), [])
        self.assertEqual(len(interaction.replies), 1)
        self.assertIn("目標價必須大於 0", interaction.replies[0])

    def test_valid_target_is_saved_and_mentions_alert_channel(self):
        interaction = self.run_set(105.0)
        alerts = db.list_all_alerts()
        self.assertEqual([(a["symbol"], a["target"], a["direction"]) for a in alerts],
                         [("2330", 105.0, "above")])
        self.assertIn("警示頻道", interaction.replies[0])
        self.assertNotIn("DM", interaction.replies[0])


if __name__ == "__main__":
    unittest.main()
