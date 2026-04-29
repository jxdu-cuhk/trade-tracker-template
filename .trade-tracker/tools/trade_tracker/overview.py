from __future__ import annotations

import html
import re

from .market_data import current_fx_rates_to_cny
from .settings import OVERVIEW_CURRENCIES, OVERVIEW_CURRENCY_METRIC_ORDER, OVERVIEW_HIDDEN_METRICS, OVERVIEW_METRIC_CLASSES, OVERVIEW_METRIC_ORDER
from .utils import cell_text


def move_dividend_metric_later(html: str) -> str:
    card_pattern = re.compile(
        r"\n\s*<div class=\"metric-card\">\s*"
        r"<div class=\"metric-label\">分红净额</div>\s*"
        r"<div class=\"metric-value[^\"]*\">.*?</div>\s*"
        r"<div class=\"metric-note\">.*?</div>\s*"
        r"</div>",
        re.S,
    )
    card_match = card_pattern.search(html)
    if not card_match:
        return html

    dividend_card = card_match.group(0)
    without_card = html[: card_match.start()] + html[card_match.end() :]
    anchor_pattern = re.compile(
        r"\n\s*<div class=\"metric-card\">\s*"
        r"<div class=\"metric-label\">综合年化</div>\s*"
        r"<div class=\"metric-value[^\"]*\">.*?</div>\s*"
        r"<div class=\"metric-note\">.*?</div>\s*"
        r"</div>",
        re.S,
    )
    anchor_match = anchor_pattern.search(without_card)
    if not anchor_match:
        return html
    return without_card[: anchor_match.end()] + dividend_card + without_card[anchor_match.end() :]


def find_matching_div_bounds(html_text: str, start_index: int) -> tuple[int, int] | None:
    depth = 1
    for match in re.finditer(r"</?div\b[^>]*>", html_text[start_index:], re.I):
        tag = match.group(0)
        depth += -1 if tag.startswith("</") else 1
        if depth == 0:
            return start_index + match.start(), start_index + match.end()
    return None


def optimize_overview_metrics(html_text: str) -> str:
    grid_match = re.search(r"<div class=\"dashboard-grid\">", html_text)
    if not grid_match:
        return html_text
    grid_body_start = grid_match.end()
    grid_bounds = find_matching_div_bounds(html_text, grid_body_start)
    if not grid_bounds:
        return html_text
    grid_body_end, grid_close_end = grid_bounds
    grid_body = html_text[grid_body_start:grid_body_end]
    card_pattern = re.compile(
        r"\s*<div class=\"metric-card\">\s*"
        r"<div class=\"metric-label\">(?P<label>.*?)</div>\s*"
        r"<div class=\"metric-value[^\"]*\">.*?</div>\s*"
        r"<div class=\"metric-note\">.*?</div>\s*"
        r"</div>",
        re.S,
    )
    cards = []
    for card_match in card_pattern.finditer(grid_body):
        label = cell_text(card_match.group("label"))
        if label in OVERVIEW_HIDDEN_METRICS:
            continue
        card_html = card_match.group(0).strip()
        extra_class = OVERVIEW_METRIC_CLASSES.get(label, "metric-card-mini")
        card_html = card_html.replace('class="metric-card"', f'class="metric-card {extra_class}"', 1)
        cards.append((label, card_html))
    if not cards:
        return html_text

    cards_by_label = {label: card_html for label, card_html in cards}
    ordered_labels = [label for label in OVERVIEW_METRIC_ORDER if label in cards_by_label]
    ordered_labels.extend(label for label, _ in cards if label not in ordered_labels)
    new_grid_body = "\n" + "\n".join(cards_by_label[label] for label in ordered_labels) + "\n"
    return html_text[:grid_body_start] + new_grid_body + html_text[grid_body_end:grid_close_end] + html_text[grid_close_end:]


def metric_card_parts(grid_body: str) -> list[tuple[str, str]]:
    card_pattern = re.compile(
        r"\s*<div class=\"metric-card[^\"]*\">\s*"
        r"<div class=\"metric-label\">(?P<label>.*?)</div>\s*"
        r"<div class=\"metric-value[^\"]*\">.*?</div>\s*"
        r"<div class=\"metric-note\">.*?</div>\s*"
        r"</div>",
        re.S,
    )
    return [(cell_text(match.group("label")), match.group(0).strip()) for match in card_pattern.finditer(grid_body)]


def extract_currency_metric_values(cards: list[tuple[str, str]]) -> dict[str, dict[str, tuple[str, str]]]:
    values: dict[str, dict[str, tuple[str, str]]] = {currency: {} for currency in OVERVIEW_CURRENCIES}
    segment_pattern = re.compile(r'<span class="metric-segment([^"]*)">(.*?)</span>', re.S)
    for label, card_html in cards:
        if label not in OVERVIEW_CURRENCY_METRIC_ORDER:
            continue
        for class_tail, raw_value in segment_pattern.findall(card_html):
            value_text = cell_text(raw_value)
            for currency in OVERVIEW_CURRENCIES:
                prefix = f"{currency} "
                if value_text.startswith(prefix):
                    value_class = ""
                    if "value-positive" in class_tail:
                        value_class = "value-positive"
                    elif "value-negative" in class_tail:
                        value_class = "value-negative"
                    elif "value-zero" in class_tail:
                        value_class = "value-zero"
                    values[currency][label] = (value_text[len(prefix) :], value_class)
                    break
    return {currency: metric_map for currency, metric_map in values.items() if metric_map}


def parse_overview_number(value_text: str) -> float | None:
    raw = cell_text(str(value_text or "")).replace(",", "").replace("%", "").strip()
    if raw in {"", "-", "--"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def overview_value_class(value: float | None) -> str:
    if value is None:
        return ""
    if value > 0:
        return "value-positive"
    if value < 0:
        return "value-negative"
    return "value-zero"


def format_overview_money(value: float | None) -> tuple[str, str]:
    if value is None:
        return "-", ""
    return f"{value:,.2f}", overview_value_class(value)


def format_overview_metric(label: str, value: float | None) -> tuple[str, str]:
    if value is None:
        return "-", ""
    text = f"{value:,.2f}"
    if label in {"当前市值", "持仓成本"}:
        return text, ""
    return text, overview_value_class(value)


def format_overview_percent(value: float | None) -> tuple[str, str]:
    if value is None:
        return "-", ""
    return f"{value * 100:.2f}%", overview_value_class(value)


def cny_overview_metric_values(values: dict[str, dict[str, tuple[str, str]]]) -> dict[str, tuple[str, str]]:
    if not values:
        return {}

    rates = current_fx_rates_to_cny()
    money_labels = [
        "总盈亏",
        "当前市值",
        "持仓成本",
        "已实现盈亏",
        "持仓浮盈亏",
        "持仓当日盈亏",
    ]
    converted: dict[str, float] = {}
    converted_capital = 0.0
    converted_capital_days = 0.0
    has_capital = False
    has_capital_days = False

    for currency, metric_map in values.items():
        rate = rates.get(currency, 1.0)
        for label in money_labels:
            value_tuple = metric_map.get(label)
            if not value_tuple:
                continue
            value = parse_overview_number(value_tuple[0])
            if value is not None:
                converted[label] = converted.get(label, 0.0) + value * rate

        pnl_value = parse_overview_number(metric_map.get("总盈亏", ("", ""))[0])
        return_value = parse_overview_number(metric_map.get("总收益率", ("", ""))[0])
        annual_value = parse_overview_number(metric_map.get("综合年化", ("", ""))[0])
        if pnl_value is not None and return_value not in (None, 0):
            converted_capital += (pnl_value / (return_value / 100.0)) * rate
            has_capital = True
        if pnl_value is not None and annual_value not in (None, 0):
            converted_capital_days += (pnl_value * 365.0 / (annual_value / 100.0)) * rate
            has_capital_days = True

    result: dict[str, tuple[str, str]] = {}
    for label in money_labels:
        if label in converted:
            result[label] = format_overview_metric(label, converted[label])

    total_pnl = converted.get("总盈亏")
    if has_capital and converted_capital:
        result["总收益率"] = format_overview_percent(total_pnl / converted_capital if total_pnl is not None else None)
    if has_capital_days and converted_capital_days:
        result["综合年化"] = format_overview_percent(total_pnl * 365.0 / converted_capital_days if total_pnl is not None else None)
    return result


def render_currency_overview_card(
    title: str,
    subtitle: str,
    metric_map: dict[str, tuple[str, str]],
    extra_class: str = "",
) -> str:
    primary_labels = ["总盈亏", "总收益率", "综合年化"]
    secondary_labels = [label for label in OVERVIEW_CURRENCY_METRIC_ORDER if label not in primary_labels]
    primary_rows = []
    for label in primary_labels:
        if label not in metric_map:
            continue
        value, value_class = metric_map[label]
        class_attr = f' class="{value_class}"' if value_class else ""
        primary_rows.append(
            f'<div class="currency-overview-primary-row"><span>{html.escape(label)}</span>'
            f'<strong{class_attr}>{html.escape(value)}</strong></div>'
        )
    secondary_rows = []
    for label in secondary_labels:
        if label not in metric_map:
            continue
        value, value_class = metric_map[label]
        class_attr = f' class="{value_class}"' if value_class else ""
        secondary_rows.append(
            f'<div class="currency-overview-row"><span>{html.escape(label)}</span>'
            f'<strong{class_attr}>{html.escape(value)}</strong></div>'
        )
    class_attr = f'currency-overview-card {extra_class}'.strip()
    return (
        f'<div class="{html.escape(class_attr)}">'
        f'<div class="currency-overview-head"><span>{html.escape(title)}</span><em>{html.escape(subtitle)}</em></div>'
        f'<div class="currency-overview-primary">{"".join(primary_rows)}</div>'
        f'<div class="currency-overview-details">{"".join(secondary_rows)}</div>'
        '</div>'
    )


def render_currency_overview(values: dict[str, dict[str, tuple[str, str]]]) -> str:
    if not values:
        return ""
    cards = []
    for currency in OVERVIEW_CURRENCIES:
        metric_map = values.get(currency)
        if not metric_map:
            continue
        cards.append(render_currency_overview_card(currency, "币种汇总", metric_map))
    cny_values = cny_overview_metric_values(values)
    if cny_values:
        cards.append(render_currency_overview_card("人民币折算汇总", "统一口径", cny_values, "currency-overview-cny-card"))
    return '<div class="currency-overview-grid">' + "".join(cards) + "</div>"


def split_overview_by_currency(html_text: str) -> str:
    grid_match = re.search(r"<div class=\"dashboard-grid\">", html_text)
    if not grid_match:
        return html_text
    grid_body_start = grid_match.end()
    grid_bounds = find_matching_div_bounds(html_text, grid_body_start)
    if not grid_bounds:
        return html_text
    grid_body_end, grid_close_end = grid_bounds
    grid_body = html_text[grid_body_start:grid_body_end]
    cards = metric_card_parts(grid_body)
    currency_values = extract_currency_metric_values(cards)
    currency_overview = render_currency_overview(currency_values)
    if not currency_overview:
        return html_text

    utility_cards = [
        card_html
        for label, card_html in cards
        if label not in OVERVIEW_CURRENCY_METRIC_ORDER
    ]
    new_grid_body = "\n" + "\n".join(utility_cards) + "\n"
    return (
        html_text[: grid_match.start()]
        + currency_overview
        + '\n<div class="dashboard-grid overview-utility-grid">'
        + new_grid_body
        + html_text[grid_body_end:grid_close_end]
        + html_text[grid_close_end:]
    )
