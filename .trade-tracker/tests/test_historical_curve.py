from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from openpyxl import Workbook


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

    def test_open_day_uses_market_close_as_curve_baseline(self):
        row = stock_row()
        row[4] = Cell(date(2026, 5, 6))
        row[10] = Cell(120)
        rows = [(2, row)]
        history = [
            SecurityHistoryPoint("2026-05-01", 120.0),
            SecurityHistoryPoint("2026-05-02", 121.0),
            SecurityHistoryPoint("2026-05-06", 120.0),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "security_history.json"
            with (
                patch.object(historical_curve_module, "HISTORY_CACHE_PATH", cache_path),
                patch("trade_tracker.historical_curve.fetch_security_history_points_online", return_value=history),
            ):
                data = replace_curve_series_with_historical_prices(FakeCore(), rows, {"curve_series": []})

        values_by_iso = {point["iso"]: point["value"] for point in data["curve_series"][0]["points"]}
        self.assertAlmostEqual(values_by_iso["2026-05-01"], -1.0)
        self.assertAlmostEqual(values_by_iso["2026-05-02"], 9.0)

    def test_imported_closed_rows_use_raw_trade_lots_for_active_capital(self):
        aggregate_row = stock_row()
        aggregate_row[2] = Cell(date(2025, 2, 19))
        aggregate_row[4] = Cell(date(2025, 4, 10))
        aggregate_row[5] = Cell("002137")
        aggregate_row[8] = Cell(258900)
        aggregate_row[9] = Cell(8.197937)
        aggregate_row[10] = Cell(6.79)
        aggregate_row[11] = Cell(1394.68)
        aggregate_row[12] = Cell(2122446)
        aggregate_row[18] = Cell("导入自 东方 成交记录")
        rows = [(322, aggregate_row)]
        history = [
            SecurityHistoryPoint("2025-02-19", 10.44),
            SecurityHistoryPoint("2025-03-31", 7.64),
            SecurityHistoryPoint("2025-04-08", 7.0),
            SecurityHistoryPoint("2025-04-10", 6.79),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            source_dir = temp_path / "history"
            source_dir.mkdir()
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "交易记录"
            sheet.append(["成交日期", "成交时间", "代码", "名称", "交易类别", "成交数量", "成交价格", "发生金额", "成交金额", "费用", "备注"])
            sheet.append([date(2025, 2, 19), None, "002137", "实益达", "买入", 30600, 10.44, -319491.28, 319464, 27.28, None])
            sheet.append([date(2025, 3, 31), None, "002137", "实益达", "卖出", 30600, 7.72, 236093.71, 236232, 138.29, None])
            sheet.append([date(2025, 3, 31), None, "002137", "实益达", "买入", 30800, 7.64, -235332.10, 235312, 20.10, None])
            sheet.append([date(2025, 4, 10), None, "002137", "实益达", "卖出", 30800, 6.79, 209092.0, 209132, 40.0, None])
            workbook.save(source_dir / "东方.xlsx")
            cache_path = temp_path / "security_history.json"
            with (
                patch.object(historical_curve_module, "HISTORY_CACHE_PATH", cache_path),
                patch.object(historical_curve_module, "HISTORY_SOURCE_DIR", source_dir),
                patch("trade_tracker.historical_curve.fetch_security_history_points_online", return_value=history),
            ):
                data = replace_curve_series_with_historical_prices(FakeCore(), rows, {"curve_series": []})

        points_by_iso = {point["iso"]: point for point in data["curve_series"][0]["points"]}
        self.assertLess(points_by_iso["2025-04-08"]["capital"], 300000)
        self.assertAlmostEqual(points_by_iso["2025-04-08"]["capital"], 235332.10)


if __name__ == "__main__":
    unittest.main()
