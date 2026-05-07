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
        2: Cell(open_serial),
        4: Cell(close_serial),
        6: Cell("现股"),
        8: Cell(qty),
        9: Cell(price),
        11: Cell(fee),
        12: Cell(capital),
        20: Cell(currency),
    }


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


if __name__ == "__main__":
    unittest.main()
