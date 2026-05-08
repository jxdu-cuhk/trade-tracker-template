from __future__ import annotations

import html

from .realized_analysis import RealizedTrade, build_realized_trades, json_payload, th


def build_option_trades(core, rows: list[tuple[int, dict[int, object]]]) -> list[RealizedTrade]:
    return [trade for trade in build_realized_trades(core, rows) if trade.category == "期权"]


def render_empty_table(headers: list[tuple[str, str, str]], body_attr: str, empty_message: str) -> str:
    return (
        '<div class="summary-wrap">\n'
        '  <table class="summary-table js-sortable-table option-analysis-table">\n'
        "    <thead>\n"
        f"      <tr>{''.join(th(css, sort_type, label) for css, sort_type, label in headers)}</tr>\n"
        "    </thead>\n"
        f'    <tbody {body_attr}>\n'
        f'      <tr><td class="text" colspan="{len(headers)}">{html.escape(empty_message)}</td></tr>\n'
        "    </tbody>\n"
        "  </table>\n"
        "</div>"
    )


def render_option_controls() -> str:
    return """
            <div class="section-toolbar realized-stage-toolbar option-analysis-toolbar">
              <span class="filter-label">区间</span>
              <select class="filter-select js-option-range" aria-label="选择期权收益区间">
                <option value="month" selected>本月</option>
                <option value="three-month">近三月</option>
                <option value="year">今年</option>
                <option value="all">全部</option>
                <option value="custom">自定义</option>
              </select>
              <span class="filter-label option-custom-control" data-option-custom hidden>开始</span>
              <input class="filter-select realized-date-input option-custom-control js-option-start" type="date" aria-label="选择期权收益开始日期" data-option-custom hidden>
              <span class="filter-label option-custom-control" data-option-custom hidden>结束</span>
              <input class="filter-select realized-date-input option-custom-control js-option-end" type="date" aria-label="选择期权收益结束日期" data-option-custom hidden>
              <span class="filter-label">币种</span>
              <select class="filter-select js-option-currency" aria-label="选择期权收益币种"></select>
              <span class="filter-label">事件</span>
              <select class="filter-select js-option-event" aria-label="选择期权事件">
                <option value="all" selected>全部事件</option>
                <option value="认购">认购</option>
                <option value="认沽">认沽</option>
              </select>
            </div>
"""


def render_option_tables() -> str:
    overview_headers = [
        ("ccy", "text", "币种"),
        ("num", "number", "期权笔数"),
        ("num", "number", "盈利笔数"),
        ("percent", "number", "胜率"),
        ("money", "number", "已实现盈亏"),
        ("money", "number", "占用/投入本金"),
        ("percent", "number", "收益率"),
        ("num", "number", "平均持有天数"),
        ("text", "text", "最大盈利"),
        ("text", "text", "最大亏损"),
    ]
    underlying_headers = [
        ("text", "text", "代码"),
        ("text", "text", "名称"),
        ("ccy", "text", "币种"),
        ("num", "number", "期权笔数"),
        ("money", "number", "认购盈亏"),
        ("money", "number", "认沽盈亏"),
        ("money", "number", "总盈亏"),
        ("percent", "number", "收益率"),
        ("percent", "number", "胜率"),
        ("text", "text", "最大盈利"),
        ("text", "text", "最大亏损"),
    ]
    detail_headers = [
        ("text", "date", "平仓日"),
        ("text", "date", "开仓日"),
        ("text", "text", "代码"),
        ("text", "text", "名称"),
        ("text", "text", "类型"),
        ("text", "text", "事件"),
        ("money", "number", "已实现盈亏"),
        ("money", "number", "占用/投入本金"),
        ("percent", "number", "收益率"),
        ("num", "number", "持有天数"),
        ("ccy", "text", "币种"),
    ]
    return (
        '<h3 class="realized-subtitle">期权总览</h3>\n'
        + render_empty_table(overview_headers, "data-option-overview-body", "当前区间没有已平仓期权。")
        + '<h3 class="realized-subtitle">标的拆分</h3>\n'
        + render_empty_table(underlying_headers, "data-option-underlying-body", "当前区间没有可拆分的期权收益。")
        + '<h3 class="realized-subtitle">期权明细</h3>\n'
        + render_empty_table(detail_headers, "data-option-detail-body", "当前区间没有期权收益明细。")
    )


def render_option_filter_script() -> str:
    return """
        <script>
        (function setupOptionAnalysis() {
          const section = document.querySelector('[data-option-analysis]');
          if (!section || section.dataset.optionReady === '1') return;
          section.dataset.optionReady = '1';

          const payloadNode = section.querySelector('[data-option-payload]');
          let payload = { trades: [] };
          try {
            payload = JSON.parse(payloadNode ? payloadNode.textContent : '{"trades":[]}');
          } catch (_error) {
            payload = { trades: [] };
          }
          const trades = Array.isArray(payload.trades) ? payload.trades.filter((trade) => trade && trade.date) : [];
          const rangeSelect = section.querySelector('.js-option-range');
          const startInput = section.querySelector('.js-option-start');
          const endInput = section.querySelector('.js-option-end');
          const currencySelect = section.querySelector('.js-option-currency');
          const eventSelect = section.querySelector('.js-option-event');
          const overviewBody = section.querySelector('[data-option-overview-body]');
          const underlyingBody = section.querySelector('[data-option-underlying-body]');
          const detailBody = section.querySelector('[data-option-detail-body]');
          const customControls = Array.from(section.querySelectorAll('[data-option-custom]'));
          if (!rangeSelect || !startInput || !endInput || !currencySelect || !eventSelect || !overviewBody || !underlyingBody || !detailBody) return;

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

          function unique(values) {
            return Array.from(new Set(values.filter(Boolean)));
          }

          function latestDate() {
            return trades.map((trade) => String(trade.date || '')).filter(Boolean).sort().pop() || '';
          }

          function isoFromDate(date) {
            return [
              date.getFullYear(),
              String(date.getMonth() + 1).padStart(2, '0'),
              String(date.getDate()).padStart(2, '0'),
            ].join('-');
          }

          function rangeBounds() {
            const latest = latestDate();
            if (!latest) return { start: '', end: '' };
            const latestObj = new Date(`${latest}T00:00:00`);
            if (rangeSelect.value === 'all') return { start: '', end: latest };
            if (rangeSelect.value === 'custom') return { start: startInput.value || '', end: endInput.value || latest };
            if (rangeSelect.value === 'year') return { start: `${latest.slice(0, 4)}-01-01`, end: latest };
            if (rangeSelect.value === 'three-month') {
              const start = new Date(latestObj);
              start.setMonth(start.getMonth() - 2);
              start.setDate(1);
              return { start: isoFromDate(start), end: latest };
            }
            return { start: `${latest.slice(0, 7)}-01`, end: latest };
          }

          function tradeCurrency(trade) {
            return String(trade.currency || '未标注币种');
          }

          function matchesFilters(trade) {
            const bounds = rangeBounds();
            const date = String(trade.date || '');
            if (bounds.start && date < bounds.start) return false;
            if (bounds.end && date > bounds.end) return false;
            if (currencySelect.value !== 'all' && tradeCurrency(trade) !== currencySelect.value) return false;
            if (eventSelect.value !== 'all' && String(trade.event || '') !== eventSelect.value) return false;
            return true;
          }

          function filteredTrades() {
            return trades
              .filter(matchesFilters)
              .sort((a, b) => String(b.date).localeCompare(String(a.date)) || number(b.pnl) - number(a.pnl));
          }

          function summaryLabel(item) {
            if (!item) return '-';
            return `${item.code || '-'} ${item.event || ''} ${formatNumber(item.pnl)}`.trim();
          }

          function renderOverview(items) {
            overviewBody.innerHTML = '';
            if (!items.length) {
              emptyRow(overviewBody, 10, '当前区间没有已平仓期权。');
              return;
            }
            const buckets = new Map();
            items.forEach((trade) => {
              const currency = tradeCurrency(trade);
              if (!buckets.has(currency)) {
                buckets.set(currency, { currency, count: 0, wins: 0, pnl: 0, capital: 0, days: 0, best: null, worst: null });
              }
              const bucket = buckets.get(currency);
              const pnl = number(trade.pnl);
              const capital = number(trade.capital);
              const days = number(trade.days);
              const item = { code: trade.code, event: trade.event, pnl };
              bucket.count += 1;
              if (pnl > 0.000001) bucket.wins += 1;
              bucket.pnl += pnl;
              bucket.capital += capital;
              bucket.days += days;
              if (pnl > 0.000001 && (!bucket.best || pnl > bucket.best.pnl)) bucket.best = item;
              if (pnl < -0.000001 && (!bucket.worst || pnl < bucket.worst.pnl)) bucket.worst = item;
            });
            Array.from(buckets.values())
              .sort((a, b) => a.currency.localeCompare(b.currency, 'zh-CN'))
              .forEach((bucket) => {
                const tr = document.createElement('tr');
                const winRate = bucket.count ? bucket.wins / bucket.count : NaN;
                const returnRate = bucket.capital ? bucket.pnl / bucket.capital : NaN;
                const avgDays = bucket.count ? bucket.days / bucket.count : NaN;
                tr.appendChild(cell('ccy', bucket.currency));
                tr.appendChild(cell('num', bucket.count.toLocaleString('en-US'), bucket.count));
                tr.appendChild(cell('num', bucket.wins.toLocaleString('en-US'), bucket.wins));
                tr.appendChild(cell('percent', formatPercent(winRate), winRate));
                tr.appendChild(cell('money', formatNumber(bucket.pnl), bucket.pnl, true));
                tr.appendChild(cell('money', formatNumber(bucket.capital), bucket.capital));
                tr.appendChild(cell('percent', formatPercent(returnRate), returnRate, true));
                tr.appendChild(cell('num', Number.isFinite(avgDays) ? formatNumber(avgDays, 1) : '-', avgDays));
                tr.appendChild(cell('text', summaryLabel(bucket.best), bucket.best ? bucket.best.pnl : NaN, true));
                tr.appendChild(cell('text', summaryLabel(bucket.worst), bucket.worst ? bucket.worst.pnl : NaN, true));
                overviewBody.appendChild(tr);
              });
          }

          function renderUnderlying(items) {
            underlyingBody.innerHTML = '';
            if (!items.length) {
              emptyRow(underlyingBody, 11, '当前区间没有可拆分的期权收益。');
              return;
            }
            const buckets = new Map();
            items.forEach((trade) => {
              const key = `${trade.code || '-'}\\u0000${tradeCurrency(trade)}`;
              if (!buckets.has(key)) {
                buckets.set(key, {
                  code: trade.code || '-',
                  name: trade.name || '-',
                  currency: tradeCurrency(trade),
                  count: 0,
                  wins: 0,
                  callPnl: 0,
                  putPnl: 0,
                  pnl: 0,
                  capital: 0,
                  best: null,
                  worst: null,
                });
              }
              const bucket = buckets.get(key);
              const pnl = number(trade.pnl);
              const event = String(trade.event || '');
              const item = { code: trade.code, event: trade.event, pnl };
              bucket.count += 1;
              if (pnl > 0.000001) bucket.wins += 1;
              if (event.includes('认购') || event.toLowerCase().includes('call')) bucket.callPnl += pnl;
              else if (event.includes('认沽') || event.toLowerCase().includes('put')) bucket.putPnl += pnl;
              bucket.pnl += pnl;
              bucket.capital += number(trade.capital);
              if (pnl > 0.000001 && (!bucket.best || pnl > bucket.best.pnl)) bucket.best = item;
              if (pnl < -0.000001 && (!bucket.worst || pnl < bucket.worst.pnl)) bucket.worst = item;
            });
            Array.from(buckets.values())
              .sort((a, b) => b.pnl - a.pnl || a.code.localeCompare(b.code, 'zh-CN'))
              .forEach((bucket) => {
                const tr = document.createElement('tr');
                const returnRate = bucket.capital ? bucket.pnl / bucket.capital : NaN;
                const winRate = bucket.count ? bucket.wins / bucket.count : NaN;
                tr.appendChild(cell('text', bucket.code));
                tr.appendChild(cell('text', bucket.name));
                tr.appendChild(cell('ccy', bucket.currency));
                tr.appendChild(cell('num', bucket.count.toLocaleString('en-US'), bucket.count));
                tr.appendChild(cell('money', formatNumber(bucket.callPnl), bucket.callPnl, true));
                tr.appendChild(cell('money', formatNumber(bucket.putPnl), bucket.putPnl, true));
                tr.appendChild(cell('money', formatNumber(bucket.pnl), bucket.pnl, true));
                tr.appendChild(cell('percent', formatPercent(returnRate), returnRate, true));
                tr.appendChild(cell('percent', formatPercent(winRate), winRate));
                tr.appendChild(cell('text', summaryLabel(bucket.best), bucket.best ? bucket.best.pnl : NaN, true));
                tr.appendChild(cell('text', summaryLabel(bucket.worst), bucket.worst ? bucket.worst.pnl : NaN, true));
                underlyingBody.appendChild(tr);
              });
          }

          function renderDetail(items) {
            detailBody.innerHTML = '';
            if (!items.length) {
              emptyRow(detailBody, 11, '当前区间没有期权收益明细。');
              return;
            }
            items.forEach((trade) => {
              const pnl = number(trade.pnl);
              const capital = number(trade.capital);
              const rawReturnRate = trade.returnRate;
              const returnRate = rawReturnRate !== null && rawReturnRate !== undefined && Number.isFinite(Number(rawReturnRate))
                ? Number(rawReturnRate)
                : (capital ? pnl / capital : NaN);
              const days = number(trade.days);
              const tr = document.createElement('tr');
              tr.appendChild(cell('text', trade.dateLabel || trade.date || '-'));
              tr.appendChild(cell('text', trade.openDateLabel || '-'));
              tr.appendChild(cell('text', trade.code || '-'));
              tr.appendChild(cell('text', trade.name || '-'));
              tr.appendChild(cell('text', trade.type || '-'));
              tr.appendChild(cell('text', trade.event || '-'));
              tr.appendChild(cell('money', formatNumber(pnl), pnl, true));
              tr.appendChild(cell('money', formatNumber(capital), capital));
              tr.appendChild(cell('percent', formatPercent(returnRate), returnRate, true));
              tr.appendChild(cell('num', days ? formatNumber(days, 1) : '-', days || NaN));
              tr.appendChild(cell('ccy', tradeCurrency(trade)));
              detailBody.appendChild(tr);
            });
          }

          function populateControls() {
            currencySelect.innerHTML = '';
            const all = document.createElement('option');
            all.value = 'all';
            all.textContent = '全部币种';
            currencySelect.appendChild(all);
            unique(trades.map(tradeCurrency)).sort((a, b) => a.localeCompare(b, 'zh-CN')).forEach((currency) => {
              const option = document.createElement('option');
              option.value = currency;
              option.textContent = currency;
              currencySelect.appendChild(option);
            });
            const latest = latestDate();
            if (latest) {
              startInput.value = `${latest.slice(0, 7)}-01`;
              endInput.value = latest;
            }
          }

          function renderAll() {
            customControls.forEach((node) => {
              node.hidden = rangeSelect.value !== 'custom';
            });
            const items = filteredTrades();
            renderOverview(items);
            renderUnderlying(items);
            renderDetail(items);
            if (typeof applyAllSummaryTableTones === 'function') applyAllSummaryTableTones();
            if (typeof balanceSummaryTableWidths === 'function') requestAnimationFrame(balanceSummaryTableWidths);
          }

          populateControls();
          rangeSelect.addEventListener('change', renderAll);
          startInput.addEventListener('change', renderAll);
          endInput.addEventListener('change', renderAll);
          currencySelect.addEventListener('change', renderAll);
          eventSelect.addEventListener('change', renderAll);
          renderAll();
        })();
        </script>
"""


def render_option_analysis_section(core, rows: list[tuple[int, dict[int, object]]]) -> str:
    trades = build_option_trades(core, rows)
    body = (
        f'<script type="application/json" data-option-payload>{json_payload(trades)}</script>'
        + render_option_controls()
        + render_option_tables()
        + render_option_filter_script()
    )
    return f"""
        <details class="dashboard-section section-collapsible" open>
          <summary class="section-summary">
            <div class="section-head">
              <div>
                <h2 class="section-title">期权收益分析</h2>
                <p class="section-note">只统计已经录入平仓日的期权收益，独立于股票清仓周期；未平仓期权仍看上方持仓表。</p>
              </div>
              <span class="section-toggle" aria-hidden="true"></span>
            </div>
          </summary>
          <div class="section-body realized-analysis option-analysis" data-option-analysis>
            {body}
          </div>
        </details>
"""


def insert_option_analysis_section(core, html_text: str, rows: list[tuple[int, dict[int, object]]]) -> str:
    if '<h2 class="section-title">期权收益分析</h2>' in html_text:
        return html_text
    section = render_option_analysis_section(core, rows)

    def section_start_for_heading(heading: str) -> int | None:
        heading_index = html_text.find(f'<h2 class="section-title">{heading}</h2>')
        if heading_index < 0:
            return None
        details_index = html_text.rfind('<details class="dashboard-section section-collapsible" open>', 0, heading_index)
        if details_index < 0:
            return None
        return details_index

    overview_start = section_start_for_heading("总体概览")
    if overview_start is not None:
        return html_text[:overview_start] + "\n" + section + html_text[overview_start:]
    timeline_start = section_start_for_heading("交易时间线")
    if timeline_start is not None:
        return html_text[:timeline_start] + "\n" + section + html_text[timeline_start:]
    if "</body>" in html_text:
        return html_text.replace("</body>", section + "</body>", 1)
    return html_text + section
