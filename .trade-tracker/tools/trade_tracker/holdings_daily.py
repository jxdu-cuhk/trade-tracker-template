from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
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


def market_trade_day_for_currency(currency: str, now: datetime | None = None) -> date:
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local_now = current.astimezone(market_timezone_for_currency(currency))
    candidate = local_now.date()
    if candidate.weekday() >= 5:
        return previous_weekday(candidate)
    return candidate


def use_entry_price_for_daily(lot, current_day: date) -> bool:
    return lot.open_date >= current_day


def lacks_owned_previous_close(lot, current_day: date) -> bool:
    return 0 < (current_day - lot.open_date).days <= 1


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
        entry_price_lots = [lot for lot in lots if use_entry_price_for_daily(lot, current_day)]
        no_baseline_lots = [lot for lot in lots if lot not in entry_price_lots and lacks_owned_previous_close(lot, current_day)]
        quote_daily_lots = [lot for lot in lots if lot not in entry_price_lots and lot not in no_baseline_lots]

        if not entry_price_lots and not no_baseline_lots:
            continue

        old_pnl = 0.0
        old_qty = sum(lot.quantity for lot in quote_daily_lots)
        if abs(old_qty) > EPSILON and original_daily is not None and abs(total_qty) > EPSILON:
            old_pnl = original_daily * old_qty / total_qty
        today_pnl = sum(unrealized_pnl(lot, current_price) for lot in entry_price_lots)
        segmented_daily = old_pnl + today_pnl
        holding["daily_pnl"] = format_money_text(key[1], segmented_daily)
        changed = True

    if changed:
        sync_daily_pnl_total(data)
    return data
