from __future__ import annotations

import json
import re
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .runtime import emit_progress
from .settings import FX_RATE_FALLBACKS_TO_CNY, FX_RATE_SECIDS_TO_CNY, FX_RATE_TENCENT_SYMBOLS_TO_CNY, FX_RATE_YAHOO_SYMBOLS_TO_CNY
from .utils import clean_name, clean_text, parse_float

_FX_RATES_TO_CNY: dict[str, float] | None = None
_FX_RATES_FUTURE: Future | None = None
_MARKET_DATA_EXECUTOR: ThreadPoolExecutor | None = None
MARKET_HTTP_TIMEOUT = 3
EASTMONEY_HTTP_TIMEOUT = 2
HKEX_HTTP_TIMEOUT = 3
HKEX_REQUEST_RETRIES = 2
MARKET_BATCH_SIZE = 80
YAHOO_BATCH_SIZE = 50
EASTMONEY_BATCH_FIELDS = "f12,f13,f14,f2,f1,f18"
EASTMONEY_SINGLE_FIELDS = "f57,f58,f43,f59,f60"
_HKEX_OPTION_ID_CACHE: dict[tuple[str, str, str, str], str | None] = {}


def chunks(items, size: int = MARKET_BATCH_SIZE):
    items = list(items)
    for index in range(0, len(items), size):
        yield items[index : index + size]


def cache_name(core, ticker, currency, name):
    from .names import cache_name as _cache_name
    return _cache_name(core, ticker, currency, name)


def scale_quote_field(value, precision) -> float | None:
    if value in ("", None) or precision in ("", None):
        return None
    try:
        return float(value) / (10 ** int(precision))
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def fetch_tencent_fx_rates_to_cny(symbols_by_currency: dict[str, str]) -> dict[str, float]:
    rates: dict[str, float] = {}
    symbol_to_currency = {symbol: currency for currency, symbol in symbols_by_currency.items() if clean_text(symbol)}
    if not symbol_to_currency:
        return rates
    url = f"https://qt.gtimg.cn/q={','.join(symbol_to_currency)}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=MARKET_HTTP_TIMEOUT) as response:
            text = response.read().decode("gb18030", "ignore")
    except (TimeoutError, URLError, OSError, ValueError):
        return rates
    for symbol, payload in re.findall(r"v_([^=]+)=\"([^\"]*)\"", text):
        currency = symbol_to_currency.get(symbol)
        if not currency:
            continue
        parts = payload.split("~")
        rate = parse_float(parts[3] if len(parts) > 3 else None)
        if isinstance(rate, (int, float)) and rate > 0:
            rates[currency] = float(rate)
    return rates


def display_currency_label(core, currency: str) -> str:
    raw = str(currency or "").strip()
    if not raw:
        return ""
    try:
        normalized = core.normalize_currency(raw)
    except Exception:
        normalized = raw.upper()
    if normalized in {"CNY", "CNH"} or raw in {"人民币", "RMB"}:
        return "人民币"
    if normalized == "HKD" or raw == "港币":
        return "港币"
    if normalized == "USD" or raw == "美元":
        return "美元"
    return raw


def normalize_quote_key(core, ticker, currency) -> tuple[str, str]:
    normalized_currency = core.normalize_currency(currency)
    return core.normalize_ticker(ticker, normalized_currency), normalized_currency


def quote_has_price(quote: object) -> bool:
    return isinstance(quote, dict) and isinstance(quote.get("last_price"), (int, float))


def eastmoney_quote_from_row(core, key: tuple[str, str], row: dict) -> dict:
    ticker, currency = key
    precision = row.get("f1") if row.get("f1") not in ("", None) else row.get("f59")
    quote_name = clean_name(row.get("f14") or row.get("f58"))
    return {
        "ticker": ticker,
        "name": quote_name,
        "last_price": scale_quote_field(row.get("f2", row.get("f43")), precision),
        "prev_close": scale_quote_field(row.get("f18", row.get("f60")), precision),
        "source": "Eastmoney",
    }


def cache_quote_name(core, key: tuple[str, str], quote: dict) -> None:
    ticker, currency = key
    quote_name = clean_name(quote.get("name"))
    if not quote_name:
        return
    cache_name(core, ticker, currency, quote_name)
    if hasattr(core, "cache_security_name"):
        core.cache_security_name(ticker, currency, quote_name)


def fetch_eastmoney_fx_rate_to_cny(secid: str) -> float | None:
    rows = fetch_eastmoney_batch_payload([secid])
    if not rows:
        return None
    return scale_quote_field(rows[0].get("f2"), rows[0].get("f1"))


def fetch_eastmoney_fx_rates_to_cny(secids_by_currency: dict[str, str]) -> dict[str, float]:
    rates: dict[str, float] = {}
    if not secids_by_currency:
        return rates
    rows = fetch_eastmoney_batch_payload(secids_by_currency.values())
    row_by_code = {clean_text(row.get("f12")): row for row in rows if isinstance(row, dict)}
    for currency, secid in secids_by_currency.items():
        code = secid.split(".", 1)[-1]
        row = row_by_code.get(code)
        if not row:
            continue
        rate = scale_quote_field(row.get("f2"), row.get("f1"))
        if isinstance(rate, (int, float)) and rate > 0:
            rates[currency] = float(rate)
    return rates


def fetch_yahoo_fx_rate_to_cny(symbol: str) -> float | None:
    if not clean_text(symbol):
        return None
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (TimeoutError, URLError, OSError, ValueError):
        return None
    try:
        result = payload["chart"]["result"][0]
        meta = result.get("meta") or {}
        price = meta.get("regularMarketPrice")
        if isinstance(price, (int, float)) and price > 0:
            return float(price)
        closes = (result.get("indicators") or {}).get("quote", [{}])[0].get("close") or []
        for close in reversed(closes):
            if isinstance(close, (int, float)) and close > 0:
                return float(close)
    except (KeyError, IndexError, TypeError):
        return None
    return None


def fetch_yahoo_fx_rates_to_cny(symbols_by_currency: dict[str, str]) -> dict[str, float]:
    rates: dict[str, float] = {}
    symbols = {currency: symbol for currency, symbol in symbols_by_currency.items() if clean_text(symbol)}
    if not symbols:
        return rates
    workers = min(4, len(symbols))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(fetch_yahoo_fx_rate_to_cny, symbol): currency
            for currency, symbol in symbols.items()
        }
        for future in as_completed(future_map):
            currency = future_map[future]
            try:
                rate = future.result()
            except Exception:
                rate = None
            if isinstance(rate, (int, float)) and rate > 0:
                rates[currency] = float(rate)
    return rates


def market_data_executor() -> ThreadPoolExecutor:
    global _MARKET_DATA_EXECUTOR
    if _MARKET_DATA_EXECUTOR is None:
        _MARKET_DATA_EXECUTOR = ThreadPoolExecutor(max_workers=4)
    return _MARKET_DATA_EXECUTOR


def compute_fx_rates_to_cny() -> dict[str, float]:
    emit_progress("读取汇率", "用于把不同币种的持仓仓位合并排序。", 38)
    rates = dict(FX_RATE_FALLBACKS_TO_CNY)
    rates["人民币"] = 1.0
    target_currencies = list(FX_RATE_TENCENT_SYMBOLS_TO_CNY)
    emit_progress("读取汇率", "优先读取腾讯港币/美元兑人民币汇率。", 39)
    try:
        tencent_rates = fetch_tencent_fx_rates_to_cny(FX_RATE_TENCENT_SYMBOLS_TO_CNY)
    except Exception:
        tencent_rates = {}
    live_currencies: set[str] = set()
    for currency, rate in tencent_rates.items():
        if currency in target_currencies and isinstance(rate, (int, float)) and rate > 0:
            rates[currency] = float(rate)
            live_currencies.add(currency)
    missing = [currency for currency in target_currencies if currency not in live_currencies]
    fetched = len(target_currencies) - len(missing)
    emit_progress("读取汇率", f"腾讯汇率完成，取到 {fetched}/{len(target_currencies)}。", 40)
    if not missing:
        return rates

    emit_progress("读取汇率", f"腾讯缺少 {'/'.join(missing)}，启动东方财富/Yahoo 兜底。", 41)
    eastmoney_rates: dict[str, float] = {}
    yahoo_rates: dict[str, float] = {}
    eastmoney_targets = {currency: FX_RATE_SECIDS_TO_CNY[currency] for currency in missing if currency in FX_RATE_SECIDS_TO_CNY}
    yahoo_targets = {currency: FX_RATE_YAHOO_SYMBOLS_TO_CNY[currency] for currency in missing if currency in FX_RATE_YAHOO_SYMBOLS_TO_CNY}
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_map = {
            executor.submit(fetch_eastmoney_fx_rates_to_cny, eastmoney_targets): "东方财富",
            executor.submit(fetch_yahoo_fx_rates_to_cny, yahoo_targets): "Yahoo",
        }
        for future in as_completed(future_map):
            source = future_map[future]
            try:
                source_rates = future.result()
            except Exception:
                source_rates = {}
            if source == "东方财富":
                eastmoney_rates = source_rates
            else:
                yahoo_rates = source_rates
            fetched = sum(1 for value in source_rates.values() if isinstance(value, (int, float)) and value > 0)
            emit_progress("读取汇率", f"{source} 兜底完成，取到 {fetched}/{len(missing)}。", 42)
    for currency in missing:
        rate = eastmoney_rates.get(currency)
        if not isinstance(rate, (int, float)):
            rate = yahoo_rates.get(currency)
        if isinstance(rate, (int, float)) and rate > 0:
            rates[currency] = float(rate)
    return rates


def start_fx_rates_prefetch() -> None:
    global _FX_RATES_FUTURE
    if _FX_RATES_TO_CNY is not None or _FX_RATES_FUTURE is not None:
        return
    _FX_RATES_FUTURE = market_data_executor().submit(compute_fx_rates_to_cny)


def current_fx_rates_to_cny() -> dict[str, float]:
    global _FX_RATES_FUTURE, _FX_RATES_TO_CNY
    if _FX_RATES_TO_CNY is not None:
        return _FX_RATES_TO_CNY
    if _FX_RATES_FUTURE is not None:
        try:
            _FX_RATES_TO_CNY = _FX_RATES_FUTURE.result()
            return _FX_RATES_TO_CNY
        except Exception:
            _FX_RATES_FUTURE = None
    _FX_RATES_TO_CNY = compute_fx_rates_to_cny()
    return _FX_RATES_TO_CNY


def option_kind_for_event(event: str):
    text = clean_text(event).lower()
    if text in {"认购", "call"}:
        return "CALL"
    if text in {"认沽", "put"}:
        return "PUT"
    return ""


def normalize_option_expiry(expiry: str) -> str:
    text = clean_text(expiry).replace("/", "-").replace(".", "-")
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if not match:
        return text
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def format_option_strike(strike) -> str:
    strike_value = parse_float(strike)
    if strike_value is None:
        return clean_text(strike)
    return f"{strike_value:.8f}".rstrip("0").rstrip(".")


def strip_hkex_hanweb_header(text: str) -> str:
    marker = "<!--SORC_HACK_HANWEB_END-->"
    if marker in text:
        return text.split(marker, 1)[1]
    return text


def hkex_option_type_for_event(event: str) -> str:
    option_kind = option_kind_for_event(event)
    if option_kind == "CALL":
        return "C"
    if option_kind == "PUT":
        return "P"
    return ""


def request_hkex_option_page(
    data: dict[str, str] | None = None,
    option_id: str | None = None,
    ucode: str = "",
    retries: int = HKEX_REQUEST_RETRIES,
) -> str:
    base_url = "https://www.hkex.com.hk/eng/sorc/options/stock_options_detail.aspx"
    if option_id:
        url = f"{base_url}?oID={option_id}&ucode={ucode}"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    else:
        request = Request(
            base_url,
            data=urlencode(data or {}).encode("utf-8"),
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": base_url,
            },
        )
    last_error = None
    for attempt in range(max(1, retries)):
        try:
            with urlopen(request, timeout=HKEX_HTTP_TIMEOUT) as response:
                return response.read().decode("utf-8", "ignore")
        except (TimeoutError, URLError, OSError) as error:
            last_error = error
            if attempt < retries - 1:
                time.sleep(0.15 * (attempt + 1))
    if last_error:
        raise last_error
    return ""


def fetch_hkex_option_id(core, ticker, event, expiry, strike) -> str | None:
    underlying = core.normalize_ticker(ticker, "HKD").zfill(5)
    option_type = hkex_option_type_for_event(str(event or ""))
    expiry_text = normalize_option_expiry(str(expiry or ""))
    strike_text = format_option_strike(strike)
    if not underlying or not option_type or not expiry_text or not strike_text:
        return None
    cache_key = (underlying, option_type, expiry_text, strike_text)
    if cache_key in _HKEX_OPTION_ID_CACHE:
        return _HKEX_OPTION_ID_CACHE[cache_key]

    try:
        html = request_hkex_option_page(
            {
                "action": "ajax",
                "type": "list",
                "underlying": underlying,
                "otype": option_type,
                "expiry": expiry_text,
                "strike": strike_text,
                "page": "1",
                "lang": "en",
            }
        )
    except (TimeoutError, URLError, OSError):
        _HKEX_OPTION_ID_CACHE[cache_key] = None
        return None

    html = strip_hkex_hanweb_header(html)
    match = re.search(r"oID=(\d+)&ucode=" + re.escape(underlying), html)
    if match:
        _HKEX_OPTION_ID_CACHE[cache_key] = match.group(1)
        return _HKEX_OPTION_ID_CACHE[cache_key]
    _HKEX_OPTION_ID_CACHE[cache_key] = None
    return None


def parse_hkex_option_detail(html: str) -> tuple[float | None, str]:
    # Prefer the visible bid/ask midpoint over the chart endpoint. The chart feed can lag
    # by a prior trading day, while the detail page carries the delayed live quote panel.
    text = clean_text(re.sub(r"<[^>]+>", " ", html))
    bid_ask_match = re.search(r"Bid / Ask\s+([0-9.,-]+)\s*/\s*([0-9.,-]+)", text, re.I)
    if bid_ask_match:
        bid = parse_float(bid_ask_match.group(1))
        ask = parse_float(bid_ask_match.group(2))
        if bid is not None and ask is not None and bid >= 0 and ask >= 0:
            midpoint = (bid + ask) / 2
            as_of_match = re.search(r"Last Traded Price\s+\(As of\s*([^)]*)\)", text, re.I)
            return midpoint, clean_text(as_of_match.group(1)) if as_of_match else ""

    as_of = ""
    price_match = re.search(
        r"Last Traded Price.*?\(As of\s*([^)]*)\).*?<span class=\"floatright col1b\"><strong>\s*([^<]+?)\s*</strong>",
        html,
        re.S | re.I,
    )
    if price_match:
        as_of = clean_text(price_match.group(1))
        return parse_float(price_match.group(2)), as_of

    text_price_match = re.search(r"Last Traded Price\s+\(As of\s*([^)]*)\)\s+([0-9.,-]+)", text, re.I)
    if text_price_match:
        return parse_float(text_price_match.group(2)), clean_text(text_price_match.group(1))
    return None, ""


def fetch_hkex_option_chart_last(option_id: str) -> float | None:
    request = Request(
        "https://www.hkex.com.hk/eng/sorc/swf/chartdata/chart.aspx",
        data=urlencode({"type": "1", "oID": option_id}).encode("utf-8"),
        headers={
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urlopen(request, timeout=6) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (TimeoutError, URLError, OSError, ValueError):
        return None
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list) or not rows:
        return None
    return parse_float(rows[0].get("olast") if isinstance(rows[0], dict) else None)


def fetch_hkex_option_quote(core, ticker, currency, event, expiry, strike) -> dict | None:
    if core.normalize_currency(currency) != "HKD":
        return None
    underlying = core.normalize_ticker(ticker, currency).zfill(5)
    option_id = fetch_hkex_option_id(core, underlying, event, expiry, strike)
    if not option_id:
        return None
    try:
        html = request_hkex_option_page(option_id=option_id, ucode=underlying, retries=1)
    except (TimeoutError, URLError, OSError):
        html = ""
    last_price, as_of = parse_hkex_option_detail(html)
    if last_price is None:
        for _attempt in range(1):
            try:
                html = request_hkex_option_page(option_id=option_id, ucode=underlying, retries=1)
            except (TimeoutError, URLError, OSError):
                continue
            last_price, as_of = parse_hkex_option_detail(html)
            if last_price is not None:
                break
    if last_price is None:
        return None
    return {
        "option_code": f"HKEX:{option_id}",
        "last_price": last_price,
        "source": "HKEX delayed detail",
        "as_of": as_of,
    }


def fetch_option_quote(core, ticker, currency, event, expiry, strike) -> dict | None:
    return fetch_hkex_option_quote(core, ticker, currency, event, expiry, strike)


def infer_secid(core, ticker, currency) -> str | None:
    normalized_ticker = core.normalize_ticker(ticker, currency)
    normalized_currency = core.normalize_currency(currency)
    if not normalized_ticker:
        return None
    if normalized_currency == "HKD":
        return f"116.{normalized_ticker.zfill(5)}"
    if normalized_ticker.isdigit():
        if normalized_ticker.startswith(("5", "6", "9")):
            return f"1.{normalized_ticker}"
        if normalized_ticker.startswith(("0", "1", "2", "3", "4", "8")):
            return f"0.{normalized_ticker}"
    return None


def eastmoney_row_lookup_key(row: dict) -> tuple[str, str]:
    market = clean_text(row.get("f13"))
    code = clean_text(row.get("f12"))
    if market == "116":
        code = code.zfill(5)
    return market, code


def fetch_eastmoney_batch_payload(secids, fields: str = EASTMONEY_BATCH_FIELDS) -> list[dict]:
    secid_list = [clean_text(secid) for secid in secids if clean_text(secid)]
    if not secid_list:
        return []
    url = (
        "https://push2.eastmoney.com/api/qt/ulist.np/get?"
        + urlencode({"secids": ",".join(secid_list), "fields": fields})
    )
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=EASTMONEY_HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (TimeoutError, URLError, OSError, ValueError):
        return []
    data = payload.get("data") if isinstance(payload, dict) else None
    rows = data.get("diff") if isinstance(data, dict) else None
    return rows if isinstance(rows, list) else []


def fetch_eastmoney_batch_payloads(secids, fields: str = EASTMONEY_BATCH_FIELDS) -> list[dict]:
    secid_groups = list(chunks(secids))
    if not secid_groups:
        return []
    if len(secid_groups) == 1:
        return fetch_eastmoney_batch_payload(secid_groups[0], fields)
    rows: list[dict] = []
    workers = min(4, len(secid_groups))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(fetch_eastmoney_batch_payload, group, fields): group for group in secid_groups}
        for future in as_completed(future_map):
            try:
                rows.extend(future.result())
            except Exception:
                continue
    return rows


def fetch_eastmoney_security_quotes(core, keys) -> dict[tuple[str, str], dict]:
    secid_to_key: dict[str, tuple[str, str]] = {}
    lookup_to_key: dict[tuple[str, str], tuple[str, str]] = {}
    for ticker, currency in keys:
        key = normalize_quote_key(core, ticker, currency)
        secid = infer_secid(core, key[0], key[1])
        if not secid:
            continue
        secid_to_key[secid] = key
        market, code = secid.split(".", 1)
        if market == "116":
            code = code.zfill(5)
        lookup_to_key[(market, code)] = key

    quotes: dict[tuple[str, str], dict] = {}
    rows = fetch_eastmoney_batch_payloads(secid_to_key)
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = lookup_to_key.get(eastmoney_row_lookup_key(row))
        if not key:
            continue
        quote = eastmoney_quote_from_row(core, key, row)
        if quote_has_price(quote):
            cache_quote_name(core, key, quote)
            quotes[key] = quote
    return quotes


def fetch_quote_payload(secid: str) -> dict | None:
    urls = [
        f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields={EASTMONEY_SINGLE_FIELDS}",
        f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields={EASTMONEY_SINGLE_FIELDS}",
    ]
    for url in urls:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=EASTMONEY_HTTP_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8", "ignore"))
            data = payload.get("data") if isinstance(payload, dict) else None
            if isinstance(data, dict):
                return data
        except (TimeoutError, URLError, OSError, ValueError):
            continue
    return None


def tencent_symbol(core, ticker, currency) -> str:
    normalized_ticker = core.normalize_ticker(ticker, currency)
    normalized_currency = core.normalize_currency(currency)
    if normalized_currency == "HKD":
        return f"hk{normalized_ticker.zfill(5)}"
    if normalized_currency == "USD":
        return f"us{normalized_ticker.upper()}"
    if normalized_currency == "CNY" and normalized_ticker.isdigit():
        market = "sh" if normalized_ticker.startswith(("5", "6", "9")) else "sz"
        return f"{market}{normalized_ticker}"
    return ""


def tencent_quote_from_payload(core, key: tuple[str, str], payload: str) -> dict | None:
    parts = payload.split("~")
    if len(parts) < 5:
        return None
    last_price = parse_float(parts[3])
    prev_close = parse_float(parts[4])
    if last_price is None:
        return None
    name = clean_name(parts[1])
    return {
        "ticker": key[0],
        "name": name,
        "last_price": last_price,
        "prev_close": prev_close,
        "source": "Tencent",
    }


def fetch_tencent_security_quotes(core, keys) -> dict[tuple[str, str], dict]:
    symbol_to_key: dict[str, tuple[str, str]] = {}
    for ticker, currency in keys:
        key = normalize_quote_key(core, ticker, currency)
        symbol = tencent_symbol(core, key[0], key[1])
        if symbol:
            symbol_to_key[symbol] = key
    if not symbol_to_key:
        return {}
    def fetch_group(symbol_group) -> dict[tuple[str, str], dict]:
        group_quotes: dict[tuple[str, str], dict] = {}
        url = f"https://qt.gtimg.cn/q={','.join(symbol_group)}"
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=MARKET_HTTP_TIMEOUT) as response:
                text = response.read().decode("gb18030", "ignore")
        except (TimeoutError, URLError, OSError, ValueError):
            return group_quotes
        for symbol, payload in re.findall(r"v_([^=]+)=\"([^\"]*)\"", text):
            key = symbol_to_key.get(symbol)
            if not key:
                continue
            quote = tencent_quote_from_payload(core, key, payload)
            if quote_has_price(quote):
                cache_quote_name(core, key, quote)
                group_quotes[key] = quote
        return group_quotes

    quotes: dict[tuple[str, str], dict] = {}
    symbol_groups = list(chunks(symbol_to_key))
    if len(symbol_groups) == 1:
        return fetch_group(symbol_groups[0])
    workers = min(4, len(symbol_groups))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {executor.submit(fetch_group, group): group for group in symbol_groups}
        for future in as_completed(future_map):
            try:
                quotes.update(future.result())
            except Exception:
                continue
    return quotes


def fetch_tencent_security_quote(core, ticker, currency) -> dict | None:
    key = normalize_quote_key(core, ticker, currency)
    return fetch_tencent_security_quotes(core, [key]).get(key)


def fetch_yahoo_security_quote(core, ticker, currency) -> dict | None:
    key = normalize_quote_key(core, ticker, currency)
    if key[1] != "USD" or not key[0]:
        return None
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{key[0]}?range=1d&interval=1d"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=MARKET_HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (TimeoutError, URLError, OSError, ValueError):
        return None
    try:
        result = payload["chart"]["result"][0]
        meta = result.get("meta") or {}
        last_price = meta.get("regularMarketPrice")
        prev_close = meta.get("chartPreviousClose") or meta.get("previousClose") or meta.get("regularMarketPreviousClose")
        if not isinstance(last_price, (int, float)):
            closes = (result.get("indicators") or {}).get("quote", [{}])[0].get("close") or []
            for close in reversed(closes):
                if isinstance(close, (int, float)) and close > 0:
                    last_price = close
                    break
        if not isinstance(last_price, (int, float)):
            return None
        return {
            "ticker": key[0],
            "name": key[0],
            "last_price": float(last_price),
            "prev_close": float(prev_close) if isinstance(prev_close, (int, float)) else None,
            "source": "Yahoo",
        }
    except (KeyError, IndexError, TypeError):
        return None


def yahoo_quote_from_result(core, key: tuple[str, str], result: dict) -> dict | None:
    last_price = result.get("regularMarketPrice")
    if not isinstance(last_price, (int, float)):
        return None
    prev_close = (
        result.get("regularMarketPreviousClose")
        or result.get("previousClose")
        or result.get("chartPreviousClose")
    )
    name = clean_name(result.get("shortName") or result.get("longName") or result.get("displayName") or key[0])
    return {
        "ticker": key[0],
        "name": name,
        "last_price": float(last_price),
        "prev_close": float(prev_close) if isinstance(prev_close, (int, float)) else None,
        "source": "Yahoo",
    }


def fetch_yahoo_security_quotes(core, keys) -> dict[tuple[str, str], dict]:
    symbol_to_key: dict[str, tuple[str, str]] = {}
    for ticker, currency in keys:
        key = normalize_quote_key(core, ticker, currency)
        if key[1] == "USD" and key[0]:
            symbol_to_key[key[0].upper()] = key
    if not symbol_to_key:
        return {}

    quotes: dict[tuple[str, str], dict] = {}
    for symbol_group in chunks(symbol_to_key, YAHOO_BATCH_SIZE):
        url = "https://query1.finance.yahoo.com/v7/finance/quote?" + urlencode({"symbols": ",".join(symbol_group)})
        request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urlopen(request, timeout=MARKET_HTTP_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8", "ignore"))
        except (TimeoutError, URLError, OSError, ValueError):
            continue
        results = ((payload.get("quoteResponse") or {}).get("result") or []) if isinstance(payload, dict) else []
        for result in results:
            if not isinstance(result, dict):
                continue
            symbol = clean_text(result.get("symbol")).upper()
            key = symbol_to_key.get(symbol)
            if not key:
                continue
            quote = yahoo_quote_from_result(core, key, result)
            if quote_has_price(quote):
                cache_quote_name(core, key, quote)
                quotes[key] = quote
    return quotes


def patch_quote_fetchers(core) -> None:
    security_quote_cache: dict[tuple[str, str], dict] = {}

    def fetch_security_quote(ticker, currency):
        key = normalize_quote_key(core, ticker, currency)
        if key in security_quote_cache:
            return security_quote_cache[key]
        normalized_ticker, normalized_currency = key

        secid = infer_secid(core, normalized_ticker, normalized_currency)
        if secid:
            eastmoney_quote = fetch_eastmoney_security_quotes(core, [key]).get(key)
            if quote_has_price(eastmoney_quote):
                security_quote_cache[key] = eastmoney_quote
                return eastmoney_quote

            data = fetch_quote_payload(secid)
            if isinstance(data, dict):
                quote = eastmoney_quote_from_row(core, key, data)
                if quote_has_price(quote):
                    cache_quote_name(core, key, quote)
                    security_quote_cache[key] = quote
                    return quote

        tencent_quote = fetch_tencent_security_quote(core, normalized_ticker, normalized_currency)
        if quote_has_price(tencent_quote):
            security_quote_cache[key] = tencent_quote
            return tencent_quote

        yahoo_quote = fetch_yahoo_security_quote(core, normalized_ticker, normalized_currency)
        if quote_has_price(yahoo_quote):
            security_quote_cache[key] = yahoo_quote
            return yahoo_quote

        security_quote_cache[key] = {}
        return security_quote_cache[key]

    def fetch_security_quotes(keys):
        quotes = {}
        sorted_keys = sorted(set(normalize_quote_key(core, ticker, currency) for ticker, currency in keys))
        if not sorted_keys:
            return quotes
        for key in sorted_keys:
            if key in security_quote_cache:
                quotes[key] = security_quote_cache[key]
        fetch_keys = [key for key in sorted_keys if key not in security_quote_cache]
        if not fetch_keys:
            return quotes
        total = len(sorted_keys)
        emit_progress("获取行情", f"批量获取 {len(fetch_keys)} 个标的的公开行情。", 42)

        tencent_quotes = fetch_tencent_security_quotes(core, fetch_keys)
        quotes.update(tencent_quotes)
        security_quote_cache.update(tencent_quotes)
        emit_progress("获取行情", f"腾讯批量行情完成，已取到 {sum(1 for key in sorted_keys if quote_has_price(quotes.get(key)))}/{total}。", 52)

        missing_keys = [key for key in fetch_keys if not quote_has_price(quotes.get(key))]
        if missing_keys:
            eastmoney_quotes = fetch_eastmoney_security_quotes(core, missing_keys)
            quotes.update(eastmoney_quotes)
            security_quote_cache.update(eastmoney_quotes)
            emit_progress("获取行情", f"东方财富补充行情完成，已取到 {sum(1 for key in sorted_keys if quote_has_price(quotes.get(key)))}/{total}。", 60)

        missing_keys = [key for key in fetch_keys if not quote_has_price(quotes.get(key))]
        if missing_keys:
            yahoo_quotes = fetch_yahoo_security_quotes(core, missing_keys)
            quotes.update(yahoo_quotes)
            security_quote_cache.update(yahoo_quotes)
            emit_progress("获取行情", f"Yahoo 美股批量行情完成，已取到 {sum(1 for key in sorted_keys if quote_has_price(quotes.get(key)))}/{total}。", 64)

        missing_keys = [key for key in fetch_keys if not quote_has_price(quotes.get(key))]
        if missing_keys:
            workers = min(6, len(missing_keys))
            completed = 0
            with ThreadPoolExecutor(max_workers=workers) as executor:
                future_map = {
                    executor.submit(fetch_security_quote, ticker, currency): (ticker, currency)
                    for ticker, currency in missing_keys
                }
                for future in as_completed(future_map):
                    ticker, currency = future_map[future]
                    try:
                        quotes[(ticker, currency)] = future.result()
                    except Exception:
                        quotes[(ticker, currency)] = {}
                    security_quote_cache[(ticker, currency)] = quotes[(ticker, currency)]
                    completed += 1
                    percent = 64 + (completed / len(missing_keys)) * 4
                    emit_progress("获取行情", f"补充行情 {completed}/{len(missing_keys)}：{ticker}", percent)

        for ticker, currency in sorted_keys:
            quote = quotes.get((ticker, currency), {})
            if not quote_has_price(quote):
                emit_progress("行情缺失", f"{ticker} {display_currency_label(core, currency)} 暂未取到公开现价。", 68)
                quotes[(ticker, currency)] = {}
                security_quote_cache[(ticker, currency)] = {}
        return quotes

    core.fetch_security_quote = fetch_security_quote
    core.fetch_security_quotes = fetch_security_quotes
