"""Background task registry."""

from .alerts import price_alert_scan, watchlist_volatility_alert
from .common import _wait_ready
from .news import auto_news_push, breaking_news_scan, market_close_push, market_open_push
from .reports import weekly_report_push


TASK_LOOPS = [
    auto_news_push,
    market_open_push,
    market_close_push,
    breaking_news_scan,
    price_alert_scan,
    watchlist_volatility_alert,
    weekly_report_push,
]

for task_loop in TASK_LOOPS:
    task_loop.before_loop(_wait_ready)


__all__ = [
    "TASK_LOOPS",
    "auto_news_push",
    "breaking_news_scan",
    "market_close_push",
    "market_open_push",
    "price_alert_scan",
    "watchlist_volatility_alert",
    "weekly_report_push",
]
