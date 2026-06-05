from datetime import datetime

from .config import TW


def is_trading_hours(now: datetime | None = None) -> bool:
    current = now or datetime.now(TW)
    if current.tzinfo is None:
        current = current.replace(tzinfo=TW)
    open_time = current.replace(hour=9, minute=0, second=0, microsecond=0)
    close_time = current.replace(hour=13, minute=30, second=0, microsecond=0)
    return current.weekday() < 5 and open_time <= current <= close_time
