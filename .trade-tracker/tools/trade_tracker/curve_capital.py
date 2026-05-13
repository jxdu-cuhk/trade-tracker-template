from __future__ import annotations

from dataclasses import dataclass

from .market_data import display_currency_label
from .options import option_strategy_capital
from .settings import OPTION_EVENTS
from .utils import cell_raw, clean_text, core_trade_type, parse_float, raw_number, raw_text_value


STOCK_EVENTS = {"现股", "Stock", "stock", "STOCK"}


@dataclass(frozen=True)
class StockCapitalLot:
    currency: str
    open_serial: float
    close_serial: float | None
    capital: float
    source: str = "stock"


def stock_currency(core, cells: dict[int, object]) -> str:
    try:
        return display_currency_label(core, core.normalize_currency(cell_raw(cells, 20)))
    except Exception:
        return clean_text(cell_raw(cells, 20))


def stock_lot_from_row(core, cells: dict[int, object]) -> StockCapitalLot | None:
    event = raw_text_value(core, cells, 6)
    if event not in STOCK_EVENTS and event not in OPTION_EVENTS:
        return None

    currency = stock_currency(core, cells)
    open_serial = parse_float(cell_raw(cells, 2))
    if not currency or open_serial is None:
        return None

    fee = abs(raw_number(cells, 11) or 0.0)
    if event in OPTION_EVENTS:
        trade_type = core_trade_type(raw_text_value(core, cells, 1))
        capital = option_strategy_capital(core, cells, trade_type, event)
        fee = 0.0
        source = "option"
    else:
        qty = raw_number(cells, 8)
        fill = raw_number(cells, 9)
        capital = raw_number(cells, 12)
        if capital is None and qty is not None and fill is not None:
            capital = abs(qty * fill)
        source = "stock"
    if capital is None or abs(capital) <= 0.000001:
        return None

    close_serial = parse_float(cell_raw(cells, 4))
    return StockCapitalLot(
        currency=currency,
        open_serial=open_serial,
        close_serial=close_serial,
        capital=abs(capital) + fee,
        source=source,
    )


def active_capital_for_serial(lots: list[StockCapitalLot], serial: float) -> float:
    return sum(
        lot.capital
        for lot in lots
        if lot.open_serial <= serial and (lot.close_serial is None or lot.close_serial >= serial)
    )


def attach_dynamic_curve_capital(core, rows: list[tuple[int, dict[int, object]]], data: dict[str, object]) -> dict[str, object]:
    lots_by_currency: dict[str, list[StockCapitalLot]] = {}
    for _row_number, cells in rows:
        lot = stock_lot_from_row(core, cells)
        if lot:
            lots_by_currency.setdefault(lot.currency, []).append(lot)

    for series in data.get("curve_series", []) or []:
        if not isinstance(series, dict):
            continue
        currency = clean_text(series.get("currency"))
        lots = lots_by_currency.get(currency) or []
        is_history_series = clean_text(series.get("source")) == "history"
        if is_history_series:
            lots = [lot for lot in lots if lot.source == "option"]
        if not lots:
            continue
        last_capital = 0.0
        max_capital = parse_float(series.get("capital")) or 0.0
        for point in sorted(series.get("points", []) or [], key=lambda item: parse_float(item.get("serial")) or 0.0):
            if not isinstance(point, dict):
                continue
            serial = parse_float(point.get("serial"))
            if serial is None:
                continue
            capital = active_capital_for_serial(lots, serial)
            base_capital = parse_float(point.get("capital")) or 0.0
            if capital > 0.000001:
                last_capital = capital
                point["capital"] = base_capital + capital if is_history_series else capital
                max_capital = max(max_capital, parse_float(point.get("capital")) or 0.0)
            elif last_capital > 0.000001:
                point["capital"] = base_capital + last_capital if is_history_series else last_capital
                max_capital = max(max_capital, parse_float(point.get("capital")) or 0.0)
        if max_capital > 0.000001:
            series["capital"] = max_capital
    return data
