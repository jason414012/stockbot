VALID_ALERT_DIRECTIONS = {"above", "below"}


def get_alert_direction(target: float, current_price: float) -> str:
    return "above" if target > current_price else "below"


def is_price_alert_triggered(direction: str, current_price: float, target: float) -> bool:
    if direction == "above":
        return current_price >= target
    if direction == "below":
        return current_price <= target
    raise ValueError(f"unknown alert direction: {direction}")


def is_volatile(change_percent: float, threshold_percent: float) -> bool:
    return abs(change_percent) >= threshold_percent
