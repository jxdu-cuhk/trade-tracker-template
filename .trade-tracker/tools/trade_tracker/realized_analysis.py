from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import date

from .market_data import display_currency_label
from .settings import OPTION_EVENTS
from .utils import (
    cell_raw,
    clean_name,
    clean_text,
    core_trade_type,
    excel_serial_to_date,
    format_date,
    parse_float,
    raw_text_value,
)


STOCK_EVENTS = {"现股", "Stock", "stock", "STOCK"}
EPSILON = 0.000001


@dataclass
class RealizedTrade:
    row_number: int
    close_date: date
    open_date: date | None
    ticker: str
    name: str
    trade_type: str
    event: str
    category: str
    currency: str
    pnl: float
    capital: float | None
    days: float | None

    @property
    def date_iso(self) -> str:
        return self.close_date.isoformat()

    @property
    def month_label(self) -> str:
        return f"{self.close_date.year}-{self.close_date.month:02d}"

    @property
    def holding_days(self) -> float | None:
        if self.days is not None:
            return max(self.days, 1.0)
        if self.open_date is None:
            return None
        return float(max((self.close_date - self.open_date).days, 1))

    @property
    def return_rate(self) -> float | None:
        if self.capital is None or abs(self.capital) < EPSILON:
            return None
        return self.pnl / self.capital


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


def trade_category(event: str) -> str:
    if event in STOCK_EVENTS:
        return "股票"
    if event in OPTION_EVENTS:
        return "期权"
    return "其他"


def realized_trade_from_row(core, row_number: int, cells: dict[int, object]) -> RealizedTrade | None:
    close_date = excel_serial_to_date(cell_raw(cells, 4))
    if close_date is None:
        return None

    try:
        metrics = core.compute_row_metrics(cells)
    except Exception:
        metrics = {}
    if not isinstance(metrics, dict):
        return None

    pnl = parse_float(metrics.get("pnl"))
    if pnl is None:
        return None

    raw_currency = cell_raw(cells, 20)
    try:
        normalized_currency = core.normalize_currency(raw_currency)
    except Exception:
        normalized_currency = clean_text(raw_currency)
    try:
        ticker = clean_text(core.normalize_ticker(cell_raw(cells, 5), normalized_currency))
    except Exception:
        ticker = clean_text(cell_raw(cells, 5)).upper()
    if not ticker:
        return None

    open_date = excel_serial_to_date(cell_raw(cells, 2))
    event = raw_text_value(core, cells, 6)
    raw_type = raw_text_value(core, cells, 1)
    trade_type = raw_type or core_trade_type(raw_type) or "-"
    capital = parse_float(metrics.get("capital"))
    days = parse_float(metrics.get("days"))
    return RealizedTrade(
        row_number=row_number,
        close_date=close_date,
        open_date=open_date,
        ticker=ticker,
        name=safe_security_name(core, ticker, normalized_currency),
        trade_type=trade_type,
        event=event or "-",
        category=trade_category(event),
        currency=normalize_currency_label(core, raw_currency),
        pnl=float(pnl),
        capital=capital,
        days=days,
    )


def build_realized_trades(core, rows: list[tuple[int, dict[int, object]]]) -> list[RealizedTrade]:
    trades = []
    for row_number, cells in rows:
        trade = realized_trade_from_row(core, row_number, cells)
        if trade:
            trades.append(trade)
    return sorted(trades, key=lambda item: (item.close_date, item.row_number), reverse=True)


def summarize_trades_by_date(trades: list[RealizedTrade]) -> dict[str, dict[str, object]]:
    summaries: dict[str, dict[str, object]] = {}
    for trade in trades:
        bucket = summaries.setdefault(
            trade.date_iso,
            {
                "date": trade.date_iso,
                "count": 0,
                "wins": 0,
                "pnl": 0.0,
                "by_currency": {},
            },
        )
        bucket["count"] = int(bucket["count"]) + 1
        if trade.pnl > EPSILON:
            bucket["wins"] = int(bucket["wins"]) + 1
        bucket["pnl"] = float(bucket["pnl"]) + trade.pnl
        by_currency = bucket["by_currency"]
        currency_bucket = by_currency.setdefault(trade.currency, {"count": 0, "pnl": 0.0})
        currency_bucket["count"] += 1
        currency_bucket["pnl"] += trade.pnl
    return summaries


def trade_payload(trade: RealizedTrade) -> dict[str, object]:
    return {
        "row": trade.row_number,
        "date": trade.date_iso,
        "dateLabel": format_date(trade.close_date),
        "month": trade.month_label,
        "openDate": trade.open_date.isoformat() if trade.open_date else "",
        "openDateLabel": format_date(trade.open_date),
        "code": trade.ticker,
        "name": trade.name,
        "type": trade.trade_type,
        "event": trade.event,
        "category": trade.category,
        "currency": trade.currency,
        "pnl": trade.pnl,
        "capital": trade.capital if trade.capital is not None else 0.0,
        "days": trade.holding_days if trade.holding_days is not None else 0.0,
        "returnRate": trade.return_rate,
    }


def json_payload(trades: list[RealizedTrade]) -> str:
    text = json.dumps(
        {"trades": [trade_payload(trade) for trade in trades]},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def th(css_class: str, sort_type: str, label: str) -> str:
    return f'<th class="{css_class}" data-sort-type="{sort_type}">{html.escape(label)}</th>'


def render_empty_table(headers: list[tuple[str, str, str]], body_attr: str, empty_message: str) -> str:
    return (
        '<div class="summary-wrap">\n'
        '  <table class="summary-table js-sortable-table realized-table">\n'
        "    <thead>\n"
        f"      <tr>{''.join(th(css, sort_type, label) for css, sort_type, label in headers)}</tr>\n"
        "    </thead>\n"
        f'    <tbody {body_attr}>\n'
        f'      <tr><td class="text" colspan="{len(headers)}">{html.escape(empty_message)}</td></tr>\n'
        "    </tbody>\n"
        "  </table>\n"
        "</div>"
    )


def render_realized_toolbar() -> str:
    return """
            <div class="section-toolbar realized-toolbar">
              <span class="filter-label">月份</span>
              <select class="filter-select js-realized-month" aria-label="选择盈亏日历月份"></select>
              <span class="filter-label">币种</span>
              <select class="filter-select js-realized-currency" aria-label="选择盈亏日历币种"></select>
            </div>
"""


def render_calendar_panel() -> str:
    day_headers = [
        ("text", "date", "平仓日"),
        ("text", "text", "代码"),
        ("text", "text", "名称"),
        ("text", "text", "品类"),
        ("text", "text", "事件"),
        ("money", "number", "已实现盈亏"),
        ("money", "number", "投入本金"),
        ("percent", "number", "收益率"),
        ("num", "number", "持有天数"),
        ("ccy", "text", "币种"),
    ]
    return (
        '<div class="realized-panel realized-calendar-panel">\n'
        '<h3 class="realized-subtitle">每日盈亏</h3>\n'
        f"{render_realized_toolbar()}\n"
        '<div class="pnl-calendar" data-pnl-calendar aria-label="每日已实现盈亏日历"></div>\n'
        '<h3 class="realized-subtitle" data-realized-day-title>当日明细</h3>\n'
        + render_empty_table(day_headers, "data-realized-day-body", "选择日期后显示当日已实现盈亏。")
        + "\n</div>"
    )


def render_stage_panel() -> str:
    summary_headers = [
        ("ccy", "text", "币种"),
        ("num", "number", "交易笔数"),
        ("percent", "number", "胜率"),
        ("money", "number", "已实现盈亏"),
        ("money", "number", "投入本金"),
        ("percent", "number", "收益率"),
        ("num", "number", "平均持有天数"),
        ("text", "text", "最大盈利"),
        ("text", "text", "最大亏损"),
    ]
    category_headers = [
        ("text", "text", "品类"),
        ("ccy", "text", "币种"),
        ("num", "number", "交易笔数"),
        ("num", "number", "盈利笔数"),
        ("money", "number", "已实现盈亏"),
        ("money", "number", "平均每笔"),
    ]
    detail_headers = [
        ("text", "date", "平仓日"),
        ("text", "date", "开仓日"),
        ("text", "text", "代码"),
        ("text", "text", "名称"),
        ("text", "text", "品类"),
        ("text", "text", "事件"),
        ("money", "number", "已实现盈亏"),
        ("percent", "number", "收益率"),
        ("num", "number", "持有天数"),
        ("ccy", "text", "币种"),
    ]
    return (
        '<div class="realized-panel realized-stage-panel">\n'
        '<h3 class="realized-subtitle">阶段账单</h3>\n'
        """
            <div class="section-toolbar realized-stage-toolbar">
              <span class="filter-label">开始</span>
              <input class="filter-select realized-date-input js-stage-start" type="date" aria-label="选择阶段开始日期">
              <span class="filter-label">结束</span>
              <input class="filter-select realized-date-input js-stage-end" type="date" aria-label="选择阶段结束日期">
              <span class="filter-label realized-range-label" data-stage-range-label></span>
            </div>
"""
        + render_empty_table(summary_headers, "data-stage-summary-body", "选择开始和结束日期后显示阶段汇总。")
        + '<h3 class="realized-subtitle">品类拆分</h3>\n'
        + render_empty_table(category_headers, "data-stage-category-body", "当前阶段没有可拆分的已实现盈亏。")
        + '<h3 class="realized-subtitle">阶段明细</h3>\n'
        + render_empty_table(detail_headers, "data-stage-detail-body", "当前阶段没有已实现盈亏记录。")
        + "\n</div>"
    )


def render_realized_filter_script() -> str:
    return """
        <script>
        (function setupRealizedAnalysis() {
          const section = document.querySelector('[data-realized-analysis]');
          if (!section || section.dataset.realizedReady === '1') return;
          section.dataset.realizedReady = '1';

          const payloadNode = section.querySelector('[data-realized-payload]');
          let payload = { trades: [] };
          try {
            payload = JSON.parse(payloadNode ? payloadNode.textContent : '{"trades":[]}');
          } catch (_error) {
            payload = { trades: [] };
          }
          const trades = Array.isArray(payload.trades) ? payload.trades.filter((trade) => trade && trade.date) : [];

          const monthSelect = section.querySelector('.js-realized-month');
          const currencySelect = section.querySelector('.js-realized-currency');
          const calendar = section.querySelector('[data-pnl-calendar]');
          const dayTitle = section.querySelector('[data-realized-day-title]');
          const dayBody = section.querySelector('[data-realized-day-body]');
          const stageStart = section.querySelector('.js-stage-start');
          const stageEnd = section.querySelector('.js-stage-end');
          const stageRangeLabel = section.querySelector('[data-stage-range-label]');
          const stageSummaryBody = section.querySelector('[data-stage-summary-body]');
          const stageCategoryBody = section.querySelector('[data-stage-category-body]');
          const stageDetailBody = section.querySelector('[data-stage-detail-body]');
          if (!monthSelect || !currencySelect || !calendar || !dayBody || !stageStart || !stageEnd) return;

          let selectedDate = '';

          function unique(values) {
            return Array.from(new Set(values.filter(Boolean)));
          }

          function sortedMonths() {
            return unique(trades.map((trade) => String(trade.month || trade.date.slice(0, 7))))
              .sort((a, b) => b.localeCompare(a, 'zh-CN', { numeric: true }));
          }

          function sortedCurrencies() {
            return unique(trades.map((trade) => String(trade.currency || '未标注币种')))
              .sort((a, b) => a.localeCompare(b, 'zh-CN'));
          }

          function isoDate(year, month, day) {
            return `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          }

          function tradeCurrency(trade) {
            return String(trade.currency || '未标注币种');
          }

          function matchesCurrency(trade) {
            return currencySelect.value === 'all' || tradeCurrency(trade) === currencySelect.value;
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
            return Number.isFinite(value) ? `${(value * 100).toFixed(2)}%` : '-';
          }

          function tone(value) {
            if (value > 0.000001) return 'value-positive';
            if (value < -0.000001) return 'value-negative';
            return 'value-zero';
          }

          function dayToneClass(stats) {
            const hasPositive = stats.some((item) => item.pnl > 0.000001);
            const hasNegative = stats.some((item) => item.pnl < -0.000001);
            if (hasPositive && !hasNegative) return 'pnl-day-positive';
            if (hasNegative && !hasPositive) return 'pnl-day-negative';
            if (hasPositive || hasNegative) return 'pnl-day-mixed';
            return stats.length ? 'pnl-day-zero' : '';
          }

          function cell(className, text, value, shouldTone = false) {
            const td = document.createElement('td');
            td.className = shouldTone ? `${tone(value)} ${className}` : className;
            if (Number.isFinite(value)) td.dataset.sortValue = String(value);
            td.textContent = text;
            return td;
          }

          function emptyRow(body, colspan, text) {
            body.innerHTML = '';
            const tr = document.createElement('tr');
            const td = document.createElement('td');
            td.className = 'text';
            td.colSpan = colspan;
            td.textContent = text;
            tr.appendChild(td);
            body.appendChild(tr);
          }

          function populateControls() {
            const months = sortedMonths();
            monthSelect.innerHTML = '';
            months.forEach((month) => {
              const option = document.createElement('option');
              option.value = month;
              option.textContent = month;
              monthSelect.appendChild(option);
            });

            currencySelect.innerHTML = '';
            const allOption = document.createElement('option');
            allOption.value = 'all';
            allOption.textContent = '全部币种';
            currencySelect.appendChild(allOption);
            sortedCurrencies().forEach((currency) => {
              const option = document.createElement('option');
              option.value = currency;
              option.textContent = currency;
              currencySelect.appendChild(option);
            });

            if (months.length) monthSelect.value = months[0];
            const dates = trades.map((trade) => trade.date).sort();
            if (dates.length) {
              const latest = dates[dates.length - 1];
              stageStart.value = `${latest.slice(0, 7)}-01`;
              stageEnd.value = latest;
            }
          }

          function tradesForDay(iso) {
            return trades
              .filter((trade) => trade.date === iso && matchesCurrency(trade))
              .sort((a, b) => number(b.pnl) - number(a.pnl));
          }

          function statsForDay(iso) {
            const stats = new Map();
            tradesForDay(iso).forEach((trade) => {
              const currency = tradeCurrency(trade);
              if (!stats.has(currency)) stats.set(currency, { currency, count: 0, pnl: 0 });
              const bucket = stats.get(currency);
              bucket.count += 1;
              bucket.pnl += number(trade.pnl);
            });
            return Array.from(stats.values()).sort((a, b) => a.currency.localeCompare(b.currency, 'zh-CN'));
          }

          function pickSelectedDate(month) {
            if (selectedDate && selectedDate.slice(0, 7) === month && tradesForDay(selectedDate).length) return;
            const candidates = trades
              .filter((trade) => String(trade.date).slice(0, 7) === month && matchesCurrency(trade))
              .map((trade) => trade.date)
              .sort();
            selectedDate = candidates.length ? candidates[candidates.length - 1] : `${month}-01`;
          }

          function renderCalendar() {
            const month = monthSelect.value;
            calendar.innerHTML = '';
            if (!month) {
              calendar.textContent = '还没有已平仓交易，暂时无法生成盈亏日历。';
              return;
            }
            pickSelectedDate(month);

            ['一', '二', '三', '四', '五', '六', '日'].forEach((label) => {
              const header = document.createElement('div');
              header.className = 'pnl-calendar-weekday';
              header.textContent = label;
              calendar.appendChild(header);
            });

            const year = Number.parseInt(month.slice(0, 4), 10);
            const monthNumber = Number.parseInt(month.slice(5, 7), 10);
            const firstDate = new Date(year, monthNumber - 1, 1);
            const leading = (firstDate.getDay() + 6) % 7;
            const daysInMonth = new Date(year, monthNumber, 0).getDate();

            for (let i = 0; i < leading; i += 1) {
              const blank = document.createElement('div');
              blank.className = 'pnl-calendar-blank';
              calendar.appendChild(blank);
            }

            for (let day = 1; day <= daysInMonth; day += 1) {
              const iso = isoDate(year, monthNumber, day);
              const stats = statsForDay(iso);
              const button = document.createElement('button');
              button.type = 'button';
              button.className = 'pnl-calendar-day';
              if (stats.length) button.classList.add('has-trades', dayToneClass(stats));
              if (iso === selectedDate) button.classList.add('is-selected');
              button.dataset.date = iso;

              const dayNumber = document.createElement('span');
              dayNumber.className = 'pnl-day-number';
              dayNumber.textContent = String(day);
              button.appendChild(dayNumber);

              const lines = document.createElement('span');
              lines.className = 'pnl-day-lines';
              if (!stats.length) {
                const empty = document.createElement('span');
                empty.className = 'pnl-day-muted';
                empty.textContent = '-';
                lines.appendChild(empty);
              } else {
                stats.forEach((item) => {
                  const line = document.createElement('span');
                  line.className = `pnl-day-line ${tone(item.pnl)}`;
                  line.textContent = `${item.currency} ${formatNumber(item.pnl)}`;
                  lines.appendChild(line);
                });
              }
              button.appendChild(lines);

              const count = document.createElement('span');
              count.className = 'pnl-day-count';
              const tradeCount = stats.reduce((total, item) => total + item.count, 0);
              count.textContent = tradeCount ? `${tradeCount} 笔` : '';
              button.appendChild(count);

              button.addEventListener('click', () => {
                selectedDate = iso;
                renderCalendar();
                renderDayDetail();
              });
              calendar.appendChild(button);
            }
          }

          function renderTradeRows(body, items, emptyText, includeOpenDate) {
            body.innerHTML = '';
            if (!items.length) {
              emptyRow(body, includeOpenDate ? 10 : 10, emptyText);
              return;
            }
            items.forEach((trade) => {
              const tr = document.createElement('tr');
              const pnl = number(trade.pnl);
              const capital = number(trade.capital);
              const rawReturnRate = trade.returnRate;
              const hasReturnRate = rawReturnRate !== null && rawReturnRate !== undefined && rawReturnRate !== '';
              const returnRate = hasReturnRate && Number.isFinite(Number(rawReturnRate)) ? Number(rawReturnRate) : (capital ? pnl / capital : NaN);
              const days = number(trade.days);
              tr.appendChild(cell('text', trade.dateLabel || String(trade.date || '-')));
              if (includeOpenDate) tr.appendChild(cell('text', trade.openDateLabel || '-'));
              tr.appendChild(cell('text', trade.code || '-'));
              tr.appendChild(cell('text', trade.name || '-'));
              tr.appendChild(cell('text', trade.category || '-'));
              tr.appendChild(cell('text', trade.event || '-'));
              tr.appendChild(cell('money', formatNumber(pnl), pnl, true));
              if (!includeOpenDate) tr.appendChild(cell('money', formatNumber(capital), capital));
              tr.appendChild(cell('percent', formatPercent(returnRate), returnRate, true));
              tr.appendChild(cell('num', days ? formatNumber(days, 1) : '-', days || NaN));
              tr.appendChild(cell('ccy', tradeCurrency(trade)));
              body.appendChild(tr);
            });
          }

          function renderDayDetail() {
            if (dayTitle) dayTitle.textContent = `当日明细 ${selectedDate || ''}`;
            renderTradeRows(dayBody, tradesForDay(selectedDate), '这个日期没有已实现盈亏记录。', false);
          }

          function stageTrades() {
            const rawStart = stageStart.value || '';
            const rawEnd = stageEnd.value || '';
            const start = rawStart && rawEnd && rawStart > rawEnd ? rawEnd : rawStart;
            const end = rawStart && rawEnd && rawStart > rawEnd ? rawStart : rawEnd;
            return trades
              .filter((trade) => (!start || trade.date >= start) && (!end || trade.date <= end))
              .sort((a, b) => String(b.date).localeCompare(String(a.date)) || number(b.pnl) - number(a.pnl));
          }

          function summaryLabel(item) {
            if (!item) return '-';
            return `${item.code || '-'} ${formatNumber(item.pnl)}`;
          }

          function renderStageSummary(items) {
            stageSummaryBody.innerHTML = '';
            if (!items.length) {
              emptyRow(stageSummaryBody, 9, '当前阶段没有已实现盈亏记录。');
              return;
            }
            const statsByCurrency = new Map();
            items.forEach((trade) => {
              const currency = tradeCurrency(trade);
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
              const pnl = number(trade.pnl);
              const capital = number(trade.capital);
              const days = number(trade.days);
              const item = { code: trade.code, pnl };
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
                stageSummaryBody.appendChild(tr);
              });
          }

          function renderStageCategory(items) {
            stageCategoryBody.innerHTML = '';
            if (!items.length) {
              emptyRow(stageCategoryBody, 6, '当前阶段没有可拆分的已实现盈亏。');
              return;
            }
            const buckets = new Map();
            items.forEach((trade) => {
              const key = `${trade.category || '其他'}\\u0000${tradeCurrency(trade)}`;
              if (!buckets.has(key)) {
                buckets.set(key, { category: trade.category || '其他', currency: tradeCurrency(trade), count: 0, wins: 0, pnl: 0 });
              }
              const bucket = buckets.get(key);
              const pnl = number(trade.pnl);
              bucket.count += 1;
              if (pnl > 0.000001) bucket.wins += 1;
              bucket.pnl += pnl;
            });

            Array.from(buckets.values())
              .sort((a, b) => a.currency.localeCompare(b.currency, 'zh-CN') || a.category.localeCompare(b.category, 'zh-CN'))
              .forEach((bucket) => {
                const tr = document.createElement('tr');
                const average = bucket.count ? bucket.pnl / bucket.count : NaN;
                tr.appendChild(cell('text', bucket.category));
                tr.appendChild(cell('ccy', bucket.currency));
                tr.appendChild(cell('num', bucket.count.toLocaleString('en-US'), bucket.count));
                tr.appendChild(cell('num', bucket.wins.toLocaleString('en-US'), bucket.wins));
                tr.appendChild(cell('money', formatNumber(bucket.pnl), bucket.pnl, true));
                tr.appendChild(cell('money', formatNumber(average), average, true));
                stageCategoryBody.appendChild(tr);
              });
          }

          function renderStage() {
            const items = stageTrades();
            if (stageRangeLabel) {
              const start = stageStart.value || '最早';
              const end = stageEnd.value || '最新';
              stageRangeLabel.textContent = `${start} 至 ${end}`;
            }
            renderStageSummary(items);
            renderStageCategory(items);
            renderTradeRows(stageDetailBody, items, '当前阶段没有已实现盈亏记录。', true);
            if (typeof applyAllSummaryTableTones === 'function') applyAllSummaryTableTones();
            if (typeof balanceSummaryTableWidths === 'function') requestAnimationFrame(balanceSummaryTableWidths);
          }

          function renderAll() {
            renderCalendar();
            renderDayDetail();
            renderStage();
          }

          populateControls();
          monthSelect.addEventListener('change', () => {
            selectedDate = '';
            renderAll();
          });
          currencySelect.addEventListener('change', () => {
            selectedDate = '';
            renderAll();
          });
          stageStart.addEventListener('change', renderStage);
          stageEnd.addEventListener('change', renderStage);
          renderAll();
        })();
        </script>
"""


def render_realized_analysis_section(core, rows: list[tuple[int, dict[int, object]]]) -> str:
    trades = build_realized_trades(core, rows)
    body = (
        f'<script type="application/json" data-realized-payload>{json_payload(trades)}</script>'
        + render_calendar_panel()
        + render_stage_panel()
        + render_realized_filter_script()
    )
    return f"""
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary">
            <div class="section-head">
              <div>
                <h2 class="section-title">盈亏日历 / 阶段账单</h2>
                <p class="section-note">只按已经录入平仓日的交易计算已实现盈亏；不拉取历史行情，也不把当前持仓浮盈亏倒推到过去日期。</p>
              </div>
              <span class="section-toggle" aria-hidden="true"></span>
            </div>
          </summary>
          <div class="section-body realized-analysis" data-realized-analysis>
            {body}
          </div>
        </details>
"""


def insert_realized_analysis_section(core, html_text: str, rows: list[tuple[int, dict[int, object]]]) -> str:
    if '<h2 class="section-title">盈亏日历 / 阶段账单</h2>' in html_text:
        return html_text
    section = render_realized_analysis_section(core, rows)

    def section_start_for_heading(heading: str) -> int | None:
        heading_index = html_text.find(f'<h2 class="section-title">{heading}</h2>')
        if heading_index < 0:
            return None
        details_index = html_text.rfind('<details class="dashboard-section section-collapsible" open>', 0, heading_index)
        if details_index < 0:
            return None
        return details_index

    clearance_start = section_start_for_heading("清仓分析")
    if clearance_start is not None:
        return html_text[:clearance_start] + "\n" + section + html_text[clearance_start:]
    timeline_start = section_start_for_heading("交易时间线")
    if timeline_start is not None:
        return html_text[:timeline_start] + "\n" + section + html_text[timeline_start:]
    worksheet_start = section_start_for_heading("工作表入口")
    if worksheet_start is not None:
        return html_text[:worksheet_start] + "\n" + section + html_text[worksheet_start:]
    if "</body>" in html_text:
        return html_text.replace("</body>", section + "</body>", 1)
    return html_text + section
