from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.curve_capital import attach_dynamic_curve_capital


class Cell:
    def __init__(self, raw):
        self.raw = raw


class FakeCore:
    def normalize_currency(self, value):
        return value

    def raw_text(self, value):
        return "" if value is None else str(value)


def row(open_serial, close_serial, qty, price, fee, capital, currency="人民币"):
    return {
        1: Cell("买入"),
        2: Cell(open_serial),
        4: Cell(close_serial),
        6: Cell("现股"),
        8: Cell(qty),
        9: Cell(price),
        11: Cell(fee),
        12: Cell(capital),
        20: Cell(currency),
    }


def option_row(open_serial, close_serial=None, capital=None):
    cells = {
        1: Cell("卖出"),
        2: Cell(open_serial),
        4: Cell(close_serial),
        6: Cell("认沽"),
        7: Cell(100),
        8: Cell(1),
        9: Cell(5),
        11: Cell(1),
        19: Cell(100),
        20: Cell("美元"),
    }
    if capital is not None:
        cells[12] = Cell(capital)
    return cells


class CurveCapitalTests(unittest.TestCase):
    def test_attach_dynamic_curve_capital_uses_active_stock_cost(self):
        data = {
            "curve_series": [
                {
                    "currency": "人民币",
                    "points": [
                        {"serial": 10, "date": "2026/01/10", "value": 0},
                        {"serial": 20, "date": "2026/01/20", "value": 100},
                        {"serial": 30, "date": "2026/01/30", "value": 120},
                    ],
                }
            ]
        }

        attach_dynamic_curve_capital(
            FakeCore(),
            [
                (2, row(10, 20, 100, 10, 2, 1000)),
                (3, row(15, None, 50, 20, 1, 1000)),
            ],
            data,
        )

        points = data["curve_series"][0]["points"]
        self.assertEqual(points[0]["capital"], 1002)
        self.assertEqual(points[1]["capital"], 2003)
        self.assertEqual(points[2]["capital"], 1001)

    def test_history_curve_keeps_its_own_daily_capital(self):
        data = {
            "curve_series": [
                {
                    "currency": "人民币",
                    "source": "history",
                    "points": [{"serial": 20, "date": "2026/01/20", "value": 100, "capital": 235332.1}],
                }
            ]
        }

        attach_dynamic_curve_capital(FakeCore(), [(2, row(10, 30, 258900, 8.2, 0, 2122446))], data)

        self.assertEqual(data["curve_series"][0]["points"][0]["capital"], 235332.1)

    def test_history_curve_adds_only_option_strategy_capital(self):
        data = {
            "curve_series": [
                {
                    "currency": "美元",
                    "source": "history",
                    "capital": 1000,
                    "points": [{"serial": 20, "date": "2026/01/20", "value": 100, "capital": 1000}],
                }
            ]
        }

        attach_dynamic_curve_capital(FakeCore(), [(2, option_row(10))], data)

        self.assertAlmostEqual(data["curve_series"][0]["points"][0]["capital"], 10501.0)
        self.assertAlmostEqual(data["curve_series"][0]["capital"], 10501.0)

    def test_attach_dynamic_curve_capital_uses_cash_secured_put_basis(self):
        data = {
            "curve_series": [
                {
                    "currency": "美元",
                    "points": [
                        {"serial": 10, "date": "2026/01/10", "value": 0},
                        {"serial": 20, "date": "2026/01/20", "value": 100},
                    ],
                }
            ]
        }

        attach_dynamic_curve_capital(FakeCore(), [(2, option_row(10))], data)

        points = data["curve_series"][0]["points"]
        self.assertAlmostEqual(points[0]["capital"], 9501.0)
        self.assertAlmostEqual(points[1]["capital"], 9501.0)
        self.assertAlmostEqual(data["curve_series"][0]["capital"], 9501.0)


if __name__ == "__main__":
    unittest.main()
