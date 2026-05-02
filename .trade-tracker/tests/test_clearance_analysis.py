from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.clearance_analysis import (
    build_clearance_cycles,
    insert_clearance_analysis_section,
    render_clearance_analysis_section,
    summarize_clearance_cycles,
)


class Cell:
    def __init__(self, raw):
        self.raw = raw


def row(**values):
    columns = {
        "kind": 1,
        "open_date": 2,
        "close_date": 4,
        "ticker": 5,
        "event": 6,
        "qty": 8,
        "capital": 12,
        "pnl": 13,
        "currency": 20,
    }
    return {columns[key]: Cell(value) for key, value in values.items()}


class FakeCore:
    @staticmethod
    def raw_text(value):
        return "" if value is None else str(value)

    @staticmethod
    def normalize_ticker(ticker, currency=""):
        return str(ticker or "").strip().upper()

    @staticmethod
    def normalize_currency(currency):
        mapping = {"人民币": "CNY", "港币": "HKD", "美元": "USD"}
        return mapping.get(str(currency or "").strip(), str(currency or "").strip().upper())

    @staticmethod
    def lookup_security_name(ticker, currency="", allow_online=False):
        return {"TICKER_A": "示例A", "TICKER_B": "示例B"}.get(str(ticker or "").strip().upper(), "")

    @staticmethod
    def compute_row_metrics(cells):
        open_date = cells[2].raw
        close_date = cells.get(4, Cell(None)).raw
        days = max((close_date - open_date).days, 1) if isinstance(open_date, date) and isinstance(close_date, date) else 1
        return {
            "pnl": float(cells[13].raw) if 13 in cells else None,
            "capital": float(cells[12].raw) if 12 in cells else None,
            "days": float(days),
        }


class ClearanceAnalysisTests(unittest.TestCase):
    def test_clearance_cycles_stop_at_flat_positions_and_skip_open_holdings(self):
        rows = [
            (
                2,
                row(
                    kind="股票",
                    open_date=date(2026, 1, 5),
                    close_date=date(2026, 1, 10),
                    ticker="ticker_a",
                    event="现股",
                    qty=100,
                    capital=1000,
                    pnl=120,
                    currency="人民币",
                ),
            ),
            (
                3,
                row(
                    kind="股票",
                    open_date=date(2026, 1, 20),
                    ticker="ticker_a",
                    event="现股",
                    qty=50,
                    capital=600,
                    currency="人民币",
                ),
            ),
            (
                4,
                row(
                    kind="股票",
                    open_date=date(2026, 2, 1),
                    close_date=date(2026, 2, 3),
                    ticker="ticker_b",
                    event="现股",
                    qty=100,
                    capital=1000,
                    pnl=-80,
                    currency="人民币",
                ),
            ),
        ]

        cycles = build_clearance_cycles(FakeCore(), rows)

        self.assertEqual([cycle.ticker for cycle in cycles], ["TICKER_B", "TICKER_A"])
        self.assertEqual(cycles[0].clear_date, date(2026, 2, 3))
        self.assertEqual(cycles[0].pnl, -80)
        self.assertEqual(cycles[1].clear_date, date(2026, 1, 10))
        self.assertEqual(cycles[1].pnl, 120)

    def test_monthly_and_yearly_summaries_use_clear_date(self):
        cycles = build_clearance_cycles(
            FakeCore(),
            [
                (
                    2,
                    row(
                        kind="股票",
                        open_date=date(2025, 12, 30),
                        close_date=date(2026, 1, 2),
                        ticker="ticker_a",
                        event="现股",
                        qty=100,
                        capital=1000,
                        pnl=100,
                        currency="人民币",
                    ),
                ),
                (
                    3,
                    row(
                        kind="股票",
                        open_date=date(2026, 1, 8),
                        close_date=date(2026, 1, 9),
                        ticker="ticker_b",
                        event="现股",
                        qty=100,
                        capital=500,
                        pnl=-20,
                        currency="人民币",
                    ),
                ),
            ],
        )

        monthly = summarize_clearance_cycles(cycles, "month")
        yearly = summarize_clearance_cycles(cycles, "year")

        self.assertEqual(len(monthly), 1)
        self.assertEqual(monthly[0].period, "2026-01")
        self.assertEqual(monthly[0].clear_count, 2)
        self.assertAlmostEqual(monthly[0].win_rate, 0.5)
        self.assertEqual(monthly[0].pnl, 80)
        self.assertEqual(yearly[0].period, "2026年")

    def test_render_clearance_section_uses_selectable_period_detail_view(self):
        rows = [
            (
                2,
                row(
                    kind="股票",
                    open_date=date(2026, 1, 5),
                    close_date=date(2026, 1, 10),
                    ticker="ticker_a",
                    event="现股",
                    qty=100,
                    capital=1000,
                    pnl=120,
                    currency="人民币",
                ),
            )
        ]

        section = render_clearance_analysis_section(FakeCore(), rows)

        self.assertIn("清仓分析", section)
        self.assertIn("统计粒度", section)
        self.assertIn("阶段汇总", section)
        self.assertIn("清仓明细", section)
        self.assertIn('data-clearance-detail-table', section)
        self.assertIn('data-clearance-month="2026-01"', section)
        self.assertIn('data-clearance-year="2026年"', section)
        self.assertNotIn("月度清仓", section)
        self.assertNotIn("年度清仓", section)

    def test_insert_clearance_section_before_timeline_not_first_section(self):
        html = """
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary"><h2 class="section-title">总体概览</h2></summary>
        </details>
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary"><h2 class="section-title">交易时间线</h2></summary>
        </details>
        """

        updated = insert_clearance_analysis_section(FakeCore(), html, [])

        self.assertLess(updated.index("总体概览"), updated.index("清仓分析"))
        self.assertLess(updated.index("清仓分析"), updated.index("交易时间线"))


if __name__ == "__main__":
    unittest.main()
