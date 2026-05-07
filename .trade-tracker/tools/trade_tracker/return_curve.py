from __future__ import annotations

import html
import json
import re
from datetime import date
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .market_data import current_fx_rates_to_cny
from .runtime import APP_DIR
from .utils import clean_text, parse_float

COMBINED_CURRENCY = "人民币折算"
COMBINED_CODE = "CNY"
COMBINED_BENCHMARK = {"label": "上证指数", "secid": "1.000001"}
BENCHMARK_TIMEOUT = 8
BENCHMARK_CACHE_PATH = APP_DIR / "tools" / "cache" / "benchmark_history.json"
BENCHMARK_CACHE_TTL_DAYS = 7


def date_iso(value: object) -> str:
    text = clean_text(value)
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


def fetch_benchmark_points_online(secid: str, start_iso: str, end_iso: str) -> list[dict[str, object]]:
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


def fetch_benchmark_points(secid: str, start_iso: str, end_iso: str) -> list[dict[str, object]]:
    if not secid or not start_iso or not end_iso:
        return []
    cache = load_benchmark_cache()
    ranges = cache.get("ranges")
    if not isinstance(ranges, dict):
        ranges = {}
        cache["ranges"] = ranges
    key = benchmark_cache_key(secid, start_iso, end_iso)
    entry = ranges.get(key)
    cached_points = cache_entry_points(entry)
    if cached_points and is_cache_entry_fresh(entry):
        return cached_points

    points = fetch_benchmark_points_online(secid, start_iso, end_iso)
    if points:
        ranges[key] = {
            "fetched_at": date.today().isoformat(),
            "points": points,
        }
        save_benchmark_cache(cache)
        return points
    return cached_points


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
        for series, point in zip(series_items, last_points):
            if not point:
                continue
            total_value += parse_float(point.get("value")) or 0.0
            point_capital = parse_float(point.get("capital"))
            total_capital += point_capital if point_capital is not None else parse_float(series.get("capital")) or 0.0
        base = by_iso[iso]
        combined_point = {
            "date": base["date"],
            "iso": base["iso"],
            "serial": base["serial"],
            "value": total_value,
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
    benchmark_points = fetch_benchmark_points(COMBINED_BENCHMARK["secid"], start_iso, end_iso)
    combined["benchmark"] = {
        "label": COMBINED_BENCHMARK["label"],
        "points": benchmark_points,
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
                      <h3 class="curve-title">{html.escape(currency)} 累计收益曲线</h3>
                      <p class="curve-subtitle" data-curve-subtitle>--</p>
                    </div>
                    <div class="curve-badge" data-curve-badge>--</div>
                  </div>
                  <svg class="curve-svg" viewBox="0 0 620 220" role="img" aria-label="{html.escape(currency)}累计收益曲线">
                    <line class="curve-axis" x1="52" y1="16" x2="52" y2="186"></line>
                    <line class="curve-axis" x1="52" y1="186" x2="602" y2="186"></line>
                    <g data-curve-grid-lines></g>
                    <line class="curve-zero-line" x1="52" y1="186" x2="602" y2="186" data-curve-zero-line></line>
                    <path class="curve-benchmark-line" data-curve-benchmark-line></path>
                    <path class="curve-area" data-curve-area></path>
                    <path class="curve-line-glow" data-curve-line-glow></path>
                    <path class="curve-line" data-curve-line></path>
                    <g data-curve-dots></g>
                    <text class="curve-axis-label" x="52" y="210" text-anchor="start" data-curve-start-label>--</text>
                    <text class="curve-axis-label" x="602" y="210" text-anchor="end" data-curve-end-label>--</text>
                    <text class="curve-axis-label" x="8" y="26" data-curve-max-label>--</text>
                    <text class="curve-axis-label" x="8" y="186" data-curve-min-label>--</text>
                    <text class="curve-end-value" x="612" y="16" data-curve-end-value>--</text>
                  </svg>
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
                    height: 220,
                    left: 52,
                    right: 18,
                    top: 16,
                    bottom: 34,
                  }};
                  dims.innerWidth = dims.width - dims.left - dims.right;
                  dims.innerHeight = dims.height - dims.top - dims.bottom;

                  function moneyText(value) {{
                    if (!Number.isFinite(value)) return '--';
                    return value.toLocaleString('zh-CN', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
                  }}

                  function compactMoneyText(value) {{
                    if (!Number.isFinite(value)) return '--';
                    const abs = Math.abs(value);
                    if (abs >= 100000000) return `${{(value / 100000000).toFixed(2)}}亿`;
                    if (abs >= 10000) return `${{(value / 10000).toFixed(2)}}万`;
                    return moneyText(value);
                  }}

                  function percentText(value) {{
                    if (!Number.isFinite(value)) return '--';
                    const sign = value > 0 ? '+' : '';
                    return `${{sign}}${{value.toFixed(2)}}%`;
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

                  function filteredPoints(points, range, latest, customStart, customEnd) {{
                    const start = rangeStart(range, latest, customStart);
                    const end = rangeEnd(range, latest, customEnd);
                    const source = (points || []).filter((point) => point && point.iso);
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
                    if (!start) return Number(visiblePoints[0]?.close || source[0]?.close || 0);
                    const anchor = source.filter((point) => point.iso <= start).slice(-1)[0];
                    return Number(anchor?.close || visiblePoints[0]?.close || source[0]?.close || 0);
                  }}

                  function linePathFromPositions(positions) {{
                    return positions.map((point, index) => `${{index ? 'L' : 'M'}} ${{point[0].toFixed(2)}} ${{point[1].toFixed(2)}}`).join(' ');
                  }}

                  function benchmarkReturnAtSerial(benchmarkValues, serial) {{
                    let selected = null;
                    for (const point of benchmarkValues) {{
                      if (Number(point.serial) <= serial) selected = point;
                      if (Number(point.serial) > serial) break;
                    }}
                    return selected ? Number(selected.returnValue) : NaN;
                  }}

                  function excessValuesFor(accountValues, benchmarkValues) {{
                    if (!benchmarkValues.length) return [];
                    return accountValues.map((point) => {{
                      const benchmarkReturn = benchmarkReturnAtSerial(benchmarkValues, Number(point.serial));
                      if (!Number.isFinite(benchmarkReturn)) return null;
                      return {{
                        ...point,
                        returnValue: Number(point.returnValue) - benchmarkReturn,
                        benchmarkReturn,
                      }};
                    }}).filter(Boolean);
                  }}

                  function drawCard(card, series, range, latest, customStart, customEnd, mode) {{
                    const points = filteredPoints(series.points || [], range, latest, customStart, customEnd);
                    const rawBenchmarkPoints = series.benchmark?.points || [];
                    const benchmarkPoints = series.benchmark
                      ? filteredPoints(series.benchmark.points || [], range, latest, customStart, customEnd)
                      : [];
                    const svg = card.querySelector('.curve-svg');
                    if (!svg || !points.length) return;
                    const capital = Number(series.capital) > 0
                      ? Number(series.capital)
                      : Math.max(Math.abs(Number(points[points.length - 1]?.value || 0)), 1);
                    const startValue = Number(points[0].value || 0);
                    function capitalForPoint(point) {{
                      const pointCapital = Number(point?.capital || 0);
                      return pointCapital > 0 ? pointCapital : capital;
                    }}
                    const accountValues = points.map((point) => ({{
                      ...point,
                      returnValue: ((Number(point.value || 0) - startValue) / capitalForPoint(point)) * 100,
                    }}));
                    const firstBenchmarkClose = benchmarkBaseClose(rawBenchmarkPoints, range, latest, customStart, customEnd, benchmarkPoints);
                    const benchmarkValues = firstBenchmarkClose > 0
                      ? benchmarkPoints.map((point) => ({{
                          ...point,
                          returnValue: ((Number(point.close || 0) / firstBenchmarkClose) - 1) * 100,
                        }}))
                      : [];
                    const excessValues = excessValuesFor(accountValues, benchmarkValues);
                    const effectiveMode = mode === 'excess' && excessValues.length ? 'excess' : 'compare';
                    const chartValues = effectiveMode === 'excess' ? excessValues : accountValues;
                    const comparisonValues = effectiveMode === 'excess' ? [] : benchmarkValues;
                    const allSeriesPoints = chartValues.concat(comparisonValues);
                    let minSerial = Math.min(...allSeriesPoints.map((point) => Number(point.serial)));
                    let maxSerial = Math.max(...allSeriesPoints.map((point) => Number(point.serial)));
                    let minValue = Math.min(0, ...allSeriesPoints.map((point) => Number(point.returnValue)));
                    let maxValue = Math.max(0, ...allSeriesPoints.map((point) => Number(point.returnValue)));
                    if (Math.abs(maxSerial - minSerial) < 1e-9) maxSerial = minSerial + 1;
                    if (Math.abs(maxValue - minValue) < 1e-9) maxValue = minValue + 1;
                    const valuePadding = Math.max((maxValue - minValue) * 0.08, 0.4);
                    minValue -= valuePadding;
                    maxValue += valuePadding;

                    const pointX = (serial) => dims.left + ((serial - minSerial) / (maxSerial - minSerial)) * dims.innerWidth;
                    const pointY = (value) => dims.top + ((maxValue - value) / (maxValue - minValue)) * dims.innerHeight;
                    const positions = chartValues.map((point) => [pointX(Number(point.serial)), pointY(Number(point.returnValue)), Number(point.returnValue)]);
                    const benchmarkPositions = comparisonValues.map((point) => [pointX(Number(point.serial)), pointY(Number(point.returnValue)), Number(point.returnValue)]);
                    const linePath = linePathFromPositions(positions);
                    const benchmarkPath = linePathFromPositions(benchmarkPositions);
                    const zeroY = pointY(0);
                    const first = points[0];
                    const last = points[points.length - 1];
                    const firstPos = positions[0];
                    const lastPos = positions[positions.length - 1];
                    const areaPath = `${{linePath}} L ${{lastPos[0].toFixed(2)}} ${{zeroY.toFixed(2)}} L ${{firstPos[0].toFixed(2)}} ${{zeroY.toFixed(2)}} Z`;

                    const gridLines = card.querySelector('[data-curve-grid-lines]');
                    if (gridLines) {{
                      gridLines.innerHTML = '';
                      for (let index = 0; index < 5; index += 1) {{
                        const y = dims.top + (dims.innerHeight / 4) * index;
                        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                        line.setAttribute('class', 'curve-grid-line');
                        line.setAttribute('x1', String(dims.left));
                        line.setAttribute('x2', String(dims.width - dims.right));
                        line.setAttribute('y1', y.toFixed(2));
                        line.setAttribute('y2', y.toFixed(2));
                        gridLines.appendChild(line);
                      }}
                    }}

                    const line = card.querySelector('[data-curve-line]');
                    const glow = card.querySelector('[data-curve-line-glow]');
                    const benchmarkLine = card.querySelector('[data-curve-benchmark-line]');
                    const area = card.querySelector('[data-curve-area]');
                    const zero = card.querySelector('[data-curve-zero-line]');
                    if (line) line.setAttribute('d', linePath);
                    if (glow) glow.setAttribute('d', linePath);
                    if (benchmarkLine) benchmarkLine.setAttribute('d', benchmarkPath);
                    if (area) area.setAttribute('d', areaPath);
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

                    const subtitle = card.querySelector('[data-curve-subtitle]');
                    const badge = card.querySelector('[data-curve-badge]');
                    const startLabel = card.querySelector('[data-curve-start-label]');
                    const endLabel = card.querySelector('[data-curve-end-label]');
                    const maxLabel = card.querySelector('[data-curve-max-label]');
                    const minLabel = card.querySelector('[data-curve-min-label]');
                    const endValue = card.querySelector('[data-curve-end-value]');
                    if (subtitle) subtitle.textContent = `${{first.date}} 至 ${{last.date}}`;
                    if (badge) {{
                      badge.className = classForValue(positions[positions.length - 1]?.[2]);
                      badge.textContent = effectiveMode === 'excess'
                        ? `超额收益 · ${{percentText(positions[positions.length - 1]?.[2])}}`
                        : `${{series.currency}} ${{moneyText(Number(last.value))}} · ${{percentText(positions[positions.length - 1]?.[2])}}`;
                    }}
                    if (startLabel) startLabel.textContent = first.date;
                    if (endLabel) endLabel.textContent = last.date;
                    if (maxLabel) maxLabel.textContent = percentText(maxValue);
                    if (minLabel) minLabel.textContent = percentText(minValue);
                    if (endValue) {{
                      endValue.textContent = percentText(lastPos[2]);
                      endValue.setAttribute('x', String(Math.min(lastPos[0] + 10, 574)));
                      endValue.setAttribute('y', String(Math.max(18, Math.min(182, lastPos[1] - 8))));
                    }}
                    const accountReturn = positions[positions.length - 1]?.[2];
                    const compareAccountReturn = accountValues[accountValues.length - 1]?.returnValue;
                    const benchmarkReturn = benchmarkValues.length ? benchmarkValues[benchmarkValues.length - 1]?.returnValue : NaN;
                    const excessReturn = Number.isFinite(compareAccountReturn) && Number.isFinite(benchmarkReturn)
                      ? Number(compareAccountReturn) - Number(benchmarkReturn)
                      : NaN;
                    card.classList.toggle('is-excess-mode', effectiveMode === 'excess');
                    card.dataset.curveMode = effectiveMode;
                    card.dataset.accountReturn = Number.isFinite(compareAccountReturn) ? String(compareAccountReturn) : '';
                    card.dataset.benchmarkReturn = Number.isFinite(benchmarkReturn) ? String(benchmarkReturn) : '';
                    card.dataset.excessReturn = Number.isFinite(excessReturn) ? String(excessReturn) : '';
                    card.dataset.benchmarkLabel = series.benchmark?.label || '市场基准';
                  }}

                  function updateSummaryBar(row, value, scale) {{
                    if (!row) return;
                    const percent = Number.isFinite(value) && scale > 0
                      ? Math.max(8, Math.min(100, Math.abs(value) / scale * 100))
                      : 8;
                    row.style.setProperty('--bar-fill', `${{percent.toFixed(1)}}%`);
                    row.classList.toggle('is-negative', Number.isFinite(value) && value < 0);
                  }}

                  function updateCurveSummary() {{
                    const primaryCard = root.querySelector('[data-return-curve-card]');
                    if (!primaryCard) return;
                    const accountReturn = Number(primaryCard.dataset.accountReturn || 'NaN');
                    const benchmarkReturn = Number(primaryCard.dataset.benchmarkReturn || 'NaN');
                    const benchmarkLabel = primaryCard.dataset.benchmarkLabel || '市场基准';
                    const diff = Number.isFinite(accountReturn) && Number.isFinite(benchmarkReturn)
                      ? accountReturn - benchmarkReturn
                      : NaN;
                    const title = root.querySelector('[data-curve-summary-title]');
                    const value = root.querySelector('[data-curve-summary-value]');
                    const mine = root.querySelector('[data-curve-summary-mine]');
                    const benchmark = root.querySelector('[data-curve-summary-benchmark]');
                    const benchmarkName = root.querySelector('[data-curve-summary-benchmark-name]');
                    const summary = root.querySelector('[data-curve-summary-title]')?.closest('.ths-curve-summary');
                    const barScale = Math.max(Math.abs(accountReturn || 0), Math.abs(benchmarkReturn || 0), 1);
                    if (summary) summary.classList.toggle('is-empty', !Number.isFinite(benchmarkReturn));
                    if (title) title.textContent = Number.isFinite(diff) ? `${{diff >= 0 ? '跑赢' : '跑输'}}${{benchmarkLabel}}` : `${{benchmarkLabel}}暂无数据`;
                    if (value) {{
                      value.classList.remove('value-positive', 'value-negative', 'value-zero');
                      value.classList.add(diff > 0 ? 'value-positive' : diff < 0 ? 'value-negative' : 'value-zero');
                      value.textContent = Number.isFinite(diff) ? percentText(diff) : '--';
                    }}
                    if (mine) mine.textContent = percentText(accountReturn);
                    if (benchmark) benchmark.textContent = percentText(benchmarkReturn);
                    if (benchmarkName) benchmarkName.textContent = `${{benchmarkLabel}}:`;
                    updateSummaryBar(mine?.closest('div'), accountReturn, barScale);
                    updateSummaryBar(benchmark?.closest('div'), benchmarkReturn, barScale);
                  }}

                  function redraw() {{
                    const active = root.querySelector('.ths-curve-tab.is-active');
                    const range = active ? active.dataset.curveRange : 'all';
                    const activeMode = root.querySelector('.ths-curve-mode.is-active');
                    const mode = activeMode ? activeMode.dataset.curveMode : 'compare';
                    const latest = latestIso();
                    const customStart = root.querySelector('[data-curve-custom-start]')?.value || '';
                    const customEnd = root.querySelector('[data-curve-custom-end]')?.value || '';
                    root.querySelectorAll('[data-return-curve-card]').forEach((card) => {{
                      const index = Number(card.dataset.seriesIndex || '0');
                      const series = seriesList[index];
                      if (series) drawCard(card, series, range, latest, customStart, customEnd, mode);
                    }});
                    updateCurveSummary();
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
                  root.querySelectorAll('.ths-curve-mode').forEach((button) => {{
                    button.addEventListener('click', () => {{
                      root.querySelectorAll('.ths-curve-mode').forEach((item) => item.classList.remove('is-active'));
                      button.classList.add('is-active');
                      redraw();
                    }});
                  }});
                  root.querySelectorAll('[data-curve-custom-start], [data-curve-custom-end]').forEach((input) => {{
                    input.addEventListener('change', redraw);
                  }});
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
