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
  gap: 8px;
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
  grid-template-columns: repeat(7, minmax(0, 1fr));
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
  display: flex;
  gap: 24px;
  align-items: center;
  border: 1px solid #edf0f2;
  border-top: 0;
  background: #ffffff;
  padding: 14px 18px 8px;
  color: #5f6368;
  font-size: 13px;
  font-weight: 700;
}}

details[data-ths-return-curve] .ths-curve-legend span {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
  border: 0;
  border-radius: 0;
  background: #ffffff;
  box-shadow: none;
  padding: 10px 18px 18px;
}}

details[data-ths-return-curve] .curve-card + .curve-card {{
  border-top: 1px solid #f0f2f4;
}}

details[data-ths-return-curve] .curve-card-head {{
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
  min-height: 250px;
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
  stroke: #4285f4;
  stroke-width: 1.3px;
  stroke-linecap: round;
  stroke-linejoin: round;
}}

details[data-ths-return-curve] .curve-line {{
  stroke-width: 1.45px;
}}

details[data-ths-return-curve] .curve-card.is-excess-mode .curve-line {{
  stroke: #ff8a00;
}}

details[data-ths-return-curve] .curve-card.is-excess-mode .curve-dot,
details[data-ths-return-curve] .curve-card.is-excess-mode .curve-dot-last {{
  fill: #ff8a00;
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

details[data-ths-return-curve] .ths-dot-excess {{
  background: #ff8a00;
}}

details[data-ths-return-curve] .ths-curve-mode-tabs {{
  display: inline-flex;
  justify-self: center;
  gap: 2px;
  margin: 8px 0 0;
  padding: 3px;
  border-radius: 999px;
  background: #f3f5f6;
}}

details[data-ths-return-curve] .ths-curve-mode {{
  appearance: none;
  border: 0;
  border-radius: 999px;
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

details[data-ths-return-curve] .ths-curve-mode.is-active {{
  background: #ff2f45;
  color: #ffffff;
}}

details[data-ths-return-curve] .curve-label,
details[data-ths-return-curve] .curve-axis-label {{
  fill: #9aa0a6;
  font-size: 12px;
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
    grid-template-columns: repeat(4, minmax(0, 1fr));
    font-size: 12px;
  }}

  details[data-ths-return-curve] .ths-curve-legend {{
    gap: 14px;
    flex-wrap: wrap;
  }}

  details[data-ths-return-curve] .curve-card {{
    padding: 10px 10px 16px;
  }}

  details[data-ths-return-curve] .ths-curve-bars {{
    grid-template-columns: 1fr;
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
  min-width: 0;
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
