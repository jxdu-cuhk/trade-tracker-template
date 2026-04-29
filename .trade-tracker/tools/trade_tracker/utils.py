from __future__ import annotations

import re
from datetime import date, timedelta

from .settings import TYPE_TO_CORE_CODE


def cell_text(cell_html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell_html)).strip()


def clean_text(value) -> str:
    if value is None:
        return ""
    text = str(value).replace("\u3000", " ").strip()
    return re.sub(r"\s+", " ", text)


def clean_name(value) -> str:
    text = clean_text(value)
    if not text or text in {"--", "-", "None", "nan", "NaN", "汇总"}:
        return ""
    return text


def normalize_source_code(value) -> str:
    text = clean_text(value)
    if not text:
        return ""
    text = re.sub(r"\.0$", "", text)
    text = re.sub(r"^(SH|SZ|HK|US)\.?", "", text, flags=re.I)
    return text.strip().upper()


def parse_float(value) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def date_key(value):
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date()
    text = clean_text(value)
    if not text:
        return None
    for pattern in (r"(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})", r"(\d{1,2})[-/\.](\d{1,2})"):
        match = re.search(pattern, text)
        if not match:
            continue
        parts = [int(part) for part in match.groups()]
        try:
            if len(parts) == 3:
                from datetime import date

                return date(parts[0], parts[1], parts[2])
        except ValueError:
            return None
    return None


def format_date(value) -> str:
    return value.strftime("%Y/%m/%d") if value else "-"


def excel_serial_to_date(value) -> date | None:
    numeric = parse_float(value)
    if numeric is None:
        return date_key(value)
    try:
        return date(1899, 12, 30) + timedelta(days=int(numeric))
    except (OverflowError, ValueError):
        return None


def cell_raw(cells: dict[int, object], column: int):
    cell = cells.get(column)
    return getattr(cell, "raw", None)


def raw_number(cells: dict[int, object], column: int) -> float | None:
    return parse_float(cell_raw(cells, column))


def raw_text_value(core, cells: dict[int, object], column: int) -> str:
    raw = cell_raw(cells, column)
    try:
        return clean_text(core.raw_text(raw))
    except Exception:
        return clean_text(raw)


def core_trade_type(raw_type: str) -> str:
    return TYPE_TO_CORE_CODE.get(clean_text(raw_type), clean_text(raw_type).lower())


def format_money_text(currency_label: str, value: float | None) -> str:
    if value is None:
        return "--"
    return f"{currency_label} {value:,.2f}" if currency_label else f"{value:,.2f}"


def format_signed_percent(value: float | None) -> str:
    if value is None:
        return "--"
    return f"{value * 100:.2f}%"


def parse_display_number(value: object) -> float | None:
    text = clean_text(value).replace(",", "").replace("%", "")
    text = re.sub(r"^(人民币|港币|美元)\s+", "", text).strip()
    if not text or text in {"-", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def currency_amounts_from_text(text: object) -> dict[str, float]:
    amounts: dict[str, float] = {}
    for part in clean_text(text).split("/"):
        part = part.strip()
        match = re.match(r"^(人民币|港币|美元)\s+(.+)$", part)
        if not match:
            continue
        amount = parse_display_number(match.group(2))
        if amount is not None:
            amounts[match.group(1)] = amount
    return amounts


def format_currency_amounts(amounts: dict[str, float]) -> str:
    rendered = [f"{currency} {amount:,.2f}" for currency, amount in amounts.items() if abs(amount) >= 0.005]
    return " / ".join(rendered) if rendered else "暂无"


def add_amount_to_text(text: object, currency: str, amount: float) -> str:
    amounts = currency_amounts_from_text(text)
    amounts[currency] = amounts.get(currency, 0.0) + amount
    return format_currency_amounts(amounts)
