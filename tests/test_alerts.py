import unittest

import _path  # noqa: F401
from stockbot.domain.alerts import (
    get_alert_direction,
    is_price_alert_triggered,
    next_volatility_level,
    validate_alert_target,
    volatility_level,
)

THRESHOLDS = (3.0, 5.0, 7.0, 9.0)


class AlertRulesTest(unittest.TestCase):
    def test_get_alert_direction(self):
        self.assertEqual(get_alert_direction(target=105, current_price=100), "above")
        self.assertEqual(get_alert_direction(target=95, current_price=100), "below")
        self.assertEqual(get_alert_direction(target=100, current_price=100), "below")

    def test_price_alert_trigger(self):
        self.assertTrue(is_price_alert_triggered("above", current_price=105, target=100))
        self.assertFalse(is_price_alert_triggered("above", current_price=95, target=100))
        self.assertTrue(is_price_alert_triggered("below", current_price=95, target=100))
        self.assertFalse(is_price_alert_triggered("below", current_price=105, target=100))

    def test_unknown_direction_raises(self):
        with self.assertRaises(ValueError):
            is_price_alert_triggered("sideways", current_price=100, target=100)

    def test_volatility_level_is_highest_reached_threshold_with_sign(self):
        cases = [
            (5.6, 5.0), (-3.0, -3.0), (2.9, None), (-2.9, None),
            (3.0, 3.0), (7.4, 7.0), (-6.0, -5.0), (9.8, 9.0), (0.0, None),
        ]
        for pct, expected in cases:
            with self.subTest(pct=pct):
                self.assertEqual(volatility_level(pct, THRESHOLDS), expected)

    def test_next_volatility_level_ladder_dedup(self):
        # 只在同向升階或方向反轉時通知，避免同級距洗版又不漏掉擴大／反轉
        cases = [
            # (情境, 已記錄, 本輪漲跌幅, 預期新紀錄；None = 不通知)
            ("首次達門檻", None, 3.2, 3.0),
            ("同級距持續", 3.0, 4.9, None),
            ("同向升階", 3.0, 5.1, 5.0),
            ("跳階只記最高", 3.0, 7.4, 7.0),
            ("回落未反轉", 5.0, 3.5, None),
            ("回落未反轉", 5.0, 1.0, None),
            ("回落未反轉", 5.0, -2.0, None),
            ("方向反轉", 5.0, -3.1, -3.0),
            ("反轉後跳階", 5.0, -6.0, -5.0),
            ("反轉後再回原方向", -3.0, 5.2, 5.0),
            ("未達門檻", None, 2.9, None),
            ("未達門檻", None, -2.9, None),
            ("超過最高門檻", 9.0, 9.8, None),
            ("跌勢同向升階", -3.0, -5.0, -5.0),
            ("跌勢同級距", -5.0, -6.9, None),
        ]
        for name, last, pct, expected in cases:
            with self.subTest(name=name, last=last, pct=pct):
                self.assertEqual(next_volatility_level(pct, last, THRESHOLDS), expected)

    def test_alert_target_must_be_positive(self):
        for target in (0, -1.5):
            with self.assertRaises(ValueError):
                validate_alert_target(target, current_price=100)

    def test_alert_target_equal_to_current_price_rejected(self):
        # 等於現價時方向判為 below，下一輪掃描 price <= target 立即觸發
        self.assertTrue(is_price_alert_triggered(get_alert_direction(100, 100), 100, 100))
        with self.assertRaisesRegex(ValueError, "目標價不可等於現價"):
            validate_alert_target(100, current_price=100)

    def test_alert_target_valid(self):
        validate_alert_target(105, current_price=100)
        validate_alert_target(95, current_price=100)


if __name__ == "__main__":
    unittest.main()
