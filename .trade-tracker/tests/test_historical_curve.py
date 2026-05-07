from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import trade_tracker.historical_curve as historical_curve_module  # noqa: E402
from trade_tracker.historical_curve import (  # noqa: E402
    SecurityHistoryPoint,
    fetch_security_history_points_online,
    parse_tencent_kline_rows,
    replace_curve_series_with_historical_prices,
)


class Cell:
    def __init__(self, raw):
        self.raw = raw


class FakeCore:
    def normalize_currency(self, value):
        text = str(value or "").strip()
        if text in {"人民币", "CNY"}:
            return "CNY"
        if text in {"港币", "HKD"}:
            return "HKD"
        if text in {"美元", "USD"}:
            return "USD"
        return text

    def normalize_ticker(self, ticker, _currency):
        return str(ticker or "").strip().upper()

    def raw_text(self, value):
        return str(value or "").strip()

    def compute_row_metrics(self, _cells):
        return {"pnl": 29.0, "capital": 1001.0, "days": 4}


def stock_row(**overrides):
    values = {
        1: "买入",
        2: date(2026, 5, 1),
        4: date(2026, 5, 5),
        5: "600000",
        6: "现股",
        8: 10,
        9: 100,
        10: 103,
        11: 1,
        12: 1001,
        20: "人民币",
    }
    values.update(overrides)
    return {column: Cell(value) for column, value in values.items()}


class HistoricalCurveTests(unittest.TestCase):
    def test_parse_tencent_kline_rows_uses_close_price(self):
        rows = [["2026-05-06", "10.00", "10.50", "10.80", "9.90", "1000"]]

        points = parse_tencent_kline_rows(rows)

        self.assertEqual(points, [SecurityHistoryPoint("2026-05-06", 10.5)])

    def test_fetch_history_prefers_tencent_before_fallback(self):
        tencent_points = [
            SecurityHistoryPoint("2026-05-01", 10.0),
            SecurityHistoryPoint("2026-05-02", 11.0),
        ]
        with (
            patch("trade_tracker.historical_curve.fetch_tencent_history_points", return_value=tencent_points) as fetch_tencent,
            patch("trade_tracker.historical_curve.fetch_eastmoney_history_points", return_value=[]) as fetch_eastmoney,
            patch("trade_tracker.historical_curve.fetch_yahoo_history_points", return_value=[]) as fetch_yahoo,
        ):
            points = fetch_security_history_points_online(FakeCore(), "600000", "CNY", date(2026, 5, 1), date(2026, 5, 7))

        self.assertEqual(points, tencent_points)
        fetch_tencent.assert_called_once()
        fetch_eastmoney.assert_not_called()
        fetch_yahoo.assert_not_called()

    def test_replace_curve_series_with_historical_prices_builds_daily_points(self):
        rows = [(2, stock_row())]
        history = [
            SecurityHistoryPoint("2026-05-01", 100.0),
            SecurityHistoryPoint("2026-05-02", 102.0),
            SecurityHistoryPoint("2026-05-05", 103.0),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "security_history.json"
            with (
                patch.object(historical_curve_module, "HISTORY_CACHE_PATH", cache_path),
                patch("trade_tracker.historical_curve.fetch_security_history_points_online", return_value=history),
            ):
                data = replace_curve_series_with_historical_prices(FakeCore(), rows, {"curve_series": []})

        series = data["curve_series"][0]
        self.assertEqual(series["source"], "history")
        self.assertEqual(series["currency"], "人民币")
        values_by_iso = {point["iso"]: point["value"] for point in series["points"]}
        self.assertAlmostEqual(values_by_iso["2026-05-01"], -1.0)
        self.assertAlmostEqual(values_by_iso["2026-05-02"], 19.0)
        self.assertAlmostEqual(values_by_iso["2026-05-05"], 29.0)


if __name__ == "__main__":
    unittest.main()
