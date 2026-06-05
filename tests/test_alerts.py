import unittest

from domain.alerts import get_alert_direction, is_price_alert_triggered, is_volatile


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

    def test_volatility_threshold(self):
        self.assertTrue(is_volatile(3.0, 3.0))
        self.assertTrue(is_volatile(-3.1, 3.0))
        self.assertFalse(is_volatile(2.9, 3.0))


if __name__ == "__main__":
    unittest.main()
