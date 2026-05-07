from __future__ import annotations

from datetime import datetime, timezone
from http.cookiejar import CookieJar
import json
import re
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from threading import Lock
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

from .runtime import SCRIPT_DIR, emit_progress
from .settings import FX_RATE_FALLBACKS_TO_CNY, FX_RATE_SECIDS_TO_CNY, FX_RATE_TENCENT_SYMBOLS_TO_CNY, FX_RATE_YAHOO_SYMBOLS_TO_CNY
from .utils import clean_name, clean_text, parse_float

_FX_RATES_TO_CNY: dict[str, float] | None = None
_FX_RATES_FUTURE: Future | None = None
_MARKET_DATA_EXECUTOR: ThreadPoolExecutor | None = None
MARKET_HTTP_TIMEOUT = 3
EASTMONEY_HTTP_TIMEOUT = 2
HKEX_HTTP_TIMEOUT = 3
HKEX_REQUEST_RETRIES = 2
US_OPTION_HTTP_TIMEOUT = 3
US_OPTION_CACHE_TTL_SECONDS = 15 * 60
MARKET_BATCH_SIZE = 80
YAHOO_BATCH_SIZE = 50
EASTMONEY_BATCH_FIELDS = "f12,f13,f14,f2,f1,f18"
EASTMONEY_SINGLE_FIELDS = "f57,f58,f43,f59,f60"
_HKEX_OPTION_ID_CACHE: dict[tuple[str, str, str, str], str | None] = {}
_US_OPTION_CHAIN_CACHE: dict[tuple[str, str], dict[tuple[str, str], dict]] = {}
_US_OPTION_CHAIN_FUTURES: dict[tuple[str, str], Future] = {}
_US_OPTION_CHAIN_LOCK = Lock()
_YAHOO_OPTION_OPENER = None
_YAHOO_OPTION_CRUMB: str | None = None
US_OPTION_CHAIN_CACHE_PATH = SCRIPT_DIR / "cache" / "us_option_chains.json"


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


def us_option_expiry_iso(expiry: str) -> str:
    return normalize_option_expiry(str(expiry or ""))


def us_option_expiry_timestamp(expiry: str) -> int | None:
    expiry_iso = us_option_expiry_iso(expiry)
    try:
        expiry_date = datetime.strptime(expiry_iso, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return int(expiry_date.timestamp())


def us_option_cache_key(core, ticker, expiry) -> tuple[str, str] | None:
    normalized_ticker = clean_text(core.normalize_ticker(ticker, "USD")).upper()
    expiry_iso = us_option_expiry_iso(str(expiry or ""))
    if not normalized_ticker or not expiry_iso:
        return None
    return normalized_ticker, expiry_iso


def us_occ_option_symbol(ticker: str, expiry_iso: str, kind: str, strike: object) -> str:
    strike_value = parse_float(strike)
    if strike_value is None:
        return ""
    try:
        expiry_date = datetime.strptime(expiry_iso, "%Y-%m-%d")
    except ValueError:
        return ""
    side = "C" if kind == "CALL" else "P"
    strike_code = int(round(float(strike_value) * 1000))
    return f"{ticker.upper()}{expiry_date:%y%m%d}{side}{strike_code:08d}"


def option_mark_price(bid, ask, last) -> float | None:
    bid_price = parse_float(bid)
    ask_price = parse_float(ask)
    last_price = parse_float(last)
    if bid_price is not None and ask_price is not None and bid_price >= 0 and ask_price > 0:
        return (float(bid_price) + float(ask_price)) / 2
    if last_price is not None and last_price >= 0:
        return float(last_price)
    if bid_price is not None and bid_price >= 0:
        return float(bid_price)
    if ask_price is not None and ask_price >= 0:
        return float(ask_price)
    return None


def yahoo_us_option_quote_from_contract(ticker: str, contract: dict) -> dict | None:
    if not isinstance(contract, dict):
        return None
    price = option_mark_price(contract.get("bid"), contract.get("ask"), contract.get("lastPrice"))
    if price is None:
        return None
    as_of = ""
    last_trade = contract.get("lastTradeDate")
    if isinstance(last_trade, (int, float)) and last_trade > 0:
        as_of = datetime.fromtimestamp(float(last_trade), timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "option_code": clean_text(contract.get("contractSymbol")) or "",
        "last_price": float(price),
        "source": "Yahoo option chain",
        "as_of": as_of,
    }


def parse_yahoo_us_option_chain(ticker: str, payload: dict) -> dict[tuple[str, str], dict]:
    chain: dict[tuple[str, str], dict] = {}
    try:
        result = payload["optionChain"]["result"][0]
    except (KeyError, IndexError, TypeError):
        return chain
    options = result.get("options") if isinstance(result, dict) else None
    if not isinstance(options, list):
        return chain
    for option_group in options:
        if not isinstance(option_group, dict):
            continue
        for field, kind in (("calls", "CALL"), ("puts", "PUT")):
            contracts = option_group.get(field)
            if not isinstance(contracts, list):
                continue
            for contract in contracts:
                if not isinstance(contract, dict):
                    continue
                strike = format_option_strike(contract.get("strike"))
                if not strike:
                    continue
                quote = yahoo_us_option_quote_from_contract(ticker, contract)
                if quote_has_price(quote):
                    chain[(kind, strike)] = quote
    return chain


def yahoo_option_opener_and_crumb():
    global _YAHOO_OPTION_CRUMB, _YAHOO_OPTION_OPENER
    if _YAHOO_OPTION_OPENER is not None and _YAHOO_OPTION_CRUMB:
        return _YAHOO_OPTION_OPENER, _YAHOO_OPTION_CRUMB
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        opener.open(Request("https://fc.yahoo.com", headers=headers), timeout=US_OPTION_HTTP_TIMEOUT).read()
    except (TimeoutError, URLError, OSError, ValueError):
        pass
    try:
        crumb = opener.open(
            Request("https://query1.finance.yahoo.com/v1/test/getcrumb", headers=headers),
            timeout=US_OPTION_HTTP_TIMEOUT,
        ).read().decode("utf-8", "ignore").strip()
    except (TimeoutError, URLError, OSError, ValueError):
        return None, ""
    if not crumb:
        return None, ""
    _YAHOO_OPTION_OPENER = opener
    _YAHOO_OPTION_CRUMB = crumb
    return opener, crumb


def fetch_yahoo_us_option_chain(core, ticker, expiry) -> dict[tuple[str, str], dict]:
    cache_key = us_option_cache_key(core, ticker, expiry)
    if cache_key is None:
        return {}
    normalized_ticker, _expiry_iso = cache_key
    expiry_timestamp = us_option_expiry_timestamp(expiry)
    if expiry_timestamp is None:
        return {}
    opener, crumb = yahoo_option_opener_and_crumb()
    if opener is None or not crumb:
        return {}
    url = "https://query1.finance.yahoo.com/v7/finance/options/" + normalized_ticker + "?" + urlencode(
        {"date": expiry_timestamp, "crumb": crumb}
    )
    try:
        with opener.open(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=US_OPTION_HTTP_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (TimeoutError, URLError, OSError, ValueError):
        return {}
    return parse_yahoo_us_option_chain(normalized_ticker, payload)


def nasdaq_us_option_quote_from_row(ticker: str, expiry_iso: str, kind: str, row: dict) -> dict | None:
    prefix = "c" if kind == "CALL" else "p"
    price = option_mark_price(row.get(f"{prefix}_Bid"), row.get(f"{prefix}_Ask"), row.get(f"{prefix}_Last"))
    if price is None:
        return None
    return {
        "option_code": us_occ_option_symbol(ticker, expiry_iso, kind, row.get("strike")),
        "last_price": float(price),
        "source": "Nasdaq option chain",
        "as_of": clean_text(row.get("expiryDate")),
    }


def parse_nasdaq_us_option_chain(ticker: str, expiry_iso: str, payload: dict) -> dict[tuple[str, str], dict]:
    chain: dict[tuple[str, str], dict] = {}
    try:
        rows = payload["data"]["table"]["rows"]
    except (KeyError, TypeError):
        return chain
    if not isinstance(rows, list):
        return chain
    for row in rows:
        if not isinstance(row, dict):
            continue
        strike = format_option_strike(row.get("strike"))
        if not strike:
            continue
        for kind in ("CALL", "PUT"):
            quote = nasdaq_us_option_quote_from_row(ticker, expiry_iso, kind, row)
            if quote_has_price(quote):
                chain[(kind, strike)] = quote
    return chain


def fetch_nasdaq_us_option_chain(core, ticker, expiry) -> dict[tuple[str, str], dict]:
    cache_key = us_option_cache_key(core, ticker, expiry)
    if cache_key is None:
        return {}
    normalized_ticker, expiry_iso = cache_key
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.nasdaq.com",
        "Referer": "https://www.nasdaq.com/",
    }
    for asset_class in ("etf", "stocks"):
        url = "https://api.nasdaq.com/api/quote/" + normalized_ticker + "/option-chain?" + urlencode(
            {
                "assetclass": asset_class,
                "fromdate": expiry_iso,
                "todate": expiry_iso,
                "limit": 10000,
            }
        )
        try:
            with urlopen(Request(url, headers=headers), timeout=US_OPTION_HTTP_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8", "ignore"))
        except (TimeoutError, URLError, OSError, ValueError):
            continue
        chain = parse_nasdaq_us_option_chain(normalized_ticker, expiry_iso, payload)
        if chain:
            return chain
    return {}


def encode_us_option_chain(chain: dict[tuple[str, str], dict]) -> list[dict]:
    rows = []
    for (kind, strike), quote in chain.items():
        if not quote_has_price(quote):
            continue
        row = {"kind": kind, "strike": strike}
        row.update(quote)
        rows.append(row)
    return rows


def decode_us_option_chain(rows: object) -> dict[tuple[str, str], dict]:
    chain: dict[tuple[str, str], dict] = {}
    if not isinstance(rows, list):
        return chain
    for row in rows:
        if not isinstance(row, dict):
            continue
        kind = clean_text(row.get("kind"))
        strike = clean_text(row.get("strike"))
        price = parse_float(row.get("last_price"))
        if kind not in {"CALL", "PUT"} or not strike or price is None:
            continue
        quote = {
            "option_code": clean_text(row.get("option_code")),
            "last_price": float(price),
            "source": clean_text(row.get("source")) or "Cached option chain",
            "as_of": clean_text(row.get("as_of")),
        }
        chain[(kind, strike)] = quote
    return chain


def load_us_option_chain_cache_file() -> dict:
    try:
        with US_OPTION_CHAIN_CACHE_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return {"chains": {}}
    if not isinstance(payload, dict):
        return {"chains": {}}
    chains = payload.get("chains")
    if not isinstance(chains, dict):
        payload["chains"] = {}
    return payload


def read_us_option_chain_file_cache(key: tuple[str, str]) -> dict[tuple[str, str], dict]:
    payload = load_us_option_chain_cache_file()
    entry = (payload.get("chains") or {}).get("|".join(key))
    if not isinstance(entry, dict):
        return {}
    fetched_at = parse_float(entry.get("fetched_at"))
    if fetched_at is None or time.time() - float(fetched_at) > US_OPTION_CACHE_TTL_SECONDS:
        return {}
    return decode_us_option_chain(entry.get("quotes"))


def write_us_option_chain_file_cache(key: tuple[str, str], chain: dict[tuple[str, str], dict]) -> None:
    if not chain:
        return
    payload = load_us_option_chain_cache_file()
    chains = payload.setdefault("chains", {})
    if not isinstance(chains, dict):
        chains = {}
        payload["chains"] = chains
    chains["|".join(key)] = {
        "fetched_at": time.time(),
        "quotes": encode_us_option_chain(chain),
    }
    try:
        US_OPTION_CHAIN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        US_OPTION_CHAIN_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError:
        return


def fetch_us_option_chain_uncached(core, ticker, expiry) -> dict[tuple[str, str], dict]:
    cache_key = us_option_cache_key(core, ticker, expiry)
    if cache_key is None:
        return {}
    cached = read_us_option_chain_file_cache(cache_key)
    if cached:
        return cached
    chain = fetch_yahoo_us_option_chain(core, ticker, expiry)
    if not chain:
        chain = fetch_nasdaq_us_option_chain(core, ticker, expiry)
    if chain:
        write_us_option_chain_file_cache(cache_key, chain)
    return chain


def fetch_us_option_chain(core, ticker, expiry) -> dict[tuple[str, str], dict]:
    cache_key = us_option_cache_key(core, ticker, expiry)
    if cache_key is None:
        return {}
    with _US_OPTION_CHAIN_LOCK:
        cached = _US_OPTION_CHAIN_CACHE.get(cache_key)
        if cached is not None:
            return cached
        future = _US_OPTION_CHAIN_FUTURES.get(cache_key)
        if future is None:
            future = market_data_executor().submit(fetch_us_option_chain_uncached, core, ticker, expiry)
            _US_OPTION_CHAIN_FUTURES[cache_key] = future
    try:
        chain = future.result()
    except Exception:
        chain = {}
    with _US_OPTION_CHAIN_LOCK:
        _US_OPTION_CHAIN_CACHE[cache_key] = chain
        if _US_OPTION_CHAIN_FUTURES.get(cache_key) is future:
            _US_OPTION_CHAIN_FUTURES.pop(cache_key, None)
    return chain


def fetch_us_option_quote(core, ticker, currency, event, expiry, strike) -> dict | None:
    if core.normalize_currency(currency) != "USD":
        return None
    option_kind = option_kind_for_event(event)
    if option_kind not in {"CALL", "PUT"}:
        return None
    chain = fetch_us_option_chain(core, ticker, expiry)
    quote = chain.get((option_kind, format_option_strike(strike)))
    return quote if quote_has_price(quote) else None


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
    normalized_currency = core.normalize_currency(currency)
    if normalized_currency == "HKD":
        return fetch_hkex_option_quote(core, ticker, currency, event, expiry, strike)
    if normalized_currency == "USD":
        return fetch_us_option_quote(core, ticker, currency, event, expiry, strike)
    return None


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
