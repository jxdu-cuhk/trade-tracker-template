from __future__ import annotations

import html
import re

from .utils import cell_text, clean_text


SECTION_ORDER = [
    "当前持仓",
    "未平仓期权",
    "盈亏日历 / 阶段账单",
    "清仓分析",
    "期权收益分析",
    "总体概览",
    "总收益曲线",
    "收益报告",
    "分年度个股汇总",
    "交易时间线",
]
DEFAULT_OPEN_SECTIONS = {"当前持仓", "未平仓期权"}


DETAILS_PATTERN = re.compile(
    r'<details class="dashboard-section section-collapsible"(?: [^>]*)?>.*?</details>',
    re.S,
)
DASHBOARD_PAGER_MARKER = 'data-dashboard-page-tabs'


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


DASHBOARD_PAGER_HTML = """
<nav class="dashboard-page-tabs" data-dashboard-page-tabs aria-label="看板分页"></nav>
"""


DASHBOARD_PAGER_SCRIPT = """
<script>
(function setupDashboardPager() {
  function ready(callback) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", callback, { once: true });
      return;
    }
    callback();
  }

  ready(function() {
    var tabs = document.querySelector("[data-dashboard-page-tabs]");
    if (!tabs || tabs.dataset.ready === "1") return;
    tabs.dataset.ready = "1";
    var sections = Array.prototype.slice.call(document.querySelectorAll("details.dashboard-section.section-collapsible"));
    if (!sections.length) return;

    function titleFor(section) {
      var title = section.querySelector(".section-title");
      return title ? title.textContent.replace(/\\s+/g, " ").trim() : "";
    }

    function keyFor(title) {
      return title.replace(/\\s+/g, "-").replace(/[^\\w\\u4e00-\\u9fff-]+/g, "-");
    }

    function setActive(targetKey) {
      var showAll = targetKey === "all";
      tabs.querySelectorAll("[data-dashboard-page]").forEach(function(button) {
        var active = button.dataset.dashboardPage === targetKey;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-selected", active ? "true" : "false");
      });
      sections.forEach(function(section) {
        var title = titleFor(section);
        var active = showAll || keyFor(title) === targetKey;
        section.hidden = !active;
        if (active && !section.open) section.open = true;
      });
      try {
        window.localStorage.setItem("trade-tracker-active-page-v1", targetKey);
      } catch (error) {}
    }

    function addButton(label, key) {
      var button = document.createElement("button");
      button.type = "button";
      button.className = "dashboard-page-tab";
      button.dataset.dashboardPage = key;
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", "false");
      button.textContent = label;
      button.addEventListener("click", function() {
        setActive(key);
        tabs.scrollIntoView({ block: "nearest", behavior: "smooth" });
      });
      tabs.appendChild(button);
    }

    sections.forEach(function(section) {
      var title = titleFor(section);
      if (title) addButton(title, keyFor(title));
    });
    addButton("全部", "all");

    var stored = "";
    try {
      stored = window.localStorage.getItem("trade-tracker-active-page-v1") || "";
    } catch (error) {}
    var firstKey = sections[0] ? keyFor(titleFor(sections[0])) : "all";
    var target = stored && (stored === "all" || tabs.querySelector('[data-dashboard-page="' + stored + '"]'))
      ? stored
      : firstKey;
    setActive(target);
  });
})();
</script>
"""


def insert_dashboard_page_tabs(html_text: str) -> str:
    if DASHBOARD_PAGER_MARKER in html_text:
        return html_text

    first_section = DETAILS_PATTERN.search(html_text)
    if not first_section:
        return html_text
    tabs = DASHBOARD_PAGER_HTML + DASHBOARD_PAGER_SCRIPT
    anchors = [
        html_text.find('id="refresh-panel"'),
        first_section.start(),
    ]
    insert_at = min(index for index in anchors if index >= 0)
    tag_start = html_text.rfind("<", 0, insert_at)
    if tag_start >= 0:
        insert_at = tag_start
    return html_text[:insert_at] + tabs + html_text[insert_at:]


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
              <div class="ths-curve-rate"><span class="ths-curve-badge">账</span> <span data-curve-hero-rate-label>总资产收益率</span> <strong class="{html.escape(rate_class)}" data-curve-hero-rate>{html.escape(rate_text)}</strong></div>
              <div class="ths-curve-compare-pill" data-curve-compare-pill hidden>
                <span><span data-curve-compare-label>同期上证指数</span> <strong data-curve-compare-benchmark>--</strong></span>
                <span>跑赢指数 <strong data-curve-compare-excess>--</strong></span>
              </div>
              <div class="ths-curve-tabs" aria-label="收益曲线时间范围">
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
              <span><i class="ths-dot ths-dot-me"></i>汇总</span>
              <span class="ths-curve-benchmark-tabs" data-curve-benchmark-tabs aria-label="选择对比指数"></span>
            </div>
"""


def render_ths_curve_summary(return_rate: str) -> str:
    return """
            <div class="ths-curve-control-panel">
              <div class="ths-curve-analysis-row">
                <span class="ths-curve-row-label">收益分析</span>
                <div class="ths-curve-metric-tabs" aria-label="收益曲线口径">
                  <button type="button" class="ths-curve-metric is-active" data-curve-metric="return">收益率</button>
                  <button type="button" class="ths-curve-metric" data-curve-metric="amount">盈亏金额</button>
                </div>
              </div>
              <div class="ths-curve-analysis-row">
                <span class="ths-curve-row-label">辅助功能</span>
                <div class="ths-curve-assist-list" aria-label="收益曲线辅助功能">
                  <button type="button" class="ths-curve-assist" data-curve-assist="extreme" aria-pressed="false"><i></i>极值分析</button>
                  <button type="button" class="ths-curve-assist" data-curve-assist="growth" aria-pressed="false"><i></i>最大增长</button>
                  <button type="button" class="ths-curve-assist is-active" data-curve-assist="drawdown" aria-pressed="true"><i></i>最大回撤</button>
                </div>
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
        '<p class="section-note">红线为历史每天的总盈亏：截至当天已实现盈亏 + 当天仍持仓的收盘浮盈/浮亏；收益率用截至当日历史最高持仓本金近似总资产基准，避免清仓换仓时分母突然变小。港币和美元按当前汇率折成人民币后合并展示，蓝线可切换对比 A 股、港股和美股主要指数。</p>',
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
