from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.performance_report import insert_performance_report_section


def section(title: str, attrs: str = "") -> str:
    return f"""
        <details class="dashboard-section section-collapsible" open {attrs}>
          <summary class="section-summary"><h2 class="section-title">{title}</h2></summary>
          <div class="section-body"></div>
        </details>
"""


class PerformanceReportTests(unittest.TestCase):
    def test_insert_performance_report_after_return_curve(self):
        html = "<main>" + section("总收益曲线", "data-ths-return-curve") + section("分年度个股汇总") + "</main>"

        updated = insert_performance_report_section(html)
        updated_again = insert_performance_report_section(updated)

        self.assertEqual(updated, updated_again)
        self.assertIn("data-performance-report", updated)
        self.assertIn("data-report-mode-control", updated)
        self.assertIn('data-report-mode="amount"', updated)
        self.assertIn('data-report-mode="rate"', updated)
        self.assertIn("账户涨跌", updated)
        self.assertIn("盈亏对比", updated)
        self.assertIn("盈亏日历", updated)
        self.assertIn("个股盈亏", updated)
        self.assertIn("data-report-title", updated)
        self.assertIn("maxGrowth", updated)
        self.assertIn("accountTotalReturn", updated)
        self.assertIn("maxAmountDrawdown", updated)
        self.assertIn("rateGrowthSwing", updated)
        self.assertIn("amountGrowthSwing", updated)
        self.assertIn("累计收益", updated)
        self.assertIn("renderSwingCards", updated)
        self.assertIn("renderCompare", updated)
        self.assertIn("renderAllPerformance", updated)
        self.assertIn("updateModeButtons", updated)
        self.assertIn("formatMetric", updated)
        self.assertIn("secondary.hidden = reportMode === 'rate'", updated)
        self.assertIn("data-report-calendar-chart", updated)
        self.assertIn("data-report-calendar-month-count", updated)
        self.assertIn("data-report-stock-list", updated)
        self.assertIn("renderStockPanel", updated)
        self.assertIn("stockItemsFromRealizedMonth", updated)
        self.assertIn("selectedMonthKey", updated)
        self.assertIn("data-report-month", updated)
        self.assertIn("data-realized-payload", updated)
        self.assertIn("data-performance-stock-payload", updated)
        self.assertIn("data-report-stock-count", updated)
        self.assertIn("stockItemsForMonth", updated)
        self.assertIn("positiveMax", updated)
        self.assertIn("negativeMax", updated)
        self.assertIn("stockTreemapLayout", updated)
        self.assertIn("stockMetricValue", updated)
        self.assertIn("absPnl", updated)
        self.assertIn("row.dataset.year || ''", updated)
        self.assertIn("盈利个股", updated)
        self.assertIn("折人民币", updated)
        self.assertIn("收益率", updated)
        self.assertLess(updated.index("总收益曲线"), updated.index("收益报告"))
        self.assertLess(updated.index("收益报告"), updated.index("分年度个股汇总"))


if __name__ == "__main__":
    unittest.main()
