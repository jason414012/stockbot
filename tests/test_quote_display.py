import asyncio
import os
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("FUGLE_API_KEY", "test-key")

from stockbot.market_formatting import format_bid_ask, format_volume_lots  # noqa: E402

STOCK = {
    "symbol": "2330", "name": "台積電", "price": 1050.0, "change": 30.0,
    "change_percent": 3.5, "volume": 45678.0, "value": 4.5e10,
    "vol_at_ask": 30000.0, "vol_at_bid": 12000.0, "is_index": False,
}
INDEX = {
    "symbol": "IX0001", "name": "加權", "price": 23000.0, "change": -700.0,
    "change_percent": -3.1, "volume": None, "value": None, "is_index": True,
}


class FormattingTest(unittest.TestCase):
    def test_bid_ask_labels(self):
        self.assertEqual(
            format_bid_ask({"vol_at_ask": 5971, "vol_at_bid": 10874}),
            "🔻 外盤 5,971 / 內盤 10,874（賣方強）",
        )
        self.assertIn("買方強", format_bid_ask({"vol_at_ask": 55, "vol_at_bid": 45}))
        self.assertIn("賣方強", format_bid_ask({"vol_at_ask": 45, "vol_at_bid": 55}))
        self.assertIn("多空均衡", format_bid_ask({"vol_at_ask": 50, "vol_at_bid": 50}))

    def test_bid_ask_empty_for_index_or_missing(self):
        self.assertEqual(format_bid_ask(INDEX), "")
        self.assertEqual(format_bid_ask({"vol_at_ask": 0, "vol_at_bid": 0}), "")
        self.assertEqual(format_bid_ask({"vol_at_ask": None, "vol_at_bid": 3}), "")

    def test_volume_lots(self):
        self.assertEqual(format_volume_lots(STOCK), "45,678 張")
        self.assertEqual(format_volume_lots(INDEX), "")


try:
    from stockbot import db, state
    from stockbot.bot_commands.common import build_quote_embed
    from stockbot.tasks import alerts as alert_tasks
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime deps
    if exc.name in {"discord", "fugle_marketdata", "feedparser", "pandas"}:
        raise unittest.SkipTest(f"optional runtime dependency not installed: {exc.name}")
    raise


class QuoteEmbedTest(unittest.TestCase):
    def test_stock_field_shows_bid_ask_index_does_not(self):
        self.assertIn("內外盤　🔺 外盤 30,000 / 內盤 12,000（買方強）",
                      build_quote_embed(STOCK).fields[0].value)
        self.assertNotIn("內外盤", build_quote_embed(INDEX).fields[0].value)


class FakeChannel:
    def __init__(self):
        self.sent: list[str] = []

    async def send(self, content):
        self.sent.append(content)


class AlertMessageTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.channel = FakeChannel()
        quotes = {"2330": STOCK, "IX0001": INDEX}

        async def fake_quote(sym):
            return quotes[sym]

        bot = mock.Mock()
        bot.get_channel.return_value = self.channel
        for target, attr, value in [
            (db, "DB_FILE", os.path.join(tmp.name, "test.db")),
            (state, "bot", bot),
            (state, "watchlist", {1: ["2330", "IX0001"]}),
            (alert_tasks, "get_stock_info_async", fake_quote),
            (alert_tasks, "is_trading_hours", lambda **kwargs: True),
        ]:
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)
        db.init_db()

    def test_price_alert_shows_volume_not_bid_ask(self):
        db.add_alert(1, "2330", 1000, "above")
        db.add_alert(1, "IX0001", 23500, "below")
        asyncio.run(alert_tasks.price_alert_scan.coro())

        stock_msg = next(m for m in self.channel.sent if "`2330`" in m)
        index_msg = next(m for m in self.channel.sent if "`IX0001`" in m)
        self.assertIn("成交量：**45,678 張**", stock_msg)
        self.assertNotIn("成交量", index_msg)
        self.assertTrue(all("外盤" not in m for m in self.channel.sent))

    def test_volatility_alert_shows_volume_not_bid_ask(self):
        asyncio.run(alert_tasks.watchlist_volatility_alert.coro())

        self.assertEqual(len(self.channel.sent), 1)
        msg = self.channel.sent[0]
        self.assertEqual(msg.count("成交量"), 1)
        self.assertIn("成交量 `45,678 張`", msg)
        self.assertNotIn("外盤", msg)


if __name__ == "__main__":
    unittest.main()
