from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.market_data import eastmoney_quote_from_row, parse_hkex_option_detail, tencent_quote_from_payload
from trade_tracker.html_tables import normalize_legacy_holdings_table, normalize_legacy_open_option_sections
from trade_tracker.options import build_stock_realized_income_maps, open_option_mark_for_row, patch_dashboard_data_with_options
from trade_tracker import state


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

    def test_open_cash_secured_put_mark_uses_option_quote(self):
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

        with patch("trade_tracker.options.fetch_option_quote", return_value={"option_code": "OPT", "last_price": 0.2}):
            _key, mark = open_option_mark_for_row(FakeCore(), open_put, {})

        self.assertEqual(mark["current_price"], "0.2")
        self.assertEqual(mark["float_pnl"], "28.00")
        self.assertEqual(mark["float_pnl_class"], "value-positive")
        self.assertEqual(mark["capital"], "1,000.00")

    def test_parse_hkex_option_detail_price(self):
        html = """
        <span class="floatleft col1a"><strong>Last Traded Price<br />
        (As of 13:30:00)</strong></span>
        <span class="floatright col1b"><strong>0.090</strong></span>
        """
        price, as_of = parse_hkex_option_detail(html)
        self.assertEqual(price, 0.09)
        self.assertEqual(as_of, "13:30:00")

    def test_parse_hkex_option_detail_prefers_bid_ask_midpoint(self):
        html = """
        Last Traded Price (As of 14:31:00) 0.370
        Bid / Ask 0.360 / 0.380
        """
        price, as_of = parse_hkex_option_detail(html)
        self.assertAlmostEqual(price, 0.37)
        self.assertEqual(as_of, "14:31:00")

    def test_public_quote_parsers_support_batch_sources(self):
        eastmoney_quote = eastmoney_quote_from_row(
            FakeCore(),
            ("00700", "HKD"),
            {"f14": "腾讯控股", "f2": 468800, "f1": 3, "f18": 479200},
        )
        self.assertEqual(eastmoney_quote["name"], "腾讯控股")
        self.assertEqual(eastmoney_quote["last_price"], 468.8)
        self.assertEqual(eastmoney_quote["prev_close"], 479.2)

        tencent_quote = tencent_quote_from_payload(
            FakeCore(),
            ("TSLA", "USD"),
            "200~特斯拉~TSLA.OQ~372.80~376.02",
        )
        self.assertEqual(tencent_quote["name"], "特斯拉")
        self.assertEqual(tencent_quote["last_price"], 372.8)
        self.assertEqual(tencent_quote["prev_close"], 376.02)

    def test_legacy_public_holdings_table_is_normalized_to_full_columns(self):
        html = """
        <table class="summary-table">
        <thead><tr><th>代码</th><th>数量</th><th>最新市值</th><th>持仓成本</th><th>浮动盈亏</th><th>现价</th><th>开仓</th></tr></thead>
        <tbody><tr><td>DEMO</td><td>3</td><td>美元 1,985.13</td><td>美元 1,986.00</td><td>美元 -0.87</td><td>661.71</td><td>2026-04-30</td></tr></tbody>
        </table>
        """
        normalized = normalize_legacy_holdings_table(FakeCore(), html)

        for header in ("名称", "盈亏率", "持股数", "当日盈亏", "个股仓位", "持股天数", "持仓均价", "回本空间", "方向", "币种", "最近买入"):
            self.assertIn(f">{header}</th>", normalized)
        self.assertIn(">662<", normalized)
        self.assertIn(">-0.04%</td>", normalized)
        self.assertIn(">多头</td>", normalized)
        self.assertIn(">美元</td>", normalized)

    def test_legacy_public_open_option_table_is_normalized_to_full_columns(self):
        html = """
        <section>
        <h2 class="section-title">未平仓期权</h2>
        <table class="summary-table">
        <thead><tr><th>代码</th><th>事件</th><th>到期</th><th>行权价</th><th>数量</th><th>开仓价</th><th>现价</th><th>未实现盈亏</th></tr></thead>
        <tbody><tr><td>DEMO</td><td>认沽</td><td>2026-05-29</td><td>80</td><td>-3</td><td>6.413</td><td>9.82</td><td>美元 -1,021.95</td></tr></tbody>
        </table>
        </section>
        """
        normalized = normalize_legacy_open_option_sections(FakeCore(), html)

        for header in ("名称", "类型", "到期日", "乘数", "浮动盈亏", "占用本金", "币种"):
            self.assertIn(f">{header}</th>", normalized)
        self.assertIn(">卖出</td>", normalized)
        self.assertIn(">3</td>", normalized)
        self.assertIn(">100</td>", normalized)
        self.assertIn(">24,000.00</td>", normalized)
        self.assertIn(">美元</td>", normalized)

    def test_normalized_option_table_preserves_prefetched_marks(self):
        html = """
        <section>
        <h2 class="section-title">未平仓期权</h2>
        <p>只要期权那一行还没有平仓价，就会继续留在这里，方便你盯到期日。</p>
        <table class="summary-table">
        <thead><tr><th>代码</th><th>名称</th><th>类型</th><th>事件</th><th>到期日</th><th>行权价</th><th>数量</th><th>乘数</th><th>开仓价</th><th>币种</th></tr></thead>
        <tbody><tr><td>DEMO</td><td>示例标的</td><td>卖出</td><td>认购</td><td>2026/05/28</td><td>32</td><td>5</td><td>1000</td><td>0.55</td><td>港币</td></tr></tbody>
        </table>
        </section>
        """
        previous = dict(state.OPEN_OPTION_MARKS)
        state.OPEN_OPTION_MARKS = {
            ("DEMO", "卖出", "认购", "2026/05/28", "32", "5", "1000", "0.55", "港币"): {
                "current_price": "0.38",
                "float_pnl": "814.50",
                "float_pnl_class": "value-positive",
                "capital": "196,060.00",
            }
        }
        try:
            normalized = normalize_legacy_open_option_sections(FakeCore(), html)
        finally:
            state.OPEN_OPTION_MARKS = previous

        self.assertIn(">0.38</td>", normalized)
        self.assertIn(">814.50</td>", normalized)
        self.assertIn(">196,060.00</td>", normalized)
        self.assertIn("HKEX 等公开行情源", normalized)


if __name__ == "__main__":
    unittest.main()
