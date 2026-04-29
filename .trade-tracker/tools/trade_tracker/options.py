from __future__ import annotations

from datetime import date

from .market_data import display_currency_label
from .settings import OPTION_EVENTS
from .utils import cell_raw, clean_text, core_trade_type, excel_serial_to_date, format_money_text, format_signed_percent, parse_display_number, raw_number, raw_text_value


def option_income_for_row(core, cells: dict[int, object]) -> dict[str, object] | None:
    event = raw_text_value(core, cells, 6)
    if event not in OPTION_EVENTS:
        return None

    trade_type = core_trade_type(raw_text_value(core, cells, 1))
    if trade_type not in {"sell", "buy"}:
        return None

    ticker = core.normalize_ticker(cell_raw(cells, 5), cell_raw(cells, 20))
    currency = core.normalize_currency(cell_raw(cells, 20))
    currency_label = display_currency_label(core, currency)
    qty = raw_number(cells, 8)
    open_price = raw_number(cells, 9)
    fee = raw_number(cells, 11) or 0.0
    multiplier = raw_number(cells, 19) or 1.0
    if not ticker or not currency_label or qty in (None, 0) or open_price is None:
        return None

    close_price = raw_number(cells, 10)
    is_closed = excel_serial_to_date(cell_raw(cells, 4)) is not None or close_price is not None
    gross_open = abs(qty) * multiplier * open_price
    if is_closed:
        close_price = close_price or 0.0
        gross_close = abs(qty) * multiplier * close_price
        income = (gross_open - gross_close - fee) if trade_type == "sell" else (gross_close - gross_open - fee)
    else:
        income = (gross_open - fee) if trade_type == "sell" else (-gross_open - fee)

    capital = None
    try:
        capital = core.row_capital(cells, trade_type, event)
    except Exception:
        capital = None
    if capital in (None, 0):
        raw_capital = raw_number(cells, 12)
        capital = (raw_capital or gross_open) + fee

    open_date = excel_serial_to_date(cell_raw(cells, 2))
    days = max(((date.today() - open_date).days if open_date else 1), 1)
    return {
        "ticker": ticker,
        "currency": currency_label,
        "currency_raw": currency,
        "income": income,
        "is_open": not is_closed,
        "open_year": str(open_date.year) if open_date else "",
        "capital": float(capital or 0.0),
        "capital_days": float(capital or 0.0) * days,
    }


def build_option_income_maps(core, rows: list[tuple[int, dict[int, object]]]) -> dict[tuple[str, str], dict[str, object]]:
    adjustments: dict[tuple[str, str], dict[str, object]] = {}
    for _row_number, cells in rows:
        option = option_income_for_row(core, cells)
        if not option:
            continue
        key = (str(option["ticker"]), str(option["currency"]))
        bucket = adjustments.setdefault(
            key,
            {
                "closed_income": 0.0,
                "open_income": 0.0,
                "open_capital": 0.0,
                "open_capital_days": 0.0,
                "open_by_year": {},
            },
        )
        income = float(option["income"])
        if option["is_open"]:
            bucket["open_income"] = float(bucket["open_income"]) + income
            bucket["open_capital"] = float(bucket["open_capital"]) + float(option["capital"])
            bucket["open_capital_days"] = float(bucket["open_capital_days"]) + float(option["capital_days"])
            year = str(option["open_year"] or "")
            if year:
                open_by_year = bucket["open_by_year"]
                year_bucket = open_by_year.setdefault(year, {"income": 0.0, "capital": 0.0, "capital_days": 0.0})
                year_bucket["income"] += income
                year_bucket["capital"] += float(option["capital"])
                year_bucket["capital_days"] += float(option["capital_days"])
        else:
            bucket["closed_income"] = float(bucket["closed_income"]) + income
    return adjustments


def adjust_summary_money_fields(row: dict[str, object], income: float, capital: float, capital_days: float) -> None:
    if abs(income) < 0.000001:
        return
    currency_label = clean_text(row.get("currency") or "")
    realized = parse_display_number(row.get("realized_pnl")) or 0.0
    total = parse_display_number(row.get("total_pnl")) or float(row.get("total_pnl_raw") or 0.0)
    row["realized_pnl"] = format_money_text(currency_label, realized + income)
    row["total_pnl_raw"] = float(row.get("total_pnl_raw") or total) + income
    row["sort_value"] = row["total_pnl_raw"]
    row["total_pnl"] = format_money_text(currency_label, row["total_pnl_raw"])
    row["capital_raw"] = float(row.get("capital_raw") or 0.0) + capital
    row["capital_days_raw"] = float(row.get("capital_days_raw") or 0.0) + capital_days
    if row["capital_raw"]:
        row["return_rate"] = format_signed_percent(float(row["total_pnl_raw"]) / float(row["capital_raw"]))
    if row["capital_days_raw"]:
        row["annualized"] = format_signed_percent(float(row["total_pnl_raw"]) * 365.0 / float(row["capital_days_raw"]))


def adjust_holding_for_options(row: dict[str, object], option_income: float) -> None:
    if abs(option_income) < 0.000001:
        return
    side = clean_text(row.get("side") or "")
    if "空头" in side:
        return
    currency_label = clean_text(row.get("currency") or "")
    original_cost = parse_display_number(row.get("all_in_cost"))
    qty = parse_display_number(row.get("qty"))
    if original_cost is None or qty in (None, 0):
        return
    adjusted_cost = original_cost - option_income
    row["all_in_cost"] = format_money_text(currency_label, adjusted_cost)
    row["avg_cost"] = format_money_text(currency_label, adjusted_cost / abs(qty))
    market_value = parse_display_number(row.get("market_value"))
    last_price = parse_display_number(row.get("last_price"))
    if market_value is not None:
        float_pnl = market_value - adjusted_cost
        row["float_pnl"] = format_money_text(currency_label, float_pnl)
        if adjusted_cost:
            row["float_pnl_pct"] = format_signed_percent(float_pnl / abs(adjusted_cost))
        if last_price not in (None, 0):
            avg_cost = adjusted_cost / abs(qty)
            breakeven = (avg_cost / last_price) - 1.0
            row["breakeven"] = "已回本" if breakeven <= 0 else format_signed_percent(breakeven)
    row["sort_value"] = adjusted_cost


def patch_dashboard_data_with_options(core, rows, data: dict[str, object]) -> dict[str, object]:
    adjustments = build_option_income_maps(core, rows)
    if not adjustments:
        return data

    for holding in data.get("holdings", []) or []:
        key = (clean_text(holding.get("ticker")), clean_text(holding.get("currency")))
        option_income = float(adjustments.get(key, {}).get("closed_income", 0.0))
        adjust_holding_for_options(holding, option_income)

    note = clean_text(data.get("totals_note") or "")
    option_note = "已平仓/到期作废期权归入对应标的；当前持仓成本按已实现期权净收益调低，未平仓期权暂不计入。"
    data["totals_note"] = option_note if not note else f"{note}；{option_note}"
    return data
