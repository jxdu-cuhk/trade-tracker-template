from __future__ import annotations

import html
import re

from . import state


DETAILS_PATTERN = re.compile(
    r'<details class="dashboard-section section-collapsible"(?: [^>]*)?>.*?</details>',
    re.S,
)


def section_title(section_html: str) -> str:
    match = re.search(r'<h2 class="section-title">(.*?)</h2>', section_html, re.S)
    if not match:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<.*?>", "", match.group(1))).strip()


def tone_class(value: float | None) -> str:
    if value is None:
        return "value-zero"
    if value > 0:
        return "value-positive"
    if value < 0:
        return "value-negative"
    return "value-zero"


def format_money(value: object, signed: bool = False) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "--"
    sign = "+" if signed and numeric > 0 else ""
    return f"{sign}{numeric:,.2f}"


def money_value(value: object, signed: bool = False) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return (
        f'<strong class="{tone_class(numeric) if signed else ""}" '
        f'data-reporting-money-cny="{numeric:.12g}" '
        f'data-reporting-money-sign="{"true" if signed else "false"}">{html.escape(format_money(numeric, signed))}</strong>'
    )


def metric_card(label: str, value: object, note: str, *, signed: bool = False) -> str:
    return f"""
      <div class="capital-quality-metric">
        <span>{html.escape(label)}</span>
        {money_value(value, signed=signed)}
        <em>{html.escape(note)}</em>
      </div>
    """


def status_class(status: object) -> str:
    text = str(status or "good")
    if text == "danger":
        return "is-danger"
    if text == "warn":
        return "is-warn"
    return "is-good"


def quality_item(item: dict[str, object]) -> str:
    return f"""
      <li class="{status_class(item.get("status"))}">
        <span>{html.escape(str(item.get("label") or ""))}</span>
        <strong>{html.escape(str(item.get("text") or ""))}</strong>
      </li>
    """


def option_source_breakdown(option_totals: dict[str, object]) -> str:
    explicit = float(option_totals.get("explicitCapitalCny") or 0.0)
    cash_put = float(option_totals.get("inferredCashSecuredPutCny") or 0.0)
    premium = float(option_totals.get("inferredPremiumCny") or 0.0)
    missing = int(option_totals.get("missingCapitalCount") or 0)
    rows = [
        ("表内资金", explicit, "手工录入的占用本金/保证金"),
        ("卖出认沽兜底", cash_put, "行权价 x 乘数 x 张数 - 权利金 + 费用"),
        ("买入期权成本", premium, "权利金 + 费用"),
    ]
    parts = [
        f"<li><span>{html.escape(label)}</span>{money_value(value)}<em>{html.escape(note)}</em></li>"
        for label, value, note in rows
        if abs(value) > 0.000001
    ]
    if missing:
        parts.append(f'<li class="is-danger"><span>缺资金口径</span><strong>{missing} 条</strong><em>卖出认购等无限风险腿不自动虚构本金</em></li>')
    if not parts:
        parts.append('<li><span>期权资金</span><strong>暂无未平仓期权资金占用</strong><em>没有需要兜底的期权腿</em></li>')
    return "\n".join(parts)


def render_capital_quality_section(payload: dict[str, object]) -> str:
    capital = payload.get("capital") if isinstance(payload, dict) else {}
    quality = payload.get("dataQuality") if isinstance(payload, dict) else {}
    if not isinstance(capital, dict):
        capital = {}
    if not isinstance(quality, dict):
        quality = {}
    option_capital = capital.get("optionCapital") if isinstance(capital.get("optionCapital"), dict) else {}
    option_totals = option_capital.get("totals") if isinstance(option_capital, dict) else {}
    if not isinstance(option_totals, dict):
        option_totals = {}
    quality_items = [item for item in quality.get("items", []) if isinstance(item, dict)]
    status = str(quality.get("status") or "good")
    label = str(quality.get("label") or "良好")
    return f"""
<details class="dashboard-section section-collapsible" open data-capital-quality>
  <summary class="section-summary">
    <div class="section-head">
      <div>
        <h2 class="section-title">资金口径 / 数据质量</h2>
        <p class="section-note">把账户资产、风险敞口、持仓成本、期权占用和行情可信度放在同一层，方便判断收益率分母和当日盈亏是否用了兜底口径。</p>
      </div>
      <span class="section-toggle" aria-hidden="true"></span>
    </div>
  </summary>
  <div class="section-body">
    <div class="capital-quality-shell">
      <div class="capital-quality-status {status_class(status)}">
        <span>数据状态</span>
        <strong>{html.escape(label)}</strong>
      </div>
      <div class="capital-quality-grid">
        {metric_card("账户资产口径", capital.get("accountAssetCny", 0.0), "折统一口径，不含现金，扣除卖出认沽占用")}
        {metric_card("风险敞口", capital.get("marketExposureCny", 0.0), "按仓位绝对值，含卖出认沽占用")}
        {metric_card("成本 / 占用", capital.get("holdingCostCny", 0.0), "现股成本 + 当前策略资金")}
        {metric_card("持仓浮盈", capital.get("holdingFloatPnlCny", 0.0), "当前持仓浮盈，已按统一汇率折算", signed=True)}
      </div>
      <div class="capital-quality-columns">
        <div class="capital-quality-card">
          <h3>期权资金口径</h3>
          <ul class="capital-quality-breakdown">
            {option_source_breakdown(option_totals)}
          </ul>
        </div>
        <div class="capital-quality-card">
          <h3>数据健康</h3>
          <ul class="capital-quality-list">
            {"".join(quality_item(item) for item in quality_items)}
          </ul>
        </div>
      </div>
    </div>
  </div>
</details>
"""


def insert_capital_quality_section(html_text: str) -> str:
    if "data-capital-quality" in html_text:
        return html_text
    payload = state.DISPLAY_PAYLOAD if isinstance(state.DISPLAY_PAYLOAD, dict) else {}
    if not payload:
        return html_text
    section_html = render_capital_quality_section(payload)
    sections = list(DETAILS_PATTERN.finditer(html_text))
    if not sections:
        return html_text
    for match in sections:
        if section_title(match.group(0)) == "当前持仓":
            return html_text[: match.end()] + "\n" + section_html + html_text[match.end() :]
    first = sections[0]
    return html_text[: first.end()] + "\n" + section_html + html_text[first.end() :]
