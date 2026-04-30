from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from . import state
from .market_data import display_currency_label, fetch_option_quote
from .runtime import emit_progress
from .settings import OPTION_EVENTS
from .utils import cell_raw, clean_text, core_trade_type, excel_serial_to_date, format_currency_amounts, format_money_text, format_signed_percent, parse_display_number, raw_number, raw_text_value


STOCK_EVENTS = {"现股", "Stock", "stock", "STOCK"}


def option_key(
    ticker: object,
    trade_type: object,
    event: object,
    expiry: object,
    strike: object,
    qty: object,
    multiplier: object,
    open_price: object,
    currency: object,
) -> tuple[str, str, str, str, str, str, str, str]:
    return (
        clean_text(ticker),
        clean_text(trade_type),
        clean_text(event),
        clean_text(expiry),
        number_key(strike),
        number_key(qty),
        number_key(multiplier),
        number_key(open_price),
        clean_text(currency),
    )


def number_key(value: object) -> str:
    numeric = parse_display_number(value)
    if numeric is None:
        return clean_text(value)
    return f"{numeric:.8f}".rstrip("0").rstrip(".")


def option_key_from_cells(core, cells: dict[int, object]) -> tuple[str, str, str, str, str, str, str, str]:
    currency = display_currency_label(core, core.normalize_currency(cell_raw(cells, 20)))
    expiry = excel_serial_to_date(cell_raw(cells, 3))
    return option_key(
        core.normalize_ticker(cell_raw(cells, 5), cell_raw(cells, 20)),
        raw_text_value(core, cells, 1),
        raw_text_value(core, cells, 6),
        expiry.strftime("%Y/%m/%d") if expiry else raw_text_value(core, cells, 3),
        raw_number(cells, 7),
        raw_number(cells, 8),
        raw_number(cells, 19) or 1,
        raw_number(cells, 9),
        currency,
    )


def option_float_pnl(trade_type: str, open_price: float, current_price: float, qty: float, multiplier: float, fee: float) -> float:
    gross_qty = abs(qty) * multiplier
    if core_trade_type(trade_type) == "sell":
        return (open_price - current_price) * gross_qty - fee
    return (current_price - open_price) * gross_qty - fee


def option_tone_class(value: float | None) -> str:
    if value is None:
        return ""
    if value > 0:
        return "value-positive"
    if value < 0:
        return "value-negative"
    return "value-zero"


def open_option_mark_for_row(core, cells: dict[int, object], quote_cache: dict[tuple[str, str, str, str, str], dict | None]) -> tuple[tuple[str, str, str, str, str, str, str, str], dict[str, str]] | None:
    event = raw_text_value(core, cells, 6)
    if event not in OPTION_EVENTS:
        return None
    if excel_serial_to_date(cell_raw(cells, 4)) is not None or raw_number(cells, 10) is not None:
        return None

    trade_type = raw_text_value(core, cells, 1)
    ticker = core.normalize_ticker(cell_raw(cells, 5), cell_raw(cells, 20))
    currency_raw = core.normalize_currency(cell_raw(cells, 20))
    currency_label = display_currency_label(core, currency_raw)
    expiry = excel_serial_to_date(cell_raw(cells, 3))
    expiry_text = expiry.strftime("%Y/%m/%d") if expiry else raw_text_value(core, cells, 3)
    strike = raw_number(cells, 7)
    qty = raw_number(cells, 8)
    open_price = raw_number(cells, 9)
    fee = raw_number(cells, 11) or 0.0
    capital = raw_number(cells, 12)
    multiplier = raw_number(cells, 19) or 1.0
    if not ticker or not currency_label or strike is None or qty in (None, 0) or open_price is None:
        return None

    quote_key = (ticker, currency_raw, event, expiry_text, number_key(strike))
    if quote_key not in quote_cache:
        quote_cache[quote_key] = fetch_option_quote(core, ticker, currency_raw, event, expiry_text, strike)
    quote = quote_cache.get(quote_key) or {}
    current_price = quote.get("last_price") if isinstance(quote, dict) else None
    pnl = (
        option_float_pnl(trade_type, open_price, float(current_price), qty, multiplier, fee)
        if isinstance(current_price, (int, float))
        else None
    )

    mark = {
        "current_price": f"{float(current_price):,.3f}".rstrip("0").rstrip(".") if isinstance(current_price, (int, float)) else "-",
        "float_pnl": f"{pnl:,.2f}" if pnl is not None else "-",
        "float_pnl_class": option_tone_class(pnl),
        "capital": f"{capital:,.2f}" if capital is not None else "-",
        "option_code": clean_text(quote.get("option_code") if isinstance(quote, dict) else ""),
    }
    return option_key_from_cells(core, cells), mark


def option_quote_request_for_row(core, cells: dict[int, object]) -> tuple[tuple[str, str, str, str, str], str, str, str, str, float] | None:
    event = raw_text_value(core, cells, 6)
    if event not in OPTION_EVENTS:
        return None
    if excel_serial_to_date(cell_raw(cells, 4)) is not None or raw_number(cells, 10) is not None:
        return None
    ticker = core.normalize_ticker(cell_raw(cells, 5), cell_raw(cells, 20))
    currency_raw = core.normalize_currency(cell_raw(cells, 20))
    expiry = excel_serial_to_date(cell_raw(cells, 3))
    expiry_text = expiry.strftime("%Y/%m/%d") if expiry else raw_text_value(core, cells, 3)
    strike = raw_number(cells, 7)
    qty = raw_number(cells, 8)
    open_price = raw_number(cells, 9)
    if not ticker or not currency_raw or strike is None or qty in (None, 0) or open_price is None:
        return None
    quote_key = (ticker, currency_raw, event, expiry_text, number_key(strike))
    return quote_key, ticker, currency_raw, event, expiry_text, strike


def prefetch_open_option_quotes(core, candidates: list[dict[int, object]]) -> dict[tuple[str, str, str, str, str], dict | None]:
    quote_cache: dict[tuple[str, str, str, str, str], dict | None] = {}
    requests = []
    seen = set()
    for cells in candidates:
        request = option_quote_request_for_row(core, cells)
        if not request:
            continue
        quote_key = request[0]
        if quote_key in seen:
            continue
        seen.add(quote_key)
        requests.append(request)
    if not requests:
        return quote_cache

    workers = min(3, len(requests))
    completed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(fetch_option_quote, core, ticker, currency_raw, event, expiry_text, strike): quote_key
            for quote_key, ticker, currency_raw, event, expiry_text, strike in requests
        }
        for future in as_completed(future_map):
            quote_key = future_map[future]
            try:
                quote_cache[quote_key] = future.result()
            except Exception:
                quote_cache[quote_key] = None
            completed += 1
            emit_progress("获取期权行情", f"公开期权行情 {completed}/{len(requests)}：{quote_key[0]} {quote_key[3]} {quote_key[4]}", 72 + (completed / len(requests)) * 8)
    return quote_cache


def build_open_option_marks(core, rows: list[tuple[int, dict[int, object]]]) -> dict[tuple[str, str, str, str, str, str, str, str], dict[str, str]]:
    marks: dict[tuple[str, str, str, str, str, str, str, str], dict[str, str]] = {}
    candidates = [
        cells
        for _row_number, cells in rows
        if raw_text_value(core, cells, 6) in OPTION_EVENTS
        and excel_serial_to_date(cell_raw(cells, 4)) is None
        and raw_number(cells, 10) is None
    ]
    if candidates:
        emit_progress("获取期权行情", f"匹配 {len(candidates)} 条未平仓期权，包含 covered call / cash-secured put。", 72)
    quote_cache = prefetch_open_option_quotes(core, candidates)
    for cells in candidates:
        option_mark = open_option_mark_for_row(core, cells, quote_cache)
        if option_mark:
            key, mark = option_mark
            marks[key] = mark
    return marks


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


def stock_realized_income_for_row(core, cells: dict[int, object]) -> dict[str, object] | None:
    event = raw_text_value(core, cells, 6)
    if event not in STOCK_EVENTS:
        return None

    is_closed = excel_serial_to_date(cell_raw(cells, 4)) is not None or raw_number(cells, 10) is not None
    if not is_closed:
        return None

    ticker = core.normalize_ticker(cell_raw(cells, 5), cell_raw(cells, 20))
    currency = core.normalize_currency(cell_raw(cells, 20))
    currency_label = display_currency_label(core, currency)
    if not ticker or not currency_label:
        return None

    try:
        metrics = core.compute_row_metrics(cells)
    except Exception:
        return None
    pnl = metrics.get("pnl") if isinstance(metrics, dict) else None
    if pnl is None:
        return None

    return {
        "ticker": ticker,
        "currency": currency_label,
        "income": float(pnl),
    }


def build_stock_realized_income_maps(core, rows: list[tuple[int, dict[int, object]]]) -> dict[tuple[str, str], float]:
    adjustments: dict[tuple[str, str], float] = {}
    for _row_number, cells in rows:
        realized = stock_realized_income_for_row(core, cells)
        if not realized:
            continue
        key = (str(realized["ticker"]), str(realized["currency"]))
        adjustments[key] = adjustments.get(key, 0.0) + float(realized["income"])
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


def adjust_holding_for_realized_income(row: dict[str, object], realized_income: float) -> None:
    if abs(realized_income) < 0.000001:
        return
    side = clean_text(row.get("side") or "")
    is_short = "空头" in side
    currency_label = clean_text(row.get("currency") or "")
    original_cost = parse_display_number(row.get("all_in_cost"))
    qty = parse_display_number(row.get("qty"))
    if original_cost is None or qty in (None, 0):
        return
    adjusted_cost = original_cost + realized_income if is_short else original_cost - realized_income
    row["all_in_cost"] = format_money_text(currency_label, adjusted_cost)
    row["avg_cost"] = format_money_text(currency_label, adjusted_cost / abs(qty))
    market_value = parse_display_number(row.get("market_value"))
    last_price = parse_display_number(row.get("last_price"))
    if market_value is not None:
        float_pnl = market_value + adjusted_cost if is_short else market_value - adjusted_cost
        row["float_pnl"] = format_money_text(currency_label, float_pnl)
        if adjusted_cost:
            row["float_pnl_pct"] = format_signed_percent(float_pnl / abs(adjusted_cost))
        if last_price not in (None, 0):
            avg_cost = adjusted_cost / abs(qty)
            breakeven = 1.0 - (avg_cost / last_price) if is_short else (avg_cost / last_price) - 1.0
            row["breakeven"] = "已回本" if breakeven <= 0 else format_signed_percent(breakeven)
    row["sort_value"] = abs(adjusted_cost)


def recompute_current_holding_totals(data: dict[str, object]) -> None:
    totals = {
        "market_value_text": {},
        "cost_text": {},
        "unrealized_pnl_text": {},
        "daily_pnl_text": {},
    }
    fields = {
        "market_value_text": "market_value",
        "cost_text": "all_in_cost",
        "unrealized_pnl_text": "float_pnl",
        "daily_pnl_text": "daily_pnl",
    }
    for holding in data.get("holdings", []) or []:
        currency = clean_text(holding.get("currency") or "")
        if not currency:
            continue
        for output_key, row_key in fields.items():
            value = parse_display_number(holding.get(row_key))
            if value is None:
                continue
            bucket = totals[output_key]
            bucket[currency] = bucket.get(currency, 0.0) + value

    for output_key, amounts in totals.items():
        data[output_key] = format_currency_amounts(amounts)


def sync_adjusted_holdings_to_summaries(data: dict[str, object]) -> None:
    holdings_by_key = {
        (clean_text(holding.get("ticker")), clean_text(holding.get("currency"))): holding
        for holding in data.get("holdings", []) or []
    }
    if not holdings_by_key:
        return

    for summary_key in ("stock_summary", "annual_summary"):
        for row in data.get(summary_key, []) or []:
            if summary_key == "annual_summary" and clean_text(row.get("year")) != str(date.today().year):
                continue
            key = (clean_text(row.get("ticker")), clean_text(row.get("currency")))
            holding = holdings_by_key.get(key)
            if not holding:
                continue
            adjusted_unrealized = parse_display_number(holding.get("float_pnl"))
            if adjusted_unrealized is None:
                continue
            currency_label = clean_text(row.get("currency") or "")
            dividend = parse_display_number(row.get("dividend")) or 0.0
            total_pnl = adjusted_unrealized + dividend
            row["unrealized_pnl"] = format_money_text(currency_label, adjusted_unrealized)
            row["total_pnl_raw"] = total_pnl
            row["total_pnl"] = format_money_text(currency_label, total_pnl)
            row["sort_value"] = total_pnl
            capital = float(row.get("capital_raw") or 0.0)
            capital_days = float(row.get("capital_days_raw") or 0.0)
            if capital:
                row["return_rate"] = format_signed_percent(total_pnl / capital)
            if capital_days:
                row["annualized"] = format_signed_percent(total_pnl * 365.0 / capital_days)


def patch_dashboard_data_with_options(core, rows, data: dict[str, object]) -> dict[str, object]:
    state.OPEN_OPTION_MARKS = build_open_option_marks(core, rows)
    option_adjustments = build_option_income_maps(core, rows)
    stock_adjustments = build_stock_realized_income_maps(core, rows)
    if not option_adjustments and not stock_adjustments:
        return data

    for holding in data.get("holdings", []) or []:
        key = (clean_text(holding.get("ticker")), clean_text(holding.get("currency")))
        option_income = float(option_adjustments.get(key, {}).get("closed_income", 0.0))
        stock_income = float(stock_adjustments.get(key, 0.0))
        adjust_holding_for_realized_income(holding, option_income + stock_income)
    recompute_current_holding_totals(data)
    sync_adjusted_holdings_to_summaries(data)

    note = clean_text(data.get("totals_note") or "")
    option_note = "已平仓/到期作废期权及已完成现股交易归入对应标的；当前持仓成本按已实现净收益调低，未平仓期权暂不计入。"
    data["totals_note"] = option_note if not note else f"{note}；{option_note}"
    return data
