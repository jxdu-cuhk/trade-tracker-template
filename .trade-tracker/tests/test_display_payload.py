from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.display_payload import build_display_payload


class Cell:
    def __init__(self, raw):
        self.raw = raw


class FakeCore:
    def normalize_currency(self, value):
        text = str(value or "").strip()
        return {"人民币": "CNY", "港币": "HKD", "美元": "USD"}.get(text, text)

    def normalize_ticker(self, ticker, _currency=""):
        return str(ticker or "").strip().upper()

    def raw_text(self, value):
        return "" if value is None else str(value)

    def compute_row_metrics(self, cells):
        return {"pnl": float(cells[13].raw), "capital": float(cells[12].raw), "days": 1.0}

    def lookup_security_name(self, _ticker, _currency="", _allow_online=False):
        return ""


def short_put_row():
    return {
        1: Cell("卖出"),
        2: Cell(date(2026, 5, 1)),
        3: Cell(date(2026, 5, 31)),
        4: Cell(None),
        5: Cell("600000"),
        6: Cell("认沽"),
        7: Cell(50),
        8: Cell(1),
        12: Cell(5000),
        19: Cell(100),
        20: Cell("人民币"),
    }


def realized_row():
    return {
        1: Cell("股票"),
        2: Cell(date(2026, 5, 1)),
        4: Cell(date(2026, 5, 8)),
        5: Cell("aaa"),
        6: Cell("现股"),
        12: Cell(1000),
        13: Cell(120),
        20: Cell("人民币"),
    }


class DisplayPayloadTests(unittest.TestCase):
    def test_holdings_totals_are_account_level_cny_values(self):
        data = {
            "holdings": [
                {
                    "ticker": "AAA",
                    "name": "A",
                    "currency": "人民币",
                    "market_value": "人民币 100.00",
                    "all_in_cost": "人民币 80.00",
                    "float_pnl": "人民币 20.00",
                    "daily_pnl": "人民币 2.00",
                },
                {
                    "ticker": "BBB",
                    "name": "B",
                    "currency": "人民币",
                    "market_value": "人民币 -40.00",
                    "all_in_cost": "人民币 50.00",
                    "float_pnl": "人民币 -10.00",
                    "daily_pnl": "人民币 -1.00",
                },
            ]
        }

        with patch("trade_tracker.display_payload.current_fx_rates_to_cny", return_value={"人民币": 1.0}):
            payload = build_display_payload(FakeCore(), [], data)

        self.assertEqual(payload["holdingsTotals"]["assetCny"], 60)
        self.assertEqual(payload["holdingsTotals"]["marketValueCny"], 140)
        self.assertEqual(payload["holdingsTotals"]["costCny"], 130)
        self.assertEqual(payload["holdingsTotals"]["floatPnlCny"], 10)
        self.assertEqual(payload["dailyPnl"]["current"]["holdingFloatCny"], 1)
        self.assertEqual(payload["dailyPnl"]["current"]["byCurrency"]["人民币"]["native"], 1)

    def test_short_put_reserve_is_exposure_not_account_asset(self):
        data = {
            "holdings": [
                {
                    "ticker": "600000",
                    "currency": "人民币",
                    "market_value": "人民币 110.00",
                    "all_in_cost": "人民币 100.00",
                    "float_pnl": "人民币 10.00",
                    "daily_pnl": "人民币 2.00",
                },
                {
                    "ticker": "600000",
                    "currency": "人民币",
                    "side": "卖出认沽",
                    "market_value": "人民币 5,000.00",
                    "all_in_cost": "人民币 5,000.00",
                    "float_pnl": "人民币 100.00",
                    "daily_pnl": "人民币 0.00",
                },
            ]
        }

        with patch("trade_tracker.display_payload.current_fx_rates_to_cny", return_value={"人民币": 1.0}):
            payload = build_display_payload(FakeCore(), [(2, short_put_row())], data)

        self.assertEqual(payload["holdingsTotals"]["assetCny"], 110)
        self.assertEqual(payload["holdingsTotals"]["marketValueCny"], 5110)
        self.assertEqual(payload["holdingsTotals"]["shortPutReserveCny"], 5000)

    def test_realized_trades_and_daily_summary_share_one_payload(self):
        with patch("trade_tracker.display_payload.current_fx_rates_to_cny", return_value={"人民币": 1.0}):
            payload = build_display_payload(FakeCore(), [(2, realized_row())], {"holdings": []})

        self.assertEqual(payload["realized"]["trades"][0]["date"], "2026-05-08")
        self.assertEqual(payload["realized"]["trades"][0]["pnl"], 120)
        self.assertEqual(payload["realized"]["daily"]["byDate"]["2026-05-08"]["pnlCny"], 120)
        self.assertEqual(payload["realizedDaily"]["byDate"]["2026-05-08"]["byCurrency"]["人民币"]["native"], 120)


if __name__ == "__main__":
    unittest.main()
