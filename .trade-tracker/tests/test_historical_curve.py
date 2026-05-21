from __future__ import annotations

import json
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
from trade_tracker import state  # noqa: E402
from trade_tracker.historical_curve import (  # noqa: E402
    SecurityHistoryPoint,
    build_stock_lots,
    build_performance_stock_payload,
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


class ImportedAggregateCore(FakeCore):
    def compute_row_metrics(self, _cells):
        return {"pnl": -109637.67, "capital": 1001.0, "days": 4}


class ClosedLossCore(FakeCore):
    def compute_row_metrics(self, _cells):
        return {"pnl": -485.9, "capital": 24106.06, "days": 5}


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
        self.assertAlmostEqual(values_by_iso["2026-05-01"], 0.0)
        self.assertAlmostEqual(values_by_iso["2026-05-02"], 19.0)
        self.assertAlmostEqual(values_by_iso["2026-05-05"], 29.0)
        points_by_iso = {point["iso"]: point for point in series["points"]}
        self.assertAlmostEqual(points_by_iso["2026-05-01"]["market_value"], 1000.0)
        self.assertAlmostEqual(points_by_iso["2026-05-01"]["net_flow"], 1001.0)
        self.assertAlmostEqual(points_by_iso["2026-05-05"]["net_flow"], -1030.0)

    def test_performance_stock_payload_includes_open_holding_float(self):
        row = stock_row()
        row[4] = Cell(None)
        row[10] = Cell(None)
        rows = [(2, row)]
        history = [
            SecurityHistoryPoint("2026-05-01", 100.0),
            SecurityHistoryPoint("2026-05-02", 110.0),
            SecurityHistoryPoint("2026-05-08", 112.0),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "security_history.json"
            with (
                patch.object(historical_curve_module, "HISTORY_CACHE_PATH", cache_path),
                patch("trade_tracker.historical_curve.fetch_security_history_points_online", return_value=history),
                patch("trade_tracker.historical_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0}),
            ):
                replace_curve_series_with_historical_prices(
                    FakeCore(),
                    rows,
                    {
                        "curve_series": [],
                        "holdings": [
                            {
                                "ticker": "600000",
                                "currency": "人民币",
                                "name": "浦发银行",
                                "last_price": "112.00",
                            }
                        ],
                    },
                )

        may_items = state.PERFORMANCE_STOCK_PAYLOAD["months"]["2026-05"]
        item = next(item for item in may_items if item["code"] == "600000")
        self.assertEqual(item["name"], "浦发银行")
        self.assertEqual(item["currency"], "人民币")
        self.assertAlmostEqual(item["pnl"], 119.0)
        self.assertAlmostEqual(item["nativeFloatPnl"], 119.0)
        self.assertAlmostEqual(item["nativeRealizedPnl"], 0.0)
        self.assertTrue(item["openAtPeriodEnd"])
        self.assertEqual(item["closedCount"], 0)
        self.assertAlmostEqual(item["capital"], 1001.0)
        self.assertAlmostEqual(item["rate"], item["pnl"] / item["capital"] * 100)

    def test_performance_stock_rate_matches_app_adjusted_cost_basis_for_open_holding(self):
        snapshots = {
            date(2026, 5, 18): {
                ("688820", "人民币"): {
                    "code": "688820",
                    "name": "盛合晶微",
                    "currency": "人民币",
                    "value": 99248.35,
                    "realized_value": 86759.24,
                    "float_value": 12489.11,
                    "capital": 539277.70,
                    "market_value": 362394.60,
                    "position_quantity": 1915.0,
                }
            },
        }

        with patch("trade_tracker.historical_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0}):
            payload = build_performance_stock_payload(snapshots)

        item = payload["years"]["2026"][0]
        self.assertAlmostEqual(item["pnl"], 99248.35)
        self.assertAlmostEqual(item["rate"], 99248.35 / (362394.60 - 99248.35) * 100)

    def test_performance_stock_payload_splits_dividend_net_from_trade_realized(self):
        snapshots = {
            date(2025, 12, 31): {
                ("300394", "人民币"): {
                    "code": "300394",
                    "name": "天孚通信",
                    "currency": "人民币",
                    "value": 305.0,
                    "realized_value": 305.0,
                    "dividend_value": 305.0,
                    "capital": 0.0,
                }
            },
            date(2026, 1, 8): {
                ("300394", "人民币"): {
                    "code": "300394",
                    "name": "天孚通信",
                    "currency": "人民币",
                    "value": 10305.0,
                    "realized_value": 10305.0,
                    "dividend_value": 305.0,
                    "capital": 100000.0,
                }
            },
        }

        with patch("trade_tracker.historical_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0}):
            payload = build_performance_stock_payload(snapshots)

        item = payload["years"]["2026"][0]
        self.assertAlmostEqual(item["nativePnl"], 10000.0)
        self.assertAlmostEqual(item["nativeRealizedPnl"], 10000.0)
        self.assertAlmostEqual(item["nativeDividendPnl"], 0.0)
        prior_item = payload["years"]["2025"][0]
        self.assertAlmostEqual(prior_item["nativePnl"], 305.0)
        self.assertAlmostEqual(prior_item["nativeRealizedPnl"], 0.0)
        self.assertAlmostEqual(prior_item["nativeDividendPnl"], 305.0)

    def test_performance_stock_monthly_rate_uses_previous_month_end_market_value(self):
        snapshots = {
            date(2026, 2, 27): {
                ("688818", "人民币"): {
                    "code": "688818",
                    "name": "中电科蓝",
                    "currency": "人民币",
                    "value": 30328.87,
                    "capital": 4735.0,
                    "market_value": 35063.87,
                    "net_flow": 0.0,
                }
            },
            date(2026, 3, 16): {
                ("688818", "人民币"): {
                    "code": "688818",
                    "name": "中电科蓝",
                    "currency": "人民币",
                    "value": 26863.87,
                    "capital": 4735.0,
                    "market_value": 0.0,
                    "net_flow": -31598.87,
                }
            },
        }

        with patch("trade_tracker.historical_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0}):
            payload = build_performance_stock_payload(snapshots)

        march_item = payload["months"]["2026-03"][0]
        self.assertAlmostEqual(march_item["pnl"], -3465.0)
        self.assertAlmostEqual(march_item["capital"], 35063.87)
        self.assertAlmostEqual(march_item["rate"], -3465.0 / 35063.87 * 100)

    def test_performance_stock_payload_splits_month_and_year_by_period_boundary(self):
        snapshots = {
            date(2025, 12, 31): {
                ("688017", "人民币"): {
                    "code": "688017",
                    "name": "绿的谐波",
                    "currency": "人民币",
                    "value": 142359.68,
                    "realized_value": 0.0,
                    "float_value": 142359.68,
                    "capital": 581294.6,
                    "market_value": 723654.28,
                    "closed_count": 0,
                }
            },
            date(2026, 1, 8): {
                ("688017", "人民币"): {
                    "code": "688017",
                    "name": "绿的谐波",
                    "currency": "人民币",
                    "value": 137389.480866,
                    "realized_value": 137389.480866,
                    "float_value": 0.0,
                    "capital": 581294.6,
                    "closed_count": 1,
                }
            },
        }

        with patch("trade_tracker.historical_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0}):
            payload = build_performance_stock_payload(snapshots)

        january = payload["months"]["2026-01"][0]
        prior_year = payload["years"]["2025"][0]
        year = payload["years"]["2026"][0]
        self.assertAlmostEqual(january["nativePnl"], -4970.199134)
        self.assertAlmostEqual(january["nativeRealizedPnl"], 137389.480866)
        self.assertAlmostEqual(january["nativeFloatPnl"], -142359.68)
        self.assertFalse(january["openAtPeriodEnd"])
        self.assertEqual(january["closedCount"], 1)
        self.assertTrue(prior_year["openAtPeriodEnd"])
        self.assertEqual(prior_year["closedCount"], 0)
        self.assertAlmostEqual(year["nativePnl"], -4970.199134)
        self.assertNotAlmostEqual(year["nativePnl"], 137389.480866)

    def test_holding_float_uses_trade_cost_as_curve_baseline(self):
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
        self.assertAlmostEqual(values_by_iso["2026-05-01"], 0.0)
        self.assertAlmostEqual(values_by_iso["2026-05-02"], 209.0)

    def test_adjusted_history_prices_do_not_create_false_monthly_profit(self):
        row = stock_row()
        for column, value in {
            2: date(2023, 10, 27),
            4: date(2023, 11, 1),
            5: "002594",
            8: 100,
            9: 241.04,
            10: 236.34,
            11: 15.9,
            12: 24106.06,
        }.items():
            row[column] = Cell(value)
        rows = [(238, row)]
        adjusted_history = [
            SecurityHistoryPoint("2023-10-27", 78.293),
            SecurityHistoryPoint("2023-10-31", 77.156),
            SecurityHistoryPoint("2023-11-01", 76.376),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "security_history.json"
            with (
                patch.object(historical_curve_module, "HISTORY_CACHE_PATH", cache_path),
                patch("trade_tracker.historical_curve.fetch_security_history_points_online", return_value=adjusted_history),
                patch("trade_tracker.historical_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0}),
            ):
                replace_curve_series_with_historical_prices(ClosedLossCore(), rows, {"curve_series": []})

        november_item = next(item for item in state.PERFORMANCE_STOCK_PAYLOAD["months"]["2023-11"] if item["code"] == "002594")
        self.assertLess(november_item["pnl"], 0)
        self.assertLess(abs(november_item["pnl"]), 1000)

    def test_adjusted_cached_history_is_refetched_on_trade_scale_mismatch(self):
        row = stock_row()
        for column, value in {
            2: date(2023, 10, 27),
            4: date(2023, 11, 1),
            5: "002594",
            8: 100,
            9: 241.04,
            10: 236.34,
            11: 15.9,
            12: 24106.06,
        }.items():
            row[column] = Cell(value)
        rows = [(238, row)]
        adjusted_cache_points = [
            {"iso": "2023-10-27", "close": 78.293},
            {"iso": "2023-10-31", "close": 77.156},
            {"iso": "2023-11-01", "close": 76.376},
        ]
        unadjusted_history = [
            SecurityHistoryPoint("2023-10-27", 241.95),
            SecurityHistoryPoint("2023-10-31", 238.54),
            SecurityHistoryPoint("2023-11-01", 236.2),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "security_history.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "securities": {
                            "CNY|002594": {
                                "ticker": "002594",
                                "currency": "CNY",
                                "fetched_at": date.today().isoformat(),
                                "points": adjusted_cache_points,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(historical_curve_module, "HISTORY_CACHE_PATH", cache_path),
                patch("trade_tracker.historical_curve.fetch_security_history_points_online", return_value=unadjusted_history) as fetch_online,
                patch("trade_tracker.historical_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0}),
            ):
                replace_curve_series_with_historical_prices(ClosedLossCore(), rows, {"curve_series": []})

            refreshed = json.loads(cache_path.read_text(encoding="utf-8"))["securities"]["CNY|002594"]

        fetch_online.assert_called_once()
        self.assertEqual(refreshed["points"][0]["close"], 241.95)
        self.assertFalse(refreshed["price_scale_mismatch"])

    def test_consistent_adjusted_cached_history_near_threshold_is_refetched(self):
        row = stock_row()
        for column, value in {
            2: date(2024, 4, 15),
            4: date(2024, 10, 9),
            5: "001223",
            8: 100,
            9: 38.89,
            10: 40.24,
            11: 12.0,
            12: 3889.0,
        }.items():
            row[column] = Cell(value)
        rows = [(300, row)]
        adjusted_cache_points = [
            {"iso": "2024-04-15", "close": 25.714},
            {"iso": "2024-10-09", "close": 27.793},
        ]
        unadjusted_history = [
            SecurityHistoryPoint("2024-04-15", 36.95),
            SecurityHistoryPoint("2024-10-09", 39.06),
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "security_history.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "securities": {
                            "CNY|001223": {
                                "ticker": "001223",
                                "currency": "CNY",
                                "fetched_at": date.today().isoformat(),
                                "points": adjusted_cache_points,
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(historical_curve_module, "HISTORY_CACHE_PATH", cache_path),
                patch("trade_tracker.historical_curve.fetch_security_history_points_online", return_value=unadjusted_history) as fetch_online,
                patch("trade_tracker.historical_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0}),
            ):
                replace_curve_series_with_historical_prices(FakeCore(), rows, {"curve_series": []})

            refreshed = json.loads(cache_path.read_text(encoding="utf-8"))["securities"]["CNY|001223"]

        fetch_online.assert_called_once()
        self.assertEqual(refreshed["points"][0]["close"], 36.95)
        self.assertFalse(refreshed["price_scale_mismatch"])

    def test_same_day_trade_price_difference_does_not_force_scale_refresh(self):
        row = stock_row()
        for column, value in {
            2: date(2026, 3, 17),
            4: date(2026, 3, 17),
            5: "01428",
            8: 2000,
            9: 16.05,
            10: 15.8,
            11: 12.0,
            12: 32100.0,
            20: "港币",
        }.items():
            row[column] = Cell(value)
        rows = [(400, row)]
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "security_history.json"
            cache_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "securities": {
                            "HKD|01428": {
                                "ticker": "01428",
                                "currency": "HKD",
                                "fetched_at": date.today().isoformat(),
                                "points": [{"iso": "2026-03-17", "close": 13.6}],
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(historical_curve_module, "HISTORY_CACHE_PATH", cache_path),
                patch("trade_tracker.historical_curve.fetch_security_history_points_online", return_value=[]) as fetch_online,
            ):
                replace_curve_series_with_historical_prices(FakeCore(), rows, {"curve_series": []})

        fetch_online.assert_not_called()

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
                data = replace_curve_series_with_historical_prices(ImportedAggregateCore(), rows, {"curve_series": []})

        points_by_iso = {point["iso"]: point for point in data["curve_series"][0]["points"]}
        self.assertLess(points_by_iso["2025-04-08"]["capital"], 300000)
        self.assertAlmostEqual(points_by_iso["2025-04-08"]["capital"], 235332.10)
        self.assertAlmostEqual(points_by_iso["2025-04-08"]["value"], -103129.67)

    def test_imported_raw_details_are_scoped_to_aggregate_window(self):
        aggregate_row = stock_row()
        aggregate_row[2] = Cell(date(2025, 10, 13))
        aggregate_row[4] = Cell(date(2025, 10, 21))
        aggregate_row[5] = Cell("688205")
        aggregate_row[8] = Cell(10)
        aggregate_row[9] = Cell(100)
        aggregate_row[10] = Cell(103)
        aggregate_row[11] = Cell(1)
        aggregate_row[12] = Cell(1000)
        aggregate_row[18] = Cell("导入自 东方两融 成交记录")
        rows = [(95, aggregate_row)]

        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir = Path(temp_dir) / "history"
            source_dir.mkdir()
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "交易记录"
            sheet.append(["成交日期", "成交时间", "代码", "名称", "交易类别", "成交数量", "成交价格", "发生金额", "成交金额", "费用", "备注"])
            sheet.append([date(2025, 10, 13), None, "688205", "德科立光电子", "买入", 10, 100, -1000, 1000, 0.5, None])
            sheet.append([date(2025, 10, 21), None, "688205", "德科立光电子", "卖出", 10, 103, 1030, 1030, 0.5, None])
            sheet.append([date(2025, 10, 30), None, "688205", "德科立光电子", "买入", 10, 105, -1050, 1050, 0.5, None])
            sheet.append([date(2025, 11, 25), None, "688205", "德科立光电子", "卖出", 10, 142, 1420, 1420, 0.5, None])
            workbook.save(source_dir / "东方两融.xlsx")

            with patch.object(historical_curve_module, "HISTORY_SOURCE_DIR", source_dir):
                lots = build_stock_lots(FakeCore(), rows)

        self.assertEqual(len(lots), 1)
        self.assertEqual(lots[0].open_date, date(2025, 10, 13))
        self.assertEqual(lots[0].close_date, date(2025, 10, 21))
        self.assertAlmostEqual(lots[0].realized_pnl or 0.0, 29.0)


if __name__ == "__main__":
    unittest.main()
