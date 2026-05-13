from __future__ import annotations

import re
from pathlib import Path

from .utils import cell_text


def compact_preview_table_spacing(output_dir: Path) -> None:
    css_path = output_dir / "resources" / "preview.css"
    if not css_path.exists():
        return
    marker = "/* Codex compact summary table spacing */"
    override = f"""
{marker}
.dashboard-grid {{
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 14px;
  align-items: stretch;
}}

.currency-overview-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 14px;
}}

.currency-overview-card {{
  border: 1px solid rgba(196, 215, 202, 0.92);
  border-radius: 22px;
  background:
    radial-gradient(circle at 92% 10%, rgba(251, 188, 4, 0.16), transparent 90px),
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(242, 249, 244, 0.97));
  box-shadow: 0 16px 38px rgba(60, 64, 67, 0.08);
  padding: 18px;
}}

.currency-overview-cny-card {{
  border-color: #9bd0ad;
  background:
    radial-gradient(circle at 92% 10%, rgba(251, 188, 4, 0.2), transparent 104px),
    linear-gradient(135deg, #fffaf0 0%, #eef8f0 100%);
}}

.currency-overview-cny-card .currency-overview-head em {{
  color: #137333;
}}

.currency-overview-head {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 14px;
}}

.currency-overview-head span {{
  color: #1f1f1f;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -0.02em;
}}

.currency-overview-head em {{
  color: #63766b;
  font-size: 11px;
  font-style: normal;
  font-weight: 700;
  letter-spacing: 0.05em;
}}

.currency-overview-primary {{
  display: grid;
  gap: 9px;
  margin-bottom: 14px;
}}

.currency-overview-primary-row,
.currency-overview-row {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 14px;
}}

.currency-overview-primary-row span,
.currency-overview-row span {{
  color: #63766b;
  font-size: 12px;
  white-space: nowrap;
}}

.currency-overview-primary-row strong {{
  color: #202124;
  font-size: 20px;
  line-height: 1.12;
  text-align: right;
  white-space: nowrap;
}}

.currency-overview-details {{
  display: grid;
  gap: 7px;
  padding-top: 12px;
  border-top: 1px solid #dfeae3;
}}

.currency-overview-row strong {{
  color: #202124;
  font-size: 13px;
  text-align: right;
  white-space: nowrap;
}}

.currency-overview-card .value-positive {{
  color: #d93025;
}}

.currency-overview-card .value-negative {{
  color: #137333;
}}

.currency-overview-card .value-zero {{
  color: #5f6368;
}}

.overview-utility-grid {{
  margin-top: 0;
}}

.metric-card {{
  position: relative;
  display: flex;
  min-height: 116px;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
  overflow: hidden;
  border-radius: 22px;
  border-color: rgba(196, 215, 202, 0.88);
  background:
    radial-gradient(circle at 92% 12%, rgba(52, 168, 83, 0.13), transparent 78px),
    linear-gradient(135deg, rgba(255, 255, 255, 0.98), rgba(246, 251, 247, 0.96));
  box-shadow: 0 16px 38px rgba(60, 64, 67, 0.08);
}}

.metric-card::before {{
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 5px;
  background: linear-gradient(180deg, #34a853, #fbbc04);
  opacity: 0.78;
}}

.metric-card-hero {{
  grid-column: span 6;
  min-height: 172px;
  padding: 22px 24px 20px;
  background:
    radial-gradient(circle at 86% 16%, rgba(251, 188, 4, 0.2), transparent 105px),
    linear-gradient(135deg, #fffaf0 0%, #eef8f0 100%);
}}

.metric-card-return,
.metric-card-annual {{
  grid-column: span 3;
  min-height: 172px;
  padding: 22px 20px 20px;
}}

.metric-card-broad {{
  grid-column: span 4;
}}

.metric-card-mini,
.metric-card-muted {{
  grid-column: span 3;
}}

.metric-card-muted {{
  background:
    radial-gradient(circle at 92% 12%, rgba(154, 160, 166, 0.11), transparent 76px),
    linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 249, 0.94));
}}

.metric-card-muted::before {{
  background: linear-gradient(180deg, #c9d6ce, #eef2ef);
}}

.metric-label {{
  margin-bottom: 6px;
  color: #466052;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}}

.metric-value {{
  font-size: 24px;
  line-height: 1.12;
}}

.metric-card-hero .metric-value {{
  font-size: 30px;
}}

.metric-value-wide {{
  display: flex;
  flex-wrap: wrap;
  gap: 5px 9px;
  font-size: 16px;
  line-height: 1.28;
}}

.metric-card-hero .metric-value-wide {{
  display: block;
  font-size: 21px;
}}

.metric-value-wide .metric-segment {{
  display: inline-flex;
  align-items: baseline;
  white-space: nowrap;
}}

.metric-card-hero .metric-segment {{
  display: block;
  margin-top: 5px;
}}

.metric-value-wide .metric-separator {{
  display: none;
}}

.metric-note {{
  margin-top: 4px;
  color: #63766b;
  font-size: 11.5px;
  line-height: 1.42;
}}

.metric-card-hero .metric-note,
.metric-card-return .metric-note,
.metric-card-annual .metric-note {{
  font-size: 12px;
}}

.holdings-account-panel {{
  display: grid;
  gap: 0;
  overflow: hidden;
  margin-bottom: 12px;
  border: 1px solid #edf0f2;
  border-radius: 10px;
  background: #ffffff;
}}

.holdings-account-grid {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr)) minmax(150px, 1.2fr);
}}

.holdings-account-metric {{
  display: grid;
  gap: 6px;
  min-height: 88px;
  align-content: center;
  padding: 13px 16px;
  border-right: 1px solid #f0f2f4;
}}

.holdings-account-metric:last-child {{
  border-right: 0;
}}

.holdings-month-metric {{
  gap: 5px;
  align-content: stretch;
}}

.holdings-account-label,
.holdings-month-label {{
  color: #9aa0a6;
  font-size: 12px;
  font-weight: 800;
}}

.holdings-account-value {{
  color: #303134;
  font-size: 22px;
  line-height: 1.05;
  font-weight: 850;
  white-space: nowrap;
}}

.holdings-account-metric span:last-child {{
  color: #9aa0a6;
  font-size: 11px;
  font-weight: 700;
}}

.holdings-realized-head {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}}

.holdings-range-tabs {{
  display: inline-flex;
  flex: 0 0 auto;
  gap: 2px;
  padding: 2px;
  border-radius: 999px;
  background: #f3f5f6;
}}

.holdings-range-tab {{
  appearance: none;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #858c91;
  cursor: pointer;
  font: inherit;
  font-size: 11px;
  font-weight: 800;
  line-height: 1;
  padding: 5px 8px;
  white-space: nowrap;
}}

.holdings-range-tab.is-active {{
  background: #ff2f45;
  color: #ffffff;
}}

.holdings-realized-range {{
  display: none;
  grid-template-columns: minmax(0, 0.84fr) minmax(110px, 1fr);
  align-items: end;
  gap: 10px;
}}

.holdings-realized-range.is-active {{
  display: grid;
}}

.holdings-realized-text {{
  display: grid;
  gap: 5px;
  min-width: 0;
}}

.holdings-account-value.value-positive {{
  color: #f12f3f;
}}

.holdings-account-value.value-negative {{
  color: #137333;
}}

.holdings-month-sparkline {{
  width: 100%;
  max-width: 156px;
  min-width: 0;
  overflow: visible;
}}

.holdings-sparkline-axis {{
  stroke: #dfe3e7;
  stroke-dasharray: 5 5;
}}

.holdings-sparkline-area {{
  fill: rgba(241, 47, 63, 0.12);
}}

.holdings-sparkline-line {{
  fill: none;
  stroke: #f12f3f;
  stroke-width: 1.8;
  stroke-linecap: round;
  stroke-linejoin: round;
}}

.holdings-sparkline-dot {{
  fill: #f12f3f;
}}

.holdings-month-sparkline-negative .holdings-sparkline-area {{
  fill: rgba(19, 115, 51, 0.12);
}}

.holdings-month-sparkline-negative .holdings-sparkline-line {{
  stroke: #137333;
}}

.holdings-month-sparkline-negative .holdings-sparkline-dot {{
  fill: #137333;
}}

details[data-ths-return-curve] .section-body {{
  display: grid;
  gap: 0;
}}

details[data-ths-return-curve] .ths-curve-hero {{
  display: grid;
  justify-items: center;
  gap: 9px;
  overflow: hidden;
  border-radius: 16px 16px 0 0;
  background: linear-gradient(180deg, #f72f3a 0%, #ff5a10 100%);
  color: #ffffff;
  padding: 22px 18px 0;
}}

details[data-ths-return-curve] .ths-curve-kicker {{
  color: rgba(255, 255, 255, 0.88);
  font-size: 14px;
  font-weight: 700;
}}

details[data-ths-return-curve] .ths-curve-value {{
  color: #ffffff;
  font-size: 42px;
  line-height: 1;
  font-weight: 800;
}}

details[data-ths-return-curve] .ths-curve-rate {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: rgba(255, 255, 255, 0.92);
  font-size: 14px;
  font-weight: 800;
}}

details[data-ths-return-curve] .ths-curve-rate strong {{
  color: #ffffff;
  font-size: 18px;
}}

details[data-ths-return-curve] .ths-curve-compare-pill {{
  display: inline-flex;
  align-items: center;
  gap: 18px;
  max-width: 100%;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  color: #697176;
  padding: 7px 18px;
  font-size: 13px;
  font-weight: 800;
}}

details[data-ths-return-curve] .ths-curve-compare-pill[hidden] {{
  display: none;
}}

details[data-ths-return-curve] .ths-curve-compare-pill strong {{
  color: #ff2f45;
  font-weight: 900;
}}

details[data-ths-return-curve] .ths-curve-compare-pill strong.value-negative {{
  color: #137333;
}}

details[data-ths-return-curve] .ths-curve-badge {{
  display: inline-flex;
  width: 22px;
  height: 22px;
  align-items: center;
  justify-content: center;
  border-radius: 5px;
  background: #ffd400;
  color: #ff5a10;
  font-size: 14px;
  font-weight: 900;
}}

details[data-ths-return-curve] .ths-curve-tabs {{
  display: grid;
  width: min(720px, 100%);
  grid-template-columns: repeat(6, minmax(0, 1fr));
  margin-top: 12px;
  color: rgba(255, 255, 255, 0.74);
  font-size: 13px;
  font-weight: 800;
}}

details[data-ths-return-curve] .ths-curve-tab {{
  position: relative;
  appearance: none;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
  padding: 12px 4px 16px;
  text-align: center;
  white-space: nowrap;
}}

details[data-ths-return-curve] .ths-curve-tab:hover,
details[data-ths-return-curve] .ths-curve-tab:focus-visible {{
  color: #ffffff;
}}

details[data-ths-return-curve] .ths-curve-tab:focus-visible {{
  outline: 2px solid rgba(255, 255, 255, 0.84);
  outline-offset: -4px;
  border-radius: 8px;
}}

details[data-ths-return-curve] .ths-curve-tab.is-active {{
  color: #ffffff;
}}

details[data-ths-return-curve] .ths-curve-tab.is-active::after {{
  content: "";
  position: absolute;
  left: 50%;
  bottom: 6px;
  width: 26px;
  height: 5px;
  border-radius: 999px;
  background: #ffffff;
  transform: translateX(-50%);
}}

details[data-ths-return-curve] .ths-curve-custom {{
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  color: rgba(255, 255, 255, 0.88);
  font-size: 12px;
  font-weight: 700;
}}

details[data-ths-return-curve] .ths-curve-custom[hidden] {{
  display: none;
}}

details[data-ths-return-curve] .ths-curve-custom input {{
  min-height: 30px;
  border: 1px solid rgba(255, 255, 255, 0.52);
  border-radius: 7px;
  background: rgba(255, 255, 255, 0.14);
  color: #ffffff;
  padding: 4px 8px;
  font: inherit;
}}

details[data-ths-return-curve] .ths-curve-legend {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(72px, 1fr));
  gap: 10px 16px;
  align-items: center;
  border: 1px solid #edf0f2;
  border-top: 0;
  background: #ffffff;
  padding: 14px 18px 10px;
  color: #5f6368;
  font-size: 13px;
  font-weight: 700;
}}

details[data-ths-return-curve] .ths-curve-legend span {{
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  min-height: 24px;
  white-space: nowrap;
}}

details[data-ths-return-curve] .ths-curve-legend .ths-curve-benchmark-tabs {{
  display: contents;
}}

details[data-ths-return-curve] .ths-curve-legend .ths-curve-benchmark-tabs[hidden] {{
  display: none;
}}

details[data-ths-return-curve] .ths-curve-benchmark {{
  appearance: none;
  display: inline-flex;
  min-height: 24px;
  align-items: center;
  justify-content: flex-start;
  gap: 5px;
  border: 0;
  background: transparent;
  color: #9aa0a6;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
  line-height: 1;
  padding: 0;
  min-width: 0;
  white-space: nowrap;
}}

details[data-ths-return-curve] .ths-curve-benchmark::before {{
  content: "";
  width: 7px;
  height: 7px;
  border-radius: 1px;
  background: #d7d9dc;
  flex: 0 0 auto;
}}

details[data-ths-return-curve] .ths-curve-benchmark:hover,
details[data-ths-return-curve] .ths-curve-benchmark:focus-visible {{
  color: #5f6368;
}}

details[data-ths-return-curve] .ths-curve-benchmark:focus-visible {{
  outline: 2px solid rgba(66, 133, 244, 0.28);
  outline-offset: 4px;
  border-radius: 4px;
}}

details[data-ths-return-curve] .ths-curve-benchmark.is-active {{
  color: #202124;
  font-weight: 900;
}}

details[data-ths-return-curve] .ths-curve-benchmark.is-active::before {{
  background: #4285f4;
}}

details[data-ths-return-curve] .ths-curve-benchmark.is-empty {{
  opacity: 0.58;
}}

details[data-ths-return-curve] .ths-dot {{
  width: 8px;
  height: 8px;
  border-radius: 2px;
}}

details[data-ths-return-curve] .ths-dot-me {{
  background: #ff2f45;
}}

details[data-ths-return-curve] .ths-dot-base {{
  background: #4285f4;
}}

details[data-ths-return-curve] .curve-grid {{
  grid-template-columns: 1fr;
  gap: 0;
  border: 1px solid #edf0f2;
  border-top: 0;
  background: #ffffff;
}}

details[data-ths-return-curve] .curve-card {{
  position: relative;
  border: 0;
  border-radius: 0;
  background: #ffffff;
  box-shadow: none;
  padding: 6px 20px 14px;
}}

details[data-ths-return-curve] .curve-card + .curve-card {{
  border-top: 1px solid #f0f2f4;
}}

details[data-ths-return-curve] .curve-card-head {{
  display: none;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 4px;
}}

details[data-ths-return-curve] .curve-title {{
  color: #202124;
  font-size: 14px;
  font-weight: 800;
}}

details[data-ths-return-curve] .curve-subtitle {{
  color: #9aa0a6;
  font-size: 12px;
}}

details[data-ths-return-curve] .curve-badge {{
  border-color: #ffd4d8;
  background: #fff4f5;
  color: #ff2f45;
  border-radius: 8px;
}}

details[data-ths-return-curve] .curve-svg {{
  display: block;
  width: 100%;
  height: auto;
  aspect-ratio: 620 / 330;
  margin-top: 2px;
  overflow: visible;
}}

details[data-ths-return-curve] .curve-axis {{
  opacity: 0;
}}

details[data-ths-return-curve] .curve-grid-line {{
  stroke: #e8eaed;
  stroke-dasharray: 4 4;
}}

details[data-ths-return-curve] .curve-zero-line {{
  stroke: #dfe3e7;
  stroke-width: 1;
  stroke-dasharray: 4 4;
  opacity: 0.9;
}}

details[data-ths-return-curve] .curve-area {{
  display: none;
}}

details[data-ths-return-curve] .curve-line,
details[data-ths-return-curve] .curve-line-glow {{
  fill: none;
  stroke: #ff2f45;
  stroke-linecap: round;
  stroke-linejoin: round;
}}

details[data-ths-return-curve] .curve-benchmark-line {{
  fill: none;
  stroke-width: 1.3px;
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke: #4285f4;
}}

details[data-ths-return-curve] .curve-line {{
  stroke-width: 1.45px;
}}

details[data-ths-return-curve] .curve-drawdown-band {{
  fill: rgba(255, 143, 15, 0.08);
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-growth-band {{
  fill: rgba(255, 77, 79, 0.07);
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-drawdown-link {{
  fill: none;
  stroke: rgba(255, 143, 15, 0.9);
  stroke-width: 1.25px;
  stroke-dasharray: 4 3;
  stroke-linecap: round;
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-growth-link {{
  fill: none;
  stroke: rgba(255, 77, 79, 0.9);
  stroke-width: 1.25px;
  stroke-dasharray: 4 3;
  stroke-linecap: round;
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-drawdown-marker {{
  fill: #ffffff;
  stroke: #ff9f1a;
  stroke-width: 1.5px;
  opacity: 0.9;
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-growth-marker {{
  fill: #ffffff;
  stroke: #ff4d4f;
  stroke-width: 1.5px;
  opacity: 0.9;
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-drawdown-label {{
  fill: #ff9f1a;
  font-size: 12px;
  font-weight: 900;
  paint-order: stroke;
  stroke: #ffffff;
  stroke-width: 4px;
  stroke-linejoin: round;
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-growth-label {{
  fill: #ff4d4f;
  font-size: 12px;
  font-weight: 900;
  paint-order: stroke;
  stroke: #ffffff;
  stroke-width: 4px;
  stroke-linejoin: round;
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-extreme-layer {{
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-extreme-line {{
  stroke: #ff9f1a;
  stroke-width: 1.1px;
  stroke-dasharray: 5 4;
  opacity: 0.95;
}}

details[data-ths-return-curve] .curve-extreme-label {{
  fill: #ff9f1a;
  font-size: 12px;
  font-weight: 900;
  paint-order: stroke;
  stroke: #ffffff;
  stroke-width: 4px;
  stroke-linejoin: round;
}}

details[data-ths-return-curve] .curve-line-glow {{
  display: none;
}}

details[data-ths-return-curve] .curve-dot,
details[data-ths-return-curve] .curve-dot-last,
details[data-ths-return-curve] .curve-benchmark-dot {{
  fill: #ff2f45;
  stroke: #ffffff;
  stroke-width: 1.5px;
}}

details[data-ths-return-curve] .curve-benchmark-dot {{
  fill: #4285f4;
}}

details[data-ths-return-curve] .curve-hover-capture {{
  fill: transparent;
  pointer-events: all;
}}

details[data-ths-return-curve] .curve-hover-layer {{
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-hover-line {{
  stroke: #6f767d;
  stroke-dasharray: 3 3;
  stroke-width: 1px;
  opacity: 0.55;
}}

details[data-ths-return-curve] .curve-hover-dot {{
  fill: #ffffff;
  stroke-width: 2px;
}}

details[data-ths-return-curve] .curve-hover-dot-me {{
  stroke: #ff2f45;
}}

details[data-ths-return-curve] .curve-hover-dot-base {{
  stroke: #4285f4;
}}

details[data-ths-return-curve] .curve-tooltip {{
  position: absolute;
  z-index: 4;
  min-width: 168px;
  transform: translate(-50%, -100%);
  border: 1px solid rgba(32, 33, 36, 0.08);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 10px 24px rgba(32, 33, 36, 0.14);
  color: #202124;
  font-size: 12px;
  line-height: 1.45;
  padding: 8px 10px;
  pointer-events: none;
}}

details[data-ths-return-curve] .curve-tooltip[hidden] {{
  display: none;
}}

details[data-ths-return-curve] .curve-tooltip-date {{
  margin-bottom: 5px;
  color: #5f6368;
  font-weight: 800;
}}

details[data-ths-return-curve] .curve-tooltip div:not(.curve-tooltip-date) {{
  display: flex;
  justify-content: space-between;
  gap: 16px;
}}

details[data-ths-return-curve] .curve-tooltip span {{
  color: #7b8288;
}}

details[data-ths-return-curve] .curve-tooltip strong {{
  font-weight: 800;
}}

details[data-ths-return-curve] .curve-tooltip-muted {{
  margin-top: 3px;
  color: #8d949b;
}}

details[data-ths-return-curve] .curve-risk-caption {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 4px 34px 8px;
  color: #8d949b;
  font-size: 12px;
  font-weight: 700;
}}

details[data-ths-return-curve] .curve-risk-caption[hidden] {{
  display: none;
}}

details[data-ths-return-curve] .curve-risk-caption span {{
  min-width: 0;
  border: 1px solid #eef1f3;
  border-radius: 8px;
  background: #fafbfc;
  padding: 7px 9px;
}}

details[data-ths-return-curve] .curve-risk-caption em {{
  display: block;
  overflow: hidden;
  color: #9aa0a6;
  font-style: normal;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

details[data-ths-return-curve] .curve-risk-caption strong {{
  display: block;
  overflow: hidden;
  margin-top: 3px;
  color: #34383c;
  font-size: 12.5px;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

details[data-ths-return-curve] .ths-curve-control-panel {{
  display: grid;
  gap: 12px;
  border: 1px solid #edf0f2;
  border-top: 0;
  background: #ffffff;
  padding: 6px 18px 18px;
}}

details[data-ths-return-curve] .ths-curve-analysis-row {{
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr);
  align-items: center;
  gap: 12px;
}}

details[data-ths-return-curve] .ths-curve-row-label {{
  color: #202124;
  font-size: 14px;
  font-weight: 800;
}}

details[data-ths-return-curve] .ths-curve-metric-tabs {{
  display: inline-flex;
  justify-self: center;
  gap: 2px;
  margin: 0;
  padding: 3px;
  border-radius: 8px;
  background: #f3f5f6;
}}

details[data-ths-return-curve] .ths-curve-metric {{
  appearance: none;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: #7b8288;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 800;
  line-height: 1;
  padding: 8px 18px;
  white-space: nowrap;
}}

details[data-ths-return-curve] .ths-curve-metric.is-active {{
  background: #ff2f45;
  color: #ffffff;
}}

details[data-ths-return-curve] .ths-curve-assist-list {{
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px 18px;
}}

details[data-ths-return-curve] .ths-curve-assist {{
  display: inline-flex;
  align-items: center;
  gap: 7px;
  appearance: none;
  border: 0;
  background: transparent;
  color: #34383c;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 800;
  line-height: 1;
  padding: 5px 0;
  white-space: nowrap;
}}

details[data-ths-return-curve] .ths-curve-assist:disabled {{
  cursor: default;
  opacity: 1;
}}

details[data-ths-return-curve] .ths-curve-assist i {{
  width: 15px;
  height: 15px;
  box-sizing: border-box;
  border: 2px solid #a4aaae;
  border-radius: 4px;
  background: #ffffff;
}}

details[data-ths-return-curve] .ths-curve-assist.is-active i {{
  border-color: #ff3b45;
  background:
    linear-gradient(135deg, transparent 0 42%, #ffffff 42% 58%, transparent 58%) center / 65% 65% no-repeat,
    #ff3b45;
}}

details[data-ths-return-curve] .curve-label,
details[data-ths-return-curve] .curve-axis-label {{
  fill: #9aa0a6;
  font-size: 12px;
}}

details[data-ths-return-curve] .curve-y-label {{
  fill: #9aa0a6;
  font-weight: 700;
}}

details[data-ths-return-curve] .curve-end-value {{
  fill: #ff2f45;
  font-size: 12px;
  font-weight: 800;
}}

details[data-ths-return-curve] .ths-curve-summary {{
  display: grid;
  justify-items: center;
  gap: 12px;
  border: 1px solid #edf0f2;
  border-top: 0;
  border-radius: 0 0 16px 16px;
  background: #ffffff;
  padding: 18px;
}}

details[data-ths-return-curve] .ths-curve-summary-title {{
  color: #202124;
  font-size: 15px;
  font-weight: 800;
}}

details[data-ths-return-curve] .ths-curve-summary-value {{
  color: #ff2f45;
  font-size: 38px;
  line-height: 1;
  font-weight: 850;
}}

details[data-ths-return-curve] .ths-curve-summary-value.value-negative {{
  color: #137333;
}}

details[data-ths-return-curve] .ths-curve-bars {{
  display: grid;
  width: min(520px, 100%);
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 28px;
}}

details[data-ths-return-curve] .ths-curve-bars div {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  color: #6f7772;
  font-size: 13px;
  font-weight: 700;
}}

details[data-ths-return-curve] .ths-curve-bars div::before {{
  content: "";
  width: 94px;
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(90deg, #ff2f45 0%, #ff2f45 var(--bar-fill, 72%), #f2f3f4 var(--bar-fill, 72%), #f2f3f4 100%);
  order: 2;
}}

details[data-ths-return-curve] .ths-curve-bars div:nth-child(2)::before {{
  background: linear-gradient(90deg, #4285f4 0%, #4285f4 var(--bar-fill, 16%), #f2f3f4 var(--bar-fill, 16%), #f2f3f4 100%);
}}

details[data-ths-return-curve] .ths-curve-bars div.is-negative::before {{
  background: linear-gradient(90deg, #137333 0%, #137333 var(--bar-fill, 72%), #f2f3f4 var(--bar-fill, 72%), #f2f3f4 100%);
}}

details[data-ths-return-curve] .ths-curve-bars strong {{
  order: 3;
  min-width: 56px;
  color: #ff2f45;
  text-align: right;
}}

details[data-ths-return-curve] .ths-curve-bars div:nth-child(2) strong {{
  color: #4285f4;
}}

.clearance-analysis {{
  display: grid;
  gap: 14px;
}}

.realized-analysis,
.realized-panel {{
  display: grid;
  gap: 14px;
}}

.realized-subtitle,
.clearance-subtitle {{
  margin: 4px 0 -4px;
  color: #202124;
  font-size: 15px;
  line-height: 1.25;
  font-weight: 800;
}}

.realized-toolbar,
.realized-stage-toolbar {{
  flex-wrap: wrap;
}}

.realized-date-input {{
  min-width: 148px;
}}

.realized-range-label {{
  color: #63766b;
  font-size: 12px;
  font-weight: 700;
}}

.pnl-calendar {{
  display: grid;
  grid-template-columns: repeat(7, minmax(92px, 1fr));
  gap: 6px;
  overflow-x: auto;
  padding-bottom: 2px;
}}

.pnl-calendar-weekday {{
  color: #63766b;
  font-size: 12px;
  font-weight: 800;
  text-align: center;
}}

.pnl-calendar-blank {{
  min-height: 92px;
}}

.pnl-calendar-day {{
  --pnl-accent: transparent;
  display: grid;
  min-height: 92px;
  grid-template-rows: auto 1fr auto;
  gap: 5px;
  border: 1px solid #dbe8df;
  border-radius: 8px;
  background: #fbfdfb;
  color: #202124;
  padding: 8px;
  text-align: left;
  cursor: pointer;
  box-shadow: inset 4px 0 0 var(--pnl-accent);
}}

.pnl-calendar-day:hover,
.pnl-calendar-day.is-selected {{
  border-color: #34a853;
  background: #f1faf4;
}}

.pnl-calendar-day.is-selected {{
  box-shadow: inset 4px 0 0 var(--pnl-accent), inset 0 0 0 1px #34a853;
}}

.pnl-calendar-day.has-trades {{
  background: #ffffff;
}}

.pnl-calendar-day.pnl-day-positive {{
  --pnl-accent: #d93025;
  border-color: #f0c7c2;
  background: #fff8f7;
}}

.pnl-calendar-day.pnl-day-negative {{
  --pnl-accent: #137333;
  border-color: #b7dfc1;
  background: #f4fbf6;
}}

.pnl-calendar-day.pnl-day-zero {{
  --pnl-accent: #9aa0a6;
}}

.pnl-calendar-day.pnl-day-mixed {{
  --pnl-accent: #fbbc04;
  border-color: #efd59a;
  background: #fffaf0;
}}

.pnl-calendar-day.pnl-day-positive.is-selected {{
  border-color: #d93025;
  background: #fff4f2;
}}

.pnl-calendar-day.pnl-day-negative.is-selected {{
  border-color: #137333;
  background: #eef8f1;
}}

.pnl-calendar-day.pnl-day-mixed.is-selected {{
  border-color: #fbbc04;
  background: #fff7df;
}}

.pnl-day-number {{
  font-size: 13px;
  font-weight: 800;
}}

.pnl-day-lines {{
  display: grid;
  align-content: start;
  gap: 3px;
  min-width: 0;
}}

.pnl-day-line,
.pnl-day-muted,
.pnl-day-count {{
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

.pnl-day-line {{
  font-size: 11px;
  font-weight: 800;
}}

.pnl-day-line.value-positive {{
  color: #d93025;
}}

.pnl-day-line.value-negative {{
  color: #137333;
}}

.pnl-day-line.value-zero {{
  color: #5f6368;
}}

.pnl-day-muted,
.pnl-day-count {{
  color: #7b8a80;
  font-size: 11px;
}}

.dashboard-topbar {{
  position: sticky;
  top: 0;
  z-index: 5;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  margin: 0 0 14px;
  border: 1px solid #edf0f2;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.94);
  padding: 10px;
  backdrop-filter: blur(12px);
  box-shadow: 0 12px 28px rgba(60, 64, 67, 0.05);
}}

.dashboard-page-tabs {{
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  min-width: 0;
}}

.dashboard-page-tab {{
  appearance: none;
  min-height: 34px;
  border: 1px solid #e2e7ea;
  border-radius: 999px;
  background: #f8fafb;
  color: #59646b;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 850;
  padding: 0 14px;
  white-space: nowrap;
}}

.dashboard-page-tab:hover,
.dashboard-page-tab:focus-visible {{
  border-color: #ff9aa5;
  background: #fff5f6;
  color: #ff2f45;
}}

.dashboard-page-tab:focus-visible {{
  outline: 2px solid rgba(255, 47, 69, 0.18);
  outline-offset: 2px;
}}

.dashboard-page-tab.is-active {{
  border-color: #ff2f45;
  background: #ff2f45;
  color: #ffffff;
  box-shadow: 0 8px 18px rgba(255, 47, 69, 0.16);
}}

.dashboard-currency-switcher {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  justify-self: end;
  padding: 4px;
  border: 1px solid #edf0f2;
  border-radius: 999px;
  background: #f8fafb;
  white-space: nowrap;
}}

.dashboard-currency-switcher span {{
  color: #7b838b;
  font-size: 12px;
  font-weight: 850;
  padding: 0 8px;
}}

.dashboard-currency-switcher button {{
  appearance: none;
  min-height: 30px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #59646b;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  font-weight: 900;
  padding: 0 11px;
}}

.dashboard-currency-switcher button:hover,
.dashboard-currency-switcher button:focus-visible {{
  color: #ff2f45;
}}

.dashboard-currency-switcher button:focus-visible {{
  outline: 2px solid rgba(255, 47, 69, 0.18);
  outline-offset: 2px;
}}

.dashboard-currency-switcher button.is-active {{
  background: #202124;
  color: #ffffff;
  box-shadow: 0 7px 16px rgba(32, 33, 36, 0.12);
}}

.performance-report-shell {{
  display: grid;
  gap: 16px;
}}

.performance-report-mode {{
  justify-self: end;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 4px;
  border-radius: 999px;
  background: #f3f4f6;
}}

.performance-report-mode button {{
  appearance: none;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #6f767d;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 900;
  min-height: 32px;
  padding: 0 14px;
  transition: background 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}}

.performance-report-mode button.is-active {{
  background: #ff4d4f;
  color: #ffffff;
  box-shadow: 0 6px 14px rgba(255, 77, 79, 0.18);
}}

.performance-block {{
  background: #ffffff;
  border: 1px solid #eef1f4;
  border-radius: 16px;
  padding: 18px;
  box-shadow: 0 14px 30px rgba(60, 64, 67, 0.06);
}}

.performance-title,
.performance-title-row h3 {{
  margin: 0;
  color: #202124;
  font-size: 20px;
  font-weight: 900;
}}

.performance-title::before {{
  content: "";
  display: inline-block;
  width: 6px;
  height: 22px;
  margin-right: 10px;
  border-radius: 999px;
  background: #ff4d4f;
  vertical-align: -4px;
}}

.performance-title-row {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}}

.performance-title-row strong {{
  color: #ff4d4f;
  font-size: 15px;
  font-weight: 900;
}}

.performance-title-row em {{
  color: #ff4d4f;
  font-style: normal;
}}

.performance-swing-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 16px;
}}

.performance-swing-card {{
  position: relative;
  min-height: 170px;
  border-radius: 10px;
  padding: 22px;
  overflow: hidden;
}}

.performance-swing-card::after {{
  content: "";
  position: absolute;
  right: 14px;
  bottom: 12px;
  width: 116px;
  height: 96px;
  opacity: 0.13;
  background:
    linear-gradient(135deg, transparent 38%, currentColor 38% 52%, transparent 52%),
    linear-gradient(45deg, transparent 45%, currentColor 45% 58%, transparent 58%);
}}

.performance-swing-card span,
.performance-swing-card small {{
  display: block;
  color: #6b7280;
  font-size: 14px;
  font-weight: 800;
}}

.performance-swing-card strong {{
  display: block;
  margin-top: 18px;
  font-size: 42px;
  line-height: 1;
  font-weight: 950;
}}

.performance-swing-card em {{
  display: block;
  margin: 8px 0 22px;
  font-size: 20px;
  font-style: normal;
  font-weight: 900;
}}

.performance-swing-card small + small {{
  margin-top: 8px;
}}

.swing-positive {{
  color: #ff4d4f;
  background: #fff1f1;
}}

.swing-negative {{
  color: #4285f4;
  background: #eef4ff;
}}

.performance-compare-list {{
  display: grid;
  gap: 14px;
  margin-top: 14px;
}}

.performance-compare-card {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) 58px minmax(0, 1fr);
  gap: 12px;
  align-items: center;
  position: relative;
  padding: 18px 18px 34px;
  border-radius: 12px;
  background: #ffffff;
  border: 1px solid #f0f2f5;
  box-shadow: 0 12px 26px rgba(60, 64, 67, 0.05);
}}

.performance-compare-card div:last-of-type {{
  text-align: right;
}}

.performance-compare-card strong {{
  display: block;
  color: #202124;
  font-size: 18px;
  font-weight: 900;
}}

.performance-compare-card span {{
  display: block;
  margin-top: 3px;
  color: #9aa0a6;
  font-size: 13px;
  font-weight: 700;
}}

.performance-compare-card em {{
  display: block;
  margin-top: 12px;
  font-size: 19px;
  font-style: normal;
  font-weight: 900;
}}

.performance-compare-card b {{
  justify-self: center;
  color: #202124;
  font-size: 20px;
  font-weight: 900;
}}

.performance-compare-card i {{
  position: absolute;
  left: 18px;
  right: 18px;
  bottom: 15px;
  height: 12px;
  border-radius: 999px;
  overflow: hidden;
  background:
    linear-gradient(90deg, #ff514d 0 var(--left), #ffffff var(--left) calc(var(--left) + 2px), #4285f4 calc(var(--left) + 2px) 100%);
}}

.performance-calendar-toolbar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin: 4px 0 14px;
}}

.performance-year-controls {{
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 4px;
  border-radius: 999px;
  background: #f3f4f6;
}}

.performance-year-button {{
  appearance: none;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #6f767d;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
  font-weight: 900;
  padding: 7px 12px;
  transition: background 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}}

.performance-year-button.is-active {{
  background: #ff4d4f;
  color: #ffffff;
  box-shadow: 0 6px 14px rgba(255, 77, 79, 0.18);
}}

.performance-calendar-stats {{
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}

.performance-calendar-stats span {{
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  background: #f7f8fa;
  color: #7b838b;
  font-size: 12px;
  font-weight: 900;
}}

.performance-calendar-stats b {{
  color: #202124;
  font-size: 13px;
}}

.performance-calendar-chart-wrap {{
  border: 1px solid #eef1f4;
  border-radius: 14px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%);
  padding: 10px 12px 8px;
  overflow: hidden;
}}

.performance-calendar-chart {{
  display: block;
  width: 100%;
  height: 236px;
}}

.performance-chart-grid {{
  stroke: #edf0f3;
  stroke-width: 1;
  stroke-dasharray: 4 5;
}}

.performance-chart-axis {{
  stroke: #d8dde3;
  stroke-width: 1.2;
}}

.performance-chart-bar-positive {{
  fill: #ff514d;
}}

.performance-chart-bar-negative {{
  fill: #4f83f1;
}}

.performance-chart-bar {{
  cursor: pointer;
}}

.performance-chart-bar.is-selected {{
  stroke: #202124;
  stroke-width: 2px;
}}

.performance-chart-x,
.performance-chart-y,
.performance-chart-empty {{
  fill: #9aa0a6;
  font-size: 12px;
  font-weight: 800;
}}

.performance-calendar {{
  display: grid;
  gap: 14px;
  margin-top: 14px;
}}

.performance-year-group {{
  border: 1px solid #eef1f4;
  border-radius: 14px;
  background: #ffffff;
  padding: 14px;
}}

.performance-year-head {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}}

.performance-year-head strong {{
  color: #202124;
  font-size: 17px;
  font-weight: 950;
}}

.performance-year-head span {{
  color: #ff4d4f;
  font-size: 15px;
  font-weight: 950;
}}

.performance-calendar-grid {{
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 7px;
}}

.performance-month {{
  appearance: none;
  border: 0;
  min-height: 88px;
  border-radius: 9px;
  padding: 11px 8px;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 6px;
  text-align: center;
  color: #ffffff;
  cursor: pointer;
  font: inherit;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.22);
  transition: box-shadow 0.16s ease, transform 0.16s ease;
}}

.performance-month:hover {{
  transform: translateY(-1px);
}}

.performance-month.is-selected {{
  box-shadow:
    0 0 0 2px #ffffff,
    0 0 0 4px #ffcc33,
    0 10px 22px rgba(60, 64, 67, 0.13);
}}

.performance-month span {{
  color: rgba(255, 255, 255, 0.72);
  font-size: 14px;
  font-weight: 900;
}}

.performance-month strong {{
  font-size: 19px;
  line-height: 1.05;
  font-weight: 950;
}}

.performance-month small {{
  color: rgba(255, 255, 255, 0.62);
  font-size: 11px;
  font-weight: 800;
}}

.performance-month-positive {{
  background: rgba(255, 91, 82, var(--tile-alpha, 0.86));
}}

.performance-month-negative {{
  background: rgba(82, 128, 230, var(--tile-alpha, 0.86));
}}

.performance-month-zero {{
  background: #eef1f5;
  color: #a4abb3;
}}

.performance-month-zero span,
.performance-month-zero small {{
  color: #a4abb3;
}}

.performance-stock-board {{
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(280px, 0.95fr);
  gap: 14px;
  align-items: stretch;
}}

.performance-treemap {{
  position: relative;
  display: block;
  min-height: 320px;
  border: 1px solid #eef1f4;
  border-radius: 14px;
  background: #f7f8fb;
  padding: 6px;
  overflow: hidden;
}}

.performance-treemap .performance-empty {{
  position: absolute;
  inset: 0;
  min-height: 0;
}}

.performance-empty {{
  width: 100%;
  min-height: 190px;
  display: grid;
  place-items: center;
  color: #9aa0a6;
  font-size: 14px;
  font-weight: 900;
}}

.performance-stock-tile {{
  position: absolute;
  box-sizing: border-box;
  min-width: 0;
  min-height: 0;
  border: 2px solid #f7f8fb;
  border-radius: 7px;
  padding: 11px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  color: #ffffff;
  overflow: hidden;
}}

.performance-stock-tile span {{
  max-width: 100%;
  font-size: 14px;
  line-height: 1.12;
  font-weight: 950;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

.performance-stock-tile strong {{
  margin-top: 5px;
  max-width: 100%;
  font-size: 13px;
  line-height: 1.12;
  font-weight: 950;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

.performance-stock-tile small {{
  margin-top: 3px;
  max-width: 100%;
  color: rgba(255, 255, 255, 0.68);
  font-size: 11px;
  line-height: 1.1;
  font-weight: 800;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

.performance-stock-tile.is-small {{
  padding: 8px 6px;
}}

.performance-stock-tile.is-small span {{
  font-size: 12px;
}}

.performance-stock-tile.is-small strong {{
  font-size: 11px;
}}

.performance-stock-tile.is-small small,
.performance-stock-tile.is-compact strong,
.performance-stock-tile.is-compact small {{
  display: none;
}}

.performance-stock-tile.is-compact {{
  padding: 4px;
}}

.performance-stock-tile.is-compact span {{
  font-size: 11px;
}}

.performance-stock-positive {{
  background: #ff6b5f;
}}

.performance-stock-negative {{
  background: #5b86e8;
}}

.performance-stock-list {{
  display: grid;
  gap: 12px;
}}

.performance-stock-rank {{
  border: 1px solid #eef1f4;
  border-radius: 14px;
  background: #ffffff;
  padding: 14px;
}}

.performance-stock-rank h4 {{
  margin: 0 0 10px;
  color: #202124;
  font-size: 15px;
  font-weight: 950;
}}

.performance-stock-rank ol {{
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 8px;
}}

.performance-stock-rank li {{
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-height: 30px;
}}

.performance-stock-rank li span {{
  width: 22px;
  height: 22px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  background: #f2f4f7;
  color: #8c939b;
  font-size: 11px;
  font-weight: 950;
}}

.performance-stock-rank li strong {{
  min-width: 0;
  color: #3c4043;
  font-size: 13px;
  font-weight: 900;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}

.performance-stock-rank li em {{
  font-style: normal;
  font-size: 13px;
  font-weight: 950;
}}

.performance-stock-empty {{
  grid-template-columns: 1fr !important;
  color: #a4abb3;
  font-size: 13px;
  font-weight: 900;
}}

@media (max-width: 1180px) {{
  .currency-overview-grid {{
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }}

  .metric-card-hero,
  .metric-card-return,
  .metric-card-annual,
  .metric-card-broad,
  .metric-card-mini,
  .metric-card-muted {{
    grid-column: span 6;
  }}
}}

@media (max-width: 980px) {{
  .holdings-account-grid {{
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }}

  .holdings-account-metric:nth-child(2n) {{
    border-right: 0;
  }}

  .holdings-account-metric:nth-child(n + 3) {{
    border-top: 1px solid #f0f2f4;
  }}
}}

@media (max-width: 760px) {{
  .currency-overview-grid {{
    grid-template-columns: 1fr;
  }}

  .dashboard-grid {{
    grid-template-columns: 1fr;
  }}

  .holdings-account-grid {{
    grid-template-columns: 1fr;
  }}

  .holdings-account-metric {{
    min-height: 0;
    border-right: 0;
    border-top: 1px solid #f0f2f4;
    padding: 13px 14px;
  }}

  .holdings-account-metric:first-child {{
    border-top: 0;
  }}

  .holdings-account-value {{
    font-size: 21px;
  }}

  .holdings-month-sparkline {{
    width: 100%;
    min-width: 0;
  }}

  .holdings-realized-range {{
    grid-template-columns: 1fr;
    align-items: stretch;
  }}

  .holdings-realized-head {{
    align-items: flex-start;
  }}

  .dashboard-topbar {{
    position: static;
    grid-template-columns: 1fr;
    padding: 8px;
  }}

  .dashboard-currency-switcher {{
    justify-self: stretch;
    overflow-x: auto;
  }}

  .dashboard-currency-switcher button {{
    flex: 1;
  }}

  .dashboard-page-tab {{
    flex: 1 1 calc(50% - 8px);
    padding-inline: 10px;
  }}

  .metric-card-hero,
  .metric-card-return,
  .metric-card-annual,
  .metric-card-broad,
  .metric-card-mini,
  .metric-card-muted {{
    grid-column: 1 / -1;
    min-height: 0;
  }}

  details[data-ths-return-curve] .ths-curve-value {{
    font-size: 34px;
  }}

  details[data-ths-return-curve] .ths-curve-tabs {{
    grid-template-columns: repeat(3, minmax(0, 1fr));
    font-size: 12px;
  }}

  details[data-ths-return-curve] .ths-curve-legend {{
    grid-template-columns: repeat(auto-fit, minmax(68px, 1fr));
    gap: 10px 12px;
  }}

  details[data-ths-return-curve] .ths-curve-legend .ths-curve-benchmark-tabs {{
    display: contents;
  }}

  details[data-ths-return-curve] .ths-curve-benchmark {{
    justify-content: flex-start;
  }}

  details[data-ths-return-curve] .curve-card {{
    padding: 10px 10px 16px;
  }}

  details[data-ths-return-curve] .curve-card-head {{
    align-items: flex-start;
  }}

  details[data-ths-return-curve] .curve-risk-caption {{
    grid-template-columns: repeat(2, minmax(0, 1fr));
    margin: 4px 6px 8px;
  }}

  details[data-ths-return-curve] .ths-curve-analysis-row {{
    grid-template-columns: 1fr;
    gap: 8px;
  }}

  details[data-ths-return-curve] .ths-curve-metric-tabs {{
    width: 100%;
  }}

  details[data-ths-return-curve] .ths-curve-metric {{
    flex: 1;
  }}

  details[data-ths-return-curve] .ths-curve-compare-pill {{
    flex-wrap: wrap;
    justify-content: center;
    gap: 6px 14px;
  }}

  details[data-ths-return-curve] .ths-curve-bars {{
    grid-template-columns: 1fr;
  }}

  .performance-report-mode {{
    justify-self: stretch;
    width: 100%;
  }}

  .performance-report-mode button {{
    flex: 1;
  }}

  .performance-swing-grid,
  .performance-compare-card {{
    grid-template-columns: 1fr;
  }}

  .performance-compare-card div:last-of-type {{
    text-align: left;
  }}

  .performance-calendar-toolbar {{
    align-items: stretch;
  }}

  .performance-year-controls,
  .performance-calendar-stats {{
    width: 100%;
  }}

  .performance-calendar-grid {{
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }}

  .performance-stock-board {{
    grid-template-columns: 1fr;
  }}

  .performance-swing-card strong {{
    font-size: 34px;
  }}
}}

.summary-table th,
.summary-table td {{
  padding: 7px 7px;
  font-size: 12.5px;
  line-height: 1.3;
}}

.summary-table thead th {{
  padding-right: 14px;
}}

.summary-wrap .summary-table {{
  width: max-content;
  min-width: 100%;
}}

.summary-wrap .summary-table.fit-width {{
  width: 100%;
  min-width: 100%;
  table-layout: auto;
}}

.summary-table th {{
  position: relative;
}}

.summary-table tfoot tr + tr td {{
  border-top: 1px solid #d8e6dc;
}}

.summary-table tfoot tr.summary-footer-cny td {{
  background: #f3fbf6;
  border-top: 2px solid #9bd0ad;
  font-weight: 700;
}}

.summary-table thead th.sort-asc::after,
.summary-table thead th.sort-desc::after {{
  right: 5px;
}}

.summary-table th,
.summary-table td,
.summary-table td.num,
.summary-table td.money,
.summary-table td.percent,
.summary-table td.ccy,
.summary-table th.num,
.summary-table th.money,
.summary-table th.percent,
.summary-table th.ccy,
.ritz .waffle th,
.ritz .waffle td,
.ritz .waffle td.num,
.ritz .waffle td.date,
.ritz .waffle td.money,
.ritz .waffle td.percent,
.ritz .waffle td.ccy {{
  text-align: left;
}}

.ritz .waffle th,
.ritz .waffle td {{
  padding: 6px 8px;
  line-height: 1.32;
}}
"""
    try:
        css = css_path.read_text(encoding="utf-8")
        if marker in css:
            css = css.split(marker, 1)[0].rstrip() + "\n"
        css_path.write_text(css.rstrip() + "\n" + override.lstrip(), encoding="utf-8")
    except OSError:
        return


def strip_redundant_table_currency_labels(html_text: str) -> str:
    table_pattern = re.compile(r"<table\b(?=[^>]*class=\"[^\"]*\bsummary-table\b)[^>]*>.*?</table>", re.S)

    def strip_table(table_match: re.Match[str]) -> str:
        table_html = table_match.group(0)
        header_match = re.search(r"<thead>\s*<tr>(.*?)</tr>\s*</thead>", table_html, re.S)
        if not header_match:
            return table_html
        header_labels = [cell_text(cell) for cell in re.findall(r"<th\b[^>]*>.*?</th>", header_match.group(1), re.S)]
        if "币种" not in header_labels:
            return table_html

        def strip_money_cell(match: re.Match[str]) -> str:
            return re.sub(r">(人民币|港币|美元)\s+", ">", match.group(0), count=1)

        return re.sub(
            r"<td\b(?=[^>]*class=\"[^\"]*\bmoney\b)[^>]*>.*?</td>",
            strip_money_cell,
            table_html,
            flags=re.S,
        )

    return table_pattern.sub(strip_table, html_text)


def tidy_preview_table_currency_labels(output_dir: Path) -> None:
    html_path = output_dir / "index.html"
    if not html_path.exists():
        return
    try:
        html_text = html_path.read_text(encoding="utf-8")
        html_path.write_text(strip_redundant_table_currency_labels(html_text), encoding="utf-8")
    except OSError:
        return
