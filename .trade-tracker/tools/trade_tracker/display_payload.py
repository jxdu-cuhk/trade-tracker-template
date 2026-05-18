from __future__ import annotations

from datetime import date

from .market_data import current_fx_rates_to_cny, display_currency_label
from .options import build_open_short_put_exposure_maps
from .realized_analysis import build_realized_trades, trade_payload
from .utils import clean_text, parse_display_number


EPSILON = 0.000001


def normalize_currency_label(core, value: object) -> str:
    text = clean_text(value)
    if not text:
        return "人民币"
    try:
        return display_currency_label(core, core.normalize_currency(text)) or text
    except Exception:
        return text


def number(value: object, default: float = 0.0) -> float:
    parsed = parse_display_number(value)
    if parsed is None:
        return default
    return float(parsed)


def rate_for_currency(rates: dict[str, float], currency: str) -> float:
    rate = rates.get(currency)
    return float(rate) if isinstance(rate, (int, float)) and rate > 0 else 1.0


def short_put_reserve_by_currency(core, rows: list[tuple[int, dict[int, object]]]) -> dict[str, float]:
    if not rows:
        return {}
    try:
        exposures = build_open_short_put_exposure_maps(core, rows)
    except Exception:
        return {}
    totals: dict[str, float] = {}
    for exposure in exposures.values():
        currency = normalize_currency_label(core, exposure.get("currency"))
        totals[currency] = totals.get(currency, 0.0) + abs(float(exposure.get("capital") or 0.0))
    return totals


def display_holding_row(core, item: dict[str, object], rates: dict[str, float]) -> dict[str, object]:
    currency = normalize_currency_label(core, item.get("currency"))
    rate = rate_for_currency(rates, currency)
    market_value = number(item.get("market_value"))
    cost = number(item.get("all_in_cost"))
    float_pnl = number(item.get("float_pnl"))
    daily_pnl = number(item.get("daily_pnl"))
    qty = number(item.get("qty"))
    option_reserve = number(item.get("option_reserve"))
    return {
        "ticker": clean_text(item.get("ticker")),
        "name": clean_text(item.get("name")) or "-",
        "currency": currency,
        "rateToCny": rate,
        "side": clean_text(item.get("side")) or "-",
        "quantity": qty,
        "lastPrice": number(item.get("last_price")),
        "marketValue": market_value,
        "marketValueCny": market_value * rate,
        "marketExposureCny": abs(market_value) * rate,
        "cost": cost,
        "costCny": abs(cost) * rate,
        "floatPnl": float_pnl,
        "floatPnlCny": float_pnl * rate,
        "dailyPnl": daily_pnl,
        "dailyPnlCny": daily_pnl * rate,
        "floatRate": number(item.get("float_pnl_pct"), 0.0) / 100.0
        if "%" in clean_text(item.get("float_pnl_pct"))
        else number(item.get("float_pnl_pct")),
        "positionWeight": number(item.get("position_weight")),
        "holdingDays": number(item.get("holding_days"), 0.0),
        "recentBuy": clean_text(item.get("recent_buy") or item.get("last_buy")),
        "optionReserve": option_reserve,
        "optionReserveCny": option_reserve * rate,
    }


def empty_currency_bucket(currency: str, rate: float) -> dict[str, object]:
    return {
        "currency": currency,
        "rateToCny": rate,
        "count": 0,
        "asset": 0.0,
        "marketValue": 0.0,
        "cost": 0.0,
        "floatPnl": 0.0,
        "dailyPnl": 0.0,
        "shortPutReserve": 0.0,
        "cny": {
            "asset": 0.0,
            "marketValue": 0.0,
            "cost": 0.0,
            "floatPnl": 0.0,
            "dailyPnl": 0.0,
            "shortPutReserve": 0.0,
        },
    }


def holdings_payload(core, rows: list[tuple[int, dict[int, object]]], data: dict[str, object]) -> dict[str, object]:
    rates = current_fx_rates_to_cny()
    holdings = [item for item in data.get("holdings", []) or [] if isinstance(item, dict)]
    rows_payload = [display_holding_row(core, item, rates) for item in holdings]
    by_currency: dict[str, dict[str, object]] = {}

    for row in rows_payload:
        currency = str(row["currency"])
        rate = float(row["rateToCny"])
        bucket = by_currency.setdefault(currency, empty_currency_bucket(currency, rate))
        bucket["count"] = int(bucket["count"]) + 1
        bucket["asset"] = float(bucket["asset"]) + float(row["marketValue"])
        bucket["marketValue"] = float(bucket["marketValue"]) + abs(float(row["marketValue"]))
        bucket["cost"] = float(bucket["cost"]) + abs(float(row["cost"]))
        bucket["floatPnl"] = float(bucket["floatPnl"]) + float(row["floatPnl"])
        bucket["dailyPnl"] = float(bucket["dailyPnl"]) + float(row["dailyPnl"])
        cny = bucket["cny"]
        cny["asset"] = float(cny["asset"]) + float(row["marketValueCny"])
        cny["marketValue"] = float(cny["marketValue"]) + float(row["marketExposureCny"])
        cny["cost"] = float(cny["cost"]) + float(row["costCny"])
        cny["floatPnl"] = float(cny["floatPnl"]) + float(row["floatPnlCny"])
        cny["dailyPnl"] = float(cny["dailyPnl"]) + float(row["dailyPnlCny"])

    reserve_by_currency = short_put_reserve_by_currency(core, rows)
    for currency, reserve in reserve_by_currency.items():
        rate = rate_for_currency(rates, currency)
        bucket = by_currency.setdefault(currency, empty_currency_bucket(currency, rate))
        reserve_cny = reserve * rate
        bucket["asset"] = float(bucket["asset"]) - reserve
        bucket["shortPutReserve"] = float(bucket["shortPutReserve"]) + reserve
        cny = bucket["cny"]
        cny["asset"] = float(cny["asset"]) - reserve_cny
        cny["shortPutReserve"] = float(cny["shortPutReserve"]) + reserve_cny

    totals = {
        "assetCny": 0.0,
        "marketValueCny": 0.0,
        "costCny": 0.0,
        "floatPnlCny": 0.0,
        "dailyPnlCny": 0.0,
        "shortPutReserveCny": 0.0,
        "count": len(rows_payload),
    }
    for bucket in by_currency.values():
        cny = bucket["cny"]
        totals["assetCny"] += float(cny["asset"])
        totals["marketValueCny"] += float(cny["marketValue"])
        totals["costCny"] += float(cny["cost"])
        totals["floatPnlCny"] += float(cny["floatPnl"])
        totals["dailyPnlCny"] += float(cny["dailyPnl"])
        totals["shortPutReserveCny"] += float(cny["shortPutReserve"])
    totals["floatRate"] = totals["floatPnlCny"] / totals["costCny"] if abs(totals["costCny"]) > EPSILON else None

    return {
        "rows": rows_payload,
        "totals": totals,
        "byCurrency": dict(sorted(by_currency.items())),
    }


def realized_daily_payload(core, rows: list[tuple[int, dict[int, object]]], rates: dict[str, float]) -> dict[str, object]:
    try:
        trades = build_realized_trades(core, rows)
    except Exception:
        trades = []
    return realized_daily_payload_from_trades(core, trades, rates)


def realized_daily_payload_from_trades(core, trades, rates: dict[str, float]) -> dict[str, object]:
    by_date: dict[str, dict[str, object]] = {}
    for trade in trades:
        currency = normalize_currency_label(core, trade.currency)
        rate = rate_for_currency(rates, currency)
        bucket = by_date.setdefault(
            trade.date_iso,
            {
                "date": trade.date_iso,
                "count": 0,
                "pnlCny": 0.0,
                "capitalCny": 0.0,
                "byCurrency": {},
            },
        )
        bucket["count"] = int(bucket["count"]) + 1
        bucket["pnlCny"] = float(bucket["pnlCny"]) + trade.pnl * rate
        if trade.capital is not None:
            bucket["capitalCny"] = float(bucket["capitalCny"]) + abs(trade.capital * rate)
        currency_bucket = bucket["byCurrency"].setdefault(
            currency,
            {"currency": currency, "rateToCny": rate, "count": 0, "native": 0.0, "cny": 0.0},
        )
        currency_bucket["count"] += 1
        currency_bucket["native"] += trade.pnl
        currency_bucket["cny"] += trade.pnl * rate
    return {"byDate": dict(sorted(by_date.items()))}


def realized_payload(core, rows: list[tuple[int, dict[int, object]]], rates: dict[str, float]) -> dict[str, object]:
    try:
        trades = build_realized_trades(core, rows)
    except Exception:
        trades = []
    trade_rows = [trade_payload(trade) for trade in trades]
    daily = realized_daily_payload_from_trades(core, trades, rates)
    months = sorted(
        {str(trade.get("month") or str(trade.get("date") or "")[:7]) for trade in trade_rows if trade.get("date")},
        reverse=True,
    )
    currencies = sorted({str(trade.get("currency") or "未标注币种") for trade in trade_rows})
    return {
        "trades": trade_rows,
        "daily": daily,
        "months": months,
        "currencies": currencies,
    }


def holdings_metrics_from_payload(payload: dict[str, object]) -> dict[str, float]:
    totals = payload.get("holdingsTotals") if isinstance(payload, dict) else None
    if not isinstance(totals, dict):
        return {}
    count = float(totals.get("count") or 0.0)
    if count <= 0:
        return {}
    return {
        "asset": float(totals.get("assetCny") or 0.0),
        "market_value": float(totals.get("marketValueCny") or 0.0),
        "cost": float(totals.get("costCny") or 0.0),
        "float_pnl": float(totals.get("floatPnlCny") or 0.0),
        "daily_pnl": float(totals.get("dailyPnlCny") or 0.0),
        "count": count,
    }


def build_display_payload(core, rows: list[tuple[int, dict[int, object]]], data: dict[str, object]) -> dict[str, object]:
    rates = current_fx_rates_to_cny()
    holding_payload = holdings_payload(core, rows, data)
    realized = realized_payload(core, rows, rates)
    daily_by_currency = {
        currency: {
            "currency": currency,
            "native": bucket.get("dailyPnl", 0.0),
            "cny": bucket.get("cny", {}).get("dailyPnl", 0.0),
            "rateToCny": bucket.get("rateToCny", 1.0),
        }
        for currency, bucket in holding_payload["byCurrency"].items()
    }
    return {
        "version": 1,
        "generatedDate": date.today().isoformat(),
        "ratesToCny": rates,
        "holdings": holding_payload["rows"],
        "holdingsTotals": holding_payload["totals"],
        "holdingsByCurrency": holding_payload["byCurrency"],
        "dailyPnl": {
            "current": {
                "date": date.today().isoformat(),
                "holdingFloatCny": holding_payload["totals"]["dailyPnlCny"],
                "byCurrency": daily_by_currency,
            }
        },
        "realized": realized,
        "realizedDaily": realized["daily"],
    }
