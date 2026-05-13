from __future__ import annotations

import html
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .historical_curve import SecurityHistoryPoint, fetch_tencent_history_points, fetch_yahoo_history_points
from .market_data import current_fx_rates_to_cny
from .runtime import APP_DIR, emit_progress
from .utils import clean_text, parse_float

COMBINED_CURRENCY = "人民币折算"
COMBINED_CODE = "CNY"
BENCHMARKS = [
    {"id": "sse", "market": "A股", "label": "上证指数", "short_label": "上证", "secid": "1.000001", "tencent": "sh000001"},
    {"id": "szse", "market": "A股", "label": "深证成指", "short_label": "深证", "secid": "0.399001", "tencent": "sz399001"},
    {"id": "chinext", "market": "A股", "label": "创业板指", "short_label": "创业板", "secid": "0.399006", "tencent": "sz399006"},
    {"id": "sse50", "market": "A股", "label": "上证50", "short_label": "上证50", "secid": "1.000016", "tencent": "sh000016"},
    {"id": "csi300", "market": "A股", "label": "沪深300", "short_label": "沪深300", "secid": "1.000300", "tencent": "sh000300"},
    {"id": "csi500", "market": "A股", "label": "中证500", "short_label": "中证500", "secid": "1.000905", "tencent": "sh000905"},
    {
        "id": "star",
        "market": "A股",
        "label": "科创综指",
        "short_label": "科创综指",
        "secid": "1.000680",
        "tencent": "sh000680",
        "csindex": "000680",
    },
    {"id": "star50", "market": "A股", "label": "科创50", "short_label": "科创50", "secid": "1.000688", "tencent": "sh000688"},
    {"id": "hsi", "market": "港股", "label": "恒生指数", "short_label": "恒指", "tencent": "hkHSI", "yahoo": "^HSI"},
    {"id": "hstech", "market": "港股", "label": "恒生科技", "short_label": "恒科", "tencent": "hkHSTECH"},
    {"id": "hscei", "market": "港股", "label": "国企指数", "short_label": "国企", "tencent": "hkHSCEI", "yahoo": "^HSCE"},
    {"id": "sp500", "market": "美股", "label": "标普500", "short_label": "标普500", "yahoo": "^GSPC"},
    {"id": "nasdaq", "market": "美股", "label": "纳斯达克", "short_label": "纳指", "yahoo": "^IXIC"},
    {"id": "dow", "market": "美股", "label": "道琼斯", "short_label": "道指", "yahoo": "^DJI"},
    {"id": "russell2000", "market": "美股", "label": "罗素2000", "short_label": "罗素", "yahoo": "^RUT"},
]
COMBINED_BENCHMARK = BENCHMARKS[0]
BENCHMARK_TIMEOUT = 8
BENCHMARK_CACHE_PATH = APP_DIR / "tools" / "cache" / "benchmark_history.json"
BENCHMARK_CACHE_TTL_DAYS = 7
BENCHMARK_FETCH_WORKERS = 12


def date_iso(value: object) -> str:
    text = clean_text(value)
    compact_match = re.match(r"^(\d{4})(\d{2})(\d{2})$", text)
    if compact_match:
        year, month, day = (int(part) for part in compact_match.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"
    match = re.match(r"^(\d{4})[-/\.](\d{1,2})[-/\.](\d{1,2})$", text)
    if not match:
        return ""
    year, month, day = (int(part) for part in match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}"


def date_label_from_iso(iso: str) -> str:
    return iso.replace("-", "/")


def excel_serial_from_iso(iso: str) -> float | None:
    try:
        year, month, day = (int(part) for part in iso.split("-"))
        return float((date(year, month, day) - date(1899, 12, 30)).days)
    except (TypeError, ValueError):
        return None


def benchmark_cache_key(secid: str, start_iso: str, end_iso: str) -> str:
    return f"{secid}|{start_iso}|{end_iso}"


def load_benchmark_cache() -> dict[str, object]:
    try:
        payload = json.loads(BENCHMARK_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    ranges = payload.get("ranges")
    if not isinstance(ranges, dict):
        payload["ranges"] = {}
    payload["version"] = 1
    return payload


def save_benchmark_cache(payload: dict[str, object]) -> None:
    try:
        BENCHMARK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        BENCHMARK_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return


def cache_entry_points(entry: object) -> list[dict[str, object]]:
    if not isinstance(entry, dict):
        return []
    points = entry.get("points")
    return list(points) if isinstance(points, list) else []


def is_cache_entry_fresh(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    try:
        fetched_at = date.fromisoformat(clean_text(entry.get("fetched_at")))
    except ValueError:
        return False
    return (date.today() - fetched_at).days <= BENCHMARK_CACHE_TTL_DAYS


def points_cover_start(points: list[dict[str, object]], start_iso: str) -> bool:
    if not points or not start_iso:
        return False
    first_iso = clean_text(points[0].get("iso"))
    return bool(first_iso and first_iso <= start_iso)


def requires_start_coverage(benchmark: dict[str, object]) -> bool:
    return bool(clean_text(benchmark.get("csindex")))


def benchmark_definition(identifier: object) -> dict[str, object]:
    if isinstance(identifier, dict):
        return dict(identifier)
    text = clean_text(identifier)
    for benchmark in BENCHMARKS:
        aliases = {
            clean_text(benchmark.get("id")),
            clean_text(benchmark.get("secid")),
            clean_text(benchmark.get("tencent")),
            clean_text(benchmark.get("yahoo")),
        }
        if text and text in aliases:
            return dict(benchmark)
    return {"id": text, "label": text or "市场基准", "secid": text}


def benchmark_cache_identifier(benchmark: dict[str, object]) -> str:
    return (
        clean_text(benchmark.get("cache_key"))
        or clean_text(benchmark.get("secid"))
        or clean_text(benchmark.get("yahoo"))
        or clean_text(benchmark.get("tencent"))
        or clean_text(benchmark.get("id"))
    )


def history_points_to_benchmark_points(points: list[SecurityHistoryPoint]) -> list[dict[str, object]]:
    converted = []
    for point in points:
        serial = excel_serial_from_iso(point.iso)
        if serial is None:
            continue
        converted.append(
            {
                "date": date_label_from_iso(point.iso),
                "iso": point.iso,
                "serial": serial,
                "close": point.close,
            }
        )
    return converted


def benchmark_tencent_symbol(secid: str) -> str:
    benchmark = benchmark_definition(secid)
    symbol = clean_text(benchmark.get("tencent"))
    if symbol:
        return symbol
    return {
        "0.399001": "sz399001",
        "0.399006": "sz399006",
        "1.000001": "sh000001",
        "1.000016": "sh000016",
        "1.000300": "sh000300",
        "1.000680": "sh000680",
        "1.000688": "sh000688",
        "1.000905": "sh000905",
    }.get(clean_text(secid), "")


def fetch_tencent_benchmark_points(symbol: str, start_iso: str, end_iso: str) -> list[dict[str, object]]:
    symbol = clean_text(symbol)
    if not symbol or not start_iso or not end_iso:
        return []
    try:
        start = date.fromisoformat(start_iso)
        end = date.fromisoformat(end_iso)
    except ValueError:
        return []
    return history_points_to_benchmark_points(fetch_tencent_history_points(symbol, start, end))


def fetch_yahoo_benchmark_points(symbol: str, start_iso: str, end_iso: str) -> list[dict[str, object]]:
    symbol = clean_text(symbol)
    if not symbol or not start_iso or not end_iso:
        return []
    try:
        start = date.fromisoformat(start_iso)
        end = date.fromisoformat(end_iso)
    except ValueError:
        return []
    return history_points_to_benchmark_points(fetch_yahoo_history_points(symbol, start, end))


def fetch_eastmoney_benchmark_points(secid: str, start_iso: str, end_iso: str) -> list[dict[str, object]]:
    if not secid or not start_iso or not end_iso:
        return []
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": "101",
        "fqt": "1",
        "beg": start_iso.replace("-", ""),
        "end": end_iso.replace("-", ""),
    }
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=BENCHMARK_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (TimeoutError, URLError, OSError, ValueError):
        return []
    rows = ((payload.get("data") or {}).get("klines") or []) if isinstance(payload, dict) else []
    points = []
    for row in rows:
        parts = clean_text(row).split(",")
        if len(parts) < 3:
            continue
        iso = date_iso(parts[0])
        close = parse_float(parts[2])
        serial = excel_serial_from_iso(iso)
        if not iso or close is None or serial is None:
            continue
        points.append(
            {
                "date": date_label_from_iso(iso),
                "iso": iso,
                "serial": serial,
                "close": close,
            }
        )
    return points


def fetch_csindex_benchmark_points(index_code: str, start_iso: str, end_iso: str) -> list[dict[str, object]]:
    index_code = clean_text(index_code)
    if not index_code or not start_iso or not end_iso:
        return []
    params = {
        "indexCode": index_code,
        "startDate": start_iso.replace("-", ""),
        "endDate": end_iso.replace("-", ""),
    }
    url = "https://www.csindex.com.cn/csindex-home/perf/index-perf?" + urlencode(params)
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urlopen(request, timeout=BENCHMARK_TIMEOUT) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except (TimeoutError, URLError, OSError, ValueError):
        return []
    rows = payload.get("data") if isinstance(payload, dict) and clean_text(payload.get("code")) == "200" else []
    if not isinstance(rows, list):
        return []
    points = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        iso = date_iso(row.get("tradeDate"))
        close = parse_float(row.get("close"))
        serial = excel_serial_from_iso(iso)
        if not iso or close is None or serial is None:
            continue
        points.append(
            {
                "date": date_label_from_iso(iso),
                "iso": iso,
                "serial": serial,
                "close": close,
            }
        )
    return sorted({clean_text(point["iso"]): point for point in points}.values(), key=lambda item: str(item["iso"]))


def fetch_benchmark_points_online(identifier: object, start_iso: str, end_iso: str) -> list[dict[str, object]]:
    benchmark = benchmark_definition(identifier)
    secid = clean_text(benchmark.get("secid"))
    tencent_symbol = clean_text(benchmark.get("tencent")) or benchmark_tencent_symbol(secid)
    points = fetch_tencent_benchmark_points(tencent_symbol, start_iso, end_iso)
    if points:
        csindex_code = clean_text(benchmark.get("csindex"))
        if csindex_code and not points_cover_start(points, start_iso):
            csindex_points = fetch_csindex_benchmark_points(csindex_code, start_iso, end_iso)
            if csindex_points:
                return csindex_points
        return points
    yahoo_symbol = clean_text(benchmark.get("yahoo"))
    points = fetch_yahoo_benchmark_points(yahoo_symbol, start_iso, end_iso)
    if points:
        return points
    points = fetch_csindex_benchmark_points(clean_text(benchmark.get("csindex")), start_iso, end_iso)
    if points:
        return points
    return fetch_eastmoney_benchmark_points(secid, start_iso, end_iso)


def fetch_benchmark_points(identifier: object, start_iso: str, end_iso: str) -> list[dict[str, object]]:
    benchmark = benchmark_definition(identifier)
    cache_id = benchmark_cache_identifier(benchmark)
    if not cache_id or not start_iso or not end_iso:
        return []
    cache = load_benchmark_cache()
    ranges = cache.get("ranges")
    if not isinstance(ranges, dict):
        ranges = {}
        cache["ranges"] = ranges
    key = benchmark_cache_key(cache_id, start_iso, end_iso)
    entry = ranges.get(key)
    cached_points = cache_entry_points(entry)
    if cached_points and is_cache_entry_fresh(entry) and (
        not requires_start_coverage(benchmark) or points_cover_start(cached_points, start_iso)
    ):
        return cached_points

    points = fetch_benchmark_points_online(benchmark, start_iso, end_iso)
    if points:
        ranges[key] = {
            "fetched_at": date.today().isoformat(),
            "points": points,
        }
        save_benchmark_cache(cache)
        return points
    return cached_points


def fetch_benchmark_payloads(start_iso: str, end_iso: str) -> list[dict[str, object]]:
    if not start_iso or not end_iso:
        return []
    results: dict[str, list[dict[str, object]]] = {}
    emit_progress("拉取指数基准", f"准备读取 {len(BENCHMARKS)} 个可切换指数基准。", 80)
    workers = min(BENCHMARK_FETCH_WORKERS, len(BENCHMARKS))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_map = {
            executor.submit(fetch_benchmark_points, benchmark, start_iso, end_iso): benchmark
            for benchmark in BENCHMARKS
        }
        completed = 0
        for future in as_completed(future_map):
            benchmark = future_map[future]
            benchmark_id = clean_text(benchmark.get("id"))
            try:
                results[benchmark_id] = future.result()
            except Exception:
                results[benchmark_id] = []
            completed += 1
            emit_progress(
                "拉取指数基准",
                f"指数基准 {completed}/{len(BENCHMARKS)}：{clean_text(benchmark.get('short_label')) or clean_text(benchmark.get('label'))}",
                80 + (completed / len(BENCHMARKS)) * 4,
            )
    payloads = []
    for benchmark in BENCHMARKS:
        benchmark_id = clean_text(benchmark.get("id"))
        payloads.append(
            {
                "id": benchmark_id,
                "market": clean_text(benchmark.get("market")),
                "label": clean_text(benchmark.get("label")),
                "shortLabel": clean_text(benchmark.get("short_label")) or clean_text(benchmark.get("label")),
                "points": results.get(benchmark_id, []),
            }
        )
    return payloads


def normalize_curve_points(points: list[dict[str, object]]) -> list[dict[str, object]]:
    by_day: dict[str, dict[str, object]] = {}
    for point in points:
        serial = parse_float(point.get("serial"))
        value = parse_float(point.get("value"))
        label = clean_text(point.get("date"))
        iso = date_iso(label)
        if serial is None or value is None or not label or not iso:
            continue
        by_day[iso] = {
            "date": label,
            "iso": iso,
            "serial": serial,
            "value": value,
        }
        for key in ("float_value", "realized_value", "total_value"):
            extra_value = parse_float(point.get(key))
            if extra_value is not None:
                by_day[iso][key] = extra_value
        capital = parse_float(point.get("capital"))
        if capital is not None:
            by_day[iso]["capital"] = capital
    return sorted(by_day.values(), key=lambda item: (str(item["iso"]), float(item["serial"])))


def cny_rate_for_currency(currency: str, rates: dict[str, float]) -> float:
    text = clean_text(currency)
    if text in {"人民币", "CNY", "RMB"}:
        return 1.0
    return rates.get(text, 1.0)


def converted_series(series_list: list[dict[str, object]]) -> list[dict[str, object]]:
    rates = current_fx_rates_to_cny()
    converted = []
    for series in series_list:
        currency = clean_text(series.get("currency")) or "-"
        rate = cny_rate_for_currency(currency, rates)
        points = []
        for point in normalize_curve_points(list(series.get("points") or [])):
            value = parse_float(point.get("value"))
            if value is None:
                continue
            converted_point = {
                "date": point["date"],
                "iso": point["iso"],
                "serial": point["serial"],
                "value": value * rate,
            }
            for key in ("float_value", "realized_value", "total_value"):
                extra_value = parse_float(point.get(key))
                if extra_value is not None:
                    converted_point[key] = extra_value * rate
            capital = parse_float(point.get("capital"))
            if capital is not None:
                converted_point["capital"] = capital * rate
            points.append(converted_point)
        if points:
            converted.append(
                {
                    "currency": currency,
                    "rate": rate,
                    "capital": (parse_float(series.get("capital")) or 0.0) * rate,
                    "points": points,
                }
            )
    return converted


def combine_series_to_cny(series_list: list[dict[str, object]]) -> dict[str, object] | None:
    series_items = converted_series(series_list)
    if not series_items:
        return None

    by_iso: dict[str, dict[str, object]] = {}
    for series in series_items:
        for point in series["points"]:
            by_iso.setdefault(str(point["iso"]), {"date": point["date"], "iso": point["iso"], "serial": point["serial"]})
    combined_points = []
    last_points: list[dict[str, object] | None] = [None] * len(series_items)
    indexes = [0] * len(series_items)
    for iso in sorted(by_iso):
        for index, series in enumerate(series_items):
            points = list(series["points"])
            while indexes[index] < len(points) and str(points[indexes[index]]["iso"]) <= iso:
                last_points[index] = points[indexes[index]]
                indexes[index] += 1
        total_value = 0.0
        total_capital = 0.0
        total_float = 0.0
        total_realized = 0.0
        total_total = 0.0
        for series, point in zip(series_items, last_points):
            if not point:
                continue
            total_value += parse_float(point.get("value")) or 0.0
            total_float += parse_float(point.get("float_value")) or parse_float(point.get("value")) or 0.0
            total_realized += parse_float(point.get("realized_value")) or 0.0
            total_total += parse_float(point.get("total_value")) or parse_float(point.get("value")) or 0.0
            point_capital = parse_float(point.get("capital"))
            total_capital += point_capital if point_capital is not None else parse_float(series.get("capital")) or 0.0
        base = by_iso[iso]
        combined_point = {
            "date": base["date"],
            "iso": base["iso"],
            "serial": base["serial"],
            "value": total_value,
            "float_value": total_float,
            "realized_value": total_realized,
            "total_value": total_total,
        }
        if total_capital > 0.000001:
            combined_point["capital"] = total_capital
        combined_points.append(combined_point)

    capital = parse_float(combined_points[-1].get("capital")) if combined_points else None
    if capital is None:
        capital = sum(parse_float(series.get("capital")) or 0.0 for series in series_items)
    return {
        "currency": COMBINED_CURRENCY,
        "code": COMBINED_CODE,
        "capital": capital,
        "points": combined_points,
    }


def curve_payload(series_list: list[dict[str, object]]) -> list[dict[str, object]]:
    combined = combine_series_to_cny(series_list)
    if not combined:
        return []
    points = list(combined.get("points") or [])
    start_iso = str(points[0]["iso"]) if points else ""
    end_iso = str(points[-1]["iso"]) if points else ""
    benchmarks = fetch_benchmark_payloads(start_iso, end_iso)
    combined["benchmarks"] = benchmarks
    combined["benchmark"] = benchmarks[0] if benchmarks else {
        "id": COMBINED_BENCHMARK["id"],
        "market": COMBINED_BENCHMARK["market"],
        "label": COMBINED_BENCHMARK["label"],
        "points": [],
    }
    return [combined]


def safe_json(data: object) -> str:
    return (
        json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )


def render_curve_card(index: int, series: dict[str, object]) -> str:
    currency = clean_text(series.get("currency")) or "-"
    return f"""
                <div class="curve-card" data-return-curve-card data-series-index="{index}">
                  <div class="curve-card-head">
                    <div>
                      <h3 class="curve-title">{html.escape(currency)} 收益分析曲线</h3>
                      <p class="curve-subtitle" data-curve-subtitle>--</p>
                    </div>
                    <div class="curve-badge" data-curve-badge>--</div>
                  </div>
                  <svg class="curve-svg" viewBox="0 0 620 330" role="img" aria-label="{html.escape(currency)}收益分析曲线">
                    <line class="curve-axis" x1="34" y1="24" x2="34" y2="282"></line>
                    <line class="curve-axis" x1="34" y1="282" x2="564" y2="282"></line>
                    <g data-curve-grid-lines></g>
                    <g data-curve-y-labels></g>
                    <g class="curve-extreme-layer" data-curve-extreme-layer>
                      <line class="curve-extreme-line curve-extreme-max" data-curve-extreme-max-line></line>
                      <line class="curve-extreme-line curve-extreme-min" data-curve-extreme-min-line></line>
                      <text class="curve-extreme-label curve-extreme-label-max" data-curve-extreme-max-label>--</text>
                      <text class="curve-extreme-label curve-extreme-label-min" data-curve-extreme-min-label>--</text>
                    </g>
                    <line class="curve-zero-line" x1="34" y1="282" x2="564" y2="282" data-curve-zero-line></line>
                    <rect class="curve-drawdown-band" data-curve-drawdown-band></rect>
                    <rect class="curve-growth-band" data-curve-growth-band></rect>
                    <path class="curve-benchmark-line" data-curve-benchmark-line></path>
                    <path class="curve-area" data-curve-area></path>
                    <path class="curve-line-glow" data-curve-line-glow></path>
                    <path class="curve-line" data-curve-line></path>
                    <path class="curve-drawdown-link" data-curve-drawdown-link></path>
                    <path class="curve-growth-link" data-curve-growth-link></path>
                    <g data-curve-dots></g>
                    <g class="curve-drawdown-layer" data-curve-drawdown-layer>
                      <circle class="curve-drawdown-marker curve-drawdown-peak" data-curve-drawdown-peak></circle>
                      <circle class="curve-drawdown-marker curve-drawdown-trough" data-curve-drawdown-trough></circle>
                      <text class="curve-drawdown-label" data-curve-drawdown-label>--</text>
                    </g>
                    <g class="curve-growth-layer" data-curve-growth-layer>
                      <circle class="curve-growth-marker curve-growth-trough" data-curve-growth-trough></circle>
                      <circle class="curve-growth-marker curve-growth-peak" data-curve-growth-peak></circle>
                      <text class="curve-growth-label" data-curve-growth-label>--</text>
                    </g>
                    <g class="curve-hover-layer" data-curve-hover-layer>
                      <line class="curve-hover-line" data-curve-hover-line></line>
                      <circle class="curve-hover-dot curve-hover-dot-me" data-curve-hover-dot-me></circle>
                      <circle class="curve-hover-dot curve-hover-dot-base" data-curve-hover-dot-base></circle>
                    </g>
                    <text class="curve-axis-label" x="34" y="314" text-anchor="start" data-curve-start-label>--</text>
                    <text class="curve-axis-label" x="564" y="314" text-anchor="end" data-curve-end-label>--</text>
                    <text class="curve-end-value" x="574" y="18" data-curve-end-value>--</text>
                    <rect class="curve-hover-capture" x="0" y="0" width="620" height="306" data-curve-hover-capture></rect>
                  </svg>
                  <div class="curve-tooltip" data-curve-tooltip hidden></div>
                  <div class="curve-risk-caption" data-curve-drawdown-caption hidden></div>
                  <div class="curve-risk-caption curve-growth-caption" data-curve-growth-caption hidden></div>
                </div>
"""


def render_curve_script(payload: list[dict[str, object]]) -> str:
    payload_json = safe_json(payload)
    return f"""
                <script type="application/json" data-return-curve-json>{payload_json}</script>
                <script>
                (function initReturnCurveTabs() {{
                  const currentScript = document.currentScript;
                  const root = currentScript && typeof currentScript.closest === 'function'
                    ? (currentScript.closest('details[data-ths-return-curve]') || document)
                    : document;
                  const dataNode = root.querySelector('[data-return-curve-json]');
                  const grid = root.querySelector('[data-ths-curve-grid]');
                  if (!dataNode || !grid) return;
                  let seriesList = [];
                  try {{
                    seriesList = JSON.parse(dataNode.textContent || '[]');
                  }} catch (error) {{
                    seriesList = [];
                  }}

                  const dims = {{
                    width: 620,
                    height: 330,
                    left: 34,
                    right: 56,
                    top: 24,
                    bottom: 48,
                  }};
                  dims.innerWidth = dims.width - dims.left - dims.right;
                  dims.innerHeight = dims.height - dims.top - dims.bottom;

                  function reportingRateToCny() {{
                    const api = window.tradeTrackerReportingCurrency;
                    if (api && typeof api.rateToCny === 'function') {{
                      const rate = Number(api.rateToCny());
                      if (Number.isFinite(rate) && rate > 0) return rate;
                    }}
                    const label = document.documentElement.dataset.reportingCurrency || '人民币';
                    const rate = Number((window.tradeTrackerFxRatesToCny || {{}})[label]);
                    return Number.isFinite(rate) && rate > 0 ? rate : 1;
                  }}

                  function reportingMoneyValue(value) {{
                    const numeric = Number(value);
                    if (!Number.isFinite(numeric)) return NaN;
                    return numeric / reportingRateToCny();
                  }}

                  function moneyText(value) {{
                    const converted = reportingMoneyValue(value);
                    if (!Number.isFinite(converted)) return '--';
                    return converted.toLocaleString('zh-CN', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
                  }}

                  function signedMoneyText(value) {{
                    if (!Number.isFinite(value)) return '--';
                    return `${{value > 0 ? '+' : ''}}${{moneyText(value)}}`;
                  }}

                  function compactMoneyText(value) {{
                    const converted = reportingMoneyValue(value);
                    if (!Number.isFinite(converted)) return '--';
                    const abs = Math.abs(converted);
                    const sign = converted < 0 ? '-' : '';
                    if (abs >= 100000000) return `${{sign}}${{(abs / 100000000).toFixed(2)}}亿`;
                    if (abs >= 10000) return `${{sign}}${{(abs / 10000).toFixed(2)}}万`;
                    return moneyText(value);
                  }}

                  function percentText(value) {{
                    if (!Number.isFinite(value)) return '--';
                    const sign = value > 0 ? '+' : '';
                    return `${{sign}}${{value.toFixed(2)}}%`;
                  }}

                  function numberFromText(text) {{
                    const cleaned = String(text || '').replace(/,/g, '').replace(/[^0-9.+-]/g, '');
                    const parsed = Number(cleaned);
                    return Number.isFinite(parsed) ? parsed : NaN;
                  }}

                  function liveDailyReference() {{
                    const panel = document.querySelector('[data-holdings-reference-card] [data-holdings-range-panel="day"]');
                    const valueNode = panel?.querySelector('.holdings-account-value');
                    const detailNodes = panel ? Array.from(panel.querySelectorAll('.holdings-realized-text span')) : [];
                    const pnl = numberFromText(valueNode?.textContent || '');
                    const returnValue = numberFromText(detailNodes[1]?.textContent || '');
                    if (!Number.isFinite(pnl) && !Number.isFinite(returnValue)) return null;
                    return {{ pnl, returnValue }};
                  }}

                  function classForValue(value) {{
                    if (!Number.isFinite(value)) return 'curve-badge';
                    if (value > 0) return 'curve-badge curve-badge-positive';
                    if (value < 0) return 'curve-badge curve-badge-negative';
                    return 'curve-badge';
                  }}

                  function parseDate(iso) {{
                    const parts = String(iso || '').split('-').map(Number);
                    if (parts.length !== 3 || parts.some((part) => !Number.isFinite(part))) return null;
                    return new Date(Date.UTC(parts[0], parts[1] - 1, parts[2]));
                  }}

                  function isoFromDate(date) {{
                    return date.toISOString().slice(0, 10);
                  }}

                  function serialFromIso(iso) {{
                    const parsed = parseDate(iso);
                    if (!parsed) return NaN;
                    return (parsed.getTime() - Date.UTC(1899, 11, 30)) / 86400000;
                  }}

                  function dateLabelFromIso(iso) {{
                    const parsed = parseDate(iso);
                    if (!parsed) return String(iso || '');
                    const year = parsed.getUTCFullYear();
                    const month = String(parsed.getUTCMonth() + 1).padStart(2, '0');
                    const day = String(parsed.getUTCDate()).padStart(2, '0');
                    return `${{year}}/${{month}}/${{day}}`;
                  }}

                  function previousPointFrom(point) {{
                    const parsed = parseDate(point?.iso);
                    const serial = Number(point?.serial || NaN);
                    const priorDate = parsed ? new Date(parsed.getTime() - 86400000) : null;
                    const iso = priorDate ? isoFromDate(priorDate) : String(point?.iso || '');
                    const serialValue = Number.isFinite(serial) ? serial - 1 : serialFromIso(iso);
                    return {{
                      ...(point || {{}}),
                      iso,
                      date: iso ? dateLabelFromIso(iso) : String(point?.date || ''),
                      serial: Number.isFinite(serialValue) ? serialValue : 0,
                    }};
                  }}

                  function shiftMonths(date, months) {{
                    const copy = new Date(date.getTime());
                    copy.setUTCMonth(copy.getUTCMonth() + months);
                    return copy;
                  }}

                  function shiftYears(date, years) {{
                    const copy = new Date(date.getTime());
                    copy.setUTCFullYear(copy.getUTCFullYear() + years);
                    return copy;
                  }}

                  function firstDayOfMonth(date) {{
                    return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
                  }}

                  function firstDayOfYear(date) {{
                    return new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
                  }}

                  function latestIso() {{
                    let latest = '';
                    seriesList.forEach((series) => {{
                      (series.points || []).forEach((point) => {{
                        if (point.iso && point.iso > latest) latest = point.iso;
                      }});
                    }});
                    return latest;
                  }}

                  function benchmarksForSeries(series) {{
                    const items = Array.isArray(series?.benchmarks) && series.benchmarks.length
                      ? series.benchmarks
                      : (series?.benchmark ? [series.benchmark] : []);
                    return items.filter((benchmark) => benchmark && (benchmark.id || benchmark.label));
                  }}

                  function activeBenchmarkId() {{
                    const active = root.querySelector('.ths-curve-benchmark.is-active');
                    return active?.dataset.curveBenchmark || root.dataset.curveBenchmark || '';
                  }}

                  function selectedBenchmarkFor(series) {{
                    const benchmarks = benchmarksForSeries(series);
                    if (!benchmarks.length) return null;
                    const selectedId = activeBenchmarkId();
                    return benchmarks.find((benchmark) => String(benchmark.id || benchmark.label) === selectedId)
                      || benchmarks.find((benchmark) => (benchmark.points || []).length)
                      || benchmarks[0];
                  }}

                  function updateBenchmarkTabs() {{
                    const tabs = root.querySelector('[data-curve-benchmark-tabs]');
                    if (!tabs) return;
                    const benchmarks = benchmarksForSeries(seriesList[0] || {{}});
                    const previousId = activeBenchmarkId();
                    const firstId = benchmarks.length ? String(benchmarks[0].id || benchmarks[0].label || '') : '';
                    const selectedId = benchmarks.some((benchmark) => String(benchmark.id || benchmark.label) === previousId)
                      ? previousId
                      : firstId;
                    root.dataset.curveBenchmark = selectedId;
                    tabs.innerHTML = '';
                    benchmarks.forEach((benchmark) => {{
                      const benchmarkId = String(benchmark.id || benchmark.label || '');
                      const label = String(benchmark.label || benchmarkId || '市场基准');
                      const shortLabel = String(benchmark.shortLabel || label);
                      const market = String(benchmark.market || '');
                      const hasPoints = (benchmark.points || []).length > 0;
                      const button = document.createElement('button');
                      button.type = 'button';
                      button.className = `ths-curve-benchmark${{benchmarkId === selectedId ? ' is-active' : ''}}${{hasPoints ? '' : ' is-empty'}}`;
                      button.dataset.curveBenchmark = benchmarkId;
                      button.textContent = shortLabel;
                      button.setAttribute('aria-label', label);
                      button.title = market ? `${{label}} · ${{market}}` : label;
                      button.setAttribute('aria-pressed', benchmarkId === selectedId ? 'true' : 'false');
                      tabs.appendChild(button);
                    }});
                    tabs.hidden = !benchmarks.length;
                  }}

                  function rangeStart(range, latest, customStart) {{
                    const latestDate = parseDate(latest);
                    if (!latestDate) return '';
                    if (range === 'day') return latest;
                    if (range === 'month') return isoFromDate(firstDayOfMonth(latestDate));
                    if (range === 'three-month') return isoFromDate(shiftMonths(latestDate, -3));
                    if (range === 'year') return isoFromDate(firstDayOfYear(latestDate));
                    if (range === 'three-year') return isoFromDate(shiftYears(latestDate, -3));
                    if (range === 'custom') return customStart || '';
                    return '';
                  }}

                  function rangeEnd(range, latest, customEnd) {{
                    if (range === 'custom') return customEnd || latest;
                    return latest;
                  }}

                  function rangePnlLabel(range) {{
                    if (range === 'day') return '当日盈亏';
                    if (range === 'month') return '本月盈亏';
                    if (range === 'three-month') return '近三月盈亏';
                    if (range === 'year') return '今年盈亏';
                    if (range === 'three-year') return '近三年盈亏';
                    if (range === 'custom') return '阶段盈亏';
                    return '全部盈亏';
                  }}

                  function rangeRateLabel(range) {{
                    return '总资产收益率';
                  }}

                  function filteredPoints(points, range, latest, customStart, customEnd) {{
                    const start = rangeStart(range, latest, customStart);
                    const end = rangeEnd(range, latest, customEnd);
                    const source = (points || []).filter((point) => point && point.iso);
                    if (range === 'day') {{
                      const dayPoints = source.filter((point) => !end || point.iso <= end).slice(-2);
                      return dayPoints.length ? dayPoints : source.slice(-1);
                    }}
                    const filtered = source.filter((point) => {{
                      if (start && point.iso < start) return false;
                      if (end && point.iso > end) return false;
                      return true;
                    }});
                    if (!start) return filtered.length ? filtered : source.slice(-1);
                    if (filtered.length) {{
                      if (filtered[0]?.iso === start) return filtered;
                      const anchor = source.filter((point) => point.iso < start).slice(-1)[0];
                      if (!anchor) return filtered;
                      const serial = serialFromIso(start);
                      if (!Number.isFinite(serial)) return filtered;
                      return [{{ ...anchor, iso: start, date: dateLabelFromIso(start), serial }}].concat(filtered);
                    }}
                    const anchor = source.filter((point) => (!end || point.iso <= end)).slice(-1)[0] || source.slice(-1)[0];
                    if (!anchor) return [];
                    const serial = serialFromIso(start);
                    return Number.isFinite(serial)
                      ? [{{ ...anchor, iso: start, date: dateLabelFromIso(start), serial }}]
                      : [anchor];
                  }}

                  function benchmarkBaseClose(points, range, latest, customStart, customEnd, visiblePoints) {{
                    const start = rangeStart(range, latest, customStart);
                    const source = (points || []).filter((point) => point && point.iso);
                    if (!source.length) return NaN;
                    if (range === 'day') return Number(visiblePoints[0]?.close || source.filter((point) => point.iso < start).slice(-1)[0]?.close || source[0]?.close || 0);
                    if (!start) return Number(visiblePoints[0]?.close || source[0]?.close || 0);
                    const anchor = source.filter((point) => point.iso <= start).slice(-1)[0];
                    return Number(anchor?.close || visiblePoints[0]?.close || source[0]?.close || 0);
                  }}

                  function linePathFromPositions(positions) {{
                    return positions.map((point, index) => `${{index ? 'L' : 'M'}} ${{point[0].toFixed(2)}} ${{point[1].toFixed(2)}}`).join(' ');
                  }}

                  function valueForMetric(point, metric) {{
                    return Number(metric === 'amount' ? point?.amountValue : point?.returnValue);
                  }}

                  function metricText(value, metric) {{
                    return metric === 'amount' ? signedMoneyText(value) : percentText(value);
                  }}

                  function axisText(value, metric) {{
                    if (metric !== 'amount') return percentText(value);
                    if (!Number.isFinite(value)) return '--';
                    const sign = value > 0 ? '+' : '';
                    return `${{sign}}${{compactMoneyText(value)}}`;
                  }}

                  function niceStep(rawStep) {{
                    const step = Math.abs(Number(rawStep || 0));
                    if (!Number.isFinite(step) || step <= 0) return 1;
                    const exponent = Math.floor(Math.log10(step));
                    const base = Math.pow(10, exponent);
                    const fraction = step / base;
                    if (fraction >= 5) return 5 * base;
                    if (fraction >= 2) return 2 * base;
                    return base;
                  }}

                  function niceScale(minValue, maxValue, metric) {{
                    let low = Number(minValue);
                    let high = Number(maxValue);
                    if (!Number.isFinite(low)) low = 0;
                    if (!Number.isFinite(high)) high = 0;
                    if (Math.abs(high - low) < 1e-9) {{
                      const fallback = metric === 'amount' ? 10000 : 1;
                      low -= fallback;
                      high += fallback;
                    }}
                    const padding = Math.max((high - low) * 0.08, metric === 'amount' ? 1000 : 0.2);
                    low -= padding;
                    high += padding;
                    if (low > 0) low = 0;
                    if (high < 0) high = 0;
                    const step = niceStep((high - low) / 4);
                    const niceMin = Math.floor(low / step) * step;
                    const niceMax = Math.ceil(high / step) * step;
                    const ticks = [];
                    for (let value = niceMin; value <= niceMax + step / 2; value += step) {{
                      ticks.push(Math.abs(value) < step / 1000000 ? 0 : value);
                    }}
                    return {{ min: niceMin, max: niceMax, ticks }};
                  }}

                  function daysBetween(startPoint, endPoint) {{
                    const start = Number(startPoint?.serial);
                    const end = Number(endPoint?.serial);
                    if (!Number.isFinite(start) || !Number.isFinite(end)) return NaN;
                    return Math.max(0, Math.round(end - start));
                  }}

                  function daysText(days) {{
                    if (!Number.isFinite(days)) return '--';
                    return days <= 0 ? '当日' : `${{days}}天`;
                  }}

                  function pointAtOrBeforeSerial(points, serial) {{
                    let selected = null;
                    for (const point of points || []) {{
                      if (Number(point.serial) <= serial) selected = point;
                      if (Number(point.serial) > serial) break;
                    }}
                    return selected;
                  }}

                  function setSvgHidden(node, hidden) {{
                    if (!node) return;
                    node.style.display = hidden ? 'none' : '';
                  }}

                  function shortDateLabel(label) {{
                    const text = String(label || '');
                    const match = text.match(/^(\\d{{4}})[\\/-](\\d{{2}})[\\/-](\\d{{2}})$/);
                    if (!match) return text;
                    return `${{match[1].slice(2)}}.${{match[2]}}.${{match[3]}}`;
                  }}

                  function activeAssists() {{
                    const isActive = (name) => root.querySelector(`[data-curve-assist="${{name}}"]`)?.classList.contains('is-active');
                    return {{
                      drawdown: isActive('drawdown'),
                      extreme: isActive('extreme'),
                      growth: isActive('growth'),
                    }};
                  }}

                  function drawdownNav(point) {{
                    const returnValue = Number(point?.returnValue);
                    if (!Number.isFinite(returnValue)) return NaN;
                    return 1 + returnValue / 100;
                  }}

                  function drawdownRateBetween(peakPoint, troughPoint) {{
                    const peakNav = drawdownNav(peakPoint);
                    const troughNav = drawdownNav(troughPoint);
                    if (!Number.isFinite(peakNav) || !Number.isFinite(troughNav) || peakNav <= 0 || troughNav <= 0) return NaN;
                    return ((troughNav / peakNav) - 1) * 100;
                  }}

                  function maxDrawdownFor(points, metric) {{
                    const mode = metric === 'amount' ? 'amount' : 'return';
                    let peak = null;
                    let result = null;
                    (points || []).forEach((point, index) => {{
                      const nav = drawdownNav(point);
                      const amount = Number(point?.amountValue || 0);
                      const primary = mode === 'amount' ? amount : nav;
                      if (!Number.isFinite(primary)) return;
                      if (mode === 'return' && primary <= 0) return;
                      if (!peak || primary > peak.primary) {{
                        peak = {{ point, index, nav, amount, primary }};
                      }}
                      if (!peak || index <= peak.index) return;
                      const amountDrop = amount - peak.amount;
                      const rateDrop = drawdownRateBetween(peak.point, point);
                      const primaryDrop = mode === 'amount' ? amountDrop : rateDrop;
                      if (Number.isFinite(primaryDrop) && primaryDrop < 0 && (!result || primaryDrop < result.primaryDrop)) {{
                        result = {{
                          peak: peak.point,
                          trough: point,
                          peakIndex: peak.index,
                          troughIndex: index,
                          amount: amountDrop,
                          rate: rateDrop,
                          primaryDrop,
                          mode,
                          peakNav: peak.nav,
                          troughNav: nav,
                          peakAmount: peak.amount,
                          troughAmount: amount,
                          peakPrimary: peak.primary,
                        }};
                      }}
                    }});
                    if (result) {{
                      result.durationDays = daysBetween(result.peak, result.trough);
                      let recovery = null;
                      (points || []).slice(result.troughIndex + 1).forEach((point) => {{
                        let recovered = false;
                        if (result.mode === 'amount') {{
                          const amount = Number(point?.amountValue);
                          recovered = Number.isFinite(amount) && amount >= result.peakAmount;
                        }} else {{
                          const nav = drawdownNav(point);
                          recovered = Number.isFinite(nav) && nav >= result.peakNav;
                        }}
                        recovery = recovered ? (recovery || point) : null;
                      }});
                      if (recovery) {{
                        result.recovery = recovery;
                        const latestPoint = (points || [])[points.length - 1];
                        result.recoveredDays = Math.max(1, daysBetween(recovery, latestPoint) + 1);
                      }}
                    }}
                    return result && result.primaryDrop < 0 ? result : null;
                  }}

                  function maxGrowthFor(points, metric) {{
                    const mode = metric === 'amount' ? 'amount' : 'return';
                    let trough = null;
                    let result = null;
                    (points || []).forEach((point, index) => {{
                      const nav = drawdownNav(point);
                      const amount = Number(point?.amountValue || 0);
                      const primary = mode === 'amount' ? amount : nav;
                      if (!Number.isFinite(primary)) return;
                      if (mode === 'return' && primary <= 0) return;
                      if (!trough || primary < trough.primary) {{
                        trough = {{ point, index, nav, amount, primary }};
                      }}
                      if (!trough || index <= trough.index) return;
                      const amountGain = amount - trough.amount;
                      const rateGain = drawdownRateBetween(trough.point, point);
                      const primaryGain = mode === 'amount' ? amountGain : rateGain;
                      if (Number.isFinite(primaryGain) && primaryGain > 0 && (!result || primaryGain > result.primaryGain)) {{
                        result = {{
                          trough: trough.point,
                          peak: point,
                          troughIndex: trough.index,
                          peakIndex: index,
                          amount: amountGain,
                          rate: rateGain,
                          primaryGain,
                          mode,
                          troughNav: trough.nav,
                          peakNav: nav,
                          troughAmount: trough.amount,
                          peakAmount: amount,
                        }};
                      }}
                    }});
                    if (result) result.durationDays = daysBetween(result.trough, result.peak);
                    return result && result.primaryGain > 0 ? result : null;
                  }}

                  function installHoverHandlers(card) {{
                    if (card.dataset.curveHoverBound === '1') return;
                    const svg = card.querySelector('.curve-svg');
                    const tooltip = card.querySelector('[data-curve-tooltip]');
                    if (!svg || !tooltip) return;
                    const hide = () => {{
                      tooltip.hidden = true;
                      const state = card._curveHoverState || {{}};
                      setSvgHidden(state.hoverLayer, true);
                    }};
                    const move = (event) => {{
                      const state = card._curveHoverState;
                      if (!state || !state.points || !state.points.length) return hide();
                      const svgRect = svg.getBoundingClientRect();
                      const viewX = ((event.clientX - svgRect.left) / Math.max(svgRect.width, 1)) * dims.width;
                      const hitSlop = 28;
                      const minX = dims.left;
                      const maxX = dims.width - dims.right;
                      if (viewX < minX - hitSlop || viewX > maxX + hitSlop) return hide();
                      const clampedViewX = Math.max(minX, Math.min(maxX, viewX));
                      let selected = state.points[0];
                      state.points.forEach((point) => {{
                        if (Math.abs(point.x - clampedViewX) < Math.abs(selected.x - clampedViewX)) selected = point;
                      }});
                      if (!selected) return hide();
                      const benchmark = selected.benchmark;
                      if (state.hoverLine) {{
                        state.hoverLine.setAttribute('x1', selected.x.toFixed(2));
                        state.hoverLine.setAttribute('x2', selected.x.toFixed(2));
                        state.hoverLine.setAttribute('y1', String(dims.top));
                        state.hoverLine.setAttribute('y2', String(dims.top + dims.innerHeight));
                      }}
                      if (state.hoverDotMe) {{
                        state.hoverDotMe.setAttribute('cx', selected.x.toFixed(2));
                        state.hoverDotMe.setAttribute('cy', selected.y.toFixed(2));
                        state.hoverDotMe.setAttribute('r', '4.5');
                      }}
                      if (state.hoverDotBase) {{
                        if (benchmark) {{
                          state.hoverDotBase.setAttribute('cx', benchmark.x.toFixed(2));
                          state.hoverDotBase.setAttribute('cy', benchmark.y.toFixed(2));
                          state.hoverDotBase.setAttribute('r', '4.2');
                        }}
                        setSvgHidden(state.hoverDotBase, !benchmark);
                      }}
                      setSvgHidden(state.hoverLayer, false);
                      const dailyValue = state.metric === 'amount'
                        ? selected.accountDailyAmount
                        : selected.accountDailyReturn;
                      const benchmarkDaily = benchmark
                        ? (state.metric === 'amount' ? benchmark.dailyAmountValue : benchmark.dailyReturn)
                        : NaN;
                      tooltip.innerHTML = `
                        <div class="curve-tooltip-date">${{selected.date}}</div>
                        <div><span>我</span><strong>${{metricText(selected.accountValue, state.metric)}}</strong></div>
                        <div><span>${{state.benchmarkLabel}}</span><strong>${{benchmark ? metricText(benchmark.value, state.metric) : '--'}}</strong></div>
                        <div class="curve-tooltip-muted"><span>当日</span><strong>${{metricText(dailyValue, state.metric)}}</strong></div>
                        <div class="curve-tooltip-muted"><span>基准当日</span><strong>${{benchmark ? metricText(benchmarkDaily, state.metric) : '--'}}</strong></div>
                      `;
                      const cardRect = card.getBoundingClientRect();
                      const left = svgRect.left - cardRect.left + (selected.x / dims.width) * svgRect.width;
                      const top = svgRect.top - cardRect.top + (Math.min(selected.y, benchmark?.y ?? selected.y) / dims.height) * svgRect.height;
                      const safeLeft = Math.max(88, Math.min(cardRect.width - 88, left));
                      tooltip.style.left = `${{safeLeft}}px`;
                      tooltip.style.top = `${{Math.max(12, top - 10)}}px`;
                      tooltip.hidden = false;
                    }};
                    svg.addEventListener('pointermove', move);
                    svg.addEventListener('pointerleave', hide);
                    svg.addEventListener('pointercancel', hide);
                    card.dataset.curveHoverBound = '1';
                    hide();
                  }}

                  function drawCard(card, series, range, latest, customStart, customEnd, metric, assists) {{
                    metric = metric === 'amount' ? 'amount' : 'return';
                    assists = assists || activeAssists();
                    let points = filteredPoints(series.points || [], range, latest, customStart, customEnd);
                    const activeBenchmark = selectedBenchmarkFor(series);
                    const rawBenchmarkPoints = activeBenchmark?.points || [];
                    const benchmarkPoints = activeBenchmark
                      ? filteredPoints(rawBenchmarkPoints, range, latest, customStart, customEnd)
                      : [];
                    const svg = card.querySelector('.curve-svg');
                    if (!svg || !points.length) return;
                    const capital = Number(series.capital) > 0
                      ? Number(series.capital)
                      : Math.max(Math.abs(Number(points[points.length - 1]?.value || 0)), 1);
                    const carriedCapitalByIso = new Map();
                    let carriedCapital = 0;
                    (series.points || []).forEach((point) => {{
                      const pointCapital = Number(point?.capital);
                      if (Number.isFinite(pointCapital) && pointCapital > carriedCapital) carriedCapital = pointCapital;
                      if (point?.iso && carriedCapital > 0) carriedCapitalByIso.set(point.iso, carriedCapital);
                    }});
                    function capitalForPoint(point) {{
                      const carried = carriedCapitalByIso.get(point?.iso);
                      if (Number.isFinite(carried) && carried > 0) return carried;
                      if (point && Object.prototype.hasOwnProperty.call(point, 'capital')) {{
                        const pointCapital = Number(point.capital);
                        if (Number.isFinite(pointCapital) && pointCapital > 0) return pointCapital;
                      }}
                      return capital;
                    }}
                    let baseCapital = range === 'all' ? capital : capitalForPoint(points[0]);
                    if (!Number.isFinite(baseCapital) || baseCapital <= 0) baseCapital = capital;
                    function referenceCapitalFor(visiblePoints, fallbackCapital) {{
                      const capitals = (visiblePoints || [])
                        .map((point) => capitalForPoint(point))
                        .filter((value) => Number.isFinite(value) && value > 0);
                      if (!capitals.length) return fallbackCapital > 0 ? fallbackCapital : capital;
                      return Math.max(...capitals);
                    }}
                    let referenceCapital = referenceCapitalFor(points, baseCapital);
                    function returnBaseForPoint(point, previousPoint) {{
                      const previousCapital = capitalForPoint(previousPoint);
                      if (previousCapital > 0) return previousCapital;
                      const currentCapital = capitalForPoint(point);
                      if (currentCapital > 0) return currentCapital;
                      return baseCapital;
                    }}
                    function accountValuesFrom(visiblePoints, periodCapital, rangeMode) {{
                      const rangeBaseAmount = rangeMode === 'all' ? 0 : Number(visiblePoints[0]?.value || 0);
                      return visiblePoints.map((point, index) => {{
                        const previousPoint = index > 0 ? visiblePoints[index - 1] : null;
                        const delta = previousPoint ? Number(point.value || 0) - Number(previousPoint.value || 0) : 0;
                        const returnBase = returnBaseForPoint(point, previousPoint);
                        const dailyReturn = returnBase > 0 ? (delta / returnBase) * 100 : 0;
                        const floatAmount = Number(point.value || 0);
                        const periodAmount = floatAmount - rangeBaseAmount;
                        const pointCapital = capitalForPoint(point);
                        const returnCapital = rangeMode === 'all' ? pointCapital : periodCapital;
                        const floatReturn = returnCapital > 0 ? (periodAmount / returnCapital) * 100 : 0;
                        return {{
                          ...point,
                          dailyAmountValue: delta,
                          dailyReturn,
                          amountValue: periodAmount,
                          cumulativeAmountValue: periodAmount,
                          rawAmountValue: floatAmount,
                          baseCapital: returnBase > 0 ? returnBase : baseCapital,
                          referenceCapital: periodCapital,
                          returnValue: floatReturn,
                          cumulativeReturnValue: floatReturn,
                        }};
                      }});
                    }}
                    let accountValues = accountValuesFrom(points, referenceCapital, range);
                    const firstBenchmarkClose = benchmarkBaseClose(rawBenchmarkPoints, range, latest, customStart, customEnd, benchmarkPoints);
                    let benchmarkGrowth = 1;
                    const benchmarkValues = firstBenchmarkClose > 0
                      ? benchmarkPoints.map((point, index) => {{
                          const previousPoint = index > 0 ? benchmarkPoints[index - 1] : null;
                          const previousClose = Number(previousPoint?.close || 0);
                          const close = Number(point.close || 0);
                          const dailyReturn = previousClose > 0 ? ((close / previousClose) - 1) * 100 : 0;
                          if (index > 0 && Number.isFinite(dailyReturn)) benchmarkGrowth *= 1 + dailyReturn / 100;
                          const cumulativeReturnValue = (benchmarkGrowth - 1) * 100;
                          const cumulativeAmountValue = (cumulativeReturnValue / 100) * referenceCapital;
                          return {{
                          ...point,
                          dailyReturn,
                          returnValue: cumulativeReturnValue,
                          cumulativeReturnValue,
                          dailyAmountValue: (dailyReturn / 100) * referenceCapital,
                          amountValue: cumulativeAmountValue,
                          cumulativeAmountValue,
                          baseCapital: referenceCapital,
                        }};
                        }})
                      : [];
                    const accountMetricValues = accountValues.map((point) => ({{ ...point, metricValue: valueForMetric(point, metric) }}));
                    const benchmarkMetricValues = benchmarkValues.map((point) => ({{ ...point, metricValue: valueForMetric(point, metric) }}));
                    const allSeriesPoints = accountMetricValues.concat(benchmarkMetricValues)
                      .filter((point) => Number.isFinite(Number(point.metricValue)));
                    let minSerial = Math.min(...allSeriesPoints.map((point) => Number(point.serial)));
                    let maxSerial = Math.max(...allSeriesPoints.map((point) => Number(point.serial)));
                    const rawMinValue = Math.min(0, ...allSeriesPoints.map((point) => Number(point.metricValue)));
                    const rawMaxValue = Math.max(0, ...allSeriesPoints.map((point) => Number(point.metricValue)));
                    const scale = niceScale(rawMinValue, rawMaxValue, metric);
                    let minValue = scale.min;
                    let maxValue = scale.max;
                    if (Math.abs(maxSerial - minSerial) < 1e-9) maxSerial = minSerial + 1;
                    if (Math.abs(maxValue - minValue) < 1e-9) maxValue = minValue + 1;

                    const pointX = (serial) => dims.left + ((serial - minSerial) / (maxSerial - minSerial)) * dims.innerWidth;
                    const pointY = (value) => dims.top + ((maxValue - value) / (maxValue - minValue)) * dims.innerHeight;
                    const positions = accountMetricValues.map((point) => [pointX(Number(point.serial)), pointY(Number(point.metricValue)), Number(point.metricValue)]);
                    const benchmarkPositions = benchmarkMetricValues.map((point) => [pointX(Number(point.serial)), pointY(Number(point.metricValue)), Number(point.metricValue)]);
                    const linePath = linePathFromPositions(positions);
                    const benchmarkPath = linePathFromPositions(benchmarkPositions);
                    const zeroY = pointY(0);
                    const first = points[0];
                    const last = points[points.length - 1];
                    const firstPos = positions[0];
                    const lastPos = positions[positions.length - 1];
                    const periodPnl = accountValues[accountValues.length - 1]?.amountValue;
                    const periodReturn = accountValues[accountValues.length - 1]?.returnValue;
                    const periodBenchmarkReturn = benchmarkValues.length ? benchmarkValues[benchmarkValues.length - 1]?.returnValue : NaN;
                    const periodBenchmarkAmount = benchmarkValues.length ? benchmarkValues[benchmarkValues.length - 1]?.amountValue : NaN;
                    const periodExcessReturn = Number.isFinite(periodReturn) && Number.isFinite(periodBenchmarkReturn)
                      ? Number(periodReturn) - Number(periodBenchmarkReturn)
                      : NaN;
                    const periodExcessAmount = Number.isFinite(periodPnl) && Number.isFinite(periodBenchmarkAmount)
                      ? Number(periodPnl) - Number(periodBenchmarkAmount)
                      : NaN;
                    const drawdown = assists.drawdown ? maxDrawdownFor(accountValues, metric) : null;
                    const growth = assists.growth ? maxGrowthFor(accountValues, metric) : null;
                    const areaPath = `${{linePath}} L ${{lastPos[0].toFixed(2)}} ${{zeroY.toFixed(2)}} L ${{firstPos[0].toFixed(2)}} ${{zeroY.toFixed(2)}} Z`;

                    const gridLines = card.querySelector('[data-curve-grid-lines]');
                    const yLabels = card.querySelector('[data-curve-y-labels]');
                    if (gridLines) {{
                      gridLines.innerHTML = '';
                      if (yLabels) yLabels.innerHTML = '';
                      (scale.ticks || []).forEach((tick) => {{
                        const y = pointY(tick);
                        if (y < dims.top - 1 || y > dims.top + dims.innerHeight + 1) return;
                        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                        line.setAttribute('class', 'curve-grid-line');
                        line.setAttribute('x1', String(dims.left));
                        line.setAttribute('x2', String(dims.width - dims.right));
                        line.setAttribute('y1', y.toFixed(2));
                        line.setAttribute('y2', y.toFixed(2));
                        gridLines.appendChild(line);
                        if (yLabels) {{
                          const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                          label.setAttribute('class', 'curve-axis-label curve-y-label');
                          label.setAttribute('x', String(dims.width - 10));
                          label.setAttribute('y', (y + 4).toFixed(2));
                          label.setAttribute('text-anchor', 'end');
                          label.textContent = axisText(tick, metric);
                          yLabels.appendChild(label);
                        }}
                      }});
                    }}

                    const extremeLayer = card.querySelector('[data-curve-extreme-layer]');
                    const extremeMaxLine = card.querySelector('[data-curve-extreme-max-line]');
                    const extremeMinLine = card.querySelector('[data-curve-extreme-min-line]');
                    const extremeMaxLabel = card.querySelector('[data-curve-extreme-max-label]');
                    const extremeMinLabel = card.querySelector('[data-curve-extreme-min-label]');
                    const extremeItems = accountMetricValues
                      .map((point, index) => ({{ point, index, value: Number(point.metricValue), position: positions[index] }}))
                      .filter((item) => Number.isFinite(item.value) && item.position);
                    if (assists.extreme && extremeItems.length) {{
                      const maxItem = extremeItems.reduce((best, item) => (item.value > best.value ? item : best), extremeItems[0]);
                      const minItem = extremeItems.reduce((best, item) => (item.value < best.value ? item : best), extremeItems[0]);
                      const applyExtremeLine = (lineNode, labelNode, item, side) => {{
                        const y = pointY(item.value);
                        if (lineNode) {{
                          lineNode.setAttribute('x1', String(dims.left));
                          lineNode.setAttribute('x2', String(dims.width - dims.right));
                          lineNode.setAttribute('y1', y.toFixed(2));
                          lineNode.setAttribute('y2', y.toFixed(2));
                        }}
                        if (labelNode) {{
                          const x = side === 'right' ? dims.width - dims.right - 8 : dims.left + 8;
                          labelNode.setAttribute('x', String(x));
                          labelNode.setAttribute('y', String(Math.max(dims.top + 12, Math.min(dims.top + dims.innerHeight - 4, y - 6))));
                          labelNode.setAttribute('text-anchor', side === 'right' ? 'end' : 'start');
                          labelNode.textContent = axisText(item.value, metric);
                        }}
                      }};
                      applyExtremeLine(extremeMaxLine, extremeMaxLabel, maxItem, 'right');
                      applyExtremeLine(extremeMinLine, extremeMinLabel, minItem, 'left');
                      setSvgHidden(extremeLayer, false);
                    }} else {{
                      setSvgHidden(extremeLayer, true);
                    }}

                    const line = card.querySelector('[data-curve-line]');
                    const glow = card.querySelector('[data-curve-line-glow]');
                    const benchmarkLine = card.querySelector('[data-curve-benchmark-line]');
                    const drawdownBand = card.querySelector('[data-curve-drawdown-band]');
                    const drawdownLink = card.querySelector('[data-curve-drawdown-link]');
                    const drawdownLayer = card.querySelector('[data-curve-drawdown-layer]');
                    const drawdownPeak = card.querySelector('[data-curve-drawdown-peak]');
                    const drawdownTrough = card.querySelector('[data-curve-drawdown-trough]');
                    const drawdownLabel = card.querySelector('[data-curve-drawdown-label]');
                    const drawdownCaption = card.querySelector('[data-curve-drawdown-caption]');
                    const growthBand = card.querySelector('[data-curve-growth-band]');
                    const growthLink = card.querySelector('[data-curve-growth-link]');
                    const growthLayer = card.querySelector('[data-curve-growth-layer]');
                    const growthPeak = card.querySelector('[data-curve-growth-peak]');
                    const growthTrough = card.querySelector('[data-curve-growth-trough]');
                    const growthLabel = card.querySelector('[data-curve-growth-label]');
                    const growthCaption = card.querySelector('[data-curve-growth-caption]');
                    const area = card.querySelector('[data-curve-area]');
                    const zero = card.querySelector('[data-curve-zero-line]');
                    if (line) line.setAttribute('d', linePath);
                    if (glow) glow.setAttribute('d', linePath);
                    if (benchmarkLine) benchmarkLine.setAttribute('d', benchmarkPath);
                    if (area) area.setAttribute('d', areaPath);
                    if (drawdown && positions[drawdown.peakIndex] && positions[drawdown.troughIndex]) {{
                      const peakPos = positions[drawdown.peakIndex];
                      const troughPos = positions[drawdown.troughIndex];
                      const startX = Math.min(peakPos[0], troughPos[0]);
                      const endX = Math.max(peakPos[0], troughPos[0]);
                      if (drawdownBand) {{
                        drawdownBand.setAttribute('x', startX.toFixed(2));
                        drawdownBand.setAttribute('y', String(dims.top));
                        drawdownBand.setAttribute('width', Math.max(2, endX - startX).toFixed(2));
                        drawdownBand.setAttribute('height', String(dims.innerHeight));
                      }}
                      if (drawdownLink) {{
                        drawdownLink.setAttribute(
                          'd',
                          `M ${{peakPos[0].toFixed(2)}} ${{peakPos[1].toFixed(2)}} L ${{troughPos[0].toFixed(2)}} ${{troughPos[1].toFixed(2)}}`
                        );
                      }}
                      if (drawdownPeak) {{
                        drawdownPeak.setAttribute('cx', peakPos[0].toFixed(2));
                        drawdownPeak.setAttribute('cy', peakPos[1].toFixed(2));
                        drawdownPeak.setAttribute('r', '3.8');
                      }}
                      if (drawdownTrough) {{
                        drawdownTrough.setAttribute('cx', troughPos[0].toFixed(2));
                        drawdownTrough.setAttribute('cy', troughPos[1].toFixed(2));
                        drawdownTrough.setAttribute('r', '3.8');
                      }}
                      if (drawdownLabel) {{
                        const labelText = metric === 'amount' ? signedMoneyText(drawdown.amount) : percentText(drawdown.rate);
                        const labelX = Math.max(dims.left + 8, Math.min(dims.width - dims.right - 8, troughPos[0] - 6));
                        const labelY = Math.max(dims.top + 14, Math.min(dims.top + dims.innerHeight - 4, troughPos[1] - 8));
                        drawdownLabel.setAttribute('x', labelX.toFixed(2));
                        drawdownLabel.setAttribute('y', labelY.toFixed(2));
                        drawdownLabel.setAttribute('text-anchor', 'end');
                        drawdownLabel.textContent = labelText;
                      }}
                      if (drawdownCaption) {{
                        const recoveryText = drawdown.recovery
                          ? `已修复 ${{daysText(drawdown.recoveredDays)}}`
                          : '尚未修复';
                        const primaryLabel = metric === 'amount' ? '利润最大回撤' : '收益率最大回撤';
                        const primaryText = metric === 'amount' ? signedMoneyText(drawdown.amount) : percentText(drawdown.rate);
                        const secondaryLabel = metric === 'amount' ? '对应收益率回撤' : '对应利润回撤';
                        const secondaryText = metric === 'amount' ? percentText(drawdown.rate) : signedMoneyText(drawdown.amount);
                        drawdownCaption.innerHTML = `
                          <span><em>${{primaryLabel}}</em><strong>${{primaryText}}</strong></span>
                          <span><em>${{secondaryLabel}}</em><strong>${{secondaryText}}</strong></span>
                          <span><em>回撤区间</em><strong>${{drawdown.peak.date}} 至 ${{drawdown.trough.date}} · ${{daysText(drawdown.durationDays)}}</strong></span>
                          <span><em>已修复天数</em><strong>${{recoveryText}}</strong></span>
                        `;
                        drawdownCaption.hidden = false;
                      }}
                      setSvgHidden(drawdownBand, false);
                      setSvgHidden(drawdownLink, false);
                      setSvgHidden(drawdownLayer, false);
                    }} else {{
                      setSvgHidden(drawdownBand, true);
                      setSvgHidden(drawdownLink, true);
                      setSvgHidden(drawdownLayer, true);
                      if (drawdownCaption) drawdownCaption.hidden = true;
                    }}
                    if (growth && positions[growth.troughIndex] && positions[growth.peakIndex]) {{
                      const troughPos = positions[growth.troughIndex];
                      const peakPos = positions[growth.peakIndex];
                      const startX = Math.min(troughPos[0], peakPos[0]);
                      const endX = Math.max(troughPos[0], peakPos[0]);
                      if (growthBand) {{
                        growthBand.setAttribute('x', startX.toFixed(2));
                        growthBand.setAttribute('y', String(dims.top));
                        growthBand.setAttribute('width', Math.max(2, endX - startX).toFixed(2));
                        growthBand.setAttribute('height', String(dims.innerHeight));
                      }}
                      if (growthLink) {{
                        growthLink.setAttribute(
                          'd',
                          `M ${{troughPos[0].toFixed(2)}} ${{troughPos[1].toFixed(2)}} L ${{peakPos[0].toFixed(2)}} ${{peakPos[1].toFixed(2)}}`
                        );
                      }}
                      if (growthTrough) {{
                        growthTrough.setAttribute('cx', troughPos[0].toFixed(2));
                        growthTrough.setAttribute('cy', troughPos[1].toFixed(2));
                        growthTrough.setAttribute('r', '3.8');
                      }}
                      if (growthPeak) {{
                        growthPeak.setAttribute('cx', peakPos[0].toFixed(2));
                        growthPeak.setAttribute('cy', peakPos[1].toFixed(2));
                        growthPeak.setAttribute('r', '3.8');
                      }}
                      if (growthLabel) {{
                        const labelText = metric === 'amount' ? signedMoneyText(growth.amount) : percentText(growth.rate);
                        const labelX = Math.max(dims.left + 8, Math.min(dims.width - dims.right - 8, peakPos[0] + 6));
                        const labelY = Math.max(dims.top + 14, Math.min(dims.top + dims.innerHeight - 4, peakPos[1] - 8));
                        growthLabel.setAttribute('x', labelX.toFixed(2));
                        growthLabel.setAttribute('y', labelY.toFixed(2));
                        growthLabel.setAttribute('text-anchor', 'start');
                        growthLabel.textContent = labelText;
                      }}
                      if (growthCaption) {{
                        const primaryLabel = metric === 'amount' ? '利润最大增长' : '收益率最大增长';
                        const primaryText = metric === 'amount' ? signedMoneyText(growth.amount) : percentText(growth.rate);
                        const secondaryLabel = metric === 'amount' ? '对应收益率增长' : '对应利润增长';
                        const secondaryText = metric === 'amount' ? percentText(growth.rate) : signedMoneyText(growth.amount);
                        growthCaption.innerHTML = `
                          <span><em>${{primaryLabel}}</em><strong>${{primaryText}}</strong></span>
                          <span><em>${{secondaryLabel}}</em><strong>${{secondaryText}}</strong></span>
                          <span><em>增长区间</em><strong>${{growth.trough.date}} 至 ${{growth.peak.date}} · ${{daysText(growth.durationDays)}}</strong></span>
                        `;
                        growthCaption.hidden = false;
                      }}
                      setSvgHidden(growthBand, false);
                      setSvgHidden(growthLink, false);
                      setSvgHidden(growthLayer, false);
                    }} else {{
                      setSvgHidden(growthBand, true);
                      setSvgHidden(growthLink, true);
                      setSvgHidden(growthLayer, true);
                      if (growthCaption) growthCaption.hidden = true;
                    }}
                    if (zero) {{
                      zero.setAttribute('x1', String(dims.left));
                      zero.setAttribute('x2', String(dims.width - dims.right));
                      zero.setAttribute('y1', zeroY.toFixed(2));
                      zero.setAttribute('y2', zeroY.toFixed(2));
                    }}

                    const dots = card.querySelector('[data-curve-dots]');
                    if (dots) {{
                      dots.innerHTML = '';
                      [firstPos, lastPos].forEach((position, index) => {{
                        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                        dot.setAttribute('class', index ? 'curve-dot curve-dot-last' : 'curve-dot');
                        dot.setAttribute('cx', position[0].toFixed(2));
                        dot.setAttribute('cy', position[1].toFixed(2));
                        dot.setAttribute('r', index ? '4.8' : '3.2');
                        dots.appendChild(dot);
                      }});
                      if (benchmarkPositions.length) {{
                        const benchmarkLast = benchmarkPositions[benchmarkPositions.length - 1];
                        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                        dot.setAttribute('class', 'curve-benchmark-dot');
                        dot.setAttribute('cx', benchmarkLast[0].toFixed(2));
                        dot.setAttribute('cy', benchmarkLast[1].toFixed(2));
                        dot.setAttribute('r', '3.2');
                        dots.appendChild(dot);
                      }}
                    }}

                    const hoverLayer = card.querySelector('[data-curve-hover-layer]');
                    const hoverLine = card.querySelector('[data-curve-hover-line]');
                    const hoverDotMe = card.querySelector('[data-curve-hover-dot-me]');
                    const hoverDotBase = card.querySelector('[data-curve-hover-dot-base]');
                    const hoverPoints = accountMetricValues.map((point, index) => {{
                      const position = positions[index];
                      const benchmarkPoint = pointAtOrBeforeSerial(benchmarkMetricValues, Number(point.serial));
                      const benchmarkMetric = benchmarkPoint ? valueForMetric(benchmarkPoint, metric) : NaN;
                      const benchmark = benchmarkPoint && Number.isFinite(benchmarkMetric)
                        ? {{
                            value: benchmarkMetric,
                            x: pointX(Number(benchmarkPoint.serial)),
                            y: pointY(benchmarkMetric),
                            dailyReturn: Number(benchmarkPoint.dailyReturn || 0),
                            dailyAmountValue: Number(benchmarkPoint.dailyAmountValue || 0),
                          }}
                        : null;
                      return {{
                        date: point.date,
                        x: position[0],
                        y: position[1],
                        accountValue: Number(point.metricValue),
                        accountDailyReturn: Number(point.dailyReturn || 0),
                        accountDailyAmount: Number(point.dailyAmountValue || 0),
                        benchmark,
                      }};
                    }}).filter((point) => Number.isFinite(point.x) && Number.isFinite(point.y));
                    card._curveHoverState = {{
                      metric,
                      benchmarkLabel: activeBenchmark?.label || '市场基准',
                      points: hoverPoints,
                      hoverLayer,
                      hoverLine,
                      hoverDotMe,
                      hoverDotBase,
                    }};
                    installHoverHandlers(card);
                    setSvgHidden(hoverLayer, true);

                    const subtitle = card.querySelector('[data-curve-subtitle]');
                    const badge = card.querySelector('[data-curve-badge]');
                    const startLabel = card.querySelector('[data-curve-start-label]');
                    const endLabel = card.querySelector('[data-curve-end-label]');
                    const endValue = card.querySelector('[data-curve-end-value]');
                    if (subtitle) subtitle.textContent = `${{first.date}} 至 ${{last.date}}`;
                    if (badge) {{
                      const badgeValue = metric === 'amount' ? periodPnl : periodReturn;
                      const badgeLabel = metric === 'amount' ? rangePnlLabel(range) : rangeRateLabel(range);
                      badge.className = classForValue(badgeValue);
                      badge.textContent = `${{badgeLabel}} ${{metricText(badgeValue, metric)}}`;
                    }}
                    if (startLabel) startLabel.textContent = first.date;
                    if (endLabel) endLabel.textContent = last.date;
                    if (endValue) {{
                      endValue.textContent = '';
                      endValue.setAttribute('x', String(Math.min(lastPos[0] + 10, 568)));
                      endValue.setAttribute('y', String(Math.max(24, Math.min(280, lastPos[1] - 8))));
                    }}
                    card.dataset.curveMetric = metric;
                    card.dataset.accountReturn = Number.isFinite(periodReturn) ? String(periodReturn) : '';
                    card.dataset.benchmarkReturn = Number.isFinite(periodBenchmarkReturn) ? String(periodBenchmarkReturn) : '';
                    card.dataset.excessReturn = Number.isFinite(periodExcessReturn) ? String(periodExcessReturn) : '';
                    card.dataset.accountAmount = Number.isFinite(periodPnl) ? String(periodPnl) : '';
                    card.dataset.benchmarkAmount = Number.isFinite(periodBenchmarkAmount) ? String(periodBenchmarkAmount) : '';
                    card.dataset.excessAmount = Number.isFinite(periodExcessAmount) ? String(periodExcessAmount) : '';
                    card.dataset.benchmarkLabel = activeBenchmark?.label || '市场基准';
                    card.dataset.periodPnl = Number.isFinite(periodPnl) ? String(periodPnl) : '';
                    card.dataset.periodReturn = Number.isFinite(periodReturn) ? String(periodReturn) : '';
                    card.dataset.periodLabel = rangePnlLabel(range);
                    card.dataset.periodRateLabel = rangeRateLabel(range);
                    card.dataset.periodStart = first.date || '';
                    card.dataset.periodEnd = last.date || '';
                  }}

                  function updateSummaryBar(row, value, scale) {{
                    if (!row) return;
                    const percent = Number.isFinite(value) && scale > 0
                      ? Math.max(8, Math.min(100, Math.abs(value) / scale * 100))
                      : 8;
                    row.style.setProperty('--bar-fill', `${{percent.toFixed(1)}}%`);
                    row.classList.toggle('is-negative', Number.isFinite(value) && value < 0);
                  }}

                  function updateCurveSummary(metric) {{
                    const primaryCard = root.querySelector('[data-return-curve-card]');
                    if (!primaryCard) return;
                    const metricMode = metric === 'amount' ? 'amount' : 'return';
                    const accountValue = Number(primaryCard.dataset[metricMode === 'amount' ? 'accountAmount' : 'accountReturn'] || 'NaN');
                    const benchmarkValue = Number(primaryCard.dataset[metricMode === 'amount' ? 'benchmarkAmount' : 'benchmarkReturn'] || 'NaN');
                    const diff = Number(primaryCard.dataset[metricMode === 'amount' ? 'excessAmount' : 'excessReturn'] || 'NaN');
                    const benchmarkLabel = primaryCard.dataset.benchmarkLabel || '市场基准';
                    const title = root.querySelector('[data-curve-summary-title]');
                    const value = root.querySelector('[data-curve-summary-value]');
                    const mine = root.querySelector('[data-curve-summary-mine]');
                    const benchmark = root.querySelector('[data-curve-summary-benchmark]');
                    const benchmarkName = root.querySelector('[data-curve-summary-benchmark-name]');
                    const legendBenchmark = root.querySelector('[data-curve-legend-benchmark]');
                    const summary = root.querySelector('[data-curve-summary-title]')?.closest('.ths-curve-summary');
                    const barScale = Math.max(Math.abs(accountValue || 0), Math.abs(benchmarkValue || 0), 1);
                    if (summary) summary.classList.toggle('is-empty', !Number.isFinite(benchmarkValue));
                    if (title) title.textContent = Number.isFinite(diff) ? `${{diff >= 0 ? '跑赢' : '跑输'}}${{benchmarkLabel}}` : `${{benchmarkLabel}}暂无数据`;
                    if (value) {{
                      value.classList.remove('value-positive', 'value-negative', 'value-zero');
                      value.classList.add(diff > 0 ? 'value-positive' : diff < 0 ? 'value-negative' : 'value-zero');
                      value.textContent = metricText(diff, metricMode);
                    }}
                    if (mine) mine.textContent = metricText(accountValue, metricMode);
                    if (benchmark) benchmark.textContent = metricText(benchmarkValue, metricMode);
                    if (benchmarkName) benchmarkName.textContent = `${{benchmarkLabel}}:`;
                    if (legendBenchmark) legendBenchmark.textContent = benchmarkLabel;
                    updateSummaryBar(mine?.closest('div'), accountValue, barScale);
                    updateSummaryBar(benchmark?.closest('div'), benchmarkValue, barScale);
                  }}

                  function setToneClass(node, value, baseClass) {{
                    if (!node) return;
                    node.className = baseClass;
                    node.classList.add(value > 0 ? 'value-positive' : value < 0 ? 'value-negative' : 'value-zero');
                  }}

                  function captureCurveHeroDefaults() {{
                    const nodes = [
                      root.querySelector('[data-curve-hero-kicker]'),
                      root.querySelector('[data-curve-hero-value]'),
                      root.querySelector('[data-curve-hero-rate]'),
                      root.querySelector('[data-curve-hero-rate-label]'),
                    ].filter(Boolean);
                    nodes.forEach((node) => {{
                      if (!node.dataset.defaultText) node.dataset.defaultText = node.textContent || '';
                      if (!node.dataset.defaultClass) node.dataset.defaultClass = node.className || '';
                    }});
                  }}

                  function updateCurveHero(range, metric) {{
                    metric = metric === 'amount' ? 'amount' : 'return';
                    const primaryCard = root.querySelector('[data-return-curve-card]');
                    if (!primaryCard) return;
                    const kicker = root.querySelector('[data-curve-hero-kicker]');
                    const value = root.querySelector('[data-curve-hero-value]');
                    const rate = root.querySelector('[data-curve-hero-rate]');
                    const rateLabel = root.querySelector('[data-curve-hero-rate-label]');
                    const comparePill = root.querySelector('[data-curve-compare-pill]');
                    const compareLabel = root.querySelector('[data-curve-compare-label]');
                    const compareBenchmark = root.querySelector('[data-curve-compare-benchmark]');
                    const compareExcess = root.querySelector('[data-curve-compare-excess]');
                    captureCurveHeroDefaults();
                    const periodPnl = Number(primaryCard.dataset.periodPnl || 'NaN');
                    const periodReturn = Number(primaryCard.dataset.periodReturn || 'NaN');
                    const benchmarkReturn = Number(primaryCard.dataset.benchmarkReturn || 'NaN');
                    const excessReturn = Number(primaryCard.dataset.excessReturn || 'NaN');
                    const benchmarkLabel = primaryCard.dataset.benchmarkLabel || '指数';
                    const start = shortDateLabel(primaryCard.dataset.periodStart || '');
                    const end = shortDateLabel(primaryCard.dataset.periodEnd || '');
                    const dateRange = start && end ? `(${{start}}-${{end}})` : '';
                    if (kicker) kicker.textContent = `${{primaryCard.dataset.periodLabel || '区间盈亏'}}${{dateRange}}`;
                    if (value) {{
                      setToneClass(value, periodPnl, 'ths-curve-value');
                      value.textContent = signedMoneyText(periodPnl);
                    }}
                    if (rate) {{
                      setToneClass(rate, periodReturn, '');
                      rate.textContent = percentText(periodReturn);
                    }}
                    if (rateLabel) rateLabel.textContent = primaryCard.dataset.periodRateLabel || '区间收益率';
                    if (comparePill) comparePill.hidden = !Number.isFinite(benchmarkReturn);
                    if (compareLabel) compareLabel.textContent = `同期${{benchmarkLabel}}`;
                    if (compareBenchmark) compareBenchmark.textContent = percentText(benchmarkReturn);
                    if (compareExcess) {{
                      compareExcess.classList.remove('value-positive', 'value-negative', 'value-zero');
                      compareExcess.classList.add(excessReturn > 0 ? 'value-positive' : excessReturn < 0 ? 'value-negative' : 'value-zero');
                      compareExcess.textContent = percentText(excessReturn);
                    }}
                  }}

                  function redraw() {{
                    const active = root.querySelector('.ths-curve-tab.is-active');
                    const range = active ? active.dataset.curveRange : 'all';
                    const activeMetric = root.querySelector('.ths-curve-metric.is-active');
                    const metric = activeMetric?.dataset.curveMetric === 'amount' ? 'amount' : 'return';
                    const assists = activeAssists();
                    const latest = latestIso();
                    const customStart = root.querySelector('[data-curve-custom-start]')?.value || '';
                    const customEnd = root.querySelector('[data-curve-custom-end]')?.value || '';
                    root.querySelectorAll('[data-return-curve-card]').forEach((card) => {{
                      const index = Number(card.dataset.seriesIndex || '0');
                      const series = seriesList[index];
                      if (series) drawCard(card, series, range, latest, customStart, customEnd, metric, assists);
                    }});
                    updateCurveHero(range, metric);
                    updateCurveSummary(metric);
                    const custom = root.querySelector('[data-curve-custom]');
                    if (custom) custom.hidden = range !== 'custom';
                  }}

                  root.querySelectorAll('.ths-curve-tab').forEach((button) => {{
                    button.addEventListener('click', () => {{
                      root.querySelectorAll('.ths-curve-tab').forEach((item) => item.classList.remove('is-active'));
                      button.classList.add('is-active');
                      redraw();
                    }});
                  }});
                  root.addEventListener('click', (event) => {{
                    const benchmarkButton = event.target?.closest?.('.ths-curve-benchmark');
                    if (benchmarkButton && root.contains(benchmarkButton)) {{
                      root.querySelectorAll('.ths-curve-benchmark').forEach((item) => {{
                        const active = item === benchmarkButton;
                        item.classList.toggle('is-active', active);
                        item.setAttribute('aria-pressed', active ? 'true' : 'false');
                      }});
                      root.dataset.curveBenchmark = benchmarkButton.dataset.curveBenchmark || '';
                      redraw();
                      return;
                    }}
                    const metricButton = event.target?.closest?.('.ths-curve-metric');
                    if (metricButton && root.contains(metricButton)) {{
                      root.querySelectorAll('.ths-curve-metric').forEach((item) => item.classList.remove('is-active'));
                      metricButton.classList.add('is-active');
                      redraw();
                      return;
                    }}
                    const assistButton = event.target?.closest?.('.ths-curve-assist:not(.is-fixed)');
                    if (assistButton && root.contains(assistButton)) {{
                      const nextActive = !assistButton.classList.contains('is-active');
                      assistButton.classList.toggle('is-active', nextActive);
                      assistButton.setAttribute('aria-pressed', nextActive ? 'true' : 'false');
                      redraw();
                    }}
                  }});
                  root.querySelectorAll('[data-curve-custom-start], [data-curve-custom-end]').forEach((input) => {{
                    input.addEventListener('change', redraw);
                  }});
                  window.addEventListener('trade-tracker-reporting-currency-change', redraw);
                  updateBenchmarkTabs();
                  if (document.readyState === 'loading') {{
                    document.addEventListener('DOMContentLoaded', redraw, {{ once: true }});
                  }} else {{
                    redraw();
                  }}
                }})();
                </script>
"""


def render_tonghuashun_curve_panels(series_list: list[dict[str, object]]) -> str:
    payload = curve_payload(series_list)
    if not payload:
        return '<div class="empty-state">当前还没有足够的数据可画收益曲线。</div>'
    cards = "".join(render_curve_card(index, series) for index, series in enumerate(payload))
    return f'<div class="curve-grid" data-ths-curve-grid>{cards}</div>{render_curve_script(payload)}'
