from __future__ import annotations

import sys
import unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.holdings_daily import apply_segmented_daily_pnl, market_trade_day_for_currency


class FakeCore:
    def normalize_currency(self, value):
        text = str(value or "").strip()
        if text in {"美元", "USD"}:
            return "USD"
        if text in {"港币", "HKD"}:
            return "HKD"
        if text in {"人民币", "CNY"}:
            return "CNY"
        return text

    def normalize_ticker(self, ticker, _currency):
        return str(ticker or "").strip().upper()

    def raw_text(self, value):
        return str(value or "").strip()


class Cell:
    def __init__(self, raw):
        self.raw = raw


def stock_row(
    ticker: str = "SOXL",
    open_date: date = date(2026, 5, 11),
    quantity: float = 36,
    open_price: float = 187.49,
    fee: float = 2.10,
    capital: float = 6749.64,
    currency: str = "美元",
):
    return {
        1: Cell("股票"),
        2: Cell(open_date),
        4: Cell(None),
        5: Cell(ticker),
        6: Cell("现股"),
        8: Cell(quantity),
        9: Cell(open_price),
        11: Cell(fee),
        12: Cell(capital),
        20: Cell(currency),
    }


class HoldingsDailyTests(unittest.TestCase):
    def test_us_market_day_lags_beijing_midnight_for_new_lots(self):
        now = datetime(2026, 5, 12, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        data = {
            "holdings": [
                {
                    "ticker": "SOXL",
                    "currency": "美元",
                    "last_price": "186.00",
                    "daily_pnl": "美元 +120.00",
                }
            ]
        }

        updated = apply_segmented_daily_pnl(FakeCore(), [(2, stock_row())], data, now=now)

        self.assertEqual(market_trade_day_for_currency("美元", now), date(2026, 5, 11))
        self.assertEqual(updated["holdings"][0]["daily_pnl"], "美元 -55.74")
        self.assertEqual(updated["daily_pnl_text"], "美元 -55.74")

    def test_us_lot_becomes_old_after_next_us_session_starts(self):
        now = datetime(2026, 5, 12, 22, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        data = {
            "holdings": [
                {
                    "ticker": "SOXL",
                    "currency": "美元",
                    "last_price": "188.00",
                    "daily_pnl": "美元 +60.00",
                }
            ]
        }

        updated = apply_segmented_daily_pnl(FakeCore(), [(2, stock_row())], data, now=now)

        self.assertEqual(market_trade_day_for_currency("美元", now), date(2026, 5, 12))
        self.assertEqual(updated["holdings"][0]["daily_pnl"], "美元 +60.00")
        self.assertNotIn("daily_pnl_text", updated)

    def test_asia_markets_roll_after_local_open(self):
        before_open = datetime(2026, 5, 12, 8, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
        after_open = datetime(2026, 5, 12, 9, 30, tzinfo=ZoneInfo("Asia/Shanghai"))

        self.assertEqual(market_trade_day_for_currency("人民币", before_open), date(2026, 5, 11))
        self.assertEqual(market_trade_day_for_currency("港币", before_open), date(2026, 5, 11))
        self.assertEqual(market_trade_day_for_currency("人民币", after_open), date(2026, 5, 12))
        self.assertEqual(market_trade_day_for_currency("港币", after_open), date(2026, 5, 12))


if __name__ == "__main__":
    unittest.main()
