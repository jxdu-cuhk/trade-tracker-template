from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import trade_tracker.return_curve as return_curve_module
from trade_tracker.return_curve import combine_series_to_cny, curve_payload, date_iso, render_tonghuashun_curve_panels


class ReturnCurveTests(unittest.TestCase):
    def test_benchmark_catalog_has_expected_unique_indices(self):
        labels = [item["label"] for item in return_curve_module.BENCHMARKS]
        ids = [item["id"] for item in return_curve_module.BENCHMARKS]
        sources = [item.get("secid") or item.get("tencent") or item.get("yahoo") for item in return_curve_module.BENCHMARKS]

        self.assertEqual(len(labels), len(set(labels)))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(sources), len(set(sources)))
        for label in [
            "上证指数",
            "深证成指",
            "创业板指",
            "上证50",
            "沪深300",
            "中证500",
            "科创综指",
            "科创50",
            "恒生指数",
            "恒生科技",
            "国企指数",
            "标普500",
            "纳斯达克",
            "道琼斯",
            "罗素2000",
        ]:
            self.assertIn(label, labels)

    def test_date_iso_accepts_compact_csindex_dates(self):
        self.assertEqual(date_iso("20220411"), "2022-04-11")

    def test_combine_series_to_cny_merges_currency_points(self):
        with patch("trade_tracker.return_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0, "港币": 0.9, "美元": 7.2}):
            series = combine_series_to_cny(
                [
                    {
                        "currency": "人民币",
                        "capital": 100,
                        "points": [
                            {"date": "2026/05/01", "serial": 46143, "value": 10, "capital": 100, "market_value": 110, "net_flow": 100},
                            {"date": "2026/05/03", "serial": 46145, "value": 20, "capital": 120, "market_value": 140, "net_flow": -20},
                        ],
                    },
                    {
                        "currency": "港币",
                        "capital": 200,
                        "points": [
                            {"date": "2026/05/02", "serial": 46144, "value": 30, "capital": 200, "market_value": 230, "net_flow": 50},
                        ],
                    },
                ]
            )

        self.assertEqual(series["currency"], "人民币折算")
        self.assertEqual(len(series["points"]), 3)
        self.assertAlmostEqual(series["points"][1]["value"], 37.0)
        self.assertAlmostEqual(series["points"][1]["capital"], 280.0)
        self.assertAlmostEqual(series["points"][1]["market_value"], 317.0)
        self.assertAlmostEqual(series["points"][1]["net_flow"], 45.0)
        self.assertAlmostEqual(series["points"][2]["value"], 47.0)
        self.assertAlmostEqual(series["points"][2]["capital"], 300.0)
        self.assertAlmostEqual(series["points"][2]["market_value"], 347.0)
        self.assertAlmostEqual(series["points"][2]["net_flow"], -20.0)

    def test_curve_payload_collapses_same_day_to_last_point(self):
        with (
            patch("trade_tracker.return_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0}),
            patch("trade_tracker.return_curve.fetch_benchmark_points", return_value=[]),
        ):
            payload = curve_payload(
                [
                    {
                        "currency": "人民币",
                        "code": "CNY",
                        "points": [
                            {"date": "2026/05/07", "serial": 46149, "value": 10, "capital": 90},
                            {"date": "2026/05/07", "serial": 46149, "value": 18, "capital": 100},
                            {"date": "2026/05/08", "serial": 46150, "value": 20},
                        ],
                    }
                ]
            )

        self.assertEqual(len(payload[0]["points"]), 2)
        self.assertEqual(payload[0]["points"][0]["value"], 18)
        self.assertEqual(payload[0]["points"][0]["capital"], 100)

    def test_render_curve_has_clickable_ranges_and_local_json(self):
        benchmark_points = [{"date": "2026/05/07", "iso": "2026-05-07", "serial": 46149, "close": 100}]
        with (
            patch("trade_tracker.return_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0}),
            patch("trade_tracker.return_curve.fetch_benchmark_points", return_value=benchmark_points),
        ):
            html = render_tonghuashun_curve_panels(
                [
                    {
                        "currency": "人民币",
                        "code": "CNY",
                        "capital": 100,
                        "points": [{"date": "2026/05/07", "serial": 46149, "value": 10}],
                    }
                ]
            )
        payload_match = re.search(r'<script type="application/json" data-return-curve-json>(.*?)</script>', html)

        self.assertIsNotNone(payload_match)
        self.assertIn("data-ths-curve-grid", html)
        self.assertIn("data-return-curve-card", html)
        self.assertIn("curve-benchmark-line", html)
        self.assertIn("data-curve-benchmark-tabs", html)
        self.assertIn("ths-curve-benchmark", html)
        self.assertIn("selectedBenchmarkFor", html)
        self.assertIn("上证50", html)
        self.assertIn("科创综指", html)
        self.assertIn("科创50", html)
        self.assertIn("恒生指数", html)
        self.assertIn("标普500", html)
        self.assertIn("range === 'three-year'", html)
        self.assertIn("capitalForPoint(point)", html)
        self.assertIn("serialFromIso", html)
        self.assertIn("benchmarkBaseClose", html)
        self.assertIn("updateSummaryBar", html)
        self.assertIn("updateCurveHero", html)
        self.assertIn("captureCurveHeroDefaults", html)
        self.assertIn("updateCurveHero(range, metric)", html)
        self.assertIn("range === 'all'", html)
        self.assertIn("dataset.defaultText", html)
        self.assertIn("valueForMetric", html)
        self.assertIn("metricText", html)
        self.assertIn("const candleWidth = Math.max(1.2, Math.min(12", html)
        self.assertIn("const rawHeight = Math.abs(closeY - openY)", html)
        self.assertIn("body.setAttribute('rx', '0')", html)
        self.assertIn("resetKlineViewport", html)
        self.assertIn("curveKlineStartSerial", html)
        self.assertIn("installKlineNavigationHandlers", html)
        self.assertIn("addEventListener('wheel'", html)
        self.assertIn("activeCandleButton", html)
        self.assertIn("setCandleInterval('week', false)", html)
        self.assertIn("Math.exp(cappedDelta * 0.00075)", html)
        self.assertNotIn("data-curve-candle-interval=\"day\"", html)
        self.assertNotIn(">日K</button>", html)
        self.assertIn("dailyReturn", html)
        self.assertIn("cumulativeReturnValue", html)
        self.assertIn("cumulativeAmountValue", html)
        self.assertIn("dailyAmountValue: dailyProfit", html)
        self.assertIn("rangeBaseAmount", html)
        self.assertIn("amountValue: periodAmount", html)
        self.assertIn("rawAmountValue: floatAmount", html)
        self.assertIn("profitValueForPoint", html)
        self.assertIn("accountAssetValue", html)
        self.assertIn("externalFlowForPoint", html)
        self.assertIn("pointNumberValue", html)
        self.assertIn("currentAsset - previousAsset", html)
        self.assertIn("assetChange - externalFlow", html)
        self.assertIn("let accountReturnGrowth = 1", html)
        self.assertIn("accountReturnGrowth *= 1 + dailyReturn / 100", html)
        self.assertNotIn("rangeMode === 'all' ? pointCapital : periodCapital", html)
        self.assertIn("收益分析曲线", html)
        self.assertIn("总资产收益率", html)
        self.assertIn("data-curve-hover-layer", html)
        self.assertIn("data-curve-hover-capture", html)
        self.assertIn("data-curve-tooltip", html)
        self.assertIn("data-curve-excess-line", html)
        self.assertIn("curve-excess-dot", html)
        self.assertIn("data-curve-hover-dot-excess", html)
        self.assertIn("excessMetricValues", html)
        self.assertIn("dailyExcessValue", html)
        self.assertIn("installHoverHandlers", html)
        self.assertIn("clampedViewX", html)
        self.assertIn("lineHoverPoints", html)
        self.assertIn("candleHoverPoints", html)
        self.assertIn("state.chartMode === 'candlestick'", html)
        self.assertIn("<span>开盘</span>", html)
        self.assertIn("<span>最高</span>", html)
        self.assertIn("<span>最低</span>", html)
        self.assertIn("<span>收盘</span>", html)
        self.assertIn("<span>区间变化</span>", html)
        self.assertIn("<span>振幅</span>", html)
        self.assertIn("activeAssists", html)
        self.assertIn("root.addEventListener('click'", html)
        self.assertIn("maxDrawdownFor", html)
        self.assertIn("recovery = recovered ? (recovery || point) : null", html)
        self.assertIn("maxGrowthFor", html)
        self.assertIn("data-curve-drawdown-band", html)
        self.assertIn("data-curve-growth-band", html)
        self.assertIn("data-curve-drawdown-link", html)
        self.assertIn("data-curve-growth-link", html)
        self.assertIn("data-curve-drawdown-label", html)
        self.assertIn("data-curve-growth-label", html)
        self.assertIn("data-curve-drawdown-caption", html)
        self.assertIn("data-curve-growth-caption", html)
        self.assertIn("data-curve-extreme-layer", html)
        self.assertIn("data-curve-extreme-max-label", html)
        self.assertIn("const tone = tick > 0 ? 'positive' : tick < 0 ? 'negative' : 'zero'", html)
        self.assertIn("curve-y-label-${tone}", html)
        self.assertIn("dims.width - dims.right + 16", html)
        self.assertIn("dominant-baseline", html)
        self.assertIn("text-anchor', 'start'", html)
        self.assertIn("收益率最大回撤", html)
        self.assertIn("利润最大回撤", html)
        self.assertIn("收益率最大增长", html)
        self.assertIn("利润最大增长", html)
        self.assertIn("对应收益率回撤", html)
        self.assertIn("对应利润回撤", html)
        self.assertIn("对应收益率增长", html)
        self.assertIn("对应利润增长", html)
        self.assertIn("回撤区间", html)
        self.assertIn("增长区间", html)
        self.assertIn("已修复天数", html)
        self.assertIn("recoveredDays", html)
        self.assertIn("niceScale", html)
        self.assertIn("if (metric !== 'amount')", html)
        self.assertIn("dataset.excessReturn", html)
        self.assertIn("dataset.excessAmount", html)
        self.assertIn("dataset.accountAmount", html)
        self.assertIn("dataset.periodPnl", html)
        self.assertIn("benchmarkAmountTotal", html)
        self.assertIn("pointBeforeSerial", html)
        self.assertIn("const previousAccountPoint = pointBeforeSerial(accountValues, benchmarkSerial)", html)
        self.assertIn("const benchmarkCapital = accountAssetValue(previousAccountPoint) || accountAssetValue(accountPoint) || referenceCapital", html)
        self.assertIn("trade-tracker-return-curve-money-hidden-v1", html)
        self.assertIn("displaySignedMoneyText", html)
        self.assertIn("moneyHidden()", html)
        self.assertIn("range === 'day'", html)
        self.assertIn(".ths-curve-metric", html)
        self.assertNotIn("data-curve-drawdown-segment", html)
        payload = json.loads(payload_match.group(1))
        self.assertEqual(payload[0]["currency"], "人民币折算")
        self.assertEqual(payload[0]["points"][0]["iso"], "2026-05-07")
        self.assertEqual(payload[0]["benchmark"]["label"], "上证指数")
        self.assertEqual(payload[0]["benchmarks"][3]["label"], "上证50")
        self.assertEqual(payload[0]["benchmarks"][6]["label"], "科创综指")
        self.assertEqual(payload[0]["benchmarks"][7]["label"], "科创50")
        self.assertEqual(payload[0]["benchmarks"][8]["market"], "港股")
        self.assertEqual(payload[0]["benchmarks"][11]["label"], "标普500")
        self.assertEqual(payload[0]["benchmarks"][11]["shortLabel"], "标普500")
        self.assertEqual(payload[0]["benchmark"]["points"][0]["close"], 100)

    def test_fetch_benchmark_points_uses_fresh_local_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "benchmark_history.json"
            key = return_curve_module.benchmark_cache_key("1.000001", "2026-05-01", "2026-05-07")
            cached_points = [{"date": "2026/05/07", "iso": "2026-05-07", "serial": 46149, "close": 100}]
            cache_path.write_text(
                json.dumps({"version": 1, "ranges": {key: {"fetched_at": date.today().isoformat(), "points": cached_points}}}),
                encoding="utf-8",
            )

            with (
                patch.object(return_curve_module, "BENCHMARK_CACHE_PATH", cache_path),
                patch.object(return_curve_module, "fetch_benchmark_points_online", return_value=[]) as fetch_online,
            ):
                points = return_curve_module.fetch_benchmark_points("1.000001", "2026-05-01", "2026-05-07")

        self.assertEqual(points, cached_points)
        fetch_online.assert_not_called()

    def test_fetch_tencent_benchmark_points_converts_history_points(self):
        history_point = SimpleNamespace(iso="2026-05-07", close=3100.5)
        with patch.object(return_curve_module, "fetch_tencent_history_points", return_value=[history_point]) as fetch_history:
            points = return_curve_module.fetch_tencent_benchmark_points("sh000001", "2026-05-01", "2026-05-07")

        self.assertEqual(
            points,
            [{"date": "2026/05/07", "iso": "2026-05-07", "serial": 46149.0, "close": 3100.5}],
        )
        fetch_history.assert_called_once_with("sh000001", date(2026, 5, 1), date(2026, 5, 7))

    def test_fetch_benchmark_points_online_prefers_tencent_index(self):
        tencent_points = [{"date": "2026/05/07", "iso": "2026-05-07", "serial": 46149, "close": 3100.5}]
        with (
            patch.object(return_curve_module, "fetch_tencent_benchmark_points", return_value=tencent_points) as fetch_tencent,
            patch.object(return_curve_module, "fetch_eastmoney_benchmark_points", return_value=[]) as fetch_eastmoney,
        ):
            points = return_curve_module.fetch_benchmark_points_online("1.000001", "2026-05-01", "2026-05-07")

        self.assertEqual(points, tencent_points)
        fetch_tencent.assert_called_once_with("sh000001", "2026-05-01", "2026-05-07")
        fetch_eastmoney.assert_not_called()

    def test_fetch_benchmark_points_online_backfills_star_composite_from_csindex(self):
        tencent_points = [{"date": "2025/01/20", "iso": "2025-01-20", "serial": 45677, "close": 1200}]
        csindex_points = [{"date": "2022/04/11", "iso": "2022-04-11", "serial": 44662, "close": 1146.55}]
        with (
            patch.object(return_curve_module, "fetch_tencent_benchmark_points", return_value=tencent_points) as fetch_tencent,
            patch.object(return_curve_module, "fetch_csindex_benchmark_points", return_value=csindex_points) as fetch_csindex,
        ):
            points = return_curve_module.fetch_benchmark_points_online("star", "2022-04-11", "2026-05-13")

        self.assertEqual(points, csindex_points)
        fetch_tencent.assert_called_once_with("sh000680", "2022-04-11", "2026-05-13")
        fetch_csindex.assert_called_once_with("000680", "2022-04-11", "2026-05-13")

    def test_fetch_benchmark_points_refreshes_short_star_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_path = Path(temp_dir) / "benchmark_history.json"
            key = return_curve_module.benchmark_cache_key("1.000680", "2022-04-11", "2026-05-13")
            cached_points = [{"date": "2025/01/20", "iso": "2025-01-20", "serial": 45677, "close": 1200}]
            online_points = [{"date": "2022/04/11", "iso": "2022-04-11", "serial": 44662, "close": 1146.55}]
            cache_path.write_text(
                json.dumps({"version": 1, "ranges": {key: {"fetched_at": date.today().isoformat(), "points": cached_points}}}),
                encoding="utf-8",
            )

            with (
                patch.object(return_curve_module, "BENCHMARK_CACHE_PATH", cache_path),
                patch.object(return_curve_module, "fetch_benchmark_points_online", return_value=online_points) as fetch_online,
            ):
                points = return_curve_module.fetch_benchmark_points("star", "2022-04-11", "2026-05-13")

        self.assertEqual(points, online_points)
        fetch_online.assert_called_once()

    def test_fetch_benchmark_points_online_uses_yahoo_for_us_index(self):
        yahoo_points = [{"date": "2026/05/07", "iso": "2026-05-07", "serial": 46149, "close": 5100.5}]
        with (
            patch.object(return_curve_module, "fetch_tencent_benchmark_points", return_value=[]) as fetch_tencent,
            patch.object(return_curve_module, "fetch_yahoo_benchmark_points", return_value=yahoo_points) as fetch_yahoo,
            patch.object(return_curve_module, "fetch_eastmoney_benchmark_points", return_value=[]) as fetch_eastmoney,
        ):
            points = return_curve_module.fetch_benchmark_points_online("sp500", "2026-05-01", "2026-05-07")

        self.assertEqual(points, yahoo_points)
        fetch_tencent.assert_called_once_with("", "2026-05-01", "2026-05-07")
        fetch_yahoo.assert_called_once_with("^GSPC", "2026-05-01", "2026-05-07")
        fetch_eastmoney.assert_not_called()


if __name__ == "__main__":
    unittest.main()
