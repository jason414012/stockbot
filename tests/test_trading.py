import unittest
from datetime import date

import _path  # noqa: F401
from stockbot.domain.trading import (
    calculate_buy_position,
    calculate_fee,
    calculate_sell_position,
    calculate_tax,
    calc_sell_cost_and_new_avg,
    get_tax_label,
    parse_trade_date,
)


class TradingRulesTest(unittest.TestCase):
    def test_parse_trade_date(self):
        self.assertEqual(parse_trade_date(None, today=date(2026, 6, 5)), "2026-06-05")
        self.assertEqual(parse_trade_date("2026-01-02"), "2026-01-02")
        self.assertIsNone(parse_trade_date("2026/01/02"))

    def test_fee_and_tax_rules(self):
        self.assertEqual(calculate_fee(10, 1), 20)
        self.assertEqual(calculate_fee(1000, 1000), 1425)
        self.assertEqual(calculate_tax(100, 1000, is_etf=False, is_daytrade=False), 300)
        self.assertEqual(calculate_tax(100, 1000, is_etf=False, is_daytrade=True), 150)
        self.assertEqual(calculate_tax(100, 1000, is_etf=True, is_daytrade=False), 100)
        self.assertEqual(calculate_tax(100, 1000, is_etf=True, is_daytrade=True), 50)
        self.assertEqual(calculate_tax(1, 1, is_etf=True, is_daytrade=True), 1)

    def test_tax_label(self):
        self.assertEqual(get_tax_label(False, False), "一般股票 0.3%")
        self.assertEqual(get_tax_label(False, True), "現股當沖 0.15%")
        self.assertEqual(get_tax_label(True, False), "ETF 0.1%")
        self.assertEqual(get_tax_label(True, True), "ETF 當沖 0.05%")

    def test_lifo_sell_cost_and_remaining_average(self):
        transactions = [
            {"type": "buy", "price": 10, "shares": 100, "fee": 20, "date": "2026-06-01"},
            {"type": "buy", "price": 20, "shares": 100, "fee": 20, "date": "2026-06-02"},
            {"type": "sell", "price": 30, "shares": 50, "fee": 20, "tax": 45, "date": "2026-06-03"},
        ]

        sell_cost, new_avg = calc_sell_cost_and_new_avg(transactions, 80)

        self.assertAlmostEqual(sell_cost, 1316.0)
        self.assertAlmostEqual(new_avg, 10.2)

    def test_buy_position_keeps_realized_pnl(self):
        position = {"avg_cost": 10.2, "shares": 100, "realized_pnl": 500.0}

        result = calculate_buy_position(position, price=20, shares=100)

        self.assertEqual(result.fee, 20)
        self.assertEqual(result.shares, 200)
        self.assertEqual(result.realized_pnl, 500.0)
        self.assertAlmostEqual(result.avg_cost, 15.2)

    def test_sell_position_applies_lifo_and_daytrade_tax(self):
        position = {"avg_cost": 15.1, "shares": 200, "realized_pnl": 100.0}
        transactions = [
            {"type": "buy", "price": 10, "shares": 100, "fee": 20, "date": "2026-06-01"},
            {"type": "buy", "price": 20, "shares": 100, "fee": 20, "date": "2026-06-02"},
        ]

        result = calculate_sell_position(
            position,
            transactions,
            price=30,
            shares=100,
            tx_date="2026-06-02",
            is_etf=False,
        )

        self.assertTrue(result.is_daytrade)
        self.assertEqual(result.fee, 20)
        self.assertEqual(result.tax, 4)
        self.assertAlmostEqual(result.sell_cost, 2020.0)
        self.assertAlmostEqual(result.pnl, 956.0)
        self.assertAlmostEqual(result.realized_pnl, 1056.0)
        self.assertAlmostEqual(result.avg_cost, 10.2)
        self.assertEqual(result.shares, 100)


if __name__ == "__main__":
    unittest.main()
