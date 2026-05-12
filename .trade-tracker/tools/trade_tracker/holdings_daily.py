from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .historical_curve import build_stock_lots, unrealized_pnl
from .utils import clean_text, format_currency_amounts, format_money_text, parse_display_number


EPSILON = 0.000001


def previous_weekday(day: date) -> date:
    current = day - timedelta(days=1)
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def market_timezone_for_currency(currency: str):
    label = clean_text(currency).upper()
    if label in {"美元", "USD"}:
        name, fallback = "America/New_York", timezone(timedelta(hours=-5))
    elif label in {"港币", "HKD"}:
        name, fallback = "Asia/Hong_Kong", timezone(timedelta(hours=8))
    else:
        name, fallback = "Asia/Shanghai", timezone(timedelta(hours=8))
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return fallback


def market_session_start_for_currency(currency: str) -> time:
    label = clean_text(currency).upper()
    if label in {"美元", "USD"}:
        return time(4, 0)
    if label in {"港币", "HKD"}:
        return time(9, 0)
    return time(9, 0)


def market_trade_day_for_currency(currency: str, now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_now = current.astimezone(market_timezone_for_currency(currency))
    candidate = local_now.date()
    if candidate.weekday() >= 5 or local_now.time() < market_session_start_for_currency(currency):
        return previous_weekday(candidate)
    return candidate


def sync_daily_pnl_total(data: dict[str, object]) -> None:
    amounts: dict[str, float] = {}
    for holding in data.get("holdings", []) or []:
        if not isinstance(holding, dict):
            continue
        currency = clean_text(holding.get("currency"))
        value = parse_display_number(holding.get("daily_pnl"))
        if not currency or value is None:
            continue
        amounts[currency] = amounts.get(currency, 0.0) + value
    data["daily_pnl_text"] = format_currency_amounts(amounts)


def apply_segmented_daily_pnl(
    core,
    rows,
    data: dict[str, object],
    today: date | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    if not isinstance(data, dict):
        return data
    open_lots_by_key = {}
    for lot in build_stock_lots(core, rows):
        if lot.close_date is not None:
            continue
        open_lots_by_key.setdefault((lot.ticker, lot.currency), []).append(lot)
    if not open_lots_by_key:
        return data

    changed = False
    for holding in data.get("holdings", []) or []:
        if not isinstance(holding, dict):
            continue
        key = (clean_text(holding.get("ticker")), clean_text(holding.get("currency")))
        lots = open_lots_by_key.get(key)
        current_price = parse_display_number(holding.get("last_price"))
        if not lots or current_price is None:
            continue

        original_daily = parse_display_number(holding.get("daily_pnl"))
        total_qty = sum(lot.quantity for lot in lots)
        current_day = today or market_trade_day_for_currency(key[1], now)
        old_qty = sum(lot.quantity for lot in lots if lot.open_date < current_day)
        today_lots = [lot for lot in lots if lot.open_date >= current_day]

        if not today_lots:
            continue

        old_pnl = 0.0
        if abs(old_qty) > EPSILON and original_daily is not None and abs(total_qty) > EPSILON:
            old_pnl = original_daily * old_qty / total_qty
        today_pnl = sum(unrealized_pnl(lot, current_price) for lot in today_lots)
        segmented_daily = old_pnl + today_pnl
        holding["daily_pnl"] = format_money_text(key[1], segmented_daily)
        changed = True

    if changed:
        sync_daily_pnl_total(data)
    return data
