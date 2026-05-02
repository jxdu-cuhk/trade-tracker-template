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

.clearance-analysis {{
  display: grid;
  gap: 14px;
}}

.clearance-subtitle {{
  margin: 4px 0 -4px;
  color: #202124;
  font-size: 15px;
  line-height: 1.25;
  font-weight: 800;
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

@media (max-width: 760px) {{
  .currency-overview-grid {{
    grid-template-columns: 1fr;
  }}

  .dashboard-grid {{
    grid-template-columns: 1fr;
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
