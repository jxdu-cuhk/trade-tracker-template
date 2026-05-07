from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.dashboard_layout import apply_tonghuashun_curve_style, collapse_secondary_sections, reorder_dashboard_sections


def section(title: str, body: str = "") -> str:
    return f"""
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary"><h2 class="section-title">{title}</h2></summary>
          <div class="section-body">{body}</div>
        </details>
"""


class DashboardLayoutTests(unittest.TestCase):
    def test_reorder_dashboard_sections_uses_requested_heading_order(self):
        html = (
            "<main>"
            + section("总体概览")
            + section("总收益曲线")
            + section("当前持仓")
            + section("未平仓期权")
            + section("分年度个股汇总")
            + section("盈亏日历 / 阶段账单")
            + section("清仓分析")
            + section("交易时间线")
            + section("工作表入口")
            + "</main>"
        )

        updated = reorder_dashboard_sections(html)
        titles = [
            "当前持仓",
            "未平仓期权",
            "盈亏日历 / 阶段账单",
            "清仓分析",
            "总体概览",
            "总收益曲线",
            "分年度个股汇总",
            "交易时间线",
            "工作表入口",
        ]

        positions = [updated.index(f"<h2 class=\"section-title\">{title}</h2>") for title in titles]
        self.assertEqual(positions, sorted(positions))

    def test_apply_tonghuashun_curve_style_inserts_local_benchmark_shell(self):
        html = (
            '<div class="currency-overview-card currency-overview-cny-card">'
            '<span>总盈亏</span><strong class="value-positive">460,060.03</strong>'
            '<span>总收益率</span><strong class="value-positive">2.11%</strong>'
            "</div>"
            "<script>document.querySelector('details[data-ths-return-curve]')</script>"
            + section(
                "总收益曲线",
                '<div class="curve-grid" data-ths-curve-grid><div class="curve-card"><svg class="curve-svg"></svg></div></div>',
            )
        )

        updated = apply_tonghuashun_curve_style(html)
        updated_again = apply_tonghuashun_curve_style(updated)

        self.assertIn("data-ths-return-curve", updated)
        self.assertIn("ths-curve-hero", updated)
        self.assertIn("460,060.03", updated)
        self.assertIn("2.11%", updated)
        self.assertIn("上证指数", updated)
        self.assertIn("超额收益", updated)
        self.assertIn('data-curve-mode="excess"', updated)
        self.assertLess(updated.index("ths-curve-hero"), updated.index("curve-grid"))
        self.assertLess(updated.index("curve-grid"), updated.index("ths-curve-summary"))
        self.assertEqual(updated, updated_again)

    def test_collapse_secondary_sections_only_keeps_current_and_options_open(self):
        html = (
            "<main>"
            + section("当前持仓")
            + section("未平仓期权")
            + section("盈亏日历 / 阶段账单")
            + section("总收益曲线")
            + "</main>"
        )

        updated = collapse_secondary_sections(html)

        self.assertIn('<h2 class="section-title">当前持仓</h2>', updated)
        self.assertIn('<h2 class="section-title">未平仓期权</h2>', updated)
        self.assertRegex(updated, r'<details class="dashboard-section section-collapsible" open>\s*<summary[^>]*><h2 class="section-title">当前持仓</h2>')
        self.assertRegex(updated, r'<details class="dashboard-section section-collapsible" open>\s*<summary[^>]*><h2 class="section-title">未平仓期权</h2>')
        self.assertRegex(updated, r'<details class="dashboard-section section-collapsible">\s*<summary[^>]*><h2 class="section-title">盈亏日历 / 阶段账单</h2>')
        self.assertRegex(updated, r'<details class="dashboard-section section-collapsible">\s*<summary[^>]*><h2 class="section-title">总收益曲线</h2>')


if __name__ == "__main__":
    unittest.main()
