import os
import unittest

import _path  # noqa: F401

os.environ.setdefault("DISCORD_TOKEN", "test-token")
os.environ.setdefault("FUGLE_API_KEY", "test-key")


class TaskRegistryTest(unittest.TestCase):
    def test_seven_background_tasks_are_registered_with_before_loop(self):
        try:
            from stockbot import tasks
        except ModuleNotFoundError as exc:
            if exc.name in {"discord", "fugle_marketdata"}:
                self.skipTest(f"optional runtime dependency not installed: {exc.name}")
            raise

        expected_names = [
            "auto_news_push",
            "market_open_push",
            "market_close_push",
            "breaking_news_scan",
            "price_alert_scan",
            "watchlist_volatility_alert",
            "weekly_report_push",
        ]

        self.assertEqual([loop.coro.__name__ for loop in tasks.TASK_LOOPS], expected_names)
        self.assertEqual(len(tasks.TASK_LOOPS), 7)
        self.assertTrue(all(getattr(loop, "_before_loop", None) is not None for loop in tasks.TASK_LOOPS))


if __name__ == "__main__":
    unittest.main()
