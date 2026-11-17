from collections.abc import Sequence

VALID_ALERT_DIRECTIONS = {"above", "below"}


def get_alert_direction(target: float, current_price: float) -> str:
    return "above" if target > current_price else "below"


def is_price_alert_triggered(direction: str, current_price: float, target: float) -> bool:
    if direction == "above":
        return current_price >= target
    if direction == "below":
        return current_price <= target
    raise ValueError(f"unknown alert direction: {direction}")


def volatility_level(change_percent: float, thresholds: Sequence[float]) -> float | None:
    """漲跌幅絕對值已達到的最高門檻，帶漲跌正負號；未達任何門檻回傳 None。"""
    reached = [t for t in thresholds if abs(change_percent) >= t]
    if not reached:
        return None
    level = max(reached)
    return level if change_percent > 0 else -level


def next_volatility_level(
    change_percent: float, last_level: float | None, thresholds: Sequence[float]
) -> float | None:
    """階梯去重：同向升階或方向反轉才通知，回傳要記錄的新級距；不需通知回傳 None。"""
    level = volatility_level(change_percent, thresholds)
    if level is None:
        return None
    if last_level is None or (level > 0) != (last_level > 0) or abs(level) > abs(last_level):
        return level
    return None


def validate_alert_target(target: float, current_price: float) -> None:
    """目標價須為正數且不可等於現價（等於現價會在下一輪掃描立即觸發）。"""
    if target <= 0:
        raise ValueError("目標價必須大於 0")
    if target == current_price:
        raise ValueError("目標價不可等於現價")
