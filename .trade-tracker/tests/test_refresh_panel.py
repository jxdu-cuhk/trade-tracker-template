from __future__ import annotations

import sys
import unittest
from pathlib import Path


TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from trade_tracker.refresh_panel import add_refresh_progress_panel


class RefreshPanelTests(unittest.TestCase):
    def test_refresh_panel_uses_shared_refresh_buttons_and_compact_status(self):
        html = "<html><head></head><body><main></main></body></html>"

        updated = add_refresh_progress_panel(html)

        self.assertIn('id="refresh-panel"', updated)
        self.assertIn("document.querySelectorAll('[data-refresh-start]')", updated)
        self.assertIn("setButtonsDisabled", updated)
        self.assertIn("grid-template-columns: minmax(180px, 0.68fr) minmax(180px, 0.32fr)", updated)
        self.assertIn(".refresh-panel.is-running .refresh-steps", updated)


if __name__ == "__main__":
    unittest.main()
