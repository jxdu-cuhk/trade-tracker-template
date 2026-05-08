from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.option_analysis import build_option_trades, insert_option_analysis_section, render_option_analysis_section


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
        names = {"PDD": "PDD Holdings Inc.", "TICKER_A": "示例A"}
        return names.get(str(ticker or "").strip().upper(), "")

    @staticmethod
    def compute_row_metrics(cells):
        return {
            "pnl": float(cells[13].raw) if 13 in cells else None,
            "capital": float(cells[12].raw) if 12 in cells else None,
            "days": 3.0,
        }


class OptionAnalysisTests(unittest.TestCase):
    def test_build_option_trades_only_uses_closed_options(self):
        rows = [
            (
                2,
                row(
                    kind="卖出",
                    open_date=date(2026, 5, 1),
                    close_date=date(2026, 5, 8),
                    ticker="PDD",
                    event="认沽",
                    capital=9700,
                    pnl=120,
                    currency="美元",
                ),
            ),
            (
                3,
                row(
                    kind="股票",
                    open_date=date(2026, 5, 1),
                    close_date=date(2026, 5, 8),
                    ticker="ticker_a",
                    event="现股",
                    capital=1000,
                    pnl=80,
                    currency="人民币",
                ),
            ),
            (
                4,
                row(
                    kind="卖出",
                    open_date=date(2026, 5, 1),
                    ticker="PDD",
                    event="认沽",
                    capital=9700,
                    pnl=10,
                    currency="美元",
                ),
            ),
        ]

        trades = build_option_trades(FakeCore(), rows)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].ticker, "PDD")
        self.assertEqual(trades[0].name, "PDD Holdings Inc.")
        self.assertEqual(trades[0].pnl, 120)

    def test_render_option_analysis_section_has_independent_tables(self):
        rows = [
            (
                2,
                row(
                    kind="卖出",
                    open_date=date(2026, 5, 1),
                    close_date=date(2026, 5, 8),
                    ticker="PDD",
                    event="认沽",
                    capital=9700,
                    pnl=120,
                    currency="美元",
                ),
            )
        ]

        section = render_option_analysis_section(FakeCore(), rows)

        self.assertIn("期权收益分析", section)
        self.assertIn("期权总览", section)
        self.assertIn("标的拆分", section)
        self.assertIn("期权明细", section)
        self.assertIn('data-option-analysis', section)
        self.assertIn('"code":"PDD"', section)

    def test_insert_option_analysis_before_overview(self):
        html = """
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary"><h2 class="section-title">清仓分析</h2></summary>
        </details>
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary"><h2 class="section-title">总体概览</h2></summary>
        </details>
        """

        updated = insert_option_analysis_section(FakeCore(), html, [])

        self.assertLess(updated.index("清仓分析"), updated.index("期权收益分析"))
        self.assertLess(updated.index("期权收益分析"), updated.index("总体概览"))


if __name__ == "__main__":
    unittest.main()
