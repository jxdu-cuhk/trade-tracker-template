from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.overview import insert_transaction_fee_metric, split_overview_by_currency


class Cell:
    def __init__(self, raw):
        self.raw = raw


class Core:
    def normalize_currency(self, value):
        mapping = {
            "人民币": "CNY",
            "RMB": "CNY",
            "CNY": "CNY",
            "港币": "HKD",
            "HKD": "HKD",
            "美元": "USD",
            "USD": "USD",
        }
        return mapping.get(str(value or "").strip(), str(value or "").strip().upper())


def overview_shell() -> str:
    return """
        <div class="dashboard-grid">
          <div class="metric-card">
            <div class="metric-label">总盈亏</div>
            <div class="metric-value metric-value-wide">
              <span class="metric-segment value-positive">人民币 100.00</span>
              <span class="metric-separator"> / </span>
              <span class="metric-segment value-negative">港币 -20.00</span>
            </div>
            <div class="metric-note">示例</div>
          </div>
        </div>
    """


class OverviewTests(unittest.TestCase):
    def test_insert_transaction_fee_metric_groups_by_currency(self):
        rows = [
            (2, {11: Cell(2.5), 20: Cell("CNY")}),
            (3, {11: Cell(-3), 20: Cell("HKD")}),
            (4, {11: Cell(0), 20: Cell("USD")}),
        ]

        updated = insert_transaction_fee_metric(Core(), rows, overview_shell())

        self.assertIn("交易费用", updated)
        self.assertIn("人民币 2.50", updated)
        self.assertIn("港币 3.00", updated)
        self.assertNotIn("美元 0.00", updated)

    def test_split_overview_by_currency_includes_transaction_fee_in_reporting_card(self):
        rows = [
            (2, {11: Cell(2.5), 20: Cell("CNY")}),
            (3, {11: Cell(3), 20: Cell("HKD")}),
        ]
        html = insert_transaction_fee_metric(Core(), rows, overview_shell())

        with patch("trade_tracker.overview.current_fx_rates_to_cny", return_value={"人民币": 1.0, "港币": 0.9}):
            updated = split_overview_by_currency(html)

        self.assertIn("<span>交易费用</span>", updated)
        self.assertIn('data-reporting-money-cny="5.200000"', updated)
        self.assertIn(">5.20</strong>", updated)


if __name__ == "__main__":
    unittest.main()
