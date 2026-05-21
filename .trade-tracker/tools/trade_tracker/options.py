from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

from . import state
from .dividends import build_dividend_income_maps
from .market_data import display_currency_label, fetch_option_quote, option_kind_for_event
from .runtime import emit_progress
from .settings import OPTION_EVENTS
from .utils import cell_raw, clean_text, core_trade_type, excel_serial_to_date, format_currency_amounts, format_money_text, format_signed_percent, format_signed_percent_with_plus, parse_display_number, raw_number, raw_text_value


STOCK_EVENTS = {"现股", "Stock", "stock", "STOCK"}
EPSILON = 0.000001


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


def option_gross_premium(cells: dict[int, object]) -> float | None:
    qty = raw_number(cells, 8)
    open_price = raw_number(cells, 9)
    multiplier = raw_number(cells, 19) or 1.0
    if qty in (None, 0) or open_price is None:
        return None
    return abs(float(qty) * float(multiplier) * float(open_price))


def cash_secured_put_capital(cells: dict[int, object]) -> float | None:
    strike = raw_number(cells, 7)
    qty = raw_number(cells, 8)
    open_price = raw_number(cells, 9)
    multiplier = raw_number(cells, 19) or 1.0
    fee = abs(raw_number(cells, 11) or 0.0)
    if strike is None or qty in (None, 0) or open_price is None:
        return None
    notional = abs(float(strike) * float(qty) * float(multiplier))
    premium = abs(float(open_price) * float(qty) * float(multiplier))
    return max(notional - premium + fee, 0.0)


def explicit_option_capital(core, cells: dict[int, object], trade_type: str, event: str) -> float | None:
    raw_capital = raw_number(cells, 12)
    if raw_capital is not None and abs(raw_capital) > EPSILON:
        return abs(float(raw_capital))
    try:
        row_capital = core.row_capital(cells, trade_type, event)
    except Exception:
        row_capital = None
    if row_capital is not None and abs(float(row_capital or 0.0)) > EPSILON:
        return abs(float(row_capital))
    return None


def option_strategy_capital(core, cells: dict[int, object], trade_type: str, event: str) -> float:
    normalized_trade_type = core_trade_type(trade_type)
    explicit = explicit_option_capital(core, cells, normalized_trade_type, event)
    if explicit is not None:
        return explicit

    if normalized_trade_type == "sell" and option_kind_for_event(event) == "PUT":
        capital = cash_secured_put_capital(cells)
        if capital is not None and capital > EPSILON:
            return capital

    if normalized_trade_type == "buy":
        premium = option_gross_premium(cells)
        fee = abs(raw_number(cells, 11) or 0.0)
        if premium is not None:
            return premium + fee

    return 0.0


def stock_position_key(core, ticker: object, currency: object) -> tuple[str, str] | None:
    try:
        currency_raw = core.normalize_currency(currency)
    except Exception:
        currency_raw = clean_text(currency)
    try:
        normalized_ticker = core.normalize_ticker(ticker, currency_raw)
    except Exception:
        normalized_ticker = clean_text(ticker).upper()
    currency_label = display_currency_label(core, currency_raw)
    if not normalized_ticker or not currency_label:
        return None
    return clean_text(normalized_ticker), clean_text(currency_label)


def build_current_cycle_boundaries(core, rows: list[tuple[int, dict[int, object]]]) -> dict[tuple[str, str], dict[str, date | None]]:
    events_by_key: dict[tuple[str, str], list[tuple[date, int, float]]] = {}
    for _row_number, cells in rows:
        if raw_text_value(core, cells, 6) not in STOCK_EVENTS:
            continue
        open_date = excel_serial_to_date(cell_raw(cells, 2))
        quantity = raw_number(cells, 8)
        if open_date is None or quantity in (None, 0):
            continue
        key = stock_position_key(core, cell_raw(cells, 5), cell_raw(cells, 20))
        if key is None:
            continue
        trade_type = core_trade_type(raw_text_value(core, cells, 1))
        signed_quantity = -abs(float(quantity)) if trade_type == "sell" else abs(float(quantity))
        events_by_key.setdefault(key, []).append((open_date, 0, signed_quantity))
        close_date = excel_serial_to_date(cell_raw(cells, 4))
        if close_date is not None:
            events_by_key[key].append((close_date, 1, -signed_quantity))

    boundaries: dict[tuple[str, str], dict[str, date | None]] = {}
    for key, events in events_by_key.items():
        position = 0.0
        last_clear = None
        active_start = None
        for event_date, order, delta in sorted(events, key=lambda item: (item[0], item[1])):
            was_flat = abs(position) <= EPSILON
            position += delta
            is_flat = abs(position) <= EPSILON
            if was_flat and not is_flat:
                active_start = event_date
            if not was_flat and is_flat:
                last_clear = event_date
                active_start = None
        if abs(position) > EPSILON and active_start is not None:
            boundaries[key] = {"start": active_start, "last_clear": last_clear}
    return boundaries


def build_current_cycle_clear_dates(core, rows: list[tuple[int, dict[int, object]]]) -> dict[tuple[str, str], date]:
    return {
        key: boundary["last_clear"]
        for key, boundary in build_current_cycle_boundaries(core, rows).items()
        if isinstance(boundary.get("last_clear"), date)
    }


def is_current_cycle_event(key: tuple[str, str], event_date: date | None, boundaries: dict[tuple[str, str], dict[str, date | None]]) -> bool:
    boundary = boundaries.get(key)
    if boundary is None:
        return True
    start = boundary.get("start")
    return isinstance(start, date) and event_date is not None and event_date >= start


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
    multiplier = raw_number(cells, 19) or 1.0
    if not ticker or not currency_label or strike is None or qty in (None, 0) or open_price is None:
        return None
    capital = option_strategy_capital(core, cells, trade_type, event)

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
    open_date = excel_serial_to_date(cell_raw(cells, 2))

    mark = {
        "open_date": open_date.strftime("%Y/%m/%d") if open_date else "-",
        "current_price": f"{float(current_price):,.3f}".rstrip("0").rstrip(".") if isinstance(current_price, (int, float)) else "-",
        "float_pnl": f"{pnl:,.2f}" if pnl is not None else "-",
        "float_pnl_class": option_tone_class(pnl),
        "capital": f"{capital:,.2f}" if capital > EPSILON else "-",
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

    workers = min(6, len(requests))
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
    close_date = excel_serial_to_date(cell_raw(cells, 4))
    is_closed = close_date is not None or close_price is not None
    gross_open = abs(qty) * multiplier * open_price
    if is_closed:
        close_price = close_price or 0.0
        gross_close = abs(qty) * multiplier * close_price
        income = (gross_open - gross_close - fee) if trade_type == "sell" else (gross_close - gross_open - fee)
    else:
        income = (gross_open - fee) if trade_type == "sell" else (-gross_open - fee)

    capital = option_strategy_capital(core, cells, trade_type, event)

    open_date = excel_serial_to_date(cell_raw(cells, 2))
    days = max(((date.today() - open_date).days if open_date else 1), 1)
    return {
        "ticker": ticker,
        "currency": currency_label,
        "currency_raw": currency,
        "income": income,
        "is_open": not is_closed,
        "open_date": open_date,
        "close_date": close_date,
        "open_year": str(open_date.year) if open_date else "",
        "capital": float(capital or 0.0),
        "capital_days": float(capital or 0.0) * days,
    }


def build_option_income_maps(
    core,
    rows: list[tuple[int, dict[int, object]]],
    boundaries: dict[tuple[str, str], dict[str, date | None]] | None = None,
) -> dict[tuple[str, str], dict[str, object]]:
    adjustments: dict[tuple[str, str], dict[str, object]] = {}
    boundaries = boundaries or {}
    for _row_number, cells in rows:
        option = option_income_for_row(core, cells)
        if not option:
            continue
        key = (str(option["ticker"]), str(option["currency"]))
        event_date = option.get("open_date") if option["is_open"] else option.get("close_date") or option.get("open_date")
        if not is_current_cycle_event(key, event_date if isinstance(event_date, date) else None, boundaries):
            continue
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

    close_date = excel_serial_to_date(cell_raw(cells, 4))
    is_closed = close_date is not None or raw_number(cells, 10) is not None
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
        "date": close_date,
    }


def build_stock_realized_income_maps(
    core,
    rows: list[tuple[int, dict[int, object]]],
    boundaries: dict[tuple[str, str], dict[str, date | None]] | None = None,
) -> dict[tuple[str, str], float]:
    adjustments: dict[tuple[str, str], float] = {}
    boundaries = boundaries or {}
    for _row_number, cells in rows:
        realized = stock_realized_income_for_row(core, cells)
        if not realized:
            continue
        key = (str(realized["ticker"]), str(realized["currency"]))
        event_date = realized.get("date")
        if not is_current_cycle_event(key, event_date if isinstance(event_date, date) else None, boundaries):
            continue
        adjustments[key] = adjustments.get(key, 0.0) + float(realized["income"])
    return adjustments


def build_current_cycle_dividend_income_maps(
    core,
    data: dict[str, object],
    boundaries: dict[tuple[str, str], dict[str, date | None]],
) -> dict[tuple[str, str], float]:
    if not boundaries or not hasattr(core, "load_dividend_events"):
        return build_dividend_income_maps(data)
    try:
        events = core.load_dividend_events() or []
    except Exception:
        events = []
    if not events:
        return build_dividend_income_maps(data)

    adjustments: dict[tuple[str, str], float] = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        key = stock_position_key(core, event.get("ticker"), event.get("currency"))
        if key is None:
            continue
        amount = parse_display_number(event.get("amount"))
        event_date = excel_serial_to_date(event.get("serial")) or excel_serial_to_date(event.get("date"))
        if amount is None or not is_current_cycle_event(key, event_date, boundaries):
            continue
        adjustments[key] = adjustments.get(key, 0.0) + float(amount)
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
            if float_pnl >= -0.005:
                row["breakeven"] = "-"
            else:
                breakeven = (avg_cost / last_price) - 1.0
                row["breakeven"] = format_signed_percent_with_plus(breakeven)
    row["sort_value"] = abs(adjusted_cost)


def option_reserved_capital(core, cells: dict[int, object], trade_type: str, event: str) -> float:
    return option_strategy_capital(core, cells, trade_type, event)


def open_short_put_exposure_for_row(core, cells: dict[int, object]) -> dict[str, object] | None:
    event = raw_text_value(core, cells, 6)
    if event not in OPTION_EVENTS or option_kind_for_event(event) != "PUT":
        return None
    trade_type = core_trade_type(raw_text_value(core, cells, 1))
    if trade_type != "sell":
        return None
    is_closed = excel_serial_to_date(cell_raw(cells, 4)) is not None or raw_number(cells, 10) is not None
    if is_closed:
        return None

    ticker = core.normalize_ticker(cell_raw(cells, 5), cell_raw(cells, 20))
    currency_raw = core.normalize_currency(cell_raw(cells, 20))
    currency_label = display_currency_label(core, currency_raw)
    if not ticker or not currency_label:
        return None

    capital = option_reserved_capital(core, cells, trade_type, event)
    if capital <= 0:
        return None

    mark = state.OPEN_OPTION_MARKS.get(option_key_from_cells(core, cells), {})
    float_pnl = parse_display_number(mark.get("float_pnl") if isinstance(mark, dict) else None) or 0.0
    open_date = excel_serial_to_date(cell_raw(cells, 2))
    days = max(((date.today() - open_date).days if open_date else 1), 1)
    return {
        "ticker": ticker,
        "currency": currency_label,
        "currency_raw": currency_raw,
        "capital": capital,
        "float_pnl": float_pnl,
        "capital_days": capital * days,
        "count": 1,
        "open_date": open_date,
    }


def build_open_short_put_exposure_maps(core, rows: list[tuple[int, dict[int, object]]]) -> dict[tuple[str, str], dict[str, object]]:
    exposures: dict[tuple[str, str], dict[str, object]] = {}
    for _row_number, cells in rows:
        exposure = open_short_put_exposure_for_row(core, cells)
        if not exposure:
            continue
        key = (str(exposure["ticker"]), str(exposure["currency"]))
        bucket = exposures.setdefault(
            key,
            {
                "ticker": exposure["ticker"],
                "currency": exposure["currency"],
                "currency_raw": exposure["currency_raw"],
                "capital": 0.0,
                "float_pnl": 0.0,
                "capital_days": 0.0,
                "count": 0,
                "first_open_date": exposure.get("open_date"),
            },
        )
        bucket["capital"] = float(bucket["capital"]) + float(exposure["capital"])
        bucket["float_pnl"] = float(bucket["float_pnl"]) + float(exposure["float_pnl"])
        bucket["capital_days"] = float(bucket["capital_days"]) + float(exposure["capital_days"])
        bucket["count"] = int(bucket["count"]) + 1
        open_date = exposure.get("open_date")
        first_open_date = bucket.get("first_open_date")
        if open_date and (not first_open_date or open_date < first_open_date):
            bucket["first_open_date"] = open_date
    return exposures


def append_short_put_side(side: object) -> str:
    text = clean_text(side)
    if not text or text == "-":
        return "卖出认沽"
    if "卖出认沽" in text:
        return text
    return f"{text}+卖出认沽"


def merge_open_short_put_exposure_into_holding(core, holding: dict[str, object], exposure: dict[str, object]) -> None:
    currency_label = clean_text(holding.get("currency") or exposure.get("currency") or "")
    capital = float(exposure.get("capital") or 0.0)
    float_pnl = float(exposure.get("float_pnl") or 0.0)
    market_value = parse_display_number(holding.get("market_value")) or 0.0
    all_in_cost = parse_display_number(holding.get("all_in_cost")) or 0.0
    current_float_pnl = parse_display_number(holding.get("float_pnl")) or 0.0

    merged_cost = all_in_cost + capital
    merged_float_pnl = current_float_pnl + float_pnl
    merged_market_value = market_value + capital

    holding["market_value"] = format_money_text(currency_label, merged_market_value)
    holding["all_in_cost"] = format_money_text(currency_label, merged_cost)
    holding["float_pnl"] = format_money_text(currency_label, merged_float_pnl)
    if merged_cost:
        holding["float_pnl_pct"] = format_signed_percent(merged_float_pnl / abs(merged_cost))
    holding["side"] = append_short_put_side(holding.get("side"))
    holding["option_reserve"] = format_money_text(currency_label, capital)
    holding["option_reserve_count"] = int(exposure.get("count") or 0)
    holding["sort_value"] = abs(merged_market_value)


def make_open_short_put_holding(core, exposure: dict[str, object]) -> dict[str, object]:
    ticker = clean_text(exposure.get("ticker"))
    currency_label = clean_text(exposure.get("currency"))
    capital = float(exposure.get("capital") or 0.0)
    float_pnl = float(exposure.get("float_pnl") or 0.0)
    count = int(exposure.get("count") or 0)
    open_date = exposure.get("first_open_date")
    try:
        name = clean_text(core.lookup_security_name(ticker, currency_label, False))
    except Exception:
        name = ""
    if not name:
        try:
            name = clean_text(core.lookup_security_name(ticker, currency_label, True))
        except Exception:
            name = ""
    current_value = capital
    return {
        "ticker": ticker,
        "name": name or "-",
        "currency": currency_label,
        "side": "卖出认沽",
        "qty": f"{count}腿",
        "all_in_cost": format_money_text(currency_label, capital),
        "avg_cost": "-",
        "market_value": format_money_text(currency_label, current_value),
        "last_price": "-",
        "float_pnl": format_money_text(currency_label, float_pnl),
        "float_pnl_pct": format_signed_percent(float_pnl / capital) if capital else "--",
        "daily_pnl": format_money_text(currency_label, 0.0),
        "breakeven": "-",
        "last_buy": open_date.strftime("%Y/%m/%d") if open_date else "-",
        "recent_buy": open_date.strftime("%Y/%m/%d") if open_date else "-",
        "option_reserve": format_money_text(currency_label, capital),
        "option_reserve_count": count,
        "sort_value": abs(current_value),
    }


def apply_open_short_put_exposures_to_holdings(core, data: dict[str, object], exposures: dict[tuple[str, str], dict[str, object]]) -> None:
    if not exposures:
        return
    holdings = data.setdefault("holdings", [])
    holdings_by_key = {
        (clean_text(holding.get("ticker")), clean_text(holding.get("currency"))): holding
        for holding in holdings
        if isinstance(holding, dict)
    }
    for key, exposure in exposures.items():
        holding = holdings_by_key.get(key)
        if holding:
            merge_open_short_put_exposure_into_holding(core, holding, exposure)
        else:
            first_open_date = exposure.get("first_open_date")
            if first_open_date:
                days = max((date.today() - first_open_date).days, 1)
                state.HOLDING_DAYS_MAP[(str(exposure.get("ticker")), str(exposure.get("currency_raw")))] = str(days)
            holdings.append(make_open_short_put_holding(core, exposure))


def add_open_short_put_capital_to_summaries(data: dict[str, object], exposures: dict[tuple[str, str], dict[str, object]]) -> None:
    if not exposures:
        return
    current_year = str(date.today().year)
    for summary_key in ("stock_summary", "annual_summary"):
        for row in data.get(summary_key, []) or []:
            if summary_key == "annual_summary" and clean_text(row.get("year")) != current_year:
                continue
            key = (clean_text(row.get("ticker")), clean_text(row.get("currency")))
            exposure = exposures.get(key)
            if not exposure:
                continue
            row["capital_raw"] = float(row.get("capital_raw") or 0.0) + float(exposure.get("capital") or 0.0)
            row["capital_days_raw"] = float(row.get("capital_days_raw") or 0.0) + float(exposure.get("capital_days") or 0.0)
            total_pnl = float(row.get("total_pnl_raw") or parse_display_number(row.get("total_pnl")) or 0.0)
            if row["capital_raw"]:
                row["return_rate"] = format_signed_percent(total_pnl / float(row["capital_raw"]))
            if row["capital_days_raw"]:
                row["annualized"] = format_signed_percent(total_pnl * 365.0 / float(row["capital_days_raw"]))


def holding_cycle_return_rate(holding: dict[str, object]) -> float | None:
    float_pnl = parse_display_number(holding.get("float_pnl"))
    adjusted_cost = parse_display_number(holding.get("all_in_cost"))
    if float_pnl is None or adjusted_cost is None or abs(adjusted_cost) <= EPSILON:
        return None
    return float_pnl / abs(adjusted_cost)


def holding_cycle_days(
    key: tuple[str, str],
    holding: dict[str, object],
    boundaries: dict[tuple[str, str], dict[str, date | None]] | None,
) -> int | None:
    start = None
    if boundaries:
        boundary = boundaries.get(key)
        if boundary:
            start = boundary.get("start")
    if not isinstance(start, date):
        start = excel_serial_to_date(holding.get("last_buy")) or excel_serial_to_date(holding.get("recent_buy"))
    if not isinstance(start, date):
        return None
    return max((date.today() - start).days, 1)


def sync_holding_cycle_return_rates_to_summaries(
    data: dict[str, object],
    boundaries: dict[tuple[str, str], dict[str, date | None]] | None = None,
) -> None:
    holdings_by_key = {
        (clean_text(holding.get("ticker")), clean_text(holding.get("currency"))): holding
        for holding in data.get("holdings", []) or []
        if isinstance(holding, dict)
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
            return_rate = holding_cycle_return_rate(holding)
            if return_rate is None:
                continue
            row["return_rate"] = format_signed_percent(return_rate)
            days = holding_cycle_days(key, holding, boundaries)
            if days:
                row["annualized"] = format_signed_percent(return_rate * 365.0 / days)


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


def sync_adjusted_holdings_to_summaries(
    data: dict[str, object],
    applied_income_by_key: dict[tuple[str, str], float],
) -> None:
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
            realized_raw = parse_display_number(row.get("realized_pnl"))
            realized = realized_raw or 0.0
            dividend = parse_display_number(row.get("dividend")) or 0.0
            applied_income = float(applied_income_by_key.get(key, 0.0))
            total_pnl = (
                adjusted_unrealized
                if realized_raw is None and "realized_pnl" not in row
                else adjusted_unrealized + realized + dividend - applied_income
            )
            row["unrealized_pnl"] = format_money_text(currency_label, adjusted_unrealized)
            row["total_pnl_raw"] = total_pnl
            row["total_pnl"] = format_money_text(currency_label, total_pnl)
            row["sort_value"] = total_pnl


def patch_dashboard_data_with_options(core, rows, data: dict[str, object]) -> dict[str, object]:
    state.OPEN_OPTION_MARKS = build_open_option_marks(core, rows)
    boundaries = build_current_cycle_boundaries(core, rows)
    option_adjustments = build_option_income_maps(core, rows, boundaries)
    short_put_exposures = build_open_short_put_exposure_maps(core, rows)
    stock_adjustments = build_stock_realized_income_maps(core, rows, boundaries)
    dividend_adjustments = build_current_cycle_dividend_income_maps(core, data, boundaries)
    if not option_adjustments and not short_put_exposures and not stock_adjustments and not dividend_adjustments:
        sync_holding_cycle_return_rates_to_summaries(data, boundaries)
        return data

    applied_income_by_key: dict[tuple[str, str], float] = {}
    for holding in data.get("holdings", []) or []:
        key = (clean_text(holding.get("ticker")), clean_text(holding.get("currency")))
        option_income = float(option_adjustments.get(key, {}).get("closed_income", 0.0))
        stock_income = float(stock_adjustments.get(key, 0.0))
        dividend_income = float(dividend_adjustments.get(key, 0.0))
        applied_income = option_income + stock_income + dividend_income
        applied_income_by_key[key] = applied_income
        adjust_holding_for_realized_income(holding, applied_income)
    apply_open_short_put_exposures_to_holdings(core, data, short_put_exposures)
    recompute_current_holding_totals(data)
    sync_adjusted_holdings_to_summaries(data, applied_income_by_key)
    add_open_short_put_capital_to_summaries(data, short_put_exposures)
    sync_holding_cycle_return_rates_to_summaries(data, boundaries)

    note = clean_text(data.get("totals_note") or "")
    option_note = "同一轮持仓周期内的已平仓现股、期权和分红会回冲当前持仓成本；清仓归零前的历史收益不再滚入新一轮浮盈。卖出认沽按占用本金计入当前持仓市值和仓位，未录入本金时按 cash-secured 口径推导，covered call 不重复计入。"
    data["totals_note"] = option_note if not note else f"{note}；{option_note}"
    return data
