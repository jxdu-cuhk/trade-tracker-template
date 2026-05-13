from __future__ import annotations

import html
import json
import re

from .reporting_currency import REPORTING_CURRENCIES, reporting_currency_options
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
<div class="dashboard-topbar" data-dashboard-topbar>
  <nav class="dashboard-page-tabs" data-dashboard-page-tabs aria-label="看板分页"></nav>
  <div class="dashboard-currency-switcher" data-dashboard-currency-switcher aria-label="统一口径币种">
    <span>统一口径</span>
    {buttons}
  </div>
</div>
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
      requestAnimationFrame(function() {
        if (typeof window.balanceSummaryTableWidths === "function") {
          window.balanceSummaryTableWidths();
        }
        window.dispatchEvent(new CustomEvent("trade-tracker-dashboard-page-change", {
          detail: { page: targetKey }
        }));
      });
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


def safe_json(data: object) -> str:
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def render_dashboard_pager_html() -> str:
    buttons = "\n    ".join(
        f'<button type="button" data-reporting-currency-button data-reporting-currency="{html.escape(currency)}">{html.escape(currency)}</button>'
        for currency in REPORTING_CURRENCIES
    )
    return DASHBOARD_PAGER_HTML.format(buttons=buttons)


def render_dashboard_currency_script() -> str:
    options = reporting_currency_options()
    rates = {str(item["label"]): float(item["rateToCny"]) for item in options}
    options_json = safe_json(options)
    rates_json = safe_json(rates)
    return f"""
<script>
(function setupDashboardReportingCurrency() {{
  const currencyOptions = {options_json};
  const fxRatesToCny = {rates_json};
  window.tradeTrackerFxRatesToCny = Object.assign({{}}, window.tradeTrackerFxRatesToCny || {{}}, fxRatesToCny);

  function ready(callback) {{
    if (document.readyState === "loading") {{
      document.addEventListener("DOMContentLoaded", callback, {{ once: true }});
      return;
    }}
    callback();
  }}

  function validCurrency(label) {{
    return currencyOptions.some((item) => item.label === label) ? label : "人民币";
  }}

  function activeCurrency() {{
    return validCurrency(document.documentElement.dataset.reportingCurrency || "人民币");
  }}

  function rateToCny(label) {{
    const rate = Number((window.tradeTrackerFxRatesToCny || {{}})[validCurrency(label)]);
    return Number.isFinite(rate) && rate > 0 ? rate : 1;
  }}

  function fromCny(value, label) {{
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return NaN;
    return numeric / rateToCny(label || activeCurrency());
  }}

  function formatMoney(value, signed) {{
    if (!Number.isFinite(value)) return "--";
    const sign = signed && value > 0 ? "+" : "";
    return sign + value.toLocaleString("zh-CN", {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
  }}

  function updateMoneyNodes(label) {{
    document.querySelectorAll("[data-reporting-money-cny]").forEach((node) => {{
      const raw = Number(node.dataset.reportingMoneyCny || "NaN");
      const converted = fromCny(raw, label);
      node.textContent = formatMoney(converted, node.dataset.reportingMoneySign === "true");
      if (Number.isFinite(converted)) node.dataset.sortValue = String(converted);
    }});
  }}

  function updateCurrencyLabels(label) {{
    document.querySelectorAll("[data-reporting-currency-label]").forEach((node) => {{
      node.textContent = label;
    }});
    document.querySelectorAll("[data-reporting-title-template]").forEach((node) => {{
      node.textContent = String(node.dataset.reportingTitleTemplate || "").replace(/\\{{currency\\}}/g, label);
    }});
    document.querySelectorAll("[data-reporting-note-template]").forEach((node) => {{
      node.textContent = String(node.dataset.reportingNoteTemplate || "").replace(/\\{{currency\\}}/g, label);
    }});
  }}

  function updateButtons(label) {{
    document.querySelectorAll("[data-reporting-currency-button]").forEach((button) => {{
      const active = button.dataset.reportingCurrency === label;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    }});
  }}

  function setReportingCurrency(label, options) {{
    const next = validCurrency(label);
    const opts = options || {{}};
    document.documentElement.dataset.reportingCurrency = next;
    updateButtons(next);
    updateCurrencyLabels(next);
    updateMoneyNodes(next);
    if (opts.persist !== false) {{
      try {{
        window.localStorage.setItem("trade-tracker-reporting-currency-v1", next);
      }} catch (error) {{}}
    }}
    if (opts.dispatch !== false) {{
      window.dispatchEvent(new CustomEvent("trade-tracker-reporting-currency-change", {{
        detail: {{ currency: next, rateToCny: rateToCny(next) }}
      }}));
    }}
  }}

  window.tradeTrackerReportingCurrency = {{
    label: activeCurrency,
    rateToCny: function(label) {{ return rateToCny(label || activeCurrency()); }},
    fromCny: function(value, label) {{ return fromCny(value, label); }},
    formatMoney: formatMoney,
    set: setReportingCurrency,
  }};

  ready(function() {{
    let stored = "人民币";
    try {{
      stored = window.localStorage.getItem("trade-tracker-reporting-currency-v1") || "人民币";
    }} catch (error) {{}}
    document.querySelectorAll("[data-reporting-currency-button]").forEach((button) => {{
      button.addEventListener("click", function() {{
        setReportingCurrency(button.dataset.reportingCurrency || "人民币");
      }});
    }});
    setReportingCurrency(stored, {{ persist: false }});
  }});
}})();
</script>
"""


def insert_dashboard_page_tabs(html_text: str) -> str:
    if DASHBOARD_PAGER_MARKER in html_text:
        return html_text

    first_section = DETAILS_PATTERN.search(html_text)
    if not first_section:
        return html_text
    tabs = render_dashboard_pager_html() + DASHBOARD_PAGER_SCRIPT + render_dashboard_currency_script()
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
              <button type="button" class="ths-curve-privacy-toggle" data-curve-money-toggle aria-pressed="false" aria-label="隐藏金额" title="隐藏金额">
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path class="eye-open" d="M2.8 12s3.3-5.2 9.2-5.2S21.2 12 21.2 12s-3.3 5.2-9.2 5.2S2.8 12 2.8 12Z"></path>
                  <circle class="eye-open" cx="12" cy="12" r="2.6"></circle>
                  <path class="eye-off" d="M4.2 4.2 19.8 19.8"></path>
                  <path class="eye-off" d="M7.8 7.4C4.5 8.8 2.8 12 2.8 12s3.3 5.2 9.2 5.2c1.2 0 2.3-.2 3.2-.6"></path>
                  <path class="eye-off" d="M10.1 6.9c.6-.1 1.2-.1 1.9-.1 5.9 0 9.2 5.2 9.2 5.2s-.9 1.4-2.5 2.8"></path>
                </svg>
              </button>
              <div class="ths-curve-scope-tabs" data-curve-scope-tabs aria-label="选择收益曲线范围"></div>
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
              <span><i class="ths-dot ths-dot-me"></i><span data-curve-legend-mine>汇总</span></span>
              <span class="ths-curve-benchmark-tabs" data-curve-benchmark-tabs aria-label="选择对比指数"></span>
              <button type="button" class="ths-curve-series-toggle is-active" data-curve-toggle="excess" aria-pressed="true">
                <i class="ths-dot ths-dot-excess"></i>超额收益
              </button>
            </div>
"""


def render_ths_curve_summary(return_rate: str) -> str:
    return """
            <div class="ths-curve-control-panel">
              <div class="ths-curve-analysis-row ths-curve-toolbar-row">
                <span class="ths-curve-row-label">展示</span>
                <div class="ths-curve-toolbar">
                  <div class="ths-curve-metric-tabs" aria-label="收益曲线口径">
                    <button type="button" class="ths-curve-metric is-active" data-curve-metric="return">收益率</button>
                    <button type="button" class="ths-curve-metric" data-curve-metric="amount">盈亏金额</button>
                  </div>
                  <div class="ths-curve-chart-control">
                    <div class="ths-curve-chart-tabs" aria-label="收益曲线图形">
                      <button type="button" class="ths-curve-chart-mode is-active" data-curve-chart-mode="line">折线图</button>
                      <button type="button" class="ths-curve-chart-mode" data-curve-chart-mode="candlestick">K线图</button>
                    </div>
                    <div class="ths-curve-candle-tabs" data-curve-candle-tabs aria-label="选择K线周期" hidden>
                      <button type="button" class="ths-curve-candle-interval" data-curve-candle-interval="week">周K</button>
                      <button type="button" class="ths-curve-candle-interval" data-curve-candle-interval="month">月K</button>
                      <button type="button" class="ths-curve-candle-interval" data-curve-candle-interval="year">年K</button>
                    </div>
                  </div>
                </div>
              </div>
              <div class="ths-curve-analysis-row">
                <span class="ths-curve-row-label">辅助功能</span>
                <div class="ths-curve-assist-list" aria-label="收益曲线辅助功能">
                  <button type="button" class="ths-curve-assist" data-curve-assist="extreme" aria-pressed="false"><i></i>极值分析</button>
                  <button type="button" class="ths-curve-assist" data-curve-assist="growth" aria-pressed="false"><i></i>最大增长</button>
                  <button type="button" class="ths-curve-assist" data-curve-assist="drawdown" aria-pressed="false"><i></i>最大回撤</button>
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
        '<p class="section-note">红线为历史每天的总盈亏：截至当天已实现盈亏 + 当天仍持仓的收盘浮盈/浮亏；收益率用截至当日历史最高持仓本金近似总资产基准，避免清仓换仓时分母突然变小。不同币种会按当前汇率统一折算，金额可在人民币、港币和美元之间切换；蓝线可切换对比 A 股、港股和美股主要指数。</p>',
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
