from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import trade_tracker.return_curve as return_curve_module
from trade_tracker.return_curve import combine_series_to_cny, curve_payload, render_tonghuashun_curve_panels


class ReturnCurveTests(unittest.TestCase):
    def test_combine_series_to_cny_merges_currency_points(self):
        with patch("trade_tracker.return_curve.current_fx_rates_to_cny", return_value={"人民币": 1.0, "港币": 0.9, "美元": 7.2}):
            series = combine_series_to_cny(
                [
                    {
                        "currency": "人民币",
                        "capital": 100,
                        "points": [
                            {"date": "2026/05/01", "serial": 46143, "value": 10, "capital": 100},
                            {"date": "2026/05/03", "serial": 46145, "value": 20, "capital": 120},
                        ],
                    },
                    {
                        "currency": "港币",
                        "capital": 200,
                        "points": [
                            {"date": "2026/05/02", "serial": 46144, "value": 30, "capital": 200},
                        ],
                    },
                ]
            )

        self.assertEqual(series["currency"], "人民币折算")
        self.assertEqual(len(series["points"]), 3)
        self.assertAlmostEqual(series["points"][1]["value"], 37.0)
        self.assertAlmostEqual(series["points"][1]["capital"], 280.0)
        self.assertAlmostEqual(series["points"][2]["value"], 47.0)
        self.assertAlmostEqual(series["points"][2]["capital"], 300.0)

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
        self.assertIn("range === 'three-year'", html)
        self.assertIn("capitalForPoint(point)", html)
        self.assertIn("serialFromIso", html)
        self.assertIn("benchmarkBaseClose", html)
        self.assertIn("updateSummaryBar", html)
        self.assertIn("updateCurveHero", html)
        self.assertIn("captureCurveHeroDefaults", html)
        self.assertIn("updateCurveHero(range, metric)", html)
        self.assertIn("range === 'all'", html)
        self.assertIn("kicker.dataset.defaultText", html)
        self.assertIn("dataset.defaultText", html)
        self.assertIn("valueForMetric", html)
        self.assertIn("metricText", html)
        self.assertIn("dailyReturn", html)
        self.assertIn("cumulativeReturnValue", html)
        self.assertIn("cumulativeAmountValue", html)
        self.assertIn("dailyAmountValue: delta", html)
        self.assertIn("amountValue: floatAmount", html)
        self.assertIn("历史总盈亏曲线", html)
        self.assertIn("总盈亏率", html)
        self.assertIn("data-curve-hover-layer", html)
        self.assertIn("data-curve-hover-capture", html)
        self.assertIn("data-curve-tooltip", html)
        self.assertIn("installHoverHandlers", html)
        self.assertIn("clampedViewX", html)
        self.assertIn("maxDrawdownFor", html)
        self.assertIn("data-curve-drawdown-band", html)
        self.assertIn("data-curve-drawdown-link", html)
        self.assertIn("data-curve-drawdown-caption", html)
        self.assertIn("收益率最大回撤", html)
        self.assertIn("利润最大回撤", html)
        self.assertIn("对应收益率回撤", html)
        self.assertIn("对应利润回撤", html)
        self.assertIn("回撤区间", html)
        self.assertIn("修复情况", html)
        self.assertIn("niceScale", html)
        self.assertIn("dataset.excessReturn", html)
        self.assertIn("dataset.excessAmount", html)
        self.assertIn("dataset.accountAmount", html)
        self.assertIn("dataset.periodPnl", html)
        self.assertIn("range === 'day'", html)
        self.assertIn(".ths-curve-metric", html)
        self.assertNotIn("data-curve-excess-line", html)
        self.assertNotIn("curve-excess-dot", html)
        self.assertNotIn("data-curve-drawdown-segment", html)
        payload = json.loads(payload_match.group(1))
        self.assertEqual(payload[0]["currency"], "人民币折算")
        self.assertEqual(payload[0]["points"][0]["iso"], "2026-05-07")
        self.assertEqual(payload[0]["benchmark"]["label"], "上证指数")
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


if __name__ == "__main__":
    unittest.main()
