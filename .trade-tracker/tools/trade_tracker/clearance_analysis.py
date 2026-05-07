from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date

from .market_data import display_currency_label
from .utils import (
    cell_raw,
    clean_name,
    clean_text,
    core_trade_type,
    excel_serial_to_date,
    format_date,
    parse_float,
    raw_number,
    raw_text_value,
)


STOCK_EVENTS = {"现股", "Stock", "stock", "STOCK"}
EPSILON = 0.000001


@dataclass
class StockTradeRow:
    row_number: int
    ticker: str
    name: str
    currency: str
    open_date: date
    close_date: date | None
    signed_quantity: float
    pnl: float | None
    capital: float | None
    days: float | None


@dataclass
class StockEvent:
    event_date: date
    order: int
    row: StockTradeRow
    delta: float
    is_close: bool = False


@dataclass
class ClearanceCycle:
    ticker: str
    name: str
    currency: str
    start_date: date
    clear_date: date
    side: str
    pnl: float = 0.0
    capital: float = 0.0
    capital_days: float = 0.0
    closed_rows: set[int] = field(default_factory=set)
    touched_rows: set[int] = field(default_factory=set)

    @property
    def holding_days(self) -> int:
        return max((self.clear_date - self.start_date).days, 1)

    @property
    def trade_count(self) -> int:
        return len(self.closed_rows) or len(self.touched_rows)

    @property
    def return_rate(self) -> float | None:
        if abs(self.capital) < EPSILON:
            return None
        return self.pnl / self.capital

    @property
    def annualized(self) -> float | None:
        if abs(self.capital_days) < EPSILON:
            return None
        return self.pnl * 365.0 / self.capital_days


@dataclass
class ClearanceSummary:
    period: str
    sort_value: int
    currency: str
    cycles: list[ClearanceCycle] = field(default_factory=list)

    @property
    def clear_count(self) -> int:
        return len(self.cycles)

    @property
    def win_count(self) -> int:
        return sum(1 for cycle in self.cycles if cycle.pnl > EPSILON)

    @property
    def loss_count(self) -> int:
        return sum(1 for cycle in self.cycles if cycle.pnl < -EPSILON)

    @property
    def win_rate(self) -> float | None:
        if not self.cycles:
            return None
        return self.win_count / len(self.cycles)

    @property
    def pnl(self) -> float:
        return sum(cycle.pnl for cycle in self.cycles)

    @property
    def capital(self) -> float:
        return sum(cycle.capital for cycle in self.cycles)

    @property
    def return_rate(self) -> float | None:
        if abs(self.capital) < EPSILON:
            return None
        return self.pnl / self.capital

    @property
    def average_days(self) -> float | None:
        if not self.cycles:
            return None
        return sum(cycle.holding_days for cycle in self.cycles) / len(self.cycles)

    @property
    def best_cycle(self) -> ClearanceCycle | None:
        return max((cycle for cycle in self.cycles if cycle.pnl > EPSILON), key=lambda cycle: cycle.pnl, default=None)

    @property
    def worst_cycle(self) -> ClearanceCycle | None:
        return min((cycle for cycle in self.cycles if cycle.pnl < -EPSILON), key=lambda cycle: cycle.pnl, default=None)


def normalize_currency_label(core, currency: object) -> str:
    try:
        normalized = core.normalize_currency(currency)
    except Exception:
        normalized = clean_text(currency)
    return display_currency_label(core, normalized)


def safe_security_name(core, ticker: str, currency: str) -> str:
    try:
        name = core.lookup_security_name(ticker, currency, False)
    except Exception:
        name = ""
    return clean_name(name) or "-"


def stock_trade_row(core, row_number: int, cells: dict[int, object]) -> StockTradeRow | None:
    event = raw_text_value(core, cells, 6)
    if event not in STOCK_EVENTS:
        return None

    open_date = excel_serial_to_date(cell_raw(cells, 2))
    if open_date is None:
        return None

    quantity = raw_number(cells, 8)
    if quantity in (None, 0):
        return None

    raw_currency = cell_raw(cells, 20)
    try:
        normalized_currency = core.normalize_currency(raw_currency)
    except Exception:
        normalized_currency = clean_text(raw_currency)
    ticker = clean_text(core.normalize_ticker(cell_raw(cells, 5), normalized_currency))
    if not ticker:
        return None

    trade_type = core_trade_type(raw_text_value(core, cells, 1))
    signed_quantity = -abs(float(quantity)) if trade_type in {"sell", "卖出", "卖空", "short"} else abs(float(quantity))
    close_date = excel_serial_to_date(cell_raw(cells, 4))

    metrics: dict[str, object] = {}
    try:
        metrics = core.compute_row_metrics(cells)
    except Exception:
        metrics = {}

    pnl = parse_float(metrics.get("pnl"))
    capital = parse_float(metrics.get("capital"))
    days = parse_float(metrics.get("days"))
    currency_label = normalize_currency_label(core, raw_currency)
    return StockTradeRow(
        row_number=row_number,
        ticker=ticker,
        name=safe_security_name(core, ticker, normalized_currency),
        currency=currency_label,
        open_date=open_date,
        close_date=close_date,
        signed_quantity=signed_quantity,
        pnl=pnl,
        capital=capital,
        days=days,
    )


def stock_events_from_rows(core, rows: list[tuple[int, dict[int, object]]]) -> dict[tuple[str, str], list[StockEvent]]:
    events_by_key: dict[tuple[str, str], list[StockEvent]] = {}
    for row_number, cells in rows:
        stock_row = stock_trade_row(core, row_number, cells)
        if not stock_row:
            continue

        key = (stock_row.ticker, stock_row.currency)
        events_by_key.setdefault(key, []).append(
            StockEvent(stock_row.open_date, 0, stock_row, stock_row.signed_quantity)
        )
        if stock_row.close_date is not None:
            events_by_key[key].append(
                StockEvent(stock_row.close_date, 1, stock_row, -stock_row.signed_quantity, True)
            )
    return events_by_key


def add_closed_row_to_cycle(cycle: dict[str, object], row: StockTradeRow) -> None:
    if row.row_number in cycle["closed_rows"]:
        return
    cycle["closed_rows"].add(row.row_number)
    if row.pnl is not None:
        cycle["pnl"] = float(cycle["pnl"]) + row.pnl
    if row.capital is not None:
        cycle["capital"] = float(cycle["capital"]) + row.capital
        days = row.days if row.days is not None else max(((row.close_date or row.open_date) - row.open_date).days, 1)
        cycle["capital_days"] = float(cycle["capital_days"]) + row.capital * max(days, 1)


def build_clearance_cycles(core, rows: list[tuple[int, dict[int, object]]]) -> list[ClearanceCycle]:
    cycles: list[ClearanceCycle] = []
    for (_ticker, _currency), events in stock_events_from_rows(core, rows).items():
        position = 0.0
        active: dict[str, object] | None = None
        for event in sorted(events, key=lambda item: (item.event_date, item.order, item.row.row_number)):
            was_flat = abs(position) < EPSILON
            next_position = position + event.delta
            if active is None and was_flat and abs(next_position) >= EPSILON:
                active = {
                    "ticker": event.row.ticker,
                    "name": event.row.name,
                    "currency": event.row.currency,
                    "start_date": event.event_date,
                    "side": "空头" if next_position < 0 else "多头",
                    "pnl": 0.0,
                    "capital": 0.0,
                    "capital_days": 0.0,
                    "closed_rows": set(),
                    "touched_rows": set(),
                }

            if active is not None:
                active["touched_rows"].add(event.row.row_number)
                if event.is_close:
                    add_closed_row_to_cycle(active, event.row)

            position = next_position
            if active is not None and abs(position) < EPSILON:
                cycles.append(
                    ClearanceCycle(
                        ticker=str(active["ticker"]),
                        name=str(active["name"]),
                        currency=str(active["currency"]),
                        start_date=active["start_date"],
                        clear_date=event.event_date,
                        side=str(active["side"]),
                        pnl=float(active["pnl"]),
                        capital=float(active["capital"]),
                        capital_days=float(active["capital_days"]),
                        closed_rows=set(active["closed_rows"]),
                        touched_rows=set(active["touched_rows"]),
                    )
                )
                active = None
                position = 0.0
    return sorted(cycles, key=lambda cycle: (cycle.clear_date, cycle.pnl), reverse=True)


def summarize_clearance_cycles(cycles: list[ClearanceCycle], period: str) -> list[ClearanceSummary]:
    buckets: dict[tuple[str, str], ClearanceSummary] = {}
    for cycle in cycles:
        if period == "year":
            label = f"{cycle.clear_date.year}年"
            sort_value = cycle.clear_date.year
        else:
            label = f"{cycle.clear_date.year}-{cycle.clear_date.month:02d}"
            sort_value = cycle.clear_date.year * 100 + cycle.clear_date.month
        key = (label, cycle.currency)
        bucket = buckets.setdefault(key, ClearanceSummary(label, sort_value, cycle.currency))
        bucket.cycles.append(cycle)
    return sorted(buckets.values(), key=lambda summary: (summary.sort_value, summary.pnl), reverse=True)


def value_class(value: float | None) -> str:
    if value is None:
        return ""
    if value > EPSILON:
        return " value-positive"
    if value < -EPSILON:
        return " value-negative"
    return " value-zero"


def format_number(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return "-"
    if abs(value) < 0.5 * (10 ** -decimals):
        value = 0.0
    return f"{value:,.{decimals}f}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def td(css_class: str, text: object, sort_value: float | int | None = None, tone_value: float | None = None) -> str:
    classes = f"{value_class(tone_value)} {css_class}".strip()
    sort_attr = f' data-sort-value="{sort_value:.12g}"' if isinstance(sort_value, (int, float)) else ""
    return f'<td class="{html.escape(classes)}"{sort_attr}>{html.escape(clean_text(text))}</td>'


def th(css_class: str, sort_type: str, label: str) -> str:
    return f'<th class="{css_class}" data-sort-type="{sort_type}">{html.escape(label)}</th>'


def render_table(
    headers: list[tuple[str, str, str]],
    rows: list[str],
    empty_message: str,
    table_attrs: str = "",
) -> str:
    body = "".join(rows) if rows else f'<tr><td class="text" colspan="{len(headers)}">{html.escape(empty_message)}</td></tr>'
    return (
        '<div class="summary-wrap">\n'
        f'  <table class="summary-table js-sortable-table clearance-table"{table_attrs}>\n'
        "    <thead>\n"
        f"      <tr>{''.join(th(css, sort_type, label) for css, sort_type, label in headers)}</tr>\n"
        "    </thead>\n"
        f"    <tbody>\n      {body}\n    </tbody>\n"
        "  </table>\n"
        "</div>"
    )


def attr(value: object) -> str:
    return html.escape(clean_text(value), quote=True)


def render_clearance_toolbar() -> str:
    return """
            <div class="section-toolbar clearance-toolbar">
              <span class="filter-label">统计粒度</span>
              <select class="filter-select js-clearance-granularity" aria-label="选择清仓统计粒度">
                <option value="month" selected>月度</option>
                <option value="year">年度</option>
              </select>
              <span class="filter-label">阶段</span>
              <select class="filter-select js-clearance-period" aria-label="选择清仓阶段"></select>
            </div>
"""


def render_dynamic_summary_table() -> str:
    headers = [
        ("ccy", "text", "币种"),
        ("num", "number", "清仓次数"),
        ("percent", "number", "胜率"),
        ("money", "number", "已实现盈亏"),
        ("money", "number", "投入本金"),
        ("percent", "number", "收益率"),
        ("num", "number", "平均持有天数"),
        ("text", "text", "最赚钱"),
        ("text", "text", "最亏钱"),
    ]
    return (
        '<h3 class="clearance-subtitle">阶段汇总</h3>'
        '<div class="summary-wrap">\n'
        '  <table class="summary-table clearance-summary-table" data-clearance-summary-table>\n'
        "    <thead>\n"
        f"      <tr>{''.join(th(css, sort_type, label) for css, sort_type, label in headers)}</tr>\n"
        "    </thead>\n"
        '    <tbody data-clearance-summary-body>\n'
        '      <tr><td class="text" colspan="9">选择阶段后显示汇总。</td></tr>\n'
        "    </tbody>\n"
        "  </table>\n"
        "</div>"
    )


def render_cycle_table(cycles: list[ClearanceCycle]) -> str:
    headers = [
        ("text", "date", "清仓日"),
        ("text", "date", "建仓日"),
        ("text", "text", "代码"),
        ("text", "text", "名称"),
        ("text", "text", "方向"),
        ("money", "number", "已实现盈亏"),
        ("percent", "number", "收益率"),
        ("percent", "number", "综合年化"),
        ("num", "number", "持有天数"),
        ("num", "number", "交易行数"),
        ("ccy", "text", "币种"),
    ]
    rows = []
    for cycle in cycles:
        clear_sort = cycle.clear_date.year * 10000 + cycle.clear_date.month * 100 + cycle.clear_date.day
        start_sort = cycle.start_date.year * 10000 + cycle.start_date.month * 100 + cycle.start_date.day
        rows.append(
            (
                f'<tr data-clearance-month="{cycle.clear_date.year}-{cycle.clear_date.month:02d}"'
                f' data-clearance-year="{cycle.clear_date.year}年"'
                f' data-clearance-currency="{attr(cycle.currency)}"'
                f' data-clearance-pnl="{cycle.pnl:.12g}"'
                f' data-clearance-capital="{cycle.capital:.12g}"'
                f' data-clearance-days="{cycle.holding_days:.12g}"'
                f' data-clearance-code="{attr(cycle.ticker)}">'
            )
            + td("text", format_date(cycle.clear_date), clear_sort)
            + td("text", format_date(cycle.start_date), start_sort)
            + td("text", cycle.ticker)
            + td("text", cycle.name)
            + td("text", cycle.side)
            + td("money", format_number(cycle.pnl), cycle.pnl, cycle.pnl)
            + td("percent", format_percent(cycle.return_rate), cycle.return_rate, cycle.return_rate)
            + td("percent", format_percent(cycle.annualized), cycle.annualized, cycle.annualized)
            + td("num", f"{cycle.holding_days:,}", cycle.holding_days)
            + td("num", f"{cycle.trade_count:,}", cycle.trade_count)
            + td("ccy", cycle.currency)
            + "</tr>"
        )
    empty = "还没有识别到已经从持仓归零的现股清仓周期。"
    return '<h3 class="clearance-subtitle">清仓明细</h3>' + render_table(
        headers,
        rows,
        empty,
        ' data-clearance-detail-table',
    )


def render_clearance_filter_script() -> str:
    return """
        <script>
        (function setupClearanceAnalysis() {
          const section = document.querySelector('[data-clearance-analysis]');
          if (!section || section.dataset.clearanceReady === '1') return;
          section.dataset.clearanceReady = '1';

          const granularity = section.querySelector('.js-clearance-granularity');
          const period = section.querySelector('.js-clearance-period');
          const table = section.querySelector('[data-clearance-detail-table]');
          const summaryBody = section.querySelector('[data-clearance-summary-body]');
          if (!granularity || !period || !table || !summaryBody) return;

          const rows = Array.from(table.querySelectorAll('tbody tr[data-clearance-month]'));

          function rowPeriod(row, mode) {
            return mode === 'year' ? row.dataset.clearanceYear : row.dataset.clearanceMonth;
          }

          function periodAllLabel(mode) {
            return mode === 'year' ? '全部年份' : '全部月份';
          }

          function sortedPeriods(mode) {
            return Array.from(new Set(rows.map((row) => rowPeriod(row, mode)).filter(Boolean)))
              .sort((a, b) => b.localeCompare(a, 'zh-CN', { numeric: true }));
          }

          function populatePeriods() {
            const mode = granularity.value || 'month';
            const previous = period.value;
            const periods = sortedPeriods(mode);
            period.innerHTML = '';

            const allOption = document.createElement('option');
            allOption.value = 'all';
            allOption.textContent = periodAllLabel(mode);
            period.appendChild(allOption);

            periods.forEach((value) => {
              const option = document.createElement('option');
              option.value = value;
              option.textContent = value;
              period.appendChild(option);
            });

            period.value = periods.includes(previous) ? previous : 'all';
          }

          function number(value) {
            const parsed = Number.parseFloat(value || '0');
            return Number.isFinite(parsed) ? parsed : 0;
          }

          function formatNumber(value, digits = 2) {
            return Number(value || 0).toLocaleString('en-US', {
              minimumFractionDigits: digits,
              maximumFractionDigits: digits,
            });
          }

          function formatPercent(value) {
            if (!Number.isFinite(value)) return '-';
            return `${(value * 100).toFixed(2)}%`;
          }

          function tone(value) {
            if (value > 0.000001) return 'value-positive';
            if (value < -0.000001) return 'value-negative';
            return 'value-zero';
          }

          function cell(className, text, value, shouldTone = false) {
            const td = document.createElement('td');
            td.className = shouldTone ? `${tone(value)} ${className}` : className;
            if (Number.isFinite(value)) td.dataset.sortValue = String(value);
            td.textContent = text;
            return td;
          }

          function summaryLabel(item) {
            if (!item) return '-';
            return `${item.code} ${formatNumber(item.pnl)}`;
          }

          function renderSummary(visibleRows) {
            summaryBody.innerHTML = '';
            if (!visibleRows.length) {
              const tr = document.createElement('tr');
              const td = document.createElement('td');
              td.className = 'text';
              td.colSpan = 9;
              td.textContent = '当前阶段没有清仓记录。';
              tr.appendChild(td);
              summaryBody.appendChild(tr);
              return;
            }

            const statsByCurrency = new Map();
            visibleRows.forEach((row) => {
              const currency = row.dataset.clearanceCurrency || '未标注币种';
              if (!statsByCurrency.has(currency)) {
                statsByCurrency.set(currency, {
                  currency,
                  count: 0,
                  wins: 0,
                  pnl: 0,
                  capital: 0,
                  days: 0,
                  best: null,
                  worst: null,
                });
              }
              const stats = statsByCurrency.get(currency);
              const pnl = number(row.dataset.clearancePnl);
              const capital = number(row.dataset.clearanceCapital);
              const days = number(row.dataset.clearanceDays);
              const item = { code: row.dataset.clearanceCode || '-', pnl };
              stats.count += 1;
              if (pnl > 0.000001) stats.wins += 1;
              stats.pnl += pnl;
              stats.capital += capital;
              stats.days += days;
              if (pnl > 0.000001 && (!stats.best || pnl > stats.best.pnl)) stats.best = item;
              if (pnl < -0.000001 && (!stats.worst || pnl < stats.worst.pnl)) stats.worst = item;
            });

            Array.from(statsByCurrency.values())
              .sort((a, b) => a.currency.localeCompare(b.currency, 'zh-CN'))
              .forEach((stats) => {
                const tr = document.createElement('tr');
                const winRate = stats.count ? stats.wins / stats.count : NaN;
                const returnRate = stats.capital ? stats.pnl / stats.capital : NaN;
                const averageDays = stats.count ? stats.days / stats.count : NaN;
                tr.appendChild(cell('ccy', stats.currency));
                tr.appendChild(cell('num', stats.count.toLocaleString('en-US'), stats.count));
                tr.appendChild(cell('percent', formatPercent(winRate), winRate));
                tr.appendChild(cell('money', formatNumber(stats.pnl), stats.pnl, true));
                tr.appendChild(cell('money', formatNumber(stats.capital), stats.capital));
                tr.appendChild(cell('percent', formatPercent(returnRate), returnRate, true));
                tr.appendChild(cell('num', Number.isFinite(averageDays) ? formatNumber(averageDays, 1) : '-', averageDays));
                tr.appendChild(cell('text', summaryLabel(stats.best), stats.best ? stats.best.pnl : NaN, true));
                tr.appendChild(cell('text', summaryLabel(stats.worst), stats.worst ? stats.worst.pnl : NaN, true));
                summaryBody.appendChild(tr);
              });
          }

          function applyFilter() {
            const mode = granularity.value || 'month';
            const selectedPeriod = period.value || 'all';
            const visibleRows = [];
            rows.forEach((row) => {
              const isVisible = selectedPeriod === 'all' || rowPeriod(row, mode) === selectedPeriod;
              row.style.display = isVisible ? '' : 'none';
              if (isVisible) visibleRows.push(row);
            });
            renderSummary(visibleRows);
            if (typeof applyAllSummaryTableTones === 'function') applyAllSummaryTableTones();
            if (typeof balanceSummaryTableWidths === 'function') requestAnimationFrame(balanceSummaryTableWidths);
          }

          granularity.addEventListener('change', () => {
            populatePeriods();
            applyFilter();
          });
          period.addEventListener('change', applyFilter);

          populatePeriods();
          applyFilter();
        })();
        </script>
"""


def render_clearance_analysis_section(core, rows: list[tuple[int, dict[int, object]]]) -> str:
    cycles = build_clearance_cycles(core, rows)
    body = (
        render_clearance_toolbar()
        + render_dynamic_summary_table()
        + render_cycle_table(cycles)
        + render_clearance_filter_script()
    )
    return f"""
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary">
            <div class="section-head">
              <div>
                <h2 class="section-title">清仓分析</h2>
                <p class="section-note">按现股持仓从空仓到再次归零划分清仓周期；月度和年度统计按清仓日归属，币种分开汇总，未清仓持仓不会计入这里。</p>
              </div>
              <span class="section-toggle" aria-hidden="true"></span>
            </div>
          </summary>
          <div class="section-body clearance-analysis" data-clearance-analysis>
            {body}
          </div>
        </details>
"""


def insert_clearance_analysis_section(core, html_text: str, rows: list[tuple[int, dict[int, object]]]) -> str:
    if '<h2 class="section-title">清仓分析</h2>' in html_text:
        return html_text
    section = render_clearance_analysis_section(core, rows)

    def section_start_for_heading(heading: str) -> int | None:
        heading_index = html_text.find(f'<h2 class="section-title">{heading}</h2>')
        if heading_index < 0:
            return None
        details_index = html_text.rfind('<details class="dashboard-section section-collapsible" open>', 0, heading_index)
        if details_index < 0:
            return None
        return details_index

    timeline_start = section_start_for_heading("交易时间线")
    if timeline_start is not None:
        return html_text[:timeline_start] + "\n" + section + html_text[timeline_start:]
    worksheet_start = section_start_for_heading("工作表入口")
    if worksheet_start is not None:
        return html_text[:worksheet_start] + "\n" + section + html_text[worksheet_start:]
    if "</body>" in html_text:
        return html_text.replace("</body>", section + "</body>", 1)
    return html_text + section
