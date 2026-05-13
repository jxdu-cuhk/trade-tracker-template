from __future__ import annotations

from .market_data import current_fx_rates_to_cny
from .utils import clean_text


REPORTING_CURRENCIES = ("人民币", "港币", "美元")


def reporting_rate_to_cny(label: object, rates: dict[str, float] | None = None) -> float:
    currency = clean_text(label) or "人民币"
    if rates is None:
        rates = current_fx_rates_to_cny()
    rate = rates.get(currency, 1.0)
    if not isinstance(rate, (int, float)) or rate <= 0:
        return 1.0
    return float(rate)


def reporting_currency_options(rates: dict[str, float] | None = None) -> list[dict[str, object]]:
    if rates is None:
        rates = current_fx_rates_to_cny()
    return [
        {
            "label": currency,
            "rateToCny": reporting_rate_to_cny(currency, rates),
        }
        for currency in REPORTING_CURRENCIES
    ]
