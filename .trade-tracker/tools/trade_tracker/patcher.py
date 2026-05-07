from __future__ import annotations

from pathlib import Path

from . import state
from .analytics import build_holding_days_map, build_last_clear_date_map, build_summary_holding_days_maps
from .branding import brand_dashboard_html, brand_launcher_html
from .clearance_analysis import insert_clearance_analysis_section
from .curve_capital import attach_dynamic_curve_capital
from .dashboard_layout import apply_tonghuashun_curve_style, collapse_secondary_sections, reorder_dashboard_sections
from .dividends import load_dividend_events
from .html_tables import (
    add_balanced_summary_table_script,
    add_holdings_cny_settlement_footer_script,
    align_annual_summary_with_stock_summary,
    annotate_holdings_fx_note,
    insert_holding_metric_columns,
    insert_last_clear_date_column,
    insert_summary_holding_days_column,
    move_table_column,
    normalize_legacy_holdings_table,
    normalize_legacy_open_option_sections,
    prioritize_annual_summary_filter,
    prioritize_stock_summary_columns,
    remove_stock_summary_section,
    reorder_table_columns,
)
from .historical_curve import replace_curve_series_with_historical_prices
from .holdings_overview import insert_holdings_account_overview
from .market_data import fetch_quote_payload, infer_secid, patch_quote_fetchers, start_fx_rates_prefetch
from .names import cache_name, load_name_cache, load_workbook_name_map, name_cache_key
from .options import patch_dashboard_data_with_options
from .overview import move_dividend_metric_later, optimize_overview_metrics, split_overview_by_currency
from .refresh_panel import add_refresh_progress_panel
from .realized_analysis import insert_realized_analysis_section
from .return_curve import render_tonghuashun_curve_panels
from .runtime import emit_progress
from .settings import HOLDINGS_COLUMN_ORDER
from .utils import clean_name, parse_display_number


def patch_core(core, workbook_path: Path) -> None:
    original_render_summary_table = core.render_summary_table
    original_render_annual_summary_table = core.render_annual_summary_table
    original_render_dashboard_html = core.render_dashboard_html
    original_render_root_launcher_html = getattr(core, "render_root_launcher_html", None)
    original_lookup_security_name = core.lookup_security_name
    original_build_dashboard_data = core.build_dashboard_data
    original_load_dividend_events = getattr(core, "load_dividend_events", None)
    core.render_curve_panels = render_tonghuashun_curve_panels
    start_fx_rates_prefetch()
    emit_progress("读取名称缓存", "从历史表、券商导出和本地缓存映射标的名称。", 10)
    source_name_map = load_workbook_name_map(core)
    emit_progress("分析交易记录", "计算每只标的最后一次清仓时间。", 18)
    state.LAST_CLEAR_DATE_MAP = build_last_clear_date_map(core, workbook_path)
    emit_progress("分析持仓", "计算当前持仓天数。", 24)
    state.HOLDING_DAYS_MAP = build_holding_days_map(core, workbook_path)
    emit_progress("分析年度汇总", "累计每只股票跨年份持有天数。", 30)
    state.SUMMARY_HOLDING_DAYS_MAP, state.ANNUAL_HOLDING_DAYS_MAP = build_summary_holding_days_maps(core, workbook_path)

    def lookup_security_name(ticker, currency="", allow_online=False):
        normalized_ticker = core.normalize_ticker(ticker, currency)
        normalized_currency = core.normalize_currency(currency)
        if normalized_ticker:
            cached = load_name_cache().get(name_cache_key(core, normalized_ticker, normalized_currency))
            if cached:
                return cached

            source_name = source_name_map.get(normalized_ticker)
            if source_name:
                return cache_name(core, normalized_ticker, normalized_currency, source_name)

        original_name = clean_name(original_lookup_security_name(ticker, currency, allow_online))
        if original_name:
            return cache_name(core, normalized_ticker, normalized_currency, original_name)

        if allow_online and normalized_ticker:
            secid = infer_secid(core, normalized_ticker, normalized_currency)
            if secid:
                data = fetch_quote_payload(secid)
                if isinstance(data, dict):
                    online_name = clean_name(data.get("f58"))
                    if online_name:
                        return cache_name(core, normalized_ticker, normalized_currency, online_name)
        return ""

    def build_dashboard_data(rows):
        data = original_build_dashboard_data(rows)
        if isinstance(data, dict):
            data = patch_dashboard_data_with_options(core, rows, data)
            data = replace_curve_series_with_historical_prices(core, rows, data)
            capital_by_currency: dict[str, float] = {}
            for item in data.get("stock_summary", []) or []:
                if not isinstance(item, dict):
                    continue
                currency = str(item.get("currency") or "")
                try:
                    capital = float(item.get("capital_raw") or 0.0)
                except (TypeError, ValueError):
                    capital = 0.0
                if currency and capital:
                    capital_by_currency[currency] = capital_by_currency.get(currency, 0.0) + abs(capital)
            current_base_by_currency: dict[str, float] = {}
            for item in data.get("holdings", []) or []:
                if not isinstance(item, dict):
                    continue
                currency = str(item.get("currency") or "")
                current_value = parse_display_number(item.get("market_value"))
                if current_value is None:
                    current_value = parse_display_number(item.get("all_in_cost"))
                if currency and current_value:
                    current_base_by_currency[currency] = current_base_by_currency.get(currency, 0.0) + abs(current_value)
            for series in data.get("curve_series", []) or []:
                if isinstance(series, dict):
                    currency = str(series.get("currency") or "")
                    series["capital"] = current_base_by_currency.get(currency) or capital_by_currency.get(currency, 0.0)
            data = attach_dynamic_curve_capital(core, rows, data)
            return data
        return data

    def patched_load_dividend_events():
        return load_dividend_events(core, workbook_path, original_load_dividend_events)

    def render_summary_table(headers, rows, empty_message, summary_kind="", raw_rows=None):
        html = original_render_summary_table(headers, rows, empty_message, summary_kind, raw_rows)
        if summary_kind == "stock":
            html = insert_last_clear_date_column(core, html)
            html = insert_summary_holding_days_column(html)
            return prioritize_stock_summary_columns(html)
        if summary_kind == "holdings":
            html = normalize_legacy_holdings_table(core, html)
            html = insert_holding_metric_columns(core, html)
            return reorder_table_columns(html, HOLDINGS_COLUMN_ORDER)
        return html

    def render_annual_summary_table(headers, rows, years, empty_message):
        html = original_render_annual_summary_table(headers, rows, years, empty_message)
        html = move_table_column(html, "分红净额", "总盈亏")
        return insert_summary_holding_days_column(html)

    def render_dashboard_html(rows):
        html = optimize_overview_metrics(move_dividend_metric_later(original_render_dashboard_html(rows)))
        html = split_overview_by_currency(html)
        html = annotate_holdings_fx_note(html)
        html = align_annual_summary_with_stock_summary(html)
        html = prioritize_annual_summary_filter(html)
        html = insert_holdings_account_overview(core, html, rows)
        html = insert_realized_analysis_section(core, html, rows)
        html = insert_clearance_analysis_section(core, html, rows)
        html = remove_stock_summary_section(html)
        html = apply_tonghuashun_curve_style(html)
        html = reorder_dashboard_sections(html)
        html = collapse_secondary_sections(html)
        html = add_refresh_progress_panel(html)
        html = add_balanced_summary_table_script(html)
        html = add_holdings_cny_settlement_footer_script(html)
        html = normalize_legacy_open_option_sections(core, html)
        return brand_dashboard_html(html)

    def render_root_launcher_html(*args, **kwargs):
        if not original_render_root_launcher_html:
            return ""
        return brand_launcher_html(original_render_root_launcher_html(*args, **kwargs))

    core.render_summary_table = render_summary_table
    core.render_annual_summary_table = render_annual_summary_table
    core.render_dashboard_html = render_dashboard_html
    if original_render_root_launcher_html:
        core.render_root_launcher_html = render_root_launcher_html
    core.build_dashboard_data = build_dashboard_data
    core.load_dividend_events = patched_load_dividend_events
    core.lookup_security_name = lookup_security_name
    patch_quote_fetchers(core)
