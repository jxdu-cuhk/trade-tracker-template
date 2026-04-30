from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.options import build_stock_realized_income_maps, open_option_mark_for_row, patch_dashboard_data_with_options


class Cell:
    def __init__(self, raw):
        self.raw = raw


def row(**values):
    columns = {
        "kind": 1,
        "open_date": 2,
        "exp": 3,
        "close_date": 4,
        "ticker": 5,
        "event": 6,
        "strike": 7,
        "qty": 8,
        "open_price": 9,
        "close_price": 10,
        "fee": 11,
        "capital": 12,
        "pnl": 13,
        "multiplier": 19,
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
    def compute_row_metrics(cells):
        return {"pnl": float(cells[13].raw)}

    @staticmethod
    def row_capital(cells, trade_type, event):
        return float(cells.get(12, Cell(0)).raw or 0)


class RealizedCostAdjustmentTests(unittest.TestCase):
    def test_closed_stock_rows_are_grouped_by_ticker_and_currency(self):
        rows = [
            (
                2,
                row(
                    kind="股票",
                    open_date=46000,
                    close_date=46005,
                    ticker="TICKER_A",
                    event="现股",
                    qty=200,
                    open_price=10,
                    close_price=12,
                    fee=5,
                    pnl=395,
                    currency="人民币",
                ),
            ),
            (
                3,
                row(
                    kind="股票",
                    open_date=46006,
                    ticker="TICKER_A",
                    event="现股",
                    qty=100,
                    open_price=11,
                    pnl=999,
                    currency="人民币",
                ),
            ),
            (
                4,
                row(
                    kind="卖出",
                    open_date=46007,
                    close_date=46008,
                    ticker="TICKER_A",
                    event="认购",
                    qty=1,
                    open_price=0.2,
                    close_price=0,
                    fee=3,
                    pnl=999,
                    multiplier=100,
                    currency="人民币",
                ),
            ),
        ]

        self.assertEqual(build_stock_realized_income_maps(FakeCore(), rows), {("TICKER_A", "人民币"): 395.0})

    def test_patch_dashboard_data_reduces_long_holding_cost_and_syncs_summaries(self):
        current_year = str(date.today().year)
        prior_year = str(date.today().year - 1)
        closed_stock = row(
            kind="股票",
            open_date=46000,
            close_date=46005,
            ticker="TICKER_A",
            event="现股",
            qty=200,
            open_price=10,
            close_price=12,
            fee=5,
            pnl=395,
            currency="人民币",
        )
        data = {
            "holdings": [
                {
                    "ticker": "TICKER_A",
                    "currency": "人民币",
                    "side": "多头",
                    "qty": "1000",
                    "all_in_cost": "人民币 10,000.00",
                    "avg_cost": "人民币 10.00",
                    "market_value": "人民币 11,500.00",
                    "last_price": "人民币 11.50",
                    "float_pnl": "人民币 1,500.00",
                    "daily_pnl": "人民币 120.00",
                }
            ],
            "stock_summary": [
                {
                    "ticker": "TICKER_A",
                    "currency": "人民币",
                    "dividend": "人民币 0.00",
                    "unrealized_pnl": "人民币 1,500.00",
                    "total_pnl": "人民币 1,895.00",
                    "capital_raw": 10_000.0,
                    "capital_days_raw": 100_000.0,
                }
            ],
            "annual_summary": [
                {
                    "year": current_year,
                    "ticker": "TICKER_A",
                    "currency": "人民币",
                    "dividend": "人民币 0.00",
                    "unrealized_pnl": "人民币 1,500.00",
                    "total_pnl": "人民币 1,895.00",
                    "capital_raw": 10_000.0,
                    "capital_days_raw": 100_000.0,
                },
                {
                    "year": prior_year,
                    "ticker": "TICKER_A",
                    "currency": "人民币",
                    "dividend": "人民币 0.00",
                    "unrealized_pnl": "人民币 -50.00",
                    "total_pnl": "人民币 -50.00",
                    "capital_raw": 1_000.0,
                    "capital_days_raw": 10_000.0,
                },
            ],
        }

        patched = patch_dashboard_data_with_options(FakeCore(), [(2, closed_stock)], data)
        holding = patched["holdings"][0]

        self.assertEqual(holding["all_in_cost"], "人民币 9,605.00")
        self.assertEqual(holding["avg_cost"], "人民币 9.61")
        self.assertEqual(holding["float_pnl"], "人民币 1,895.00")
        self.assertEqual(holding["breakeven"], "已回本")
        self.assertEqual(patched["cost_text"], "人民币 9,605.00")
        self.assertEqual(patched["unrealized_pnl_text"], "人民币 1,895.00")
        self.assertEqual(patched["stock_summary"][0]["total_pnl"], "人民币 1,895.00")
        self.assertEqual(patched["annual_summary"][0]["total_pnl"], "人民币 1,895.00")
        self.assertEqual(patched["annual_summary"][1]["total_pnl"], "人民币 -50.00")

    def test_short_holding_uses_inverse_cost_direction(self):
        closed_short = row(
            kind="卖出",
            open_date=46000,
            close_date=46003,
            ticker="TICKER_B",
            event="现股",
            qty=100,
            open_price=10,
            close_price=9,
            fee=2,
            pnl=98,
            currency="人民币",
        )
        data = {
            "holdings": [
                {
                    "ticker": "TICKER_B",
                    "currency": "人民币",
                    "side": "空头",
                    "qty": "-100",
                    "all_in_cost": "人民币 1,000.00",
                    "avg_cost": "人民币 10.00",
                    "market_value": "人民币 -850.00",
                    "last_price": "人民币 8.50",
                    "float_pnl": "人民币 150.00",
                    "daily_pnl": "人民币 0.00",
                }
            ],
            "stock_summary": [],
            "annual_summary": [],
        }

        patched = patch_dashboard_data_with_options(FakeCore(), [(2, closed_short)], data)
        holding = patched["holdings"][0]

        self.assertEqual(holding["all_in_cost"], "人民币 1,098.00")
        self.assertEqual(holding["avg_cost"], "人民币 10.98")
        self.assertEqual(holding["float_pnl"], "人民币 248.00")
        self.assertEqual(holding["breakeven"], "已回本")

    def test_open_cash_secured_put_mark_uses_futu_quote(self):
        open_put = row(
            kind="卖出",
            open_date=46140,
            exp=46170,
            ticker="TICKER_A",
            event="认沽",
            strike=10,
            qty=1,
            open_price=0.5,
            fee=2,
            capital=1000,
            multiplier=100,
            currency="人民币",
        )

        with patch("trade_tracker.options.fetch_futu_option_quote", return_value={"option_code": "OPT", "last_price": 0.2}):
            _key, mark = open_option_mark_for_row(FakeCore(), open_put, {})

        self.assertEqual(mark["current_price"], "0.2")
        self.assertEqual(mark["float_pnl"], "28.00")
        self.assertEqual(mark["float_pnl_class"], "value-positive")
        self.assertEqual(mark["capital"], "1,000.00")


if __name__ == "__main__":
    unittest.main()
