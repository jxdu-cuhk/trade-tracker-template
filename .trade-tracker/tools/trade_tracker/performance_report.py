from __future__ import annotations

import json
import re

from . import state


def safe_json(data: object) -> str:
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def render_performance_report_section() -> str:
    stock_payload = safe_json(state.PERFORMANCE_STOCK_PAYLOAD or {"months": {}, "years": {}})
    template = r'''
        <details class="dashboard-section section-collapsible" open data-performance-report>
          <summary class="section-summary">
            <h2 class="section-title">收益报告</h2>
          </summary>
          <div class="section-body">
            <div class="performance-report-shell">
              <div class="performance-report-mode" role="group" aria-label="收益报告展示口径" data-report-mode-control>
                <button type="button" class="is-active" data-report-mode="amount" aria-pressed="true">金额</button>
                <button type="button" data-report-mode="rate" aria-pressed="false">收益率</button>
              </div>
              <section class="performance-block">
                <h3 class="performance-title">账户涨跌</h3>
                <div class="performance-swing-grid">
                  <div class="performance-swing-card swing-positive" data-report-growth>
                    <span data-report-title>最大涨幅</span>
                    <strong data-report-rate>--</strong>
                    <em data-report-amount>--</em>
                    <small data-report-days>增长天数 --</small>
                    <small data-report-range>--</small>
                  </div>
                  <div class="performance-swing-card swing-negative" data-report-drawdown>
                    <span data-report-title>最大回撤</span>
                    <strong data-report-rate>--</strong>
                    <em data-report-amount>--</em>
                    <small data-report-days>回撤天数 --</small>
                    <small data-report-range>--</small>
                  </div>
                </div>
              </section>
              <section class="performance-block">
                <h3 class="performance-title">盈亏对比</h3>
                <div class="performance-compare-list" data-report-compare></div>
              </section>
              <section class="performance-block">
                <div class="performance-title-row">
                  <h3 class="performance-title">盈亏日历</h3>
                  <strong data-report-calendar-total>--</strong>
                </div>
                <div class="performance-calendar-toolbar">
                  <div class="performance-year-controls" data-report-year-controls></div>
                  <div class="performance-calendar-stats">
                    <span>交易月 <b data-report-calendar-month-count>--</b></span>
                    <span class="value-positive">盈利 <b data-report-calendar-win-count>--</b></span>
                    <span class="value-negative">亏损 <b data-report-calendar-loss-count>--</b></span>
                  </div>
                </div>
                <div class="performance-calendar-chart-wrap">
                  <svg class="performance-calendar-chart" viewBox="0 0 720 200" role="img" aria-label="月度盈亏柱状图" data-report-calendar-chart></svg>
                </div>
                <div class="performance-calendar" data-report-calendar></div>
              </section>
              <section class="performance-block">
                <div class="performance-title-row">
                  <h3 class="performance-title">个股盈亏</h3>
                  <strong data-report-stock-count>--</strong>
                </div>
                <div class="performance-stock-board">
                  <div class="performance-treemap" data-report-treemap></div>
                  <div class="performance-stock-list" data-report-stock-list></div>
                </div>
              </section>
            </div>
            <script type="application/json" data-performance-stock-payload>__STOCK_PAYLOAD__</script>
            <script>
            (function setupPerformanceReport() {
              const script = document.currentScript;
              const section = script?.closest('[data-performance-report]');
              if (!section || section.dataset.reportReady === '1') return;
              section.dataset.reportReady = '1';
              const dataNode = document.querySelector('[data-return-curve-json]');
              const realizedNode = document.querySelector('[data-realized-payload]');
              const stockPayloadNode = document.querySelector('[data-performance-stock-payload]');
              const modeControl = section.querySelector('[data-report-mode-control]');
              let series = null;
              let realizedTrades = [];
              let stockPerformanceMonths = {};
              let reportMode = 'amount';
              try {
                const payload = JSON.parse(dataNode?.textContent || '[]');
                series = payload && payload[0];
              } catch (error) {
                series = null;
              }
              try {
                const realizedPayload = JSON.parse(realizedNode?.textContent || '{}');
                realizedTrades = Array.isArray(realizedPayload?.trades) ? realizedPayload.trades : [];
              } catch (error) {
                realizedTrades = [];
              }
              try {
                const stockPayload = JSON.parse(stockPayloadNode?.textContent || '{}');
                stockPerformanceMonths = stockPayload?.months && typeof stockPayload.months === 'object' ? stockPayload.months : {};
              } catch (error) {
                stockPerformanceMonths = {};
              }
              const rawPoints = (series?.points || []).filter((point) => point && point.iso);
              if (!rawPoints.length) return;

              function number(value) {
                const parsed = Number(value);
                return Number.isFinite(parsed) ? parsed : NaN;
              }

              function reportingCurrency() {
                const label = document.documentElement.dataset.reportingCurrency || '人民币';
                return ['人民币', '港币', '美元'].includes(label) ? label : '人民币';
              }

              function rateToCnyForCurrency(currency) {
                const label = String(currency || '').trim() || '人民币';
                const rate = Number((window.tradeTrackerFxRatesToCny || {})[label]);
                return Number.isFinite(rate) && rate > 0 ? rate : 1;
              }

              function reportingRateToCny() {
                const api = window.tradeTrackerReportingCurrency;
                if (api && typeof api.rateToCny === 'function') {
                  const rate = Number(api.rateToCny());
                  if (Number.isFinite(rate) && rate > 0) return rate;
                }
                return rateToCnyForCurrency(reportingCurrency());
              }

              function reportingMoney(value) {
                const numeric = number(value);
                return Number.isFinite(numeric) ? numeric / reportingRateToCny() : NaN;
              }

              function signedMoney(value) {
                const converted = reportingMoney(value);
                if (!Number.isFinite(converted)) return '--';
                const sign = converted > 0 ? '+' : converted < 0 ? '-' : '';
                return sign + Math.abs(converted).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
              }

              function compactMoney(value) {
                const converted = reportingMoney(value);
                if (!Number.isFinite(converted)) return '--';
                const sign = converted > 0 ? '+' : converted < 0 ? '-' : '';
                const abs = Math.abs(converted);
                if (abs >= 10000) return `${sign}${(abs / 10000).toFixed(abs >= 100000 ? 0 : 1)}万`;
                return signedMoney(converted * reportingRateToCny());
              }

              function percent(value) {
                if (!Number.isFinite(value)) return '--';
                return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
              }

              function formatMetric(value, compact = false) {
                return reportMode === 'rate' ? percent(value) : (compact ? compactMoney(value) : signedMoney(value));
              }

              function metricLabel() {
                return reportMode === 'rate' ? '收益率' : `折${reportingCurrency()}`;
              }

              function shortDate(iso) {
                return String(iso || '').replace(/-/g, '/');
              }

              function escapeHtml(value) {
                return String(value ?? '').replace(/[&<>"']/g, (char) => ({
                  '&': '&amp;',
                  '<': '&lt;',
                  '>': '&gt;',
                  '"': '&quot;',
                  "'": '&#39;',
                }[char]));
              }

              function daysBetween(a, b) {
                const left = number(a?.serial);
                const right = number(b?.serial);
                if (!Number.isFinite(left) || !Number.isFinite(right)) return NaN;
                return Math.max(0, Math.round(right - left));
              }

              const fallbackCapital = Math.max(number(series?.capital), Math.abs(number(rawPoints[rawPoints.length - 1]?.value)), 1);
              const carriedCapitalByIso = new Map();
              let carriedCapital = 0;
              rawPoints.forEach((point) => {
                const pointCapital = number(point?.capital);
                if (Number.isFinite(pointCapital) && pointCapital > carriedCapital) carriedCapital = pointCapital;
                if (point?.iso && carriedCapital > 0) carriedCapitalByIso.set(point.iso, carriedCapital);
              });
              function capitalFor(point) {
                const carried = carriedCapitalByIso.get(point?.iso);
                if (Number.isFinite(carried) && carried > 0) return carried;
                const value = number(point?.capital);
                return Number.isFinite(value) && value > 0 ? value : fallbackCapital;
              }

              const points = rawPoints.map((point, index) => {
                const previous = index > 0 ? rawPoints[index - 1] : null;
                const amount = number(point.value) || 0;
                const previousAmount = previous ? number(previous.value) || 0 : amount;
                const delta = index > 0 ? amount - previousAmount : 0;
                const capital = capitalFor(point);
                const previousCapital = previous ? capitalFor(previous) : capital;
                const dailyReturn = previousCapital > 0 ? (delta / previousCapital) * 100 : 0;
                const returnValue = capital > 0 ? (amount / capital) * 100 : 0;
                return {
                  ...point,
                  amountValue: amount,
                  dailyAmountValue: delta,
                  dailyReturn,
                  returnValue,
                };
              });

              function nav(point) {
                const value = 1 + number(point?.returnValue) / 100;
                return Number.isFinite(value) && value > 0 ? value : NaN;
              }

              function maxDrawdown(items) {
                let peak = null;
                let result = null;
                items.forEach((point) => {
                  const currentNav = nav(point);
                  if (!Number.isFinite(currentNav)) return;
                  if (!peak || currentNav > peak.nav) peak = { point, nav: currentNav };
                  if (!peak || peak.point === point) return;
                  const rate = ((currentNav / peak.nav) - 1) * 100;
                  const amount = number(point.amountValue) - number(peak.point.amountValue);
                  if (rate < 0 && (!result || rate < result.rate)) {
                    result = { start: peak.point, end: point, rate, amount, days: daysBetween(peak.point, point) };
                  }
                });
                return result;
              }

              function maxGrowth(items) {
                let trough = null;
                let result = null;
                items.forEach((point) => {
                  const currentNav = nav(point);
                  if (!Number.isFinite(currentNav)) return;
                  if (!trough || currentNav < trough.nav) trough = { point, nav: currentNav };
                  if (!trough || trough.point === point) return;
                  const rate = ((currentNav / trough.nav) - 1) * 100;
                  const amount = number(point.amountValue) - number(trough.point.amountValue);
                  if (rate > 0 && (!result || rate > result.rate)) {
                    result = { start: trough.point, end: point, rate, amount, days: daysBetween(trough.point, point) };
                  }
                });
                return result;
              }

              function accountTotalReturn(items) {
                if (!items.length) return null;
                const start = items[0];
                const end = items[items.length - 1];
                return {
                  start,
                  end,
                  amount: number(end.amountValue) || 0,
                  rate: number(end.returnValue) || 0,
                  days: daysBetween(start, end),
                };
              }

              function maxAmountDrawdown(items) {
                let peak = null;
                let result = null;
                items.forEach((point) => {
                  const amount = number(point.amountValue);
                  if (!Number.isFinite(amount)) return;
                  if (!peak || amount > peak.amount) peak = { point, amount };
                  if (!peak || peak.point === point) return;
                  const drawdownAmount = amount - peak.amount;
                  const rate = (number(point.returnValue) || 0) - (number(peak.point.returnValue) || 0);
                  if (drawdownAmount < 0 && (!result || drawdownAmount < result.amount)) {
                    result = { start: peak.point, end: point, rate, amount: drawdownAmount, days: daysBetween(peak.point, point) };
                  }
                });
                return result;
              }

              function fillSwingCard(card, item, options) {
                if (!card) return;
                const title = options?.title || '';
                const dayLabel = options?.dayLabel || '';
                const titleNode = card.querySelector('[data-report-title]');
                const secondary = card.querySelector('[data-report-amount]');
                if (titleNode && title) titleNode.textContent = title;
                if (!item) {
                  card.querySelector('[data-report-rate]').textContent = '--';
                  if (secondary) {
                    secondary.hidden = true;
                    secondary.textContent = '';
                  }
                  card.querySelector('[data-report-days]').textContent = `${dayLabel} --`;
                  card.querySelector('[data-report-range]').textContent = '--';
                  return;
                }
                card.querySelector('[data-report-rate]').textContent = reportMode === 'rate' ? percent(item.rate) : signedMoney(item.amount);
                if (secondary) {
                  secondary.hidden = reportMode === 'rate';
                  secondary.textContent = reportMode === 'rate' ? '' : percent(item.rate);
                }
                card.querySelector('[data-report-days]').textContent = `${dayLabel} ${Number.isFinite(item.days) ? item.days : '--'}`;
                card.querySelector('[data-report-range]').textContent = `${shortDate(item.start.iso)}-${shortDate(item.end.iso)}`;
              }

              const amountGrowthSwing = accountTotalReturn(points);
              const amountDrawdownSwing = maxAmountDrawdown(points);
              const rateGrowthSwing = maxGrowth(points);
              const rateDrawdownSwing = maxDrawdown(points);

              function renderSwingCards() {
                if (reportMode === 'rate') {
                  fillSwingCard(section.querySelector('[data-report-growth]'), rateGrowthSwing, { title: '最大涨幅', dayLabel: '增长天数' });
                  fillSwingCard(section.querySelector('[data-report-drawdown]'), rateDrawdownSwing, { title: '最大回撤', dayLabel: '回撤天数' });
                  return;
                }
                fillSwingCard(section.querySelector('[data-report-growth]'), amountGrowthSwing, { title: '累计收益', dayLabel: '累计天数' });
                fillSwingCard(section.querySelector('[data-report-drawdown]'), amountDrawdownSwing, { title: '最大回撤', dayLabel: '回撤天数' });
              }

              const dayChanges = points.slice(1).map((point) => ({
                iso: point.iso,
                label: shortDate(point.iso),
                value: number(point.dailyAmountValue) || 0,
                rate: number(point.dailyReturn) || 0,
              }));
              const sum = (items) => items.reduce((total, item) => total + item.value, 0);
              const sumRate = (items) => items.reduce((total, item) => total + (number(item.rate) || 0), 0);
              const compoundRate = (items) => {
                if (!items.length) return 0;
                const multiplier = items.reduce((amount, item) => amount * (1 + (number(item.rate) || 0) / 100), 1);
                return (multiplier - 1) * 100;
              };
              const metricValue = (item) => reportMode === 'rate' ? (number(item?.rate) || 0) : (number(item?.value) || 0);
              const metricTotal = (items) => reportMode === 'rate' ? compoundRate(items) : sum(items);
              const maxBy = (items, pick) => items.length ? items.reduce((best, item) => (pick(item) > pick(best) ? item : best), items[0]) : null;
              const minBy = (items, pick) => items.length ? items.reduce((best, item) => (pick(item) < pick(best) ? item : best), items[0]) : null;

              const monthMap = new Map();
              dayChanges.forEach((item) => {
                const key = String(item.iso).slice(0, 7);
                const bucket = monthMap.get(key) || { key, value: 0, rateMultiplier: 1, days: 0, wins: 0, losses: 0 };
                bucket.value += item.value;
                bucket.rateMultiplier *= 1 + (number(item.rate) || 0) / 100;
                bucket.days += 1;
                if (item.value > 0) bucket.wins += 1;
                if (item.value < 0) bucket.losses += 1;
                monthMap.set(key, bucket);
              });
              const months = Array.from(monthMap.values())
                .sort((a, b) => a.key.localeCompare(b.key))
                .map((item) => ({
                  ...item,
                  rate: (item.rateMultiplier - 1) * 100,
                  year: String(item.key).slice(0, 4),
                  month: Number(String(item.key).slice(5, 7)),
                }));

              function compareRow(leftTitle, leftSub, leftValue, rightTitle, rightSub, rightValue) {
                const total = Math.abs(leftValue || 0) + Math.abs(rightValue || 0);
                const ratioLeft = total > 0 ? Math.max(6, Math.abs(leftValue || 0) / total * 100) : 50;
                const ratioRight = Math.max(6, 100 - ratioLeft);
                return `
                  <div class="performance-compare-card">
                    <div><strong>${leftTitle}</strong><span>${leftSub}</span><em class="value-positive">${formatMetric(leftValue)}</em></div>
                    <b>${leftValue || rightValue ? `${Math.round(ratioLeft / 10)} : ${Math.round(ratioRight / 10)}` : '--'}</b>
                    <div><strong>${rightTitle}</strong><span>${rightSub}</span><em class="value-negative">${formatMetric(rightValue)}</em></div>
                    <i style="--left:${ratioLeft.toFixed(1)}%;--right:${ratioRight.toFixed(1)}%"></i>
                  </div>
                `;
              }

              function renderCompare() {
                const profitDays = dayChanges.filter((item) => metricValue(item) > 0);
                const lossDays = dayChanges.filter((item) => metricValue(item) < 0);
                const bestMonth = maxBy(months, metricValue);
                const worstMonth = minBy(months, metricValue);
                const bestDay = maxBy(dayChanges, metricValue);
                const worstDay = minBy(dayChanges, metricValue);
                const positiveTotal = reportMode === 'rate' ? sumRate(profitDays) : sum(profitDays);
                const negativeTotal = reportMode === 'rate' ? sumRate(lossDays) : sum(lossDays);
                section.querySelector('[data-report-compare]').innerHTML = [
                  compareRow(reportMode === 'rate' ? '盈利日收益' : '总盈利', `盈利天数 ${profitDays.length}`, positiveTotal, reportMode === 'rate' ? '亏损日收益' : '总亏损', `亏损天数 ${lossDays.length}`, negativeTotal),
                  compareRow('最大月盈利', bestMonth?.key || '--', metricValue(bestMonth), '最大月亏损', worstMonth?.key || '--', metricValue(worstMonth)),
                  compareRow('最大日盈利', bestDay?.label || '--', metricValue(bestDay), '最大日亏损', worstDay?.label || '--', metricValue(worstDay)),
                ].join('');
              }

              const years = Array.from(new Set(months.map((item) => item.year))).sort();
              const selectedYears = new Set(years);
              const yearControls = section.querySelector('[data-report-year-controls]');
              const calendarChart = section.querySelector('[data-report-calendar-chart]');
              const calendar = section.querySelector('[data-report-calendar]');
              const totalNode = section.querySelector('[data-report-calendar-total]');
              const monthCountNode = section.querySelector('[data-report-calendar-month-count]');
              const winCountNode = section.querySelector('[data-report-calendar-win-count]');
              const lossCountNode = section.querySelector('[data-report-calendar-loss-count]');
              const monthByKey = new Map(months.map((item) => [item.key, item]));
              let selectedMonthKey = months.length ? months[months.length - 1].key : '';

              function visibleMonths() {
                return months.filter((item) => selectedYears.has(item.year));
              }

              function calendarMonthsForSelectedYears() {
                return years
                  .filter((year) => selectedYears.has(year))
                  .flatMap((year) => Array.from({ length: 12 }, (_, index) => {
                    const month = index + 1;
                    const key = `${year}-${String(month).padStart(2, '0')}`;
                    return monthByKey.get(key) || { key, year, month, value: 0, rate: 0, days: 0, wins: 0, losses: 0, empty: true };
                  }));
              }

              function tileIntensity(value, maxAbs) {
                if (!Number.isFinite(value) || !value || !maxAbs) return '0.56';
                return Math.min(1, Math.max(0.62, Math.abs(value) / maxAbs * 0.42 + 0.58)).toFixed(2);
              }

              function ensureSelectedMonth(items, activeMonths) {
                const activeKeys = new Set(items.map((item) => item.key));
                if (selectedMonthKey && activeKeys.has(selectedMonthKey)) return;
                const latestActiveMonth = activeMonths[activeMonths.length - 1];
                selectedMonthKey = latestActiveMonth?.key || items.find((item) => !item.empty)?.key || items[items.length - 1]?.key || '';
              }

              function monthLabel(monthKey) {
                const [year, month] = String(monthKey || '').split('-');
                if (!year || !month) return '所选月份';
                return `${year}年${Number(month)}月`;
              }

              function setYearButtonStates() {
                if (!yearControls) return;
                yearControls.querySelectorAll('[data-report-year]').forEach((button) => {
                  const year = button.dataset.reportYear;
                  const active = year === 'all' ? selectedYears.size === years.length : selectedYears.has(year);
                  button.classList.toggle('is-active', active);
                  button.setAttribute('aria-pressed', active ? 'true' : 'false');
                });
              }

              function renderCalendarChart(items) {
                if (!calendarChart) return;
                if (!items.length) {
                  calendarChart.innerHTML = '<text x="360" y="100" text-anchor="middle" class="performance-chart-empty">暂无数据</text>';
                  return;
                }
                const width = 720;
                const height = 200;
                const left = 58;
                const right = 26;
                const top = 20;
                const bottom = 42;
                const innerWidth = width - left - right;
                const innerHeight = height - top - bottom;
                const positiveMax = Math.max(0, ...items.map((item) => Math.max(0, metricValue(item))));
                const negativeMax = Math.max(0, ...items.map((item) => Math.max(0, -metricValue(item))));
                const hasPositive = positiveMax > 0;
                const hasNegative = negativeMax > 0;
                let positiveHeight = 0;
                let negativeHeight = 0;
                let zeroY = top + innerHeight / 2;
                if (hasPositive && hasNegative) {
                  const availableHeight = innerHeight - 10;
                  const rawShare = positiveMax / (positiveMax + negativeMax);
                  const positiveShare = Math.min(0.7, Math.max(0.3, rawShare));
                  positiveHeight = availableHeight * positiveShare;
                  negativeHeight = availableHeight - positiveHeight;
                  zeroY = top + 5 + positiveHeight;
                } else if (hasPositive) {
                  positiveHeight = innerHeight - 12;
                  zeroY = top + positiveHeight + 4;
                } else if (hasNegative) {
                  negativeHeight = innerHeight - 12;
                  zeroY = top + 4;
                } else {
                  positiveHeight = innerHeight / 2 - 8;
                  negativeHeight = innerHeight / 2 - 8;
                }
                const positiveScale = hasPositive ? positiveHeight / positiveMax : 0;
                const negativeScale = hasNegative ? negativeHeight / negativeMax : 0;
                const step = innerWidth / Math.max(items.length, 1);
                const barWidth = Math.max(4, Math.min(22, step * 0.58));
                const labelEvery = Math.max(1, Math.ceil(items.length / 6));
                const gridMarks = [];
                if (hasPositive) {
                  gridMarks.push({ value: positiveMax, y: zeroY - positiveHeight, label: true });
                  if (positiveHeight >= 44) gridMarks.push({ value: positiveMax / 2, y: zeroY - positiveHeight / 2, label: false });
                }
                if (hasNegative) {
                  if (negativeHeight >= 44) gridMarks.push({ value: -negativeMax / 2, y: zeroY + negativeHeight / 2, label: false });
                  gridMarks.push({ value: -negativeMax, y: zeroY + negativeHeight, label: true });
                }
                const gridLines = gridMarks.map((mark) =>
                  `<line class="performance-chart-grid" x1="${left}" y1="${mark.y.toFixed(1)}" x2="${width - right}" y2="${mark.y.toFixed(1)}"></line>`
                ).join('');
                const yLabels = gridMarks.filter((mark) => mark.label).map((mark) =>
                  `<text class="performance-chart-y" x="${left - 8}" y="${mark.y.toFixed(1)}" text-anchor="end">${formatMetric(mark.value, true)}</text>`
                ).join('');
                const bars = items.map((item, index) => {
                  const value = metricValue(item);
                  const rawHeight = value >= 0 ? value * positiveScale : Math.abs(value) * negativeScale;
                  const barLimit = value >= 0 ? positiveHeight : negativeHeight;
                  const barHeight = value === 0 ? 1 : Math.min(barLimit, Math.max(2, rawHeight));
                  const x = left + index * step + (step - barWidth) / 2;
                  const y = value >= 0 ? zeroY - barHeight : zeroY;
                  const tone = value >= 0 ? 'positive' : 'negative';
                  const radius = Math.min(5, barWidth / 2);
                  const selected = item.key === selectedMonthKey ? ' is-selected' : '';
                  const label = index % labelEvery === 0 || index === items.length - 1
                    ? `<text class="performance-chart-x" x="${(x + barWidth / 2).toFixed(1)}" y="${height - 14}" text-anchor="middle">${String(item.year).slice(2)}/${String(item.month).padStart(2, '0')}</text>`
                    : '';
                  return `
                    <rect class="performance-chart-bar performance-chart-bar-${tone}${selected}" data-report-month="${item.key}" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" rx="${radius.toFixed(1)}" ry="${radius.toFixed(1)}">
                      <title>${item.year}年${item.month}月 ${formatMetric(value)}</title>
                    </rect>
                    ${label}
                  `;
                }).join('');
                calendarChart.innerHTML = `
                  ${gridLines}
                  <line class="performance-chart-axis" x1="${left}" y1="${zeroY.toFixed(1)}" x2="${width - right}" y2="${zeroY.toFixed(1)}"></line>
                  ${yLabels}
                  ${bars}
                `;
              }

              function renderCalendar() {
                const activeMonths = visibleMonths();
                const items = calendarMonthsForSelectedYears();
                ensureSelectedMonth(items, activeMonths);
                renderCalendarChart(items);
                if (calendar) {
                  const maxAbs = Math.max(1, ...items.map((item) => Math.abs(metricValue(item))));
                  const byYear = new Map();
                  items.forEach((item) => {
                    const bucket = byYear.get(item.year) || [];
                    bucket.push(item);
                    byYear.set(item.year, bucket);
                  });
                  calendar.innerHTML = Array.from(byYear.entries()).map(([year, yearMonths]) => {
                    const yearTotal = metricTotal(yearMonths);
                    const monthTiles = yearMonths.map((item) => {
                      const value = metricValue(item);
                      const tone = value > 0 ? 'positive' : value < 0 ? 'negative' : 'zero';
                      const tradeLabel = item.days ? `${item.days}个交易日` : '无波动';
                      const selected = item.key === selectedMonthKey ? ' is-selected' : '';
                      return `<button type="button" class="performance-month performance-month-${tone}${selected}" data-report-month="${item.key}" aria-pressed="${item.key === selectedMonthKey ? 'true' : 'false'}" style="--tile-alpha:${tileIntensity(value, maxAbs)}"><span>${item.month}月</span><strong>${formatMetric(value, true)}</strong><small>${tradeLabel}</small></button>`;
                    }).join('');
                    return `
                      <div class="performance-year-group">
                        <div class="performance-year-head"><strong>${year}年</strong><span>${formatMetric(yearTotal)}</span></div>
                        <div class="performance-calendar-grid">${monthTiles}</div>
                      </div>
                    `;
                  }).join('');
                }
                if (totalNode) totalNode.textContent = `合计 ${formatMetric(metricTotal(activeMonths))}`;
                if (monthCountNode) monthCountNode.textContent = String(activeMonths.length);
                if (winCountNode) winCountNode.textContent = String(activeMonths.filter((item) => metricValue(item) > 0).length);
                if (lossCountNode) lossCountNode.textContent = String(activeMonths.filter((item) => metricValue(item) < 0).length);
                setYearButtonStates();
                renderStockPanel();
              }

              if (yearControls) {
                yearControls.innerHTML = [
                  '<button type="button" class="performance-year-button is-active" data-report-year="all" aria-pressed="true">全部</button>',
                  ...years.map((year) => `<button type="button" class="performance-year-button is-active" data-report-year="${year}" aria-pressed="true">${year}年</button>`),
                ].join('');
                yearControls.addEventListener('click', (event) => {
                  const button = event.target?.closest?.('[data-report-year]');
                  if (!button || !yearControls.contains(button)) return;
                  const year = button.dataset.reportYear;
                  if (year === 'all') {
                    selectedYears.clear();
                    years.forEach((item) => selectedYears.add(item));
                  } else {
                    const allSelected = selectedYears.size === years.length;
                    if (allSelected) {
                      selectedYears.clear();
                      selectedYears.add(year);
                    } else if (selectedYears.has(year) && selectedYears.size > 1) {
                      selectedYears.delete(year);
                    } else if (!selectedYears.has(year)) {
                      selectedYears.add(year);
                    }
                  }
                  renderCalendar();
                });
              }
              if (calendar) {
                calendar.addEventListener('click', (event) => {
                  const button = event.target?.closest?.('[data-report-month]');
                  if (!button || !calendar.contains(button)) return;
                  selectedMonthKey = button.dataset.reportMonth || selectedMonthKey;
                  renderCalendar();
                });
              }
              if (calendarChart) {
                calendarChart.addEventListener('click', (event) => {
                  const bar = event.target?.closest?.('[data-report-month]');
                  if (!bar || !calendarChart.contains(bar)) return;
                  selectedMonthKey = bar.dataset.reportMonth || selectedMonthKey;
                  renderCalendar();
                });
              }

              function stockItemsFromRealizedMonth(monthKey) {
                const buckets = new Map();
                realizedTrades.forEach((trade) => {
                  if (!trade || trade.month !== monthKey || trade.category !== '股票') return;
                  const code = String(trade.code || '').trim();
                  if (!code) return;
                  const currency = String(trade.currency || '').trim();
                  const name = String(trade.name || code).trim() || code;
                  const pnl = number(trade.pnl);
                  if (!Number.isFinite(pnl)) return;
                  const rate = rateToCnyForCurrency(currency);
                  const key = `${code}|${currency}`;
                  const item = buckets.get(key) || { code, name, currency, pnl: 0, capital: 0, count: 0 };
                  item.pnl += pnl * rate;
                  item.capital += Math.abs((number(trade.capital) || 0) * rate);
                  item.count += 1;
                  buckets.set(key, item);
                });
                return Array.from(buckets.values()).map((item) => ({
                  ...item,
                  rate: item.capital > 0 ? (item.pnl / item.capital) * 100 : NaN,
                })).sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl));
              }

              function stockItemsForMonth(monthKey) {
                const items = Array.isArray(stockPerformanceMonths?.[monthKey]) ? stockPerformanceMonths[monthKey] : [];
                if (items.length) {
                  return items
                    .map((item) => ({
                      code: String(item.code || '').trim(),
                      name: String(item.name || item.code || '').trim(),
                      currency: String(item.currency || '').trim(),
                      sourceCurrency: String(item.sourceCurrency || item.currency || '').trim(),
                      pnl: number(item.pnl),
                      nativePnl: number(item.nativePnl),
                      capital: number(item.capital),
                      rate: number(item.rate),
                    }))
                    .filter((item) => item.code && Number.isFinite(item.pnl))
                    .sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl));
                }
                return stockItemsFromRealizedMonth(monthKey);
              }

              function stockItemsFromAnnualTable() {
                const table = document.querySelector('table[data-summary-kind="annual"]');
                if (!table) return [];
                const labels = Array.from(table.querySelectorAll('thead th')).map((node) => node.textContent.trim());
                const codeIndex = labels.indexOf('代码');
                const nameIndex = labels.indexOf('名称');
                const currencyIndex = labels.indexOf('币种');
                if (codeIndex < 0 || nameIndex < 0) return [];
                const buckets = new Map();
                table.querySelectorAll('tbody tr[data-total-pnl]').forEach((row) => {
                  if ((row.dataset.year || '') !== 'total') return;
                  const cells = Array.from(row.children);
                  const code = (cells[codeIndex]?.textContent || '').trim();
                  const name = (cells[nameIndex]?.textContent || code).trim() || code;
                  const currency = (cells[currencyIndex]?.textContent || '').trim();
                  const pnl = number(row.dataset.totalPnl);
                  if (!code || code === '汇总' || !Number.isFinite(pnl)) return;
                  const rate = rateToCnyForCurrency(currency);
                  const key = `${code}|${currency}`;
                  const item = buckets.get(key) || { code, name, currency, pnl: 0, rate: NaN };
                  item.pnl += pnl * rate;
                  buckets.set(key, item);
                });
                return Array.from(buckets.values()).sort((a, b) => Math.abs(b.pnl) - Math.abs(a.pnl));
              }

              function stockMetricValue(item) {
                if (reportMode === 'rate') {
                  const rate = number(item?.rate);
                  if (Number.isFinite(rate)) return rate;
                }
                return number(item?.pnl) || 0;
              }

              function stockMetricText(item) {
                if (reportMode === 'rate' && Number.isFinite(number(item?.rate))) return percent(number(item.rate));
                return signedMoney(number(item?.pnl) || 0);
              }

              function renderRank(title, items, tone) {
                const rows = items.length ? items.map((item, index) => `
                  <li>
                    <span>${index + 1}</span>
                    <strong>${escapeHtml(item.name || item.code)}</strong>
                    <em class="value-${tone}">${stockMetricText(item)}</em>
                  </li>
                `).join('') : '<li class="performance-stock-empty">暂无数据</li>';
                return `<div class="performance-stock-rank performance-stock-rank-${tone}"><h4>${title}</h4><ol>${rows}</ol></div>`;
              }

              function stockTreemapLayout(items) {
                const nodes = items
                  .map((item) => ({ item, absPnl: Math.abs(stockMetricValue(item)) }))
                  .filter((node) => node.absPnl > 0);
                const rects = [];
                function total(list) {
                  return list.reduce((amount, node) => amount + node.absPnl, 0);
                }
                function split(list, x, y, width, height) {
                  if (!list.length || width <= 0 || height <= 0) return;
                  if (list.length === 1) {
                    rects.push({ item: list[0].item, x, y, width, height });
                    return;
                  }
                  const all = total(list);
                  if (all <= 0) return;
                  let splitAt = 1;
                  let running = 0;
                  let bestDiff = Infinity;
                  for (let index = 1; index < list.length; index += 1) {
                    running += list[index - 1].absPnl;
                    const diff = Math.abs(all / 2 - running);
                    if (diff < bestDiff) {
                      bestDiff = diff;
                      splitAt = index;
                    }
                  }
                  const first = list.slice(0, splitAt);
                  const second = list.slice(splitAt);
                  const firstTotal = total(first);
                  const firstRatio = firstTotal / all;
                  if (width >= height) {
                    const firstWidth = width * firstRatio;
                    split(first, x, y, firstWidth, height);
                    split(second, x + firstWidth, y, width - firstWidth, height);
                  } else {
                    const firstHeight = height * firstRatio;
                    split(first, x, y, width, firstHeight);
                    split(second, x, y + firstHeight, width, height - firstHeight);
                  }
                }
                split(nodes, 0, 0, 100, 100);
                return rects;
              }

              function renderStockPanel() {
                const stocks = selectedMonthKey ? stockItemsForMonth(selectedMonthKey) : stockItemsFromAnnualTable();
                const contextLabel = selectedMonthKey ? monthLabel(selectedMonthKey) : '全部';
                const treemap = section.querySelector('[data-report-treemap]');
                const stockList = section.querySelector('[data-report-stock-list]');
                const countNode = section.querySelector('[data-report-stock-count]');
                if (treemap) {
                  if (!stocks.length) {
                    treemap.innerHTML = `<div class="performance-empty">${escapeHtml(contextLabel)}暂无个股盈亏。</div>`;
                  } else {
                    const topStocks = stocks.filter((item) => Math.abs(stockMetricValue(item)) > 0).sort((a, b) => Math.abs(stockMetricValue(b)) - Math.abs(stockMetricValue(a))).slice(0, 18);
                    const rects = stockTreemapLayout(topStocks);
                    treemap.innerHTML = rects.length ? rects.map((rect) => {
                      const item = rect.item;
                      const value = stockMetricValue(item);
                      const tone = value >= 0 ? 'positive' : 'negative';
                      const title = item.name.length > 10 ? item.name.slice(0, 10) + '...' : item.name;
                      const currencyLabel = reportMode === 'rate' ? '收益率' : (item.currency ? `${item.currency}折${reportingCurrency()}` : `折${reportingCurrency()}`);
                      const compactClass = rect.width < 14 || rect.height < 16 ? ' is-compact' : rect.width < 22 || rect.height < 20 ? ' is-small' : '';
                      const fullTitle = `${item.name || item.code} ${stockMetricText(item)}`;
                      const style = `left:${rect.x.toFixed(2)}%;top:${rect.y.toFixed(2)}%;width:${rect.width.toFixed(2)}%;height:${rect.height.toFixed(2)}%;`;
                      return `<div class="performance-stock-tile performance-stock-${tone}${compactClass}" title="${escapeHtml(fullTitle)}" style="${style}"><span>${escapeHtml(title)}</span><strong>${stockMetricText(item)}</strong><small>${escapeHtml(currencyLabel)}</small></div>`;
                    }).join('') : `<div class="performance-empty">${escapeHtml(contextLabel)}暂无有效个股盈亏。</div>`;
                  }
                }
                if (stockList) {
                  const winners = stocks.filter((item) => stockMetricValue(item) > 0).sort((a, b) => stockMetricValue(b) - stockMetricValue(a)).slice(0, 6);
                  const losers = stocks.filter((item) => stockMetricValue(item) < 0).sort((a, b) => stockMetricValue(a) - stockMetricValue(b)).slice(0, 6);
                  stockList.innerHTML = renderRank('盈利榜', winners, 'positive') + renderRank('亏损榜', losers, 'negative');
                }
                if (countNode) {
                  const wins = stocks.filter((item) => stockMetricValue(item) > 0).length;
                  const losses = stocks.filter((item) => stockMetricValue(item) < 0).length;
                  countNode.innerHTML = `${escapeHtml(contextLabel)} · 盈利个股 <em>${wins}</em> ：亏损个股 <em>${losses}</em> · ${metricLabel()}`;
                }
              }

              function updateModeButtons() {
                if (!modeControl) return;
                modeControl.querySelectorAll('[data-report-mode]').forEach((button) => {
                  const active = button.dataset.reportMode === reportMode;
                  button.classList.toggle('is-active', active);
                  button.setAttribute('aria-pressed', active ? 'true' : 'false');
                });
              }

              function renderAllPerformance() {
                renderSwingCards();
                renderCompare();
                renderCalendar();
              }
              window.addEventListener('trade-tracker-reporting-currency-change', renderAllPerformance);

              if (modeControl) {
                modeControl.addEventListener('click', (event) => {
                  const button = event.target?.closest?.('[data-report-mode]');
                  if (!button || !modeControl.contains(button)) return;
                  const nextMode = button.dataset.reportMode === 'rate' ? 'rate' : 'amount';
                  if (nextMode === reportMode) return;
                  reportMode = nextMode;
                  updateModeButtons();
                  renderAllPerformance();
                });
                updateModeButtons();
              }
              renderAllPerformance();
            })();
            </script>
          </div>
        </details>
'''
    return template.replace("__STOCK_PAYLOAD__", stock_payload)


def insert_performance_report_section(html_text: str) -> str:
    if "data-performance-report" in html_text:
        return html_text
    match = re.search(r'<details\b(?=[^>]*\bdata-ths-return-curve\b)[^>]*>.*?</details>', html_text, re.S)
    if not match:
        return html_text
    return html_text[: match.end()] + "\n" + render_performance_report_section() + html_text[match.end() :]
