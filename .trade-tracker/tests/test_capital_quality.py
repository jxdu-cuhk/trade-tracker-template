from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker import state
from trade_tracker.capital_quality import insert_capital_quality_section


def section(title: str) -> str:
    return f"""
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary"><h2 class="section-title">{title}</h2></summary>
          <div class="section-body"></div>
        </details>
"""


class CapitalQualityTests(unittest.TestCase):
    def tearDown(self):
        state.DISPLAY_PAYLOAD = {}

    def test_insert_capital_quality_after_current_holdings(self):
        state.DISPLAY_PAYLOAD = {
            "capital": {
                "accountAssetCny": 100.0,
                "marketExposureCny": 120.0,
                "holdingCostCny": 90.0,
                "holdingFloatPnlCny": 10.0,
                "optionCapital": {"totals": {"missingCapitalCount": 1}},
            },
            "dataQuality": {
                "status": "danger",
                "label": "资金口径待补",
                "items": [{"label": "资金口径", "status": "danger", "text": "1 条期权缺保证金/策略资金"}],
            },
        }
        html = "<main>" + section("当前持仓") + section("未平仓期权") + "</main>"

        updated = insert_capital_quality_section(html)
        updated_again = insert_capital_quality_section(updated)

        self.assertIn("data-capital-quality", updated)
        self.assertIn("资金口径 / 数据质量", updated)
        self.assertIn("资金口径待补", updated)
        self.assertLess(updated.index("当前持仓"), updated.index("资金口径 / 数据质量"))
        self.assertLess(updated.index("资金口径 / 数据质量"), updated.index("未平仓期权"))
        self.assertEqual(updated, updated_again)


if __name__ == "__main__":
    unittest.main()
