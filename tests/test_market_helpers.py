import os
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import _path  # noqa: F401
from stockbot.market_formatting import format_stock_message, format_value
from stockbot.market_search import _tokenize

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("FUGLE_API_KEY", "test-key")

from stockbot.market_clock import is_trading_hours  # noqa: E402


class MarketHelperTest(unittest.TestCase):
    def test_tokenize_splits_long_cjk_keyword_into_pairs(self):
        self.assertEqual(_tokenize("台積電"), ["台積", "電"])
        self.assertEqual(_tokenize("台積電 ADR"), ["台積", "電", "ADR"])

    def test_format_value_uses_ten_thousand_and_hundred_million_units(self):
        self.assertEqual(format_value(50_000), "5.00萬")
        self.assertEqual(format_value(200_000_000), "2.00億")

    def test_format_stock_message_handles_stock_and_index_quotes(self):
        stock_msg = format_stock_message({
            "symbol": "2330",
            "name": "台積電",
            "price": 1000,
            "change": 10,
            "change_percent": 1.0,
            "volume": 1234,
            "value": 50_000,
            "is_index": False,
        })
        index_msg = format_stock_message({
            "symbol": "IX0001",
            "name": "加權指數",
            "price": 20000,
            "change": -20,
            "change_percent": -0.1,
            "volume": None,
            "value": None,
            "is_index": True,
        })

        self.assertIn("台積電（2330）", stock_msg)
        self.assertIn("累計成交額：5.00萬", stock_msg)
        self.assertIn("加權指數（IX0001）", index_msg)
        self.assertIn("最新指數：20000", index_msg)

    def test_is_trading_hours_uses_taipei_weekdays(self):
        tz = ZoneInfo("Asia/Taipei")
        self.assertTrue(is_trading_hours(datetime(2026, 6, 5, 9, 0, tzinfo=tz)))
        self.assertTrue(is_trading_hours(datetime(2026, 6, 5, 13, 30, tzinfo=tz)))
        self.assertFalse(is_trading_hours(datetime(2026, 6, 5, 13, 31, tzinfo=tz)))
        self.assertFalse(is_trading_hours(datetime(2026, 6, 6, 10, 0, tzinfo=tz)))


if __name__ == "__main__":
    unittest.main()
