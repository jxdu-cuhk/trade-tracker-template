from __future__ import annotations

import html
import calendar
import re
from datetime import date, timedelta

from .historical_curve import build_stock_lots, close_for_day, fetch_histories_for_lots, unrealized_pnl
from .html_tables import body_rows, cell_text, money_for_label, summary_table_match, table_labels, text_for_label
from .market_data import current_fx_rates_to_cny, display_currency_label
from .realized_analysis import build_realized_trades
from .utils import clean_text


def tone_class(value: float | None) -> str:
    if value is None:
        return "value-zero"
    if value > 0:
        return "value-positive"
    if value < 0:
        return "value-negative"
    return "value-zero"


def format_money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}"


def format_signed_money(value: float | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:,.2f}"


def format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    sign = "+" if value > 0 else ""
    return f"{sign}{value * 100:.2f}%"


def cny_value(core, labels: list[str], cells: list[str], label: str, rates: dict[str, float], absolute: bool = False) -> float | None:
    currency, value = money_for_label(labels, cells, label)
    if value is None:
        return None
    if not currency:
        currency = text_for_label(labels, cells, "币种")
    try:
        currency = display_currency_label(core, core.normalize_currency(currency))
    except Exception:
        currency = clean_text(currency)
    converted = value * rates.get(currency, 1.0)
    return abs(converted) if absolute else converted


def holdings_metrics_from_table(core, table_html: str) -> dict[str, float]:
    labels = table_labels(table_html)
    if not labels:
        return {}
    rates = current_fx_rates_to_cny()
    totals = {
        "asset": 0.0,
        "market_value": 0.0,
        "cost": 0.0,
        "float_pnl": 0.0,
        "daily_pnl": 0.0,
    }
    count = 0
    for _prefix, _body, _suffix, cells in body_rows(table_html):
        if len(cells) != len(labels):
            continue
        count += 1
        asset = cny_value(core, labels, cells, "最新市值", rates)
        market_value = cny_value(core, labels, cells, "最新市值", rates, absolute=True)
        cost = cny_value(core, labels, cells, "持仓成本", rates, absolute=True)
        float_pnl = cny_value(core, labels, cells, "浮动盈亏", rates)
        daily_pnl = cny_value(core, labels, cells, "当日盈亏", rates)
        if asset is not None:
            totals["asset"] += asset
        if market_value is not None:
            totals["market_value"] += market_value
        if cost is not None:
            totals["cost"] += cost
        if float_pnl is not None:
            totals["float_pnl"] += float_pnl
        if daily_pnl is not None:
            totals["daily_pnl"] += daily_pnl
    totals["count"] = float(count)
    return totals


def shift_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year = day.year + month_index // 12
    month = month_index % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day.day, last_day))


def summarize_realized_range(
    trades,
    rates: dict[str, float],
    start: date,
    end: date,
    label: str,
) -> dict[str, object]:
    pnl = 0.0
    capital = 0.0
    by_day: dict[date, float] = {}
    for trade in trades:
        if trade.close_date < start or trade.close_date > end:
            continue
        rate = rates.get(trade.currency, 1.0)
        cny_pnl = trade.pnl * rate
        pnl += cny_pnl
        if trade.capital is not None:
            capital += abs(trade.capital * rate)
        by_day[trade.close_date] = by_day.get(trade.close_date, 0.0) + cny_pnl
    cumulative = []
    running = 0.0
    if by_day:
        cumulative.append((start, 0.0))
    for day in sorted(by_day):
        running += by_day[day]
        cumulative.append((day, running))
    if cumulative and cumulative[-1][0] < end:
        cumulative.append((end, running))
    return {
        "label": label,
        "pnl": pnl,
        "capital": capital,
        "rate": pnl / capital if capital else None,
        "points": cumulative,
    }


def realized_range_metrics(core, rows: list[tuple[int, dict[int, object]]]) -> dict[str, object]:
    today = date.today()
    rates = current_fx_rates_to_cny()
    trades = build_realized_trades(core, rows)
    ranges = {
        "month": summarize_realized_range(
            trades,
            rates,
            date(today.year, today.month, 1),
            today,
            f"{today.month}月已实现盈亏",
        ),
        "three-month": summarize_realized_range(
            trades,
            rates,
            shift_months(today, -3),
            today,
            "近三月已实现盈亏",
        ),
        "year": summarize_realized_range(
            trades,
            rates,
            date(today.year, 1, 1),
            today,
            "本年已实现盈亏",
        ),
    }
    return {"active": "month", "ranges": ranges}


def monthly_realized_metrics(core, rows: list[tuple[int, dict[int, object]]]) -> dict[str, object]:
    return dict(realized_range_metrics(core, rows).get("ranges", {}).get("month", {}))


def active_reference_lots(core, rows: list[tuple[int, dict[int, object]]]):
    return [lot for lot in build_stock_lots(core, rows) if lot.close_date is None]


def reference_total_for_day(day: date, lots, histories, rates: dict[str, float], live_total: float | None = None) -> float:
    if live_total is not None and day >= date.today():
        return float(live_total)
    total = 0.0
    for lot in lots:
        if day < lot.open_date:
            continue
        price = close_for_day(histories.get((lot.ticker, lot.currency), {}), day)
        if price is None:
            price = lot.open_price
        total += unrealized_pnl(lot, price) * rates.get(lot.currency, 1.0)
    return total


def reference_capital_for_day(day: date, lots, rates: dict[str, float], fallback: float | None = None) -> float:
    total = sum(lot.capital * rates.get(lot.currency, 1.0) for lot in lots if lot.open_date <= day)
    return total if total > 0.000001 else float(fallback or 0.0)


def summarize_reference_range(
    key: str,
    label: str,
    start: date,
    end: date,
    lots,
    histories,
    rates: dict[str, float],
    live_total: float | None,
    fallback_capital: float | None,
) -> dict[str, object]:
    day_set = {start, end}
    for lot in lots:
        if lot.open_date > end:
            continue
        if lot.open_date >= start:
            day_set.add(lot.open_date)
        for history_day in histories.get((lot.ticker, lot.currency), {}):
            if start <= history_day <= end and history_day >= lot.open_date:
                day_set.add(history_day)

    baseline = reference_total_for_day(start, lots, histories, rates, live_total if start >= end else None)
    points = []
    for day in sorted(day_set):
        total = reference_total_for_day(day, lots, histories, rates, live_total if day >= end else None)
        points.append((day, total - baseline))
    pnl = points[-1][1] if points else 0.0
    capital = reference_capital_for_day(end, lots, rates, fallback_capital)
    return {
        "key": key,
        "label": label,
        "pnl": pnl,
        "capital": capital,
        "rate": pnl / capital if capital else None,
        "points": points,
    }


def reference_float_metrics(core, rows: list[tuple[int, dict[int, object]]], metrics: dict[str, float]) -> dict[str, object]:
    today = date.today()
    daily_pnl = metrics.get("daily_pnl")
    asset = metrics.get("asset")
    cost = metrics.get("cost")
    daily_base = abs(asset - daily_pnl) if asset is not None and daily_pnl is not None else None
    ranges = {
        "day": {
            "label": "当日参考盈亏",
            "pnl": daily_pnl or 0.0,
            "capital": daily_base or cost or 0.0,
            "rate": daily_pnl / daily_base if daily_base else None,
            "points": [(today - timedelta(days=1), 0.0), (today, float(daily_pnl or 0.0))] if daily_pnl is not None else [],
        }
    }
    if core is None:
        return {"active": "day", "ranges": ranges}

    lots = active_reference_lots(core, rows)
    if lots:
        rates = current_fx_rates_to_cny()
        histories = fetch_histories_for_lots(core, lots)
        for key, label, start in [
            ("month", f"{today.month}月参考盈亏", date(today.year, today.month, 1)),
            ("three-month", "近三月参考盈亏", shift_months(today, -3)),
            ("year", "本年参考盈亏", date(today.year, 1, 1)),
        ]:
            ranges[key] = summarize_reference_range(
                key,
                label,
                start,
                today,
                lots,
                histories,
                rates,
                metrics.get("float_pnl"),
                cost,
            )
    return {"active": "day", "ranges": ranges}


def render_metric(label: str, value: str, value_class: str = "", detail: str = "") -> str:
    class_attr = f"holdings-account-value {value_class}".strip()
    detail_html = f'<span>{html.escape(detail)}</span>' if detail else ""
    return (
        '<div class="holdings-account-metric">'
        f'<span class="holdings-account-label">{html.escape(label)}</span>'
        f'<strong class="{html.escape(class_attr)}">{html.escape(value)}</strong>'
        f"{detail_html}"
        "</div>"
    )


def render_month_sparkline(points: list[tuple[date, float]]) -> str:
    width, height = 150, 38
    left, top, right, bottom = 5, 5, 8, 8
    inner_width = width - left - right
    inner_height = height - top - bottom
    if not points:
        return (
            f'<svg class="holdings-month-sparkline" viewBox="0 0 {width} {height}" aria-hidden="true">'
            f'<line class="holdings-sparkline-axis" x1="{left}" y1="{height - bottom}" x2="{width - right}" y2="{height - bottom}"></line>'
            "</svg>"
        )

    ordinals = [point[0].toordinal() for point in points]
    values = [point[1] for point in points]
    min_x, max_x = min(ordinals), max(ordinals)
    min_y, max_y = min(0.0, min(values)), max(0.0, max(values))
    if max_x == min_x:
        max_x = min_x + 1
    if abs(max_y - min_y) < 0.000001:
        max_y = min_y + 1.0
    padding = max((max_y - min_y) * 0.08, 1.0)
    min_y -= padding
    max_y += padding

    def x_for(day: date) -> float:
        return left + ((day.toordinal() - min_x) / (max_x - min_x)) * inner_width

    def y_for(value: float) -> float:
        return top + ((max_y - value) / (max_y - min_y)) * inner_height

    positions = [(x_for(day), y_for(value), value) for day, value in points]
    path = " ".join(f"{'L' if index else 'M'} {x:.2f} {y:.2f}" for index, (x, y, _value) in enumerate(positions))
    zero_y = y_for(0.0)
    last_x, last_y, last_value = positions[-1]
    tone = "positive" if last_value >= 0 else "negative"
    area_path = f"{path} L {last_x:.2f} {zero_y:.2f} L {positions[0][0]:.2f} {zero_y:.2f} Z"
    return (
        f'<svg class="holdings-month-sparkline holdings-month-sparkline-{tone}" viewBox="0 0 {width} {height}" aria-hidden="true">'
        f'<line class="holdings-sparkline-axis" x1="{left}" y1="{zero_y:.2f}" x2="{width - right}" y2="{zero_y:.2f}"></line>'
        f'<path class="holdings-sparkline-area" d="{area_path}"></path>'
        f'<path class="holdings-sparkline-line" d="{path}"></path>'
        f'<circle class="holdings-sparkline-dot" cx="{last_x:.2f}" cy="{last_y:.2f}" r="3.8"></circle>'
        "</svg>"
    )


def render_holdings_realized_panel(key: str, data: dict[str, object], active: bool = False) -> str:
    pnl = float(data.get("pnl") or 0.0)
    rate = data.get("rate") if isinstance(data.get("rate"), (int, float)) else None
    points = list(data.get("points") or [])
    label = str(data.get("label") or "已实现盈亏")
    active_class = " is-active" if active else ""
    return (
        f'<div class="holdings-realized-range{active_class}" data-holdings-range-panel="{html.escape(key)}">'
        '<div class="holdings-realized-text">'
        f'<span class="holdings-account-label">{html.escape(label)}</span>'
        f'<strong class="holdings-account-value {html.escape(tone_class(pnl))}">{html.escape(format_signed_money(pnl))}</strong>'
        f'<span>{html.escape(format_percent(rate))}</span>'
        "</div>"
        f"{render_month_sparkline(points)}"
        "</div>"
    )


def render_holdings_realized_metric(month: dict[str, object]) -> str:
    ranges = month.get("ranges") if isinstance(month, dict) else None
    if not isinstance(ranges, dict):
        month = {
            "active": "month",
            "ranges": {
                "month": {
                    "label": f"{int(month.get('month') or date.today().month)}月已实现盈亏",
                    "pnl": month.get("pnl"),
                    "capital": month.get("capital"),
                    "rate": month.get("rate"),
                    "points": month.get("points"),
                }
            },
        }
        ranges = month["ranges"]

    active = str(month.get("active") or "month")
    labels = [("month", "本月"), ("three-month", "近三月"), ("year", "本年")]
    buttons = "".join(
        f'<button type="button" class="holdings-range-tab{" is-active" if key == active else ""}" data-holdings-range="{html.escape(key)}">{html.escape(label)}</button>'
        for key, label in labels
        if key in ranges
    )
    panels = "".join(
        render_holdings_realized_panel(key, ranges[key], key == active)
        for key, _label in labels
        if key in ranges
    )
    return (
        '<div class="holdings-account-metric holdings-month-metric" data-holdings-range-card>'
        '<div class="holdings-realized-head">'
        '<span class="holdings-month-label">已实现</span>'
        f'<div class="holdings-range-tabs" aria-label="选择已实现盈亏区间">{buttons}</div>'
        "</div>"
        f"{panels}"
        "</div>"
    )


def render_reference_panel(key: str, data: dict[str, object], active: bool = False) -> str:
    pnl = float(data.get("pnl") or 0.0)
    rate = data.get("rate") if isinstance(data.get("rate"), (int, float)) else None
    points = list(data.get("points") or [])
    label = str(data.get("label") or "参考盈亏")
    active_class = " is-active" if active else ""
    return (
        f'<div class="holdings-realized-range{active_class}" data-holdings-range-panel="{html.escape(key)}">'
        '<div class="holdings-realized-text">'
        f'<span class="holdings-account-label">{html.escape(label)}</span>'
        f'<strong class="holdings-account-value {html.escape(tone_class(pnl))}">{html.escape(format_signed_money(pnl))}</strong>'
        f'<span>{html.escape(format_percent(rate))}</span>'
        "</div>"
        f"{render_month_sparkline(points)}"
        "</div>"
    )


def render_reference_metric(reference: dict[str, object]) -> str:
    ranges = reference.get("ranges") if isinstance(reference, dict) else None
    if not isinstance(ranges, dict):
        ranges = {}
    active = str(reference.get("active") or "day") if isinstance(reference, dict) else "day"
    labels = [("day", "当日"), ("month", "本月"), ("three-month", "近三月"), ("year", "本年")]
    buttons = "".join(
        f'<button type="button" class="holdings-range-tab{" is-active" if key == active else ""}" data-holdings-range="{html.escape(key)}">{html.escape(label)}</button>'
        for key, label in labels
        if key in ranges
    )
    panels = "".join(
        render_reference_panel(key, ranges[key], key == active)
        for key, _label in labels
        if key in ranges
    )
    return (
        '<div class="holdings-account-metric holdings-month-metric" data-holdings-reference-card data-holdings-range-card>'
        '<div class="holdings-realized-head">'
        '<span class="holdings-month-label">参考</span>'
        f'<div class="holdings-range-tabs" aria-label="选择参考盈亏区间">{buttons}</div>'
        '</div>'
        f"{panels}"
        "</div>"
    )


def render_holdings_range_script() -> str:
    return """
            <script>
            (function setupHoldingsRangeTabs() {
              document.querySelectorAll('[data-holdings-range-card]').forEach((card) => {
                if (card.dataset.rangeReady === '1') return;
                card.dataset.rangeReady = '1';
                const buttons = Array.from(card.querySelectorAll('[data-holdings-range]'));
                const panels = Array.from(card.querySelectorAll('[data-holdings-range-panel]'));
                function activate(range) {
                  buttons.forEach((button) => button.classList.toggle('is-active', button.dataset.holdingsRange === range));
                  panels.forEach((panel) => panel.classList.toggle('is-active', panel.dataset.holdingsRangePanel === range));
                }
                buttons.forEach((button) => {
                  button.addEventListener('click', () => activate(button.dataset.holdingsRange || 'month'));
                });
              });
            })();
            </script>
"""


def render_holdings_account_panel(metrics: dict[str, float], month: dict[str, object], reference: dict[str, object] | None = None) -> str:
    if not metrics or not int(metrics.get("count", 0)):
        return ""
    asset = metrics.get("asset")
    market_value = metrics.get("market_value")
    cost = metrics.get("cost")
    float_pnl = metrics.get("float_pnl")
    float_rate = float_pnl / cost if cost else None
    month_metric = render_holdings_realized_metric(month)
    reference_metric = render_reference_metric(reference or reference_float_metrics(None, [], metrics))

    return f"""
            <div class="holdings-account-panel">
              <div class="holdings-account-grid">
                {render_metric("持仓总资产", format_money(asset), "", "折人民币，不含现金")}
                {render_metric("总盈亏", format_signed_money(float_pnl), tone_class(float_pnl), format_percent(float_rate))}
                {render_metric("总市值", format_money(market_value), "", "按仓位绝对值")}
                {reference_metric}
                {month_metric}
              </div>
            </div>
            {render_holdings_range_script()}
"""


def insert_holdings_account_overview(core, html_text: str, rows: list[tuple[int, dict[int, object]]]) -> str:
    if "holdings-account-panel" in html_text:
        return html_text
    table_match = summary_table_match(html_text, "holdings")
    if not table_match:
        return html_text
    title_index = html_text.find('<h2 class="section-title">当前持仓</h2>')
    if title_index < 0:
        return html_text
    insertion_index = html_text.find('<div class="summary-wrap">', title_index)
    if insertion_index < 0 or insertion_index > table_match.start():
        return html_text
    metrics = holdings_metrics_from_table(core, table_match.group(0))
    month = realized_range_metrics(core, rows)
    reference = reference_float_metrics(core, rows, metrics)
    panel = render_holdings_account_panel(metrics, month, reference)
    if not panel:
        return html_text
    return html_text[:insertion_index] + panel + html_text[insertion_index:]
