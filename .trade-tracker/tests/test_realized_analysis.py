from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.realized_analysis import (
    build_realized_trades,
    insert_realized_analysis_section,
    render_realized_analysis_section,
    summarize_trades_by_date,
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
        return {"TICKER_A": "示例A", "TICKER_B": "示例B", "TICKER_C": "示例C"}.get(
            str(ticker or "").strip().upper(),
            "",
        )

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


class RealizedAnalysisTests(unittest.TestCase):
    def test_realized_trades_use_close_date_and_skip_open_rows(self):
        trades = build_realized_trades(
            FakeCore(),
            [
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
                        open_date=date(2026, 1, 9),
                        ticker="ticker_b",
                        event="现股",
                        qty=100,
                        capital=900,
                        pnl=80,
                        currency="人民币",
                    ),
                ),
                (
                    4,
                    row(
                        kind="卖出",
                        open_date=date(2026, 1, 6),
                        close_date=date(2026, 1, 10),
                        ticker="ticker_c",
                        event="认购",
                        qty=1,
                        capital=500,
                        pnl=-30,
                        currency="港币",
                    ),
                ),
            ],
        )

        self.assertEqual([trade.row_number for trade in trades], [4, 2])
        self.assertEqual(trades[0].category, "期权")
        self.assertEqual(trades[1].category, "股票")
        self.assertEqual(trades[1].date_iso, "2026-01-10")

    def test_daily_summary_groups_by_realized_day_and_currency(self):
        trades = build_realized_trades(
            FakeCore(),
            [
                (
                    2,
                    row(
                        kind="股票",
                        open_date=date(2026, 2, 1),
                        close_date=date(2026, 2, 3),
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
                        kind="卖出",
                        open_date=date(2026, 2, 1),
                        close_date=date(2026, 2, 3),
                        ticker="ticker_c",
                        event="认沽",
                        qty=1,
                        capital=500,
                        pnl=-20,
                        currency="港币",
                    ),
                ),
            ],
        )

        summaries = summarize_trades_by_date(trades)

        self.assertEqual(summaries["2026-02-03"]["count"], 2)
        self.assertEqual(summaries["2026-02-03"]["wins"], 1)
        self.assertAlmostEqual(summaries["2026-02-03"]["pnl"], 100)
        self.assertAlmostEqual(summaries["2026-02-03"]["by_currency"]["人民币"]["pnl"], 120)
        self.assertAlmostEqual(summaries["2026-02-03"]["by_currency"]["港币"]["pnl"], -20)

    def test_render_realized_section_has_calendar_and_custom_stage_dates(self):
        section = render_realized_analysis_section(
            FakeCore(),
            [
                (
                    2,
                    row(
                        kind="股票",
                        open_date=date(2026, 3, 1),
                        close_date=date(2026, 3, 8),
                        ticker="ticker_a",
                        event="现股",
                        qty=100,
                        capital=1000,
                        pnl=120,
                        currency="人民币",
                    ),
                )
            ],
        )

        self.assertIn("盈亏日历 / 阶段账单", section)
        self.assertIn("每日盈亏", section)
        self.assertIn("阶段账单", section)
        self.assertIn('data-pnl-calendar', section)
        self.assertIn('class="filter-select realized-date-input js-stage-start"', section)
        self.assertIn('class="filter-select realized-date-input js-stage-end"', section)
        self.assertIn('"date":"2026-03-08"', section)
        self.assertIn('"category":"股票"', section)
        self.assertIn("dayToneClass", section)
        self.assertIn("pnl-day-positive", section)
        self.assertIn("pnl-day-negative", section)
        self.assertIn("pnl > 0.000001 && (!stats.best", section)
        self.assertIn("pnl < -0.000001 && (!stats.worst", section)

    def test_insert_realized_section_before_timeline(self):
        html = """
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary"><h2 class="section-title">总体概览</h2></summary>
        </details>
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary"><h2 class="section-title">交易时间线</h2></summary>
        </details>
        """

        updated = insert_realized_analysis_section(FakeCore(), html, [])

        self.assertLess(updated.index("总体概览"), updated.index("盈亏日历 / 阶段账单"))
        self.assertLess(updated.index("盈亏日历 / 阶段账单"), updated.index("交易时间线"))


if __name__ == "__main__":
    unittest.main()
