from __future__ import annotations

import json
import re
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import URLError
from urllib.request import Request, urlopen

from .runtime import FUTU_HOST, FUTU_PORT, emit_progress
from .settings import FX_RATE_FALLBACKS_TO_CNY, FX_RATE_SECIDS_TO_CNY, FX_RATE_YAHOO_SYMBOLS_TO_CNY
from .utils import clean_name, clean_text, parse_float

_FUTU_OPEND_AVAILABLE: bool | None = None
_FX_RATES_TO_CNY: dict[str, float] | None = None


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


def fetch_eastmoney_fx_rate_to_cny(secid: str) -> float | None:
    data = fetch_quote_payload(secid)
    if not isinstance(data, dict):
        return None
    return scale_quote_field(data.get("f43"), data.get("f59"))


def fetch_yahoo_fx_rate_to_cny(symbol: str) -> float | None:
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


def current_fx_rates_to_cny() -> dict[str, float]:
    global _FX_RATES_TO_CNY
    if _FX_RATES_TO_CNY is not None:
        return _FX_RATES_TO_CNY

    emit_progress("读取汇率", "用于把不同币种的持仓仓位合并排序。", 38)
    rates = dict(FX_RATE_FALLBACKS_TO_CNY)
    rates["人民币"] = 1.0
    for currency, secid in FX_RATE_SECIDS_TO_CNY.items():
        emit_progress("读取汇率", f"等待{currency}兑人民币汇率。", 39)
        rate = fetch_eastmoney_fx_rate_to_cny(secid)
        if rate is None:
            rate = fetch_yahoo_fx_rate_to_cny(FX_RATE_YAHOO_SYMBOLS_TO_CNY.get(currency, ""))
        if isinstance(rate, (int, float)) and rate > 0:
            rates[currency] = float(rate)
    _FX_RATES_TO_CNY = rates
    return rates


def futu_opend_available() -> bool:
    global _FUTU_OPEND_AVAILABLE
    if _FUTU_OPEND_AVAILABLE is not None:
        return _FUTU_OPEND_AVAILABLE
    try:
        with socket.create_connection((FUTU_HOST, FUTU_PORT), timeout=0.25):
            _FUTU_OPEND_AVAILABLE = True
    except OSError:
        _FUTU_OPEND_AVAILABLE = False
    return _FUTU_OPEND_AVAILABLE


def futu_symbol(core, ticker, currency) -> str:
    normalized_ticker = core.normalize_ticker(ticker, currency)
    normalized_currency = core.normalize_currency(currency)
    if normalized_currency == "HKD":
        return f"HK.{normalized_ticker.zfill(5)}"
    if normalized_currency == "USD":
        return f"US.{normalized_ticker.upper()}"
    if normalized_currency == "CNY" and normalized_ticker.isdigit():
        market = "SH" if normalized_ticker.startswith(("5", "6", "9")) else "SZ"
        return f"{market}.{normalized_ticker}"
    return ""


def fetch_futu_security_quote(core, ticker, currency) -> dict | None:
    if not futu_opend_available():
        return None
    symbol = futu_symbol(core, ticker, currency)
    if not symbol:
        return None
    try:
        import futu as ft
    except ImportError:
        return None
    quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    try:
        ret, data = quote_ctx.get_market_snapshot([symbol])
        if ret != ft.RET_OK or data is None or len(data) == 0:
            return None
        row = data.iloc[0]
        name = clean_name(row.get("stock_name") or row.get("name"))
        last_price = row.get("last_price")
        prev_close = row.get("prev_close_price") or row.get("prev_close")
        return {
            "ticker": core.normalize_ticker(ticker, currency),
            "name": name,
            "last_price": float(last_price) if last_price not in ("", None) else None,
            "prev_close": float(prev_close) if prev_close not in ("", None) else None,
        }
    except Exception:
        return None
    finally:
        try:
            quote_ctx.close()
        except Exception:
            pass


def futu_option_type_for_event(event: str):
    text = clean_text(event).lower()
    if text in {"认购", "call"}:
        return "CALL"
    if text in {"认沽", "put"}:
        return "PUT"
    return ""


def option_expiry_for_futu(expiry: str) -> str:
    text = clean_text(expiry).replace("/", "-").replace(".", "-")
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", text)
    if not match:
        return text
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def fetch_futu_option_quote(core, ticker, currency, event, expiry, strike) -> dict | None:
    if not futu_opend_available():
        return None
    underlying = futu_symbol(core, ticker, currency)
    option_kind = futu_option_type_for_event(str(event or ""))
    strike_value = parse_float(strike)
    expiry_text = option_expiry_for_futu(str(expiry or ""))
    if not underlying or not option_kind or strike_value is None or not expiry_text:
        return None
    try:
        import futu as ft
    except ImportError:
        return None

    option_type = ft.OptionType.CALL if option_kind == "CALL" else ft.OptionType.PUT
    quote_ctx = ft.OpenQuoteContext(host=FUTU_HOST, port=FUTU_PORT)
    try:
        ret, data = quote_ctx.get_option_chain(
            underlying,
            start=expiry_text,
            end=expiry_text,
            option_type=option_type,
        )
        if ret != ft.RET_OK or data is None or len(data) == 0:
            return None

        code = ""
        closest_row = None
        closest_distance = None
        for _index, row in data.iterrows():
            row_strike = None
            for column in ("strike_price", "strike", "exercise_price"):
                row_strike = parse_float(row.get(column))
                if row_strike is not None:
                    break
            if row_strike is None:
                continue
            distance = abs(row_strike - strike_value)
            if closest_distance is None or distance < closest_distance:
                closest_row = row
                closest_distance = distance
        if closest_row is None or closest_distance is None or closest_distance > 0.000001:
            return None

        for column in ("code", "option_code", "stock_code"):
            raw_code = closest_row.get(column)
            if raw_code not in ("", None):
                code = str(raw_code)
                break

        last_price = None
        for column in ("last_price", "cur_price", "price"):
            last_price = parse_float(closest_row.get(column))
            if last_price is not None:
                break

        if code:
            ret, snapshot = quote_ctx.get_market_snapshot([code])
            if ret == ft.RET_OK and snapshot is not None and len(snapshot) > 0:
                snap_row = snapshot.iloc[0]
                for column in ("last_price", "cur_price", "price"):
                    snapshot_price = parse_float(snap_row.get(column))
                    if snapshot_price is not None:
                        last_price = snapshot_price
                        break

        return {"option_code": code, "last_price": last_price}
    except Exception:
        return None
    finally:
        try:
            quote_ctx.close()
        except Exception:
            pass


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


def fetch_quote_payload(secid: str) -> dict | None:
    fields = "f57,f58,f43,f59,f60"
    urls = [
        f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields={fields}",
        f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields={fields}",
    ]
    for _ in range(5):
        for url in urls:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            try:
                with urlopen(request, timeout=5) as response:
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
    if normalized_currency == "CNY" and normalized_ticker.isdigit():
        market = "sh" if normalized_ticker.startswith(("5", "6", "9")) else "sz"
        return f"{market}{normalized_ticker}"
    return ""


def fetch_tencent_security_quote(core, ticker, currency) -> dict | None:
    symbol = tencent_symbol(core, ticker, currency)
    if not symbol:
        return None
    url = f"https://qt.gtimg.cn/q={symbol}"
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=5) as response:
            text = response.read().decode("gb18030", "ignore")
    except (TimeoutError, URLError, OSError, ValueError):
        return None
    match = re.search(r'="([^"]*)"', text)
    if not match:
        return None
    parts = match.group(1).split("~")
    if len(parts) < 5:
        return None
    last_price = parse_float(parts[3])
    prev_close = parse_float(parts[4])
    if last_price is None:
        return None
    name = clean_name(parts[1])
    normalized_currency = core.normalize_currency(currency)
    return {
        "ticker": core.normalize_ticker(ticker, normalized_currency),
        "name": name,
        "last_price": last_price,
        "prev_close": prev_close,
    }


def patch_quote_fetchers(core) -> None:
    def fetch_security_quote(ticker, currency):
        normalized_ticker = core.normalize_ticker(ticker, currency)
        normalized_currency = core.normalize_currency(currency)

        futu_quote = fetch_futu_security_quote(core, normalized_ticker, normalized_currency)
        if isinstance(futu_quote, dict):
            if futu_quote.get("name"):
                cache_name(core, normalized_ticker, normalized_currency, futu_quote["name"])
            if isinstance(futu_quote.get("last_price"), (int, float)):
                return futu_quote

        secid = infer_secid(core, normalized_ticker, normalized_currency)
        if not secid:
            return {}

        data = fetch_quote_payload(secid)
        if not isinstance(data, dict):
            tencent_quote = fetch_tencent_security_quote(core, normalized_ticker, normalized_currency)
            if isinstance(tencent_quote, dict):
                if tencent_quote.get("name"):
                    cache_name(core, normalized_ticker, normalized_currency, tencent_quote["name"])
                return tencent_quote
            return {}

        precision = data.get("f59")
        quote_name = core.raw_text(data.get("f58")) if hasattr(core, "raw_text") else str(data.get("f58") or "").strip()
        if quote_name:
            cache_name(core, normalized_ticker, normalized_currency, quote_name)
            if hasattr(core, "cache_security_name"):
                core.cache_security_name(normalized_ticker, normalized_currency, quote_name)
        result = {
            "ticker": normalized_ticker,
            "name": quote_name,
            "last_price": scale_quote_field(data.get("f43"), precision),
            "prev_close": scale_quote_field(data.get("f60"), precision),
        }
        if not isinstance(result.get("last_price"), (int, float)):
            tencent_quote = fetch_tencent_security_quote(core, normalized_ticker, normalized_currency)
            if isinstance(tencent_quote, dict):
                if tencent_quote.get("name"):
                    cache_name(core, normalized_ticker, normalized_currency, tencent_quote["name"])
                return tencent_quote
        return result

    def fetch_security_quotes(keys):
        quotes = {}
        sorted_keys = sorted(keys)
        if not sorted_keys:
            return quotes
        total = len(sorted_keys)
        emit_progress("获取行情", f"准备获取 {total} 个标的的现价和昨日收盘。", 42)
        workers = min(4, len(sorted_keys))
        completed = 0
        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {
                executor.submit(fetch_security_quote, ticker, currency): (ticker, currency)
                for ticker, currency in sorted_keys
            }
            for future in as_completed(future_map):
                ticker, currency = future_map[future]
                try:
                    quotes[(ticker, currency)] = future.result()
                except Exception:
                    quotes[(ticker, currency)] = {}
                completed += 1
                percent = 42 + (completed / total) * 24
                currency_label = display_currency_label(core, currency)
                emit_progress("获取行情", f"等待实时行情 {completed}/{total}：{ticker} {currency_label}", percent)
        for ticker, currency in sorted_keys:
            quote = quotes.get((ticker, currency), {})
            if not isinstance(quote.get("last_price"), (int, float)):
                emit_progress("重试行情", f"{ticker} {display_currency_label(core, currency)} 首次未取到现价，正在重试。", 68)
                quotes[(ticker, currency)] = fetch_security_quote(ticker, currency)
        return quotes

    core.fetch_security_quote = fetch_security_quote
    core.fetch_security_quotes = fetch_security_quotes
