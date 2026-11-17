from datetime import datetime, timedelta

from .config import TW


def is_trading_hours(now: datetime | None = None, close_grace_min: int = 0) -> bool:
    """平日 09:00–13:30（台北時間）。
    close_grace_min：收盤後延長的分鐘數，讓 13:30 收盤撮合價也能被掃描到。
    """
    current = now or datetime.now(TW)
    if current.tzinfo is None:
        current = current.replace(tzinfo=TW)
    open_time = current.replace(hour=9, minute=0, second=0, microsecond=0)
    close_time = (current.replace(hour=13, minute=30, second=0, microsecond=0)
                  + timedelta(minutes=close_grace_min))
    return current.weekday() < 5 and open_time <= current <= close_time


def in_time_window(now: datetime, hour: int, minute: int, grace_min: int) -> bool:
    """now 是否落在 [hour:minute, hour:minute + grace_min) 之間（定時推播補發用）。"""
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return start <= now < start + timedelta(minutes=grace_min)
