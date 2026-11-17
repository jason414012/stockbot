import asyncio
import os
import tempfile
import unittest
from datetime import date, datetime
from unittest import mock

import _path  # noqa: F401

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("FUGLE_API_KEY", "test-key")

from stockbot.config import TW  # noqa: E402
from stockbot.market_clock import in_time_window, is_trading_hours  # noqa: E402

try:
    import pandas as pd
    from stockbot import db, state
    from stockbot.news import pick_latest_news
    from stockbot.tasks import alerts as alert_tasks
    from stockbot.tasks import news as news_tasks
    from stockbot.tasks import reports
except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime deps
    if exc.name in {"discord", "fugle_marketdata", "feedparser", "pandas"}:
        raise unittest.SkipTest(f"optional runtime dependency not installed: {exc.name}")
    raise


def tw(*args) -> datetime:
    return datetime(*args, tzinfo=TW)


class FakeDatetime(datetime):
    current: datetime = tw(2026, 11, 16, 9, 0)

    @classmethod
    def now(cls, tz=None):
        return cls.current


class FakeChannel:
    def __init__(self):
        self.sent: list = []
        self.calls: list[tuple] = []  # 每次 send 的 (content, embed 標題)

    async def send(self, content=None, embed=None):
        self.calls.append((content, embed.title if embed is not None else None))
        self.sent.append(content if content is not None else embed.title)


class FakeBot:
    def __init__(self, channel):
        self.channel = channel

    def get_channel(self, _channel_id):
        return self.channel


class MarketClockTest(unittest.TestCase):
    def test_close_grace_extends_trading_hours(self):
        self.assertFalse(is_trading_hours(tw(2026, 11, 16, 13, 33)))
        self.assertTrue(is_trading_hours(tw(2026, 11, 16, 13, 33), close_grace_min=5))
        self.assertFalse(is_trading_hours(tw(2026, 11, 16, 13, 36), close_grace_min=5))

    def test_in_time_window(self):
        self.assertTrue(in_time_window(tw(2026, 11, 16, 9, 0), 9, 0, 30))
        self.assertTrue(in_time_window(tw(2026, 11, 16, 9, 29), 9, 0, 30))
        self.assertFalse(in_time_window(tw(2026, 11, 16, 9, 30), 9, 0, 30))
        self.assertFalse(in_time_window(tw(2026, 11, 16, 8, 59), 9, 0, 30))


class PushTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(db, "DB_FILE", os.path.join(self.tmp.name, "test.db"))
        patcher.start()
        self.addCleanup(patcher.stop)
        db.init_db()

        self.channel = FakeChannel()
        for target, attr, value in [
            (state, "bot", FakeBot(self.channel)),
            (state, "pushed_news_ids", set()),
            (state, "watchlist", {}),
        ]:
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)


class MetaTest(PushTestBase):
    def test_meta_round_trip(self):
        self.assertIsNone(db.get_meta("k"))
        db.set_meta("k", "1")
        db.set_meta("k", "2")
        self.assertEqual(db.get_meta("k"), "2")


class DigestTest(PushTestBase):
    NEWS = [
        {"id": f"f{i}", "title": f"F{i}", "link": "", "source": "s",
         "category": "財經", "published": "", "ts": i}
        for i in range(8)
    ] + [{"id": "w", "title": "W", "link": "", "source": "s",
          "category": "國際", "published": "", "ts": 99}]

    def setUp(self):
        super().setUp()

        async def fake_fetch(max_per_source=5):
            return self.NEWS

        for attr, value in [("fetch_latest_news", fake_fetch), ("datetime", FakeDatetime)]:
            p = mock.patch.object(news_tasks, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def run_open(self, now):
        FakeDatetime.current = now
        asyncio.run(news_tasks.market_open_push.coro())

    def test_pick_latest_news_filters_category_and_sorts(self):
        picked = pick_latest_news(self.NEWS, "財經", 3)
        self.assertEqual([n["id"] for n in picked], ["f7", "f6", "f5"])

    def test_digest_includes_already_pushed_and_catches_up(self):
        state.pushed_news_ids.update({"f7", "f6"})
        self.run_open(tw(2026, 11, 16, 9, 12))  # restarted after 09:00
        self.assertIn("最新 5 則", self.channel.sent[0])
        self.assertEqual(self.channel.sent[1:], ["F7", "F6", "F5", "F4", "F3"])
        self.assertEqual(db.get_meta("market_open_pushed"), "2026-11-16")

    def test_digest_sends_once_per_day(self):
        self.run_open(tw(2026, 11, 16, 9, 0))
        sent = len(self.channel.sent)
        self.run_open(tw(2026, 11, 16, 9, 5))
        self.assertEqual(len(self.channel.sent), sent)

    def test_digest_skips_outside_window_and_weekend(self):
        self.run_open(tw(2026, 11, 16, 9, 30))
        self.run_open(tw(2026, 11, 21, 9, 0))  # Saturday
        self.assertEqual(self.channel.sent, [])


class AutoNewsPushTest(PushTestBase):
    """重大新聞速報併入 auto_news_push：每則新聞只推一次，盤中才加速報標頭。"""
    HEADER = "🚨 **【重大新聞速報】**"
    NEWS = [
        {"id": "b", "title": "央行宣布降息", "link": "", "source": "s",
         "category": "財經", "published": "", "ts": 2},
        {"id": "n", "title": "一般新聞", "link": "", "source": "s",
         "category": "財經", "published": "", "ts": 1},
    ]

    def setUp(self):
        super().setUp()

        async def fake_fetch(max_per_source=5):
            # 模擬單一 RSS 來源依 max_per_source 截斷
            return self.NEWS[:max_per_source]

        self.trading = True
        for attr, value in [("fetch_latest_news", fake_fetch),
                            ("is_trading_hours", lambda: self.trading)]:
            p = mock.patch.object(news_tasks, attr, value)
            p.start()
            self.addCleanup(p.stop)

    def run_push(self):
        asyncio.run(news_tasks.auto_news_push.coro())

    def news_calls(self) -> dict:
        """embed 標題 → 同一則訊息的 content（無標頭為 None）。"""
        return {title: content for content, title in self.channel.calls if title is not None}

    def test_breaking_header_during_trading_hours(self):
        self.run_push()
        calls = self.news_calls()
        # 標頭與重大新聞 embed 必須在同一則訊息，一般新聞不加
        self.assertTrue(calls["央行宣布降息"].startswith(self.HEADER))
        self.assertIsNone(calls["一般新聞"])
        self.assertFalse(any(c and c.startswith(self.HEADER) and t is None
                             for c, t in self.channel.calls))

    def test_no_breaking_header_after_hours(self):
        self.trading = False
        self.run_push()
        self.assertIsNone(self.news_calls()["央行宣布降息"])
        self.assertFalse(any(c and c.startswith(self.HEADER) for c, _ in self.channel.calls))

    def test_each_news_pushed_only_once(self):
        self.run_push()
        self.run_push()
        titles = [t for _, t in self.channel.calls]
        self.assertEqual(titles.count("央行宣布降息"), 1)
        self.assertEqual(titles.count("一般新聞"), 1)
        self.assertEqual(sum(bool(c and c.startswith(self.HEADER)) for c, _ in self.channel.calls), 1)

    def test_breaking_news_ranked_fifth_still_pushed(self):
        # 重大新聞只剩 auto_news_push 這條路徑；每來源抓少於 5 則會漏掉排名較後的速報
        self.NEWS = [
            {"id": f"n{i}", "title": f"一般新聞{i}", "link": "", "source": "s",
             "category": "財經", "published": "", "ts": 10 - i}
            for i in range(4)
        ] + [{"id": "b5", "title": "央行宣布降息", "link": "", "source": "s",
              "category": "財經", "published": "", "ts": 1}]
        self.run_push()
        calls = self.news_calls()
        self.assertIn("央行宣布降息", calls)
        self.assertTrue(calls["央行宣布降息"].startswith(self.HEADER))

    def test_failed_send_skips_item_and_keeps_pushing(self):
        # 單則發送失敗不可中斷推播（例外會終止 tasks.loop），且失敗那則不每分鐘重送
        real_send = self.channel.send

        async def flaky_send(content=None, embed=None):
            if embed is not None and embed.title == "央行宣布降息":
                raise RuntimeError("bad embed")
            await real_send(content, embed)

        with mock.patch.object(self.channel, "send", flaky_send), \
                self.assertLogs(news_tasks.logger, "WARNING"):
            self.run_push()
            self.run_push()
        titles = [t for _, t in self.channel.calls]
        self.assertEqual(titles.count("一般新聞"), 1)
        self.assertIn("b", state.pushed_news_ids)

    def test_breaking_news_scan_task_removed(self):
        # 舊的獨立速報任務會重推 auto_news_push 推過的新聞，不得再存在
        self.assertFalse(hasattr(news_tasks, "breaking_news_scan"))


class AlertTaskTestBase(PushTestBase):
    def setUp(self):
        super().setUp()
        self.quotes: dict = {}

        async def fake_quote(sym):
            q = self.quotes[sym]
            if isinstance(q, Exception):
                raise q
            return q

        FakeDatetime.current = tw(2026, 11, 16, 10, 0)
        for target, attr, value in [
            (alert_tasks, "get_stock_info_async", fake_quote),
            (alert_tasks, "is_trading_hours", lambda **kw: True),
            (alert_tasks, "datetime", FakeDatetime),
            (state, "volatility_notified", {}),
            (state, "volatility_last_reset_date", None),
        ]:
            p = mock.patch.object(target, attr, value)
            p.start()
            self.addCleanup(p.stop)

    @staticmethod
    def quote(pct, price=100.0, name="n"):
        return {"name": name, "price": price, "change_percent": pct, "volume": 1000}


class VolatilityAlertTest(AlertTaskTestBase):
    def run_scan(self, now=None):
        if now is not None:
            FakeDatetime.current = now
        asyncio.run(alert_tasks.watchlist_volatility_alert.coro())

    def test_same_level_not_repeated_but_step_up_alerts(self):
        state.watchlist.update({1: ["2330"]})
        self.quotes["2330"] = self.quote(4.0)
        self.run_scan()
        self.assertEqual(len(self.channel.sent), 1)
        self.assertIn("2330", self.channel.sent[0])
        self.assertEqual(state.volatility_notified[(1, "2330")], 3.0)

        # 同級距（仍 +4%）：不再 @ 使用者，且整則訊息不發
        self.run_scan(tw(2026, 11, 16, 10, 5))
        self.assertEqual(len(self.channel.sent), 1)

        # 漲幅擴大到 +5.2% 跨過 +5 門檻：再通知一次
        self.quotes["2330"] = self.quote(5.2)
        self.run_scan(tw(2026, 11, 16, 10, 10))
        self.assertEqual(len(self.channel.sent), 2)
        self.assertIn("2330", self.channel.sent[1])
        self.assertEqual(state.volatility_notified[(1, "2330")], 5.0)

        # +5.5% 仍在 +5 級距：不發
        self.quotes["2330"] = self.quote(5.5)
        self.run_scan(tw(2026, 11, 16, 10, 15))
        self.assertEqual(len(self.channel.sent), 2)

    def test_step_up_message_only_contains_changed_symbol(self):
        state.watchlist.update({1: ["2330", "2317"]})
        self.quotes.update({"2330": self.quote(4.0), "2317": self.quote(4.0)})
        self.run_scan()
        self.quotes.update({"2330": self.quote(5.2), "2317": self.quote(4.5)})
        self.run_scan(tw(2026, 11, 16, 10, 5))
        self.assertEqual(len(self.channel.sent), 2)
        self.assertIn("2330", self.channel.sent[1])
        self.assertNotIn("2317", self.channel.sent[1])

    def test_reversal_alerts_but_pullback_does_not(self):
        state.watchlist.update({1: ["2330"]})
        self.quotes["2330"] = self.quote(5.5)
        self.run_scan()
        # 回落但未反向跨 -3%：不通知、紀錄不變
        for minute, pct in ((5, 3.5), (10, 1.0), (15, -2.0)):
            self.quotes["2330"] = self.quote(pct)
            self.run_scan(tw(2026, 11, 16, 10, minute))
        self.assertEqual(len(self.channel.sent), 1)
        self.assertEqual(state.volatility_notified[(1, "2330")], 5.0)

        # 由漲翻跌跨過 -3%：通知並記錄 -3
        self.quotes["2330"] = self.quote(-3.1)
        self.run_scan(tw(2026, 11, 16, 10, 20))
        self.assertEqual(len(self.channel.sent), 2)
        self.assertIn("-3.10%", self.channel.sent[1])
        self.assertEqual(state.volatility_notified[(1, "2330")], -3.0)

    def test_repeat_round_only_sends_new_symbols(self):
        state.watchlist.update({1: ["2330", "2317"]})
        self.quotes.update({"2330": self.quote(4.0), "2317": self.quote(1.0)})
        self.run_scan()
        self.quotes["2317"] = self.quote(-5.0)
        self.run_scan(tw(2026, 11, 16, 10, 5))
        self.assertEqual(len(self.channel.sent), 2)
        self.assertIn("2317", self.channel.sent[1])
        self.assertNotIn("2330", self.channel.sent[1])

    def test_resets_next_day(self):
        state.watchlist.update({1: ["2330"]})
        self.quotes["2330"] = self.quote(4.0)
        self.run_scan()
        self.run_scan(tw(2026, 11, 17, 9, 5))
        self.assertEqual(len(self.channel.sent), 2)

    def test_each_user_alerted_separately(self):
        state.watchlist.update({1: ["2330"], 2: ["2330"]})
        self.quotes["2330"] = self.quote(4.0)
        self.run_scan()
        self.run_scan(tw(2026, 11, 16, 10, 5))
        self.assertEqual(len(self.channel.sent), 2)
        self.assertTrue(any("<@1>" in m for m in self.channel.sent))
        self.assertTrue(any("<@2>" in m for m in self.channel.sent))

    def test_watch_add_during_send_does_not_stop_loop(self):
        # send 期間 /watch add 新增使用者，舊寫法會丟 dict changed size 終止 tasks.loop
        state.watchlist.update({1: ["2330"], 2: ["2330"]})
        self.quotes["2330"] = self.quote(4.0)
        real_send = self.channel.send

        async def send_then_watch_add(content=None, embed=None):
            state.watchlist.setdefault(3, ["2330"])
            await real_send(content, embed)

        with mock.patch.object(self.channel, "send", send_then_watch_add):
            self.run_scan()
        self.assertEqual(len(self.channel.sent), 2)

    def test_failed_send_is_not_marked_and_retried_same_day(self):
        # 發送失敗不可記為已推，否則使用者當日永遠收不到該檔警示
        state.watchlist.update({1: ["2330"]})
        self.quotes["2330"] = self.quote(4.0)
        real_send = self.channel.send
        fails = [RuntimeError("discord down")]

        async def flaky_send(content=None, embed=None):
            if fails:
                raise fails.pop()
            await real_send(content, embed)

        with mock.patch.object(self.channel, "send", flaky_send), \
                self.assertLogs(alert_tasks.logger, "WARNING"):
            self.run_scan()
            self.assertNotIn((1, "2330"), state.volatility_notified)
            # 下一輪同級距：因未記錄，仍會重送
            self.run_scan(tw(2026, 11, 16, 10, 5))
        self.assertEqual(len(self.channel.sent), 1)
        self.assertEqual(state.volatility_notified[(1, "2330")], 3.0)

    def test_quote_failure_logs_symbol_and_continues(self):
        state.watchlist.update({1: ["9999", "2330"]})
        self.quotes.update({"9999": RuntimeError("boom"), "2330": self.quote(4.0)})
        with self.assertLogs(alert_tasks.logger, "WARNING") as logs:
            self.run_scan()
        self.assertTrue(any("9999" in line and "boom" in line for line in logs.output))
        self.assertEqual(len(self.channel.sent), 1)
        self.assertIn("2330", self.channel.sent[0])


class PriceAlertScanTest(AlertTaskTestBase):
    def test_quote_failure_logs_symbol_and_other_alerts_still_fire(self):
        db.add_alert(1, "9999", 50.0, "above")
        db.add_alert(1, "2330", 50.0, "above")
        self.quotes.update({"9999": RuntimeError("boom"), "2330": self.quote(0.0, price=60.0)})
        with self.assertLogs(alert_tasks.logger, "WARNING") as logs:
            asyncio.run(alert_tasks.price_alert_scan.coro())
        self.assertTrue(any("9999" in line and "boom" in line for line in logs.output))
        self.assertEqual(len(self.channel.sent), 1)
        self.assertIn("2330", self.channel.sent[0])
        # 報價失敗的警示不可被刪除，下次仍要掃描
        self.assertEqual([a["symbol"] for a in db.list_all_alerts()], ["9999"])


class WeeklyReportTest(PushTestBase):
    FRIDAY = tw(2026, 11, 20, 14, 5)

    def candles(self):
        days = [date(2026, 11, 12), date(2026, 11, 13), date(2026, 11, 16),
                date(2026, 11, 17), date(2026, 11, 18), date(2026, 11, 19)]
        return pd.DataFrame([
            {"date": pd.Timestamp(d), "open": 100 + i, "high": 110 + i,
             "low": 90 + i, "close": 105 + i}
            for i, d in enumerate(days)
        ])

    def test_weekly_row_uses_this_week_and_fills_today(self):
        quote = {"name": "台積電", "price": 120.0, "date": "2026-11-20",
                 "open": 119, "high": 130, "low": 95}
        with mock.patch.object(reports, "get_candles", lambda s, days=10: self.candles()), \
                mock.patch.object(reports, "get_stock_info", lambda s: quote):
            row = reports.weekly_row("2330", now=self.FRIDAY)
        # 週一 11/16 開盤 102 → 今日補上的收盤 120
        self.assertEqual(row["週漲跌%"], f"{(120 - 102) / 102 * 100:+.2f}")
        self.assertEqual((row["週高"], row["週低"], row["收盤"]), ("130.00", "92.00", "120.00"))

    def test_weekly_row_does_not_fill_stale_quote(self):
        quote = {"name": "台積電", "price": 120.0, "date": "2026-11-19",
                 "open": 1, "high": 1, "low": 1}
        with mock.patch.object(reports, "get_candles", lambda s, days=10: self.candles()), \
                mock.patch.object(reports, "get_stock_info", lambda s: quote):
            row = reports.weekly_row("2330", now=self.FRIDAY)
        self.assertEqual((row["週高"], row["收盤"]), ("115.00", "110.00"))

    def test_weekly_push_dedupes_symbols_and_sends_once_per_week(self):
        state.watchlist.update({1: ["2330"], 2: ["2330", "9999"]})
        calls = []

        def fake_row(sym):
            calls.append(sym)
            if sym == "9999":
                raise RuntimeError("boom")
            return {"代號": sym, "名稱": "n", "週漲跌%": "+1.00",
                    "週高": "1", "週低": "1", "收盤": "1"}

        FakeDatetime.current = self.FRIDAY
        with mock.patch.object(reports, "weekly_row", fake_row), \
                mock.patch.object(reports, "datetime", FakeDatetime):
            asyncio.run(reports.weekly_report_push.coro())
            asyncio.run(reports.weekly_report_push.coro())

        self.assertEqual(sorted(calls), ["2330", "9999"])
        self.assertEqual(len(self.channel.sent), 2)
        self.assertEqual(db.get_meta(reports.WEEKLY_META_KEY), "2026-W47")


if __name__ == "__main__":
    unittest.main()
