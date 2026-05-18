from __future__ import annotations

from datetime import date

from . import state
from .market_data import current_fx_rates_to_cny, display_currency_label
from .options import (
    cash_secured_put_capital,
    explicit_option_capital,
    option_gross_premium,
    option_key_from_cells,
    option_strategy_capital,
    build_open_short_put_exposure_maps,
)
from .realized_analysis import build_realized_trades, trade_payload
from .runtime import APP_DIR
from .settings import OPTION_EVENTS
from .market_data import option_kind_for_event
from .utils import cell_raw, clean_text, core_trade_type, excel_serial_to_date, parse_display_number, raw_number, raw_text_value


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
    last_price_raw = item.get("last_price")
    last_price_value = parse_display_number(last_price_raw)
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
        "lastPrice": float(last_price_value) if last_price_value is not None else None,
        "lastPriceText": clean_text(last_price_raw),
        "hasLastPrice": last_price_value is not None,
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


def is_open_option_row(core, cells: dict[int, object]) -> bool:
    event = raw_text_value(core, cells, 6)
    if event not in OPTION_EVENTS:
        return False
    if excel_serial_to_date(cell_raw(cells, 4)) is not None:
        return False
    return raw_number(cells, 10) is None


def option_capital_quality(core, rows: list[tuple[int, dict[int, object]]], rates: dict[str, float]) -> dict[str, object]:
    totals = {
        "openCount": 0,
        "openCapitalCny": 0.0,
        "explicitCapitalCny": 0.0,
        "inferredCashSecuredPutCny": 0.0,
        "inferredPremiumCny": 0.0,
        "missingCapitalCount": 0,
        "missingQuoteCount": 0,
        "inferredCount": 0,
        "explicitCount": 0,
    }
    rows_payload: list[dict[str, object]] = []
    for row_number, cells in rows:
        if not is_open_option_row(core, cells):
            continue
        event = raw_text_value(core, cells, 6)
        trade_type = raw_text_value(core, cells, 1)
        normalized_trade_type = core_trade_type(trade_type)
        currency = normalize_currency_label(core, cell_raw(cells, 20))
        rate = rate_for_currency(rates, currency)
        capital = option_strategy_capital(core, cells, trade_type, event)
        explicit = explicit_option_capital(core, cells, normalized_trade_type, event)
        kind = option_kind_for_event(event)
        source = "missing"
        source_label = "未录入"
        source_cny = 0.0
        if explicit is not None and explicit > EPSILON:
            source = "explicit"
            source_label = "表内资金"
            source_cny = explicit * rate
            totals["explicitCapitalCny"] += source_cny
            totals["explicitCount"] += 1
        elif normalized_trade_type == "sell" and kind == "PUT" and capital > EPSILON:
            source = "cash_secured_put"
            source_label = "卖出认沽兜底"
            source_cny = capital * rate
            totals["inferredCashSecuredPutCny"] += source_cny
            totals["inferredCount"] += 1
        elif normalized_trade_type == "buy" and capital > EPSILON:
            source = "premium"
            source_label = "权利金成本"
            source_cny = capital * rate
            totals["inferredPremiumCny"] += source_cny
            totals["inferredCount"] += 1
        else:
            totals["missingCapitalCount"] += 1

        totals["openCount"] += 1
        totals["openCapitalCny"] += max(source_cny, 0.0)

        mark = state.OPEN_OPTION_MARKS.get(option_key_from_cells(core, cells), {})
        current_price = parse_display_number(mark.get("current_price") if isinstance(mark, dict) else None)
        if current_price is None:
            totals["missingQuoteCount"] += 1

        rows_payload.append(
            {
                "row": row_number,
                "ticker": clean_text(core.normalize_ticker(cell_raw(cells, 5), cell_raw(cells, 20))),
                "event": event,
                "type": trade_type,
                "currency": currency,
                "capital": capital,
                "capitalCny": source_cny,
                "source": source,
                "sourceLabel": source_label,
                "hasQuote": current_price is not None,
                "cashSecuredPutCapital": cash_secured_put_capital(cells) or 0.0,
                "grossPremium": option_gross_premium(cells) or 0.0,
            }
        )
    return {"totals": totals, "rows": rows_payload}


def cache_file_status() -> dict[str, object]:
    cache_dir = APP_DIR / "tools" / "cache"
    files = {
        "securityHistory": cache_dir / "security_history.json",
        "benchmarkHistory": cache_dir / "benchmark_history.json",
    }
    return {
        key: {
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
        }
        for key, path in files.items()
    }


def realized_capital_cny(realized: dict[str, object], rates: dict[str, float]) -> float:
    total = 0.0
    for trade in realized.get("trades", []) if isinstance(realized, dict) else []:
        if not isinstance(trade, dict):
            continue
        capital = parse_display_number(trade.get("capital"))
        if capital is None or abs(capital) <= EPSILON:
            continue
        currency = clean_text(trade.get("currency")) or "人民币"
        total += abs(capital) * rate_for_currency(rates, currency)
    return total


def data_quality_payload(holding_payload: dict[str, object], option_quality: dict[str, object]) -> dict[str, object]:
    holding_rows = [row for row in holding_payload.get("rows", []) if isinstance(row, dict)]
    missing_price_rows = [
        row
        for row in holding_rows
        if not row.get("hasLastPrice") and "卖出认沽" not in clean_text(row.get("side"))
    ]
    option_totals = option_quality.get("totals", {}) if isinstance(option_quality, dict) else {}
    missing_option_quotes = int(option_totals.get("missingQuoteCount") or 0)
    missing_option_capital = int(option_totals.get("missingCapitalCount") or 0)
    inferred_count = int(option_totals.get("inferredCount") or 0)
    cache_status = cache_file_status()
    warning_count = len(missing_price_rows) + missing_option_quotes + missing_option_capital
    status = "good"
    label = "良好"
    if warning_count:
        status = "warn"
        label = "需关注"
    if missing_option_capital:
        status = "danger"
        label = "资金口径待补"
    items = [
        {
            "key": "holding_quotes",
            "label": "现股行情",
            "status": "warn" if missing_price_rows else "good",
            "text": f"{len(missing_price_rows)} 个持仓缺现价" if missing_price_rows else "当前持仓现价完整",
        },
        {
            "key": "option_quotes",
            "label": "期权行情",
            "status": "warn" if missing_option_quotes else "good",
            "text": f"{missing_option_quotes} 条未平仓期权未匹配现价" if missing_option_quotes else "未平仓期权行情已匹配",
        },
        {
            "key": "capital_basis",
            "label": "资金口径",
            "status": "danger" if missing_option_capital else ("warn" if inferred_count else "good"),
            "text": (
                f"{missing_option_capital} 条期权缺保证金/策略资金"
                if missing_option_capital
                else f"{inferred_count} 条期权使用兜底资金口径"
                if inferred_count
                else "期权资金均来自表内或无需兜底"
            ),
        },
        {
            "key": "history_cache",
            "label": "历史缓存",
            "status": "good" if cache_status["securityHistory"]["exists"] and cache_status["benchmarkHistory"]["exists"] else "warn",
            "text": (
                "个股和指数历史缓存可用"
                if cache_status["securityHistory"]["exists"] and cache_status["benchmarkHistory"]["exists"]
                else "历史缓存不完整，刷新可能需要联网补齐"
            ),
        },
    ]
    return {
        "status": status,
        "label": label,
        "warningCount": warning_count,
        "counts": {
            "holdings": len(holding_rows),
            "missingHoldingPrice": len(missing_price_rows),
            "missingOptionQuote": missing_option_quotes,
            "missingOptionCapital": missing_option_capital,
            "inferredOptionCapital": inferred_count,
        },
        "items": items,
        "cache": cache_status,
    }


def capital_payload(holding_payload: dict[str, object], realized: dict[str, object], option_quality: dict[str, object], rates: dict[str, float]) -> dict[str, object]:
    totals = holding_payload["totals"]
    option_totals = option_quality.get("totals", {}) if isinstance(option_quality, dict) else {}
    return {
        "accountAssetCny": totals["assetCny"],
        "marketExposureCny": totals["marketValueCny"],
        "holdingCostCny": totals["costCny"],
        "holdingFloatPnlCny": totals["floatPnlCny"],
        "shortPutReserveCny": totals["shortPutReserveCny"],
        "realizedClosedCapitalCny": realized_capital_cny(realized, rates),
        "openOptionCapitalCny": option_totals.get("openCapitalCny", 0.0),
        "openOptionCount": option_totals.get("openCount", 0),
        "optionCapital": option_quality,
        "basis": "当前账户资产不含现金；风险敞口按仓位绝对值；卖出认沽占用资金单列展示。",
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
    option_quality = option_capital_quality(core, rows, rates)
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
        "capital": capital_payload(holding_payload, realized, option_quality, rates),
        "dataQuality": data_quality_payload(holding_payload, option_quality),
        "tags": state.TRANSACTION_TAGS_PAYLOAD if isinstance(state.TRANSACTION_TAGS_PAYLOAD, dict) else {},
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
