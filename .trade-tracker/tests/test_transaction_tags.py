from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker import state
from trade_tracker.transaction_tags import insert_transaction_tags, parse_tags, transaction_tags_for_row


class Cell:
    def __init__(self, raw):
        self.raw = raw


def section(title: str, table_html: str = "") -> str:
    return f"""
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary"><h2 class="section-title">{title}</h2></summary>
          <div class="section-body">{table_html}</div>
        </details>
    """


def timeline_table() -> str:
    return """
      <div class="summary-wrap">
        <table class="summary-table js-sortable-table">
          <thead>
            <tr><th>年份</th><th>开仓</th><th>平仓</th><th>类型</th><th>代码</th><th>名称</th><th>事件</th><th>数量</th><th>备注</th></tr>
          </thead>
          <tbody>
            <tr><td>2026</td><td>2026/01/01</td><td></td><td>股票</td><td>AAA</td><td>A</td><td>现股</td><td>100</td><td>-</td></tr>
            <tr><td>2026</td><td>2026/01/02</td><td></td><td>股票</td><td>BBB</td><td>B</td><td>现股</td><td>200</td><td>-</td></tr>
          </tbody>
        </table>
      </div>
    """


class TransactionTagTests(unittest.TestCase):
    def tearDown(self):
        state.TRANSACTION_TAGS_BY_ROW = {}
        state.TRANSACTION_TAGS_PAYLOAD = {}
        state.TRANSACTION_TAG_COLUMN = None

    def test_parse_tags_splits_common_delimiters_and_deduplicates(self):
        self.assertEqual(parse_tags("波段，AI; #AI | 复盘"), ["波段", "AI", "复盘"])

    def test_transaction_tags_do_not_treat_year_column_as_tag_without_header(self):
        self.assertEqual(transaction_tags_for_row(2, {21: Cell("2026")}), [])

    def test_insert_transaction_tags_adds_timeline_filter_and_column(self):
        state.TRANSACTION_TAGS_BY_ROW = {2: ["波段", "AI"]}
        rows = [(2, {5: Cell("AAA")}), (3, {5: Cell("BBB")})]
        html = "<main>" + section("交易时间线", timeline_table()) + "</main>"

        updated = insert_transaction_tags(html, rows)

        self.assertIn('data-transaction-tags-ready="1"', updated)
        self.assertIn("transaction-tag-toolbar", updated)
        self.assertIn(">标签</th>", updated)
        self.assertIn('data-transaction-tags="波段|AI"', updated)
        self.assertIn('<span class="transaction-tag-chip">波段</span>', updated)
        self.assertIn('data-tag-filter="__none__"', updated)


if __name__ == "__main__":
    unittest.main()
