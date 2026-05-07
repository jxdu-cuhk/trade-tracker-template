from __future__ import annotations

import html
import re

from .utils import cell_text, clean_text


SECTION_ORDER = [
    "当前持仓",
    "未平仓期权",
    "盈亏日历 / 阶段账单",
    "清仓分析",
    "总体概览",
    "总收益曲线",
    "分年度个股汇总",
    "交易时间线",
]
DEFAULT_OPEN_SECTIONS = {"当前持仓", "未平仓期权"}


DETAILS_PATTERN = re.compile(
    r'<details class="dashboard-section section-collapsible" open(?: [^>]*)?>.*?</details>',
    re.S,
)


def normalize_title(value: str) -> str:
    return re.sub(r"\s+", "", cell_text(value))


def section_title(section_html: str) -> str:
    match = re.search(r'<h2 class="section-title">(.*?)</h2>', section_html, re.S)
    return cell_text(match.group(1)) if match else ""


def reorder_dashboard_sections(html_text: str) -> str:
    sections = list(DETAILS_PATTERN.finditer(html_text))
    if len(sections) < 2:
        return html_text

    order = {normalize_title(title): index for index, title in enumerate(SECTION_ORDER)}
    ordered_sections: list[str] = []
    remaining_sections: list[str] = []
    indexed_sections = []

    for match in sections:
        block = match.group(0)
        normalized = normalize_title(section_title(block))
        if normalized in order:
            indexed_sections.append((order[normalized], block))
        else:
            remaining_sections.append(block)

    if not indexed_sections:
        return html_text

    ordered_sections = [block for _index, block in sorted(indexed_sections, key=lambda item: item[0])]
    rebuilt = "\n".join(ordered_sections + remaining_sections)
    first, last = sections[0], sections[-1]
    return html_text[: first.start()] + rebuilt + html_text[last.end() :]


def collapse_secondary_sections(html_text: str) -> str:
    sections = list(DETAILS_PATTERN.finditer(html_text))
    if len(sections) < 2:
        return html_text

    default_open = {normalize_title(title) for title in DEFAULT_OPEN_SECTIONS}
    updated = html_text
    for match in reversed(sections):
        block = match.group(0)
        if normalize_title(section_title(block)) in default_open:
            continue
        collapsed = re.sub(r"(<details\b[^>]*)\sopen\b", r"\1", block, count=1)
        updated = updated[: match.start()] + collapsed + updated[match.end() :]
    return updated


def value_tone_class(text: str) -> str:
    cleaned = clean_text(text)
    if not cleaned or cleaned in {"-", "--"}:
        return "value-zero"
    numeric = re.sub(r"[^0-9.\-]", "", cleaned)
    try:
        value = float(numeric)
    except ValueError:
        value = 0.0
    if value > 0:
        return "value-positive"
    if value < 0:
        return "value-negative"
    return "value-zero"


def extract_cny_overview_metric(html_text: str, metric: str) -> str:
    marker = "currency-overview-card currency-overview-cny-card"
    start = html_text.find(marker)
    if start < 0:
        return ""
    snippet = html_text[start : start + 2600]
    pattern = rf"<span>{re.escape(metric)}</span>\s*<strong[^>]*>(.*?)</strong>"
    match = re.search(pattern, snippet, re.S)
    return cell_text(match.group(1)) if match else ""


def extract_curve_fallback_total(html_text: str) -> str:
    match = re.search(r'<div class="curve-badge[^"]*">(.*?)</div>', html_text, re.S)
    text = cell_text(match.group(1)) if match else ""
    return re.sub(r"^(人民币|港币|美元)\s+", "", text).strip()


def render_ths_curve_top(total_pnl: str, return_rate: str) -> str:
    total_text = total_pnl or "--"
    rate_text = return_rate or "--"
    total_class = value_tone_class(total_text)
    rate_class = value_tone_class(rate_text)
    return f"""
            <div class="ths-curve-hero">
              <div class="ths-curve-kicker" data-curve-hero-kicker>全部盈亏</div>
              <div class="ths-curve-value {html.escape(total_class)}" data-curve-hero-value>{html.escape(total_text)}</div>
              <div class="ths-curve-rate"><span class="ths-curve-badge">账</span> <span data-curve-hero-rate-label>净资产收益率</span> <strong class="{html.escape(rate_class)}" data-curve-hero-rate>{html.escape(rate_text)}</strong></div>
              <div class="ths-curve-tabs" aria-label="收益曲线时间范围">
                <button type="button" class="ths-curve-tab" data-curve-range="day">当日</button>
                <button type="button" class="ths-curve-tab" data-curve-range="month">本月</button>
                <button type="button" class="ths-curve-tab" data-curve-range="three-month">近三月</button>
                <button type="button" class="ths-curve-tab" data-curve-range="year">今年</button>
                <button type="button" class="ths-curve-tab" data-curve-range="three-year">近三年</button>
                <button type="button" class="ths-curve-tab is-active" data-curve-range="all">全部</button>
                <button type="button" class="ths-curve-tab" data-curve-range="custom">自定义</button>
              </div>
              <div class="ths-curve-custom" data-curve-custom hidden>
                <input type="date" data-curve-custom-start aria-label="收益曲线开始日期">
                <span>至</span>
                <input type="date" data-curve-custom-end aria-label="收益曲线结束日期">
              </div>
            </div>
            <div class="ths-curve-legend" aria-label="收益曲线图例">
              <span><i class="ths-dot ths-dot-me"></i>我</span>
              <span><i class="ths-dot ths-dot-base"></i>上证指数</span>
            </div>
            <div class="ths-curve-control-row">
              <div class="ths-curve-metric-tabs" aria-label="收益曲线口径">
                <button type="button" class="ths-curve-metric is-active" data-curve-metric="return">收益率</button>
                <button type="button" class="ths-curve-metric" data-curve-metric="amount">盈亏金额</button>
              </div>
            </div>
"""


def render_ths_curve_summary(return_rate: str) -> str:
    rate_text = return_rate or "--"
    rate_class = value_tone_class(rate_text)
    beat_text = rate_text if rate_text != "--" else "--"
    return f"""
            <div class="ths-curve-summary">
              <div class="ths-curve-summary-title" data-curve-summary-title>对比上证指数</div>
              <div class="ths-curve-summary-value {html.escape(rate_class)}" data-curve-summary-value>{html.escape(beat_text)}</div>
              <div class="ths-curve-bars">
                <div><span>我:</span><strong class="{html.escape(rate_class)}" data-curve-summary-mine>{html.escape(rate_text)}</strong></div>
                <div><span data-curve-summary-benchmark-name>上证指数:</span><strong data-curve-summary-benchmark>--</strong></div>
              </div>
            </div>
"""


def apply_tonghuashun_curve_style(html_text: str) -> str:
    if re.search(r'<details\b[^>]*\bdata-ths-return-curve\b', html_text):
        return html_text

    title_index = html_text.find('<h2 class="section-title">总收益曲线</h2>')
    if title_index < 0:
        return html_text
    details_start = html_text.rfind('<details class="dashboard-section section-collapsible" open', 0, title_index)
    if details_start < 0:
        return html_text
    details_end = html_text.find("</details>", title_index)
    if details_end < 0:
        return html_text
    details_end += len("</details>")

    section = html_text[details_start:details_end]
    if '<div class="curve-grid' not in section:
        return html_text

    total_pnl = extract_cny_overview_metric(html_text, "总盈亏") or extract_curve_fallback_total(section)
    return_rate = extract_cny_overview_metric(html_text, "总收益率")
    curve_top = render_ths_curve_top(total_pnl, return_rate)
    curve_summary = render_ths_curve_summary(return_rate)

    section = section.replace(
        '<details class="dashboard-section section-collapsible" open>',
        '<details class="dashboard-section section-collapsible" open data-ths-return-curve>',
        1,
    )
    section = re.sub(
        r'<p class="section-note">.*?</p>',
        '<p class="section-note">红线为历史每天的总盈亏：截至当天已实现盈亏 + 当天仍持仓的收盘浮盈/浮亏；买入当天只记入持仓基准，下一组可比收盘点开始贡献波动。港币和美元按当前汇率折成人民币后合并展示，蓝线对比上证指数。</p>',
        section,
        count=1,
        flags=re.S,
    )
    section = re.sub(r'(<div class="curve-grid\b[^>]*>)', curve_top + r"\1", section, count=1)
    details_close = section.rfind("</details>")
    body_close = section.rfind("</div>", 0, details_close)
    if body_close >= 0:
        section = section[:body_close] + curve_summary + section[body_close:]
    return html_text[:details_start] + section + html_text[details_end:]
