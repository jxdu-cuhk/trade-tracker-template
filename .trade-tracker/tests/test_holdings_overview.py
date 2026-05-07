from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.historical_curve import SecurityHistoryPoint
from trade_tracker.holdings_overview import holdings_metrics_from_table, reference_float_metrics, render_holdings_account_panel


class FakeCore:
    def normalize_currency(self, value):
        text = str(value or "").strip()
        if text in {"人民币", "CNY"}:
            return "CNY"
        return text

    def normalize_ticker(self, ticker, _currency):
        return str(ticker or "").strip()

    def raw_text(self, value):
        return str(value or "").strip()


class HoldingsOverviewTests(unittest.TestCase):
    def test_holdings_metrics_sum_account_level_values(self):
        table = """
        <table data-summary-kind="holdings">
          <thead><tr>
            <th>最新市值</th><th>持仓成本</th><th>浮动盈亏</th><th>当日盈亏</th><th>币种</th>
          </tr></thead>
          <tbody>
            <tr><td>人民币 100.00</td><td>人民币 80.00</td><td>人民币 20.00</td><td>人民币 2.00</td><td>人民币</td></tr>
            <tr><td>人民币 -40.00</td><td>人民币 50.00</td><td>人民币 -10.00</td><td>人民币 -1.00</td><td>人民币</td></tr>
          </tbody>
        </table>
        """

        metrics = holdings_metrics_from_table(FakeCore(), table)

        self.assertEqual(metrics["asset"], 60)
        self.assertEqual(metrics["market_value"], 140)
        self.assertEqual(metrics["cost"], 130)
        self.assertEqual(metrics["float_pnl"], 10)
        self.assertEqual(metrics["daily_pnl"], 1)

    def test_render_holdings_account_panel_uses_selectable_realized_ranges(self):
        html = render_holdings_account_panel(
            {"count": 1, "asset": 100.0, "market_value": 100.0, "cost": 80.0, "float_pnl": 20.0, "daily_pnl": 2.0},
            {
                "active": "month",
                "ranges": {
                    "month": {"label": "5月已实现盈亏", "pnl": 12.0, "capital": 100.0, "rate": 0.12, "points": []},
                    "three-month": {"label": "近三月已实现盈亏", "pnl": 30.0, "capital": 200.0, "rate": 0.15, "points": []},
                    "year": {"label": "本年已实现盈亏", "pnl": 60.0, "capital": 300.0, "rate": 0.2, "points": []},
                },
            },
        )

        self.assertIn("holdings-account-panel", html)
        self.assertIn("持仓总资产", html)
        self.assertIn("当日参考盈亏", html)
        self.assertIn("data-holdings-reference-card", html)
        self.assertIn(">参考<", html)
        self.assertIn('data-holdings-range="day"', html)
        self.assertIn('data-holdings-range="month"', html)
        self.assertIn('data-holdings-range="three-month"', html)
        self.assertIn('data-holdings-range="year"', html)
        self.assertIn("5月已实现盈亏", html)
        self.assertIn("近三月已实现盈亏", html)
        self.assertIn("本年已实现盈亏", html)

    def test_reference_float_metrics_builds_selectable_unrealized_ranges(self):
        class Cell:
            def __init__(self, raw):
                self.raw = raw

        row = {
            1: Cell("买入"),
            2: Cell(date(2026, 5, 1)),
            4: Cell(None),
            5: Cell("600000"),
            6: Cell("现股"),
            8: Cell(10),
            9: Cell(100),
            11: Cell(1),
            12: Cell(1001),
            20: Cell("人民币"),
        }
        history = {
            ("600000", "人民币"): {
                date(2026, 5, 1): 100.0,
                date(2026, 5, 2): 104.0,
                date(2026, 5, 7): 106.0,
            }
        }

        with (
            patch("trade_tracker.holdings_overview.date") as mock_date,
            patch("trade_tracker.holdings_overview.current_fx_rates_to_cny", return_value={"人民币": 1.0}),
            patch("trade_tracker.holdings_overview.fetch_histories_for_lots", return_value=history),
        ):
            mock_date.today.return_value = date(2026, 5, 7)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)
            metrics = reference_float_metrics(
                FakeCore(),
                [(2, row)],
                {"count": 1, "asset": 1060.0, "cost": 1001.0, "float_pnl": 59.0, "daily_pnl": 20.0},
            )

        self.assertEqual(metrics["active"], "day")
        self.assertIn("day", metrics["ranges"])
        self.assertIn("month", metrics["ranges"])
        self.assertIn("three-month", metrics["ranges"])
        self.assertIn("year", metrics["ranges"])
        self.assertEqual(metrics["ranges"]["month"]["label"], "5月参考盈亏")
        self.assertAlmostEqual(metrics["ranges"]["month"]["pnl"], 60.0)


if __name__ == "__main__":
    unittest.main()
