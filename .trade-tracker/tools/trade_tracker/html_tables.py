from __future__ import annotations

import html
import json
import re

from . import state
from .market_data import current_fx_rates_to_cny, display_currency_label
from .settings import ANNUAL_STOCK_SUMMARY_COLUMN_ORDER, HOLDINGS_COLUMN_ORDER, STOCK_SUMMARY_COLUMN_ORDER
from .utils import cell_text, parse_float
from .options import option_key


def move_cells(cells: list[str], label_from: str, label_after: str, labels: list[str] | None = None) -> list[str]:
    source_labels = labels if labels is not None else [cell_text(cell) for cell in cells]
    if label_from not in source_labels or label_after not in source_labels:
        return cells
    from_index = source_labels.index(label_from)
    after_index = source_labels.index(label_after)
    if from_index == after_index or from_index == after_index + 1:
        return cells
    moved = list(cells)
    cell = moved.pop(from_index)
    insert_at = after_index if from_index < after_index else after_index + 1
    moved.insert(insert_at, cell)
    return moved


def move_table_column(table_html: str, label_from: str, label_after: str) -> str:
    header_match = re.search(r"(<thead>\s*<tr>)(.*?)(</tr>\s*</thead>)", table_html, re.S)
    if not header_match:
        return table_html

    header_cells = re.findall(r"<th\b[^>]*>.*?</th>", header_match.group(2), re.S)
    labels = [cell_text(cell) for cell in header_cells]
    if label_from not in labels or label_after not in labels:
        return table_html

    from_index = labels.index(label_from)
    after_index = labels.index(label_after)
    if from_index == after_index or from_index == after_index + 1:
        return table_html

    new_header_cells = move_cells(header_cells, label_from, label_after, labels)
    updated = (
        table_html[: header_match.start(2)]
        + "".join(new_header_cells)
        + table_html[header_match.end(2) :]
    )

    def move_section_rows(match: re.Match[str]) -> str:
        prefix, body, suffix = match.group(1), match.group(2), match.group(3)

        def move_row(row_match: re.Match[str]) -> str:
            row_prefix, row_body, row_suffix = row_match.group(1), row_match.group(2), row_match.group(3)
            cells = re.findall(r"<td\b[^>]*>.*?</td>", row_body, re.S)
            if len(cells) != len(labels):
                return row_match.group(0)
            return row_prefix + "".join(move_cells(cells, label_from, label_after, labels)) + row_suffix

        moved_body = re.sub(r"(<tr\b[^>]*>)(.*?)(</tr>)", move_row, body, flags=re.S)
        return prefix + moved_body + suffix

    return re.sub(r"(<t(?:body|foot)>\s*)(.*?)(\s*</t(?:body|foot)>)", move_section_rows, updated, flags=re.S)


def add_open_option_mark_columns(output_dir) -> None:
    html_path = output_dir / "index.html"
    if not html_path.exists():
        return
    try:
        html_text = html_path.read_text(encoding="utf-8")
        html_path.write_text(add_open_option_mark_columns_to_html(html_text), encoding="utf-8")
    except OSError:
        return


def add_open_option_mark_columns_to_html(html_text: str) -> str:
    section_match = re.search(
        r'(<h2 class="section-title">未平仓期权</h2>.*?<table\b[^>]*class="[^"]*\bsummary-table\b[^"]*"[^>]*>)(.*?)(</table>)',
        html_text,
        re.S,
    )
    if not section_match or "data-option-marks" in section_match.group(1):
        return html_text

    table_prefix, table_body, table_suffix = section_match.groups()
    if "现价" in table_body and "浮动盈亏" in table_body and "占用本金" in table_body:
        return html_text

    updated_body = re.sub(
        r"(<th\b[^>]*>开仓价</th>)",
        r'\1<th class="money" data-sort-type="number">现价</th><th class="money" data-sort-type="number">浮动盈亏</th><th class="money" data-sort-type="number">占用本金</th>',
        table_body,
        count=1,
    )
    updated_body = re.sub(r"(<tbody>\s*)(.*?)(\s*</tbody>)", enrich_option_tbody, updated_body, flags=re.S)
    updated_prefix = table_prefix.replace("<table ", '<table data-option-marks="1" ', 1)
    updated_section = updated_prefix + updated_body + table_suffix
    section_text = section_match.group(0)
    section_text = section_text.replace(table_prefix + table_body + table_suffix, updated_section)
    section_text = section_text.replace(
        "只要期权那一行还没有平仓价，就会继续留在这里，方便你盯到期日。",
        "只要期权那一行还没有平仓价，就会继续留在这里；现价和浮动盈亏会优先通过 HKEX 等公开行情源匹配期权链，Futu OpenD 仅作为兜底，取不到时显示 -。",
        1,
    )
    return html_text[: section_match.start()] + section_text + html_text[section_match.end() :]


def enrich_option_tbody(match: re.Match[str]) -> str:
    prefix, body, suffix = match.groups()

    def enrich_row(row_match: re.Match[str]) -> str:
        row_prefix, row_body, row_suffix = row_match.groups()
        cells = re.findall(r"<td\b[^>]*>.*?</td>", row_body, re.S)
        if len(cells) < 10:
            return row_match.group(0)
        values = [cell_text(cell) for cell in cells]
        key = option_key(values[0], values[2], values[3], values[4], values[5], values[6], values[7], values[8], values[9])
        mark = state.OPEN_OPTION_MARKS.get(key, {})
        pnl_class = mark.get("float_pnl_class") or ""
        pnl_class_attr = f" {html.escape(pnl_class)}" if pnl_class else ""
        inserted = [
            f'<td class="money">{html.escape(mark.get("current_price") or "-")}</td>',
            f'<td class="money{pnl_class_attr}">{html.escape(mark.get("float_pnl") or "-")}</td>',
            f'<td class="money">{html.escape(mark.get("capital") or "-")}</td>',
        ]
        cells.insert(9, "".join(inserted))
        return row_prefix + "".join(cells) + row_suffix

    enriched = re.sub(r"(<tr\b[^>]*>)(.*?)(</tr>)", enrich_row, body, flags=re.S)
    return prefix + enriched + suffix


def reorder_table_columns(table_html: str, desired_order: list[str]) -> str:
    header_match = re.search(r"(<thead>\s*<tr>)(.*?)(</tr>\s*</thead>)", table_html, re.S)
    if not header_match:
        return table_html

    header_cells = re.findall(r"<th\b[^>]*>.*?</th>", header_match.group(2), re.S)
    labels = [cell_text(cell) for cell in header_cells]
    if not header_cells or any(label not in labels for label in desired_order):
        return table_html

    remaining_labels = [label for label in labels if label not in desired_order]
    ordered_labels = desired_order + remaining_labels
    order_indices = [labels.index(label) for label in ordered_labels]

    def reorder_cells(cells: list[str]) -> list[str]:
        if len(cells) != len(labels):
            return cells
        return [cells[index] for index in order_indices]

    updated = (
        table_html[: header_match.start(2)]
        + "".join(reorder_cells(header_cells))
        + table_html[header_match.end(2) :]
    )

    def reorder_section_rows(match: re.Match[str]) -> str:
        prefix, body, suffix = match.group(1), match.group(2), match.group(3)

        def reorder_row(row_match: re.Match[str]) -> str:
            row_prefix, row_body, row_suffix = row_match.group(1), row_match.group(2), row_match.group(3)
            cells = re.findall(r"<td\b[^>]*>.*?</td>", row_body, re.S)
            if len(cells) != len(labels):
                return row_match.group(0)
            return row_prefix + "".join(reorder_cells(cells)) + row_suffix

        reordered_body = re.sub(r"(<tr\b[^>]*>)(.*?)(</tr>)", reorder_row, body, flags=re.S)
        return prefix + reordered_body + suffix

    return re.sub(r"(<t(?:body|foot)>\s*)(.*?)(\s*</t(?:body|foot)>)", reorder_section_rows, updated, flags=re.S)


def insert_table_column(
    table_html: str,
    label: str,
    label_after: str,
    header_html: str,
    row_value,
    footer_value: str = "-",
) -> str:
    header_match = re.search(r"(<thead>\s*<tr>)(.*?)(</tr>\s*</thead>)", table_html, re.S)
    if not header_match:
        return table_html

    header_cells = re.findall(r"<th\b[^>]*>.*?</th>", header_match.group(2), re.S)
    labels = [cell_text(cell) for cell in header_cells]
    if label in labels or label_after not in labels:
        return table_html

    insert_at = labels.index(label_after) + 1
    new_header_cells = list(header_cells)
    new_header_cells.insert(insert_at, header_html)
    updated = (
        table_html[: header_match.start(2)]
        + "".join(new_header_cells)
        + table_html[header_match.end(2) :]
    )

    def insert_section_rows(match: re.Match[str]) -> str:
        section_tag, body, suffix = match.group(1), match.group(2), match.group(3)
        is_footer = section_tag.lower().startswith("<tfoot")

        def insert_row(row_match: re.Match[str]) -> str:
            row_prefix, row_body, row_suffix = row_match.group(1), row_match.group(2), row_match.group(3)
            cells = re.findall(r"<td\b[^>]*>.*?</td>", row_body, re.S)
            if len(cells) != len(labels):
                return row_match.group(0)
            new_cells = list(cells)
            value = footer_value if is_footer else row_value(labels, cells)
            new_cells.insert(insert_at, f'<td class="text">{html.escape(value or "-")}</td>')
            return row_prefix + "".join(new_cells) + row_suffix

        inserted_body = re.sub(r"(<tr\b[^>]*>)(.*?)(</tr>)", insert_row, body, flags=re.S)
        return section_tag + inserted_body + suffix

    return re.sub(r"(<t(?:body|foot)>\s*)(.*?)(\s*</t(?:body|foot)>)", insert_section_rows, updated, flags=re.S)


def insert_last_clear_date_column(core, table_html: str) -> str:
    def row_value(labels: list[str], cells: list[str]) -> str:
        try:
            code = cell_text(cells[labels.index("代码")])
            currency = core.normalize_currency(cell_text(cells[labels.index("币种")]))
        except (ValueError, IndexError):
            return "-"
        ticker = core.normalize_ticker(code, currency)
        return state.LAST_CLEAR_DATE_MAP.get((ticker, currency), "-")

    return insert_table_column(
        table_html,
        "最后清仓时间",
        "币种",
        '<th class="text" data-sort-type="date">最后清仓时间</th>',
        row_value,
    )


def table_header_html(label: str) -> str:
    configs = {
        "年份": ("text", "number"),
        "最后清仓时间": ("text", "date"),
        "代码": ("text", "text"),
        "名称": ("text", "text"),
        "已实现盈亏": ("money", "number"),
        "总盈亏": ("money", "number"),
        "总收益率": ("percent", "number"),
        "综合年化": ("percent", "number"),
        "持有天数": ("num", "number"),
        "持仓浮盈亏": ("money", "number"),
        "分红净额": ("money", "number"),
        "已平仓笔数": ("num", "number"),
        "币种": ("ccy", "text"),
        "当前方向": ("text", "text"),
        "当前仓位": ("num", "number"),
    }
    css_class, sort_type = configs.get(label, ("text", "text"))
    return f'<th class="{css_class}" data-sort-type="{sort_type}">{html.escape(label)}</th>'


def default_td_for_label(label: str, value: str = "-") -> str:
    css_class = {
        "年份": "text",
        "最后清仓时间": "text",
        "代码": "text",
        "名称": "text",
        "已实现盈亏": "money",
        "总盈亏": "money",
        "总收益率": "percent",
        "综合年化": "percent",
        "持有天数": "num",
        "持仓浮盈亏": "money",
        "分红净额": "money",
        "已平仓笔数": "num",
        "币种": "ccy",
        "当前方向": "text",
        "当前仓位": "num",
    }.get(label, "text")
    return f'<td class="{css_class}">{html.escape(value)}</td>'


def row_attr_float(row_prefix: str, attr: str) -> float | None:
    match = re.search(rf'\b{re.escape(attr)}="([^"]*)"', row_prefix)
    if not match:
        return None
    return parse_float(match.group(1))


def weighted_summary_holding_days(row_prefix: str) -> float | None:
    capital = row_attr_float(row_prefix, "data-capital")
    capital_days = row_attr_float(row_prefix, "data-capital-days")
    if capital in (None, 0) or capital_days is None:
        return None
    return max(1.0, capital_days / capital)


def cumulative_summary_holding_days(labels: list[str], cells: list[str], row_prefix: str) -> int | None:
    try:
        code = cell_text(cells[labels.index("代码")])
        currency = cell_text(cells[labels.index("币种")])
    except (ValueError, IndexError):
        return None
    year = ""
    if "年份" in labels:
        try:
            year = cell_text(cells[labels.index("年份")])
        except IndexError:
            year = ""
    if not year:
        year_match = re.search(r'\bdata-year="([^"]*)"', row_prefix)
        year = year_match.group(1) if year_match else ""
    if year and year != "全部":
        annual_days = state.ANNUAL_HOLDING_DAYS_MAP.get((code, currency, year))
        if annual_days is not None:
            return annual_days
    return state.SUMMARY_HOLDING_DAYS_MAP.get((code, currency))


def insert_summary_holding_days_column(table_html: str) -> str:
    header_match = re.search(r"(<thead>\s*<tr>)(.*?)(</tr>\s*</thead>)", table_html, re.S)
    if not header_match:
        return table_html
    header_cells = re.findall(r"<th\b[^>]*>.*?</th>", header_match.group(2), re.S)
    labels = [cell_text(cell) for cell in header_cells]
    if "持有天数" in labels or "综合年化" not in labels:
        return table_html

    insert_at = labels.index("综合年化") + 1
    new_header_cells = list(header_cells)
    new_header_cells.insert(insert_at, table_header_html("持有天数"))
    updated = (
        table_html[: header_match.start(2)]
        + "".join(new_header_cells)
        + table_html[header_match.end(2) :]
    )

    def insert_section_rows(match: re.Match[str]) -> str:
        section_tag, body, suffix = match.group(1), match.group(2), match.group(3)
        is_footer = section_tag.lower().startswith("<tfoot")

        def insert_row(row_match: re.Match[str]) -> str:
            row_prefix, row_body, row_suffix = row_match.group(1), row_match.group(2), row_match.group(3)
            cells = re.findall(r"<td\b[^>]*>.*?</td>", row_body, re.S)
            if len(cells) != len(labels):
                return row_match.group(0)
            new_cells = list(cells)
            days = None if is_footer else cumulative_summary_holding_days(labels, cells, row_prefix)
            if days is None and not is_footer:
                days = weighted_summary_holding_days(row_prefix)
            if days is None:
                new_cell = default_td_for_label("持有天数")
            else:
                rounded_days = round(days)
                new_cell = f'<td class="num" data-sort-value="{days:.12g}">{rounded_days:,}</td>'
            new_cells.insert(insert_at, new_cell)
            return row_prefix + "".join(new_cells) + row_suffix

        inserted_body = re.sub(r"(<tr\b[^>]*>)(.*?)(</tr>)", insert_row, body, flags=re.S)
        return section_tag + inserted_body + suffix

    return re.sub(r"(<t(?:body|foot)>\s*)(.*?)(\s*</t(?:body|foot)>)", insert_section_rows, updated, flags=re.S)


def parse_money_cell(cell_html: str) -> tuple[str, float] | None:
    text = cell_text(cell_html)
    if not text or text in {"-", "--"}:
        return None
    match = re.match(r"^(人民币|港币|美元)\s+(.+)$", text)
    currency = match.group(1) if match else ""
    number_text = match.group(2) if match else text
    value = parse_float(number_text)
    if value is None:
        return None
    return currency, value


def format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def set_td_sort_value(cell_html: str, sort_value: float | None) -> str:
    if sort_value is None:
        return cell_html
    match = re.match(r"(<td\b)([^>]*)(>.*?</td>)", cell_html, re.S)
    if not match:
        return cell_html
    attrs = re.sub(r'\sdata-sort-value="[^"]*"', "", match.group(2))
    return f'{match.group(1)}{attrs} data-sort-value="{sort_value:.12g}"{match.group(3)}'


def replace_td_content(cell_html: str, value: str, sort_value: float | None = None) -> str:
    match = re.match(r"(<td\b)([^>]*>)(.*?)(</td>)", cell_html, re.S)
    if not match:
        return cell_html
    attrs = match.group(2)
    if sort_value is not None:
        attrs = re.sub(r'\sdata-sort-value="[^"]*"', "", attrs)
        attrs = attrs[:-1] + f' data-sort-value="{sort_value:.12g}">'
    return f"{match.group(1)}{attrs}{html.escape(value)}{match.group(4)}"


def decorate_and_sort_holding_rows(core, table_html: str) -> str:
    header_match = re.search(r"(<thead>\s*<tr>)(.*?)(</tr>\s*</thead>)", table_html, re.S)
    body_match = re.search(r"(<tbody>\s*)(.*?)(\s*</tbody>)", table_html, re.S)
    if not header_match or not body_match:
        return table_html

    header_cells = re.findall(r"<th\b[^>]*>.*?</th>", header_match.group(2), re.S)
    labels = [cell_text(cell) for cell in header_cells]
    required = ["代码", "最新市值", "个股仓位", "方向", "币种"]
    if any(label not in labels for label in required):
        return table_html

    code_index = labels.index("代码")
    market_value_index = labels.index("最新市值")
    position_index = labels.index("个股仓位")
    side_index = labels.index("方向")
    currency_index = labels.index("币种")
    rates = current_fx_rates_to_cny()
    row_infos = []

    for row_match in re.finditer(r"(<tr\b[^>]*>)(.*?)(</tr>)", body_match.group(2), re.S):
        row_prefix, row_body, row_suffix = row_match.group(1), row_match.group(2), row_match.group(3)
        cells = re.findall(r"<td\b[^>]*>.*?</td>", row_body, re.S)
        if len(cells) != len(labels):
            row_infos.append((2, 0.0, "", row_prefix, cells, row_suffix, None))
            continue
        parsed = parse_money_cell(cells[market_value_index])
        converted_value = None
        if parsed:
            currency, value = parsed
            if not currency:
                currency = cell_text(cells[currency_index])
            currency_label = display_currency_label(core, currency)
            converted_value = value * rates.get(currency_label, 1.0)
        side = cell_text(cells[side_index])
        is_short = "空头" in side or (converted_value is not None and converted_value < 0)
        code = cell_text(cells[code_index])
        exposure = abs(converted_value) if converted_value is not None else 0.0
        row_infos.append((1 if is_short else 0, -exposure, code, row_prefix, cells, row_suffix, converted_value))

    total_exposure = sum(abs(info[6]) for info in row_infos if isinstance(info[6], (int, float)))
    rendered_rows = []
    for is_short_rank, exposure_rank, code, row_prefix, cells, row_suffix, converted_value in sorted(row_infos):
        if cells and isinstance(converted_value, (int, float)):
            cells = list(cells)
            exposure = abs(converted_value)
            weight = exposure / total_exposure if total_exposure else None
            cells[market_value_index] = set_td_sort_value(cells[market_value_index], converted_value)
            cells[position_index] = replace_td_content(cells[position_index], format_percent(weight), weight)
        rendered_rows.append(row_prefix + "".join(cells) + row_suffix)

    new_body = "\n      " + "".join(rendered_rows) + "\n    "
    return table_html[: body_match.start(2)] + new_body + table_html[body_match.end(2) :]


def insert_holding_metric_columns(core, table_html: str) -> str:
    header_match = re.search(r"(<thead>\s*<tr>)(.*?)(</tr>\s*</thead>)", table_html, re.S)
    if not header_match:
        return table_html
    header_cells = re.findall(r"<th\b[^>]*>.*?</th>", header_match.group(2), re.S)
    labels = [cell_text(cell) for cell in header_cells]
    if "代码" not in labels or "币种" not in labels or "最新市值" not in labels:
        return table_html

    currency_totals: dict[str, float] = {}
    body_match = re.search(r"<tbody>\s*(.*?)\s*</tbody>", table_html, re.S)
    if body_match:
        for row_match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", body_match.group(1), re.S):
            cells = re.findall(r"<td\b[^>]*>.*?</td>", row_match.group(1), re.S)
            if len(cells) != len(labels):
                continue
            parsed = parse_money_cell(cells[labels.index("最新市值")])
            if not parsed:
                continue
            currency, value = parsed
            if not currency:
                currency = cell_text(cells[labels.index("币种")])
            if currency and currency != "-":
                currency_totals[currency] = currency_totals.get(currency, 0.0) + abs(value)

    def position_weight(labels: list[str], cells: list[str]) -> str:
        parsed = parse_money_cell(cells[labels.index("最新市值")])
        if not parsed:
            return "-"
        currency, value = parsed
        if not currency:
            currency = cell_text(cells[labels.index("币种")])
        total = currency_totals.get(currency or "", 0.0)
        if not total:
            return "-"
        return format_percent(abs(value) / total)

    def holding_days(labels: list[str], cells: list[str]) -> str:
        try:
            code = cell_text(cells[labels.index("代码")])
            currency = core.normalize_currency(cell_text(cells[labels.index("币种")]))
        except (ValueError, IndexError):
            return "-"
        ticker = core.normalize_ticker(code, currency)
        return state.HOLDING_DAYS_MAP.get((ticker, currency), "-")

    updated = insert_table_column(
        table_html,
        "个股仓位",
        "当日盈亏",
        '<th class="percent" data-sort-type="number">个股仓位</th>',
        position_weight,
    )
    updated = insert_table_column(
        updated,
        "持股天数",
        "个股仓位",
        '<th class="num" data-sort-type="number">持股天数</th>',
        holding_days,
    )
    return decorate_and_sort_holding_rows(core, updated)


def prioritize_stock_summary_columns(table_html: str) -> str:
    return reorder_table_columns(table_html, STOCK_SUMMARY_COLUMN_ORDER)


def add_balanced_summary_table_script(html_text: str) -> str:
    marker = "function balanceSummaryTableWidths()"
    if marker in html_text:
        return html_text
    script = """
        <script>
        function tableHeaderCells(table) {
          return Array.from(table.querySelectorAll('thead th'));
        }

        function tableHeaderLabels(table) {
          return tableHeaderCells(table).map((th) => (th.textContent || '').trim());
        }

        function sortedCurrencyLabels(labels) {
          const map = {};
          labels.forEach((label) => {
            if (label && label !== '-') map[label] = 0;
          });
          return orderedCurrencyEntries(map).map(([currency]) => currency);
        }

        function formatSingleMoney(currency, value) {
          if (!currency || !Number.isFinite(value)) return '-';
          return Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        }

        function formatSinglePercent(value) {
          if (!Number.isFinite(value)) return '-';
          return `${(Number(value) * 100).toFixed(2)}%`;
        }

        function footerCellClassForHeader(header) {
          const classes = Array.from(header.classList).filter((name) => !name.startsWith('sort-'));
          return classes.length ? classes.join(' ') : 'text';
        }

        function replaceSummaryFooterRows(table, headerLabels, rowsByCurrency, statsByCurrency) {
          let tfoot = table.querySelector('tfoot');
          if (!tfoot) {
            tfoot = document.createElement('tfoot');
            table.appendChild(tfoot);
          }
          tfoot.innerHTML = '';
          const headers = tableHeaderCells(table);
          const currencies = sortedCurrencyLabels(Object.keys(rowsByCurrency));
          if (!currencies.length) {
            const row = document.createElement('tr');
            row.className = 'summary-footer';
            headerLabels.forEach((label, index) => {
              const cell = document.createElement('td');
              cell.className = footerCellClassForHeader(headers[index]);
              setSummaryCell(cell, label, index === 0 ? '汇总' : '-');
              row.appendChild(cell);
            });
            tfoot.appendChild(row);
            return;
          }

          currencies.forEach((currency) => {
            const stats = statsByCurrency[currency];
            const row = document.createElement('tr');
            row.className = 'summary-footer';
            headerLabels.forEach((label, index) => {
              const cell = document.createElement('td');
              cell.className = footerCellClassForHeader(headers[index]);
              let text = '-';

              if ((label === '代码' || label === '年份' || label === '最后清仓时间') && index === 0) {
                text = '汇总';
              } else if (label === '名称') {
                text = '-';
              } else if (label === '币种') {
                text = currency;
              } else if (label === '当前方向' || label === '方向') {
                text = stats.sides.size === 1 ? Array.from(stats.sides)[0] : '混合';
              } else if (label === '年份') {
                text = stats.years.size === 1 ? Array.from(stats.years)[0] : '全部';
              } else if (stats.countLabels.has(label)) {
                const value = stats.countTotals[label];
                text = Number.isFinite(value) ? Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 }) : '-';
              } else if (stats.moneyLabels.has(label)) {
                text = formatSingleMoney(currency, stats.moneyTotals[label]);
              } else if (label === '盈亏率' && stats.summaryKind === 'holdings') {
                text = stats.holdingCost ? formatSinglePercent(stats.holdingPnl / stats.holdingCost) : '-';
              } else if (label === '个股仓位' && stats.summaryKind === 'holdings') {
                text = stats.positionWeight ? formatSinglePercent(stats.positionWeight) : '-';
              } else if ((label === '总收益率' || label === '综合年化') && (stats.summaryKind === 'stock' || stats.summaryKind === 'annual')) {
                if (label === '总收益率') {
                  text = stats.capital ? formatSinglePercent(stats.totalPnl / stats.capital) : '-';
                } else {
                  text = stats.capitalDays ? formatSinglePercent(stats.totalPnl * 365 / stats.capitalDays) : '-';
                }
              }

              setSummaryCell(cell, label, text);
              row.appendChild(cell);
            });
            tfoot.appendChild(row);
          });
        }

        function updateSummaryTable(table) {
          const summaryKind = table.dataset.summaryKind || '';
          if (!summaryKind) return;
          const headerLabels = tableHeaderLabels(table);
          const rows = Array.from(table.querySelectorAll('tbody tr')).filter((row) => row.style.display !== 'none');
          const currencyIndex = headerLabels.indexOf('币种');
          const yearIndex = headerLabels.indexOf('年份');
          const sideIndex = headerLabels.indexOf('当前方向') >= 0 ? headerLabels.indexOf('当前方向') : headerLabels.indexOf('方向');
          const holdingsCostIndex = headerLabels.indexOf('持仓成本');
          const holdingsPnlIndex = headerLabels.indexOf('浮动盈亏');
          const holdingsWeightIndex = headerLabels.indexOf('个股仓位');
          const countLabels = new Set(['已平仓笔数', '交易笔数']);
          const moneyLabels = new Set(['分红净额', '已实现盈亏', '浮动盈亏', '持仓浮盈亏', '总盈亏', '最新市值', '当日盈亏', '持仓成本']);
          const rowsByCurrency = {};
          const statsByCurrency = {};

          const ensureStats = (currency) => {
            const label = currency || '未标注币种';
            if (!rowsByCurrency[label]) rowsByCurrency[label] = [];
            if (!statsByCurrency[label]) {
              statsByCurrency[label] = {
                summaryKind,
                countLabels,
                moneyLabels,
                rows: rowsByCurrency[label],
                years: new Set(),
                sides: new Set(),
                countTotals: {},
                moneyTotals: {},
                capital: 0,
                capitalDays: 0,
                totalPnl: 0,
                holdingCost: 0,
                holdingPnl: 0,
                positionWeight: 0,
              };
            }
            return statsByCurrency[label];
          };

          rows.forEach((row) => {
            const cells = Array.from(row.children);
            const currency = currencyIndex >= 0 ? (cells[currencyIndex]?.textContent || '').trim() : '';
            const stats = ensureStats(currency);
            rowsByCurrency[currency || '未标注币种'].push(row);

            if (yearIndex >= 0) {
              const year = (cells[yearIndex]?.textContent || '').trim();
              if (year && year !== '-') stats.years.add(year);
            }
            if (sideIndex >= 0) {
              const side = (cells[sideIndex]?.textContent || '').trim();
              if (side && side !== '-') stats.sides.add(side);
            }

            headerLabels.forEach((label, index) => {
              const text = (cells[index]?.textContent || '').trim();
              if (countLabels.has(label)) {
                const value = parseSortableValue(text, 'number');
                if (!Number.isNaN(value)) stats.countTotals[label] = (stats.countTotals[label] || 0) + value;
              }
              if (moneyLabels.has(label)) {
                const parsed = parseCurrencyCell(text);
                if (parsed) stats.moneyTotals[label] = (stats.moneyTotals[label] || 0) + parsed.value;
              }
            });

            if (summaryKind === 'stock' || summaryKind === 'annual') {
              const capital = Number.parseFloat(row.dataset.capital || 'NaN');
              const capitalDays = Number.parseFloat(row.dataset.capitalDays || 'NaN');
              const totalPnl = Number.parseFloat(row.dataset.totalPnl || 'NaN');
              if (!Number.isNaN(capital)) stats.capital += capital;
              if (!Number.isNaN(capitalDays)) stats.capitalDays += capitalDays;
              if (!Number.isNaN(totalPnl)) stats.totalPnl += totalPnl;
            }

            if (summaryKind === 'holdings') {
              const costParsed = holdingsCostIndex >= 0 ? parseCurrencyCell(cells[holdingsCostIndex]?.textContent || '') : null;
              const pnlParsed = holdingsPnlIndex >= 0 ? parseCurrencyCell(cells[holdingsPnlIndex]?.textContent || '') : null;
              const weightCell = holdingsWeightIndex >= 0 ? cells[holdingsWeightIndex] : null;
              const weight = weightCell ? Number.parseFloat(weightCell.dataset.sortValue ?? 'NaN') : NaN;
              if (costParsed) stats.holdingCost += costParsed.value;
              if (pnlParsed) stats.holdingPnl += pnlParsed.value;
              if (!Number.isNaN(weight)) stats.positionWeight += weight;
            }
          });

          replaceSummaryFooterRows(table, headerLabels, rowsByCurrency, statsByCurrency);
        }

        function balanceSummaryTableWidths() {
          document.querySelectorAll('.summary-wrap').forEach((wrap) => {
            const table = wrap.querySelector('.summary-table');
            if (!table) return;
            table.classList.remove('fit-width');
            table.style.removeProperty('width');
            const naturalWidth = table.scrollWidth;
            const availableWidth = wrap.clientWidth;
            if (naturalWidth > 0 && naturalWidth <= availableWidth + 1) {
              table.classList.add('fit-width');
            }
          });
        }

        function refreshSummaryTablesAndWidths() {
          if (typeof updateSummaryTables === 'function') updateSummaryTables();
          requestAnimationFrame(balanceSummaryTableWidths);
        }

        function refineAnnualYearFilter() {
          const select = document.querySelector('.js-year-filter[data-target-table="annual-summary-table"]');
          const table = document.querySelector('.annual-summary-table');
          if (!select || !table) return;
          const rows = Array.from(table.querySelectorAll('tbody tr'));
          const applyRefinement = () => {
            if (select.value === 'all') {
              rows.forEach((row) => {
                if ((row.dataset.year || '') === 'total') row.style.display = 'none';
              });
            }
            if (typeof updateSummaryTable === 'function') updateSummaryTable(table);
            requestAnimationFrame(balanceSummaryTableWidths);
          };
          select.addEventListener('change', applyRefinement);
          applyRefinement();
        }

        window.addEventListener('load', refreshSummaryTablesAndWidths);
        window.addEventListener('resize', balanceSummaryTableWidths);
        document.addEventListener('DOMContentLoaded', () => {
          refineAnnualYearFilter();
          refreshSummaryTablesAndWidths();
        });
        if (document.readyState !== 'loading') {
          refineAnnualYearFilter();
          refreshSummaryTablesAndWidths();
        }
        </script>
"""
    if "</body>" in html_text:
        return html_text.replace("</body>", script + "</body>", 1)
    return html_text + script


def annotate_holdings_fx_note(html_text: str) -> str:
    return html_text.replace(
        "这里只统计已经录入主表、且当前仍未平仓的现股仓位，按仓位绝对值从大到小排序。",
        "这里只统计已经录入主表、且当前仍未平仓的现股仓位；个股仓位按实时汇率折成人民币口径计算，并按仓位绝对值从大到小排序。",
        1,
    )


def summary_table_match(html_text: str, summary_kind: str) -> re.Match[str] | None:
    return re.search(
        rf'<table\b(?=[^>]*data-summary-kind="{re.escape(summary_kind)}")[^>]*>.*?</table>',
        html_text,
        re.S,
    )


def table_labels(table_html: str) -> list[str]:
    header_match = re.search(r"<thead>\s*<tr>(.*?)</tr>\s*</thead>", table_html, re.S)
    if not header_match:
        return []
    return [cell_text(cell) for cell in re.findall(r"<th\b[^>]*>.*?</th>", header_match.group(1), re.S)]


def body_rows(table_html: str) -> list[tuple[str, str, str, list[str]]]:
    body_match = re.search(r"<tbody>\s*(.*?)\s*</tbody>", table_html, re.S)
    if not body_match:
        return []
    rows = []
    for row_match in re.finditer(r"(<tr\b[^>]*>)(.*?)(</tr>)", body_match.group(1), re.S):
        cells = re.findall(r"<td\b[^>]*>.*?</td>", row_match.group(2), re.S)
        rows.append((row_match.group(1), row_match.group(2), row_match.group(3), cells))
    return rows


def cell_map_from_row(labels: list[str], cells: list[str]) -> dict[str, str]:
    if len(cells) != len(labels):
        return {}
    return dict(zip(labels, cells))


def stock_summary_lookup(stock_table_html: str) -> dict[tuple[str, str], dict[str, str]]:
    labels = table_labels(stock_table_html)
    if "代码" not in labels or "币种" not in labels:
        return {}
    lookup = {}
    for _prefix, _body, _suffix, cells in body_rows(stock_table_html):
        row_map = cell_map_from_row(labels, cells)
        if not row_map:
            continue
        key = (cell_text(row_map["代码"]), cell_text(row_map["币种"]))
        lookup[key] = row_map
    return lookup


def stock_summary_total_rows(stock_table_html: str) -> list[tuple[str, str, str, dict[str, str]]]:
    labels = table_labels(stock_table_html)
    if not labels:
        return []
    total_rows = []
    for row_prefix, _row_body, row_suffix, cells in body_rows(stock_table_html):
        row_map = cell_map_from_row(labels, cells)
        if not row_map:
            continue
        total_prefix = row_prefix
        if "data-year=" not in total_prefix:
            total_prefix = total_prefix.replace("<tr", '<tr data-year="total"', 1)
        total_rows.append((total_prefix, "", row_suffix, row_map))
    return total_rows


def annual_source_cell(label: str, annual_map: dict[str, str], stock_map: dict[str, str]) -> str:
    if label in annual_map:
        return annual_map[label]
    if label == "已平仓笔数" and "交易笔数" in annual_map:
        return annual_map["交易笔数"]
    if label in {"最后清仓时间", "当前方向", "当前仓位"} and label in stock_map:
        return stock_map[label]
    return default_td_for_label(label)


def normalize_annual_summary_columns(
    annual_table_html: str,
    stock_lookup: dict[tuple[str, str], dict[str, str]],
    stock_total_rows: list[tuple[str, str, str, dict[str, str]]],
) -> str:
    labels = table_labels(annual_table_html)
    if not labels or "代码" not in labels or "币种" not in labels:
        return annual_table_html

    header_match = re.search(r"(<thead>\s*<tr>)(.*?)(</tr>\s*</thead>)", annual_table_html, re.S)
    body_match = re.search(r"(<tbody>\s*)(.*?)(\s*</tbody>)", annual_table_html, re.S)
    if not header_match or not body_match:
        return annual_table_html

    new_headers = "".join(table_header_html(label) for label in ANNUAL_STOCK_SUMMARY_COLUMN_ORDER)
    new_header_html = header_match.group(1) + new_headers + header_match.group(3)

    rendered_rows = []
    for row_prefix, _row_body, row_suffix, stock_map in stock_total_rows:
        new_cells = [
            '<td class="text">全部</td>' if label == "年份" else stock_map.get(label, default_td_for_label(label))
            for label in ANNUAL_STOCK_SUMMARY_COLUMN_ORDER
        ]
        rendered_rows.append(row_prefix + "".join(new_cells) + row_suffix)

    for row_prefix, _row_body, row_suffix, cells in body_rows(annual_table_html):
        annual_map = cell_map_from_row(labels, cells)
        if not annual_map:
            rendered_rows.append(row_prefix + "".join(cells) + row_suffix)
            continue
        key = (cell_text(annual_map["代码"]), cell_text(annual_map["币种"]))
        stock_map = stock_lookup.get(key, {})
        new_cells = [
            annual_source_cell(label, annual_map, stock_map)
            for label in ANNUAL_STOCK_SUMMARY_COLUMN_ORDER
        ]
        rendered_rows.append(row_prefix + "".join(new_cells) + row_suffix)

    new_body_html = body_match.group(1) + "\n      " + "".join(rendered_rows) + "\n    " + body_match.group(3)

    footer_match = re.search(r"(<tfoot>\s*)(.*?)(\s*</tfoot>)", annual_table_html, re.S)
    new_footer_html = None
    if footer_match:
        cells = "".join(default_td_for_label(label) for label in ANNUAL_STOCK_SUMMARY_COLUMN_ORDER)
        new_footer_html = footer_match.group(1) + f'<tr class="summary-footer">{cells}</tr>' + footer_match.group(3)

    updated = annual_table_html
    if footer_match and new_footer_html is not None:
        updated = updated[: footer_match.start()] + new_footer_html + updated[footer_match.end() :]
    updated = updated[: body_match.start()] + new_body_html + updated[body_match.end() :]
    updated = updated[: header_match.start()] + new_header_html + updated[header_match.end() :]
    return updated


def align_annual_summary_with_stock_summary(html_text: str) -> str:
    annual_match = summary_table_match(html_text, "annual")
    stock_match = summary_table_match(html_text, "stock")
    if not annual_match or not stock_match:
        return html_text
    stock_lookup = stock_summary_lookup(stock_match.group(0))
    if not stock_lookup:
        return html_text
    total_rows = stock_summary_total_rows(stock_match.group(0))
    annual_table = normalize_annual_summary_columns(annual_match.group(0), stock_lookup, total_rows)
    return html_text[: annual_match.start()] + annual_table + html_text[annual_match.end() :]


def prioritize_annual_summary_filter(html_text: str) -> str:
    def replace_select(match: re.Match[str]) -> str:
        prefix, options, suffix = match.group(1), match.group(2), match.group(3)
        options = re.sub(r"\sselected\b", "", options)
        if 'value="total"' not in options:
            options = (
                '<option value="total" selected>全部汇总</option>'
                + options.replace('<option value="all">全部年份</option>', '<option value="all">全部年份明细</option>', 1)
            )
        else:
            options = re.sub(r'(<option value="total")([^>]*>)', r'\1 selected\2', options, count=1)
        return prefix + options + suffix

    return re.sub(
        r'(<select\b[^>]*class="[^"]*\bjs-year-filter\b[^"]*"[^>]*data-target-table="annual-summary-table"[^>]*>)(.*?)(</select>)',
        replace_select,
        html_text,
        flags=re.S,
    )


def remove_stock_summary_section(html_text: str) -> str:
    return re.sub(
        r'\n\s*<details\b(?=[^>]*class="[^"]*\bdashboard-section\b[^"]*")[^>]*>\s*'
        r'(?:(?!</details>).)*?<h2 class="section-title">个股汇总</h2>'
        r'(?:(?!</details>).)*?</details>\s*',
        "\n",
        html_text,
        flags=re.S,
    )


def add_holdings_cny_settlement_footer_script(html_text: str) -> str:
    marker = "Codex summary CNY settlement footer"
    if marker in html_text:
        return html_text
    rates_json = json.dumps(current_fx_rates_to_cny(), ensure_ascii=False)
    script = f"""
        <script>
        /* {marker} */
        (function addSummarySettlementRows() {{
          const fxRatesToCny = {rates_json};
          const moneyLabels = new Set(['分红净额', '已实现盈亏', '浮动盈亏', '持仓浮盈亏', '总盈亏', '最新市值', '当日盈亏', '持仓成本']);
          const toneLabels = new Set(['分红净额', '已实现盈亏', '浮动盈亏', '持仓浮盈亏', '总盈亏', '当日盈亏', '盈亏率', '总收益率', '综合年化']);

          function numberFromText(text) {{
            const cleaned = String(text || '').replace(/,/g, '').replace(/%/g, '').replace(/^(人民币|港币|美元)\\s+/, '').trim();
            if (!cleaned || cleaned === '-' || cleaned === '--') return null;
            const value = Number(cleaned);
            return Number.isFinite(value) ? value : null;
          }}

          function formatNumber(value) {{
            if (!Number.isFinite(value)) return '-';
            return value.toLocaleString('zh-CN', {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
          }}

          function formatPercent(value) {{
            if (!Number.isFinite(value)) return '-';
            return `${{(value * 100).toFixed(2)}}%`;
          }}

          function classForValue(label, value, baseClass) {{
            const classes = [baseClass || 'text'];
            if (toneLabels.has(label) && Number.isFinite(value)) {{
              if (value > 0) classes.push('value-positive');
              else if (value < 0) classes.push('value-negative');
              else classes.push('value-zero');
            }}
            return classes.join(' ');
          }}

          function blankStats(summaryKind) {{
            return {{ summaryKind, count: 0, money: {{}}, capital: 0, capitalDays: 0 }};
          }}

          function addMoney(stats, label, value, rate) {{
            if (!Number.isFinite(value)) return;
            stats.money[label] = (stats.money[label] || 0) + value * rate;
          }}

          function collectStats(table) {{
            const headers = Array.from(table.querySelectorAll('thead th'));
            const labels = headers.map((header) => (header.textContent || '').trim());
            const currencyIndex = labels.indexOf('币种');
            if (currencyIndex < 0) return {{ labels, byCurrency: new Map(), cny: blankStats(table.dataset.summaryKind || '') }};

            const byCurrency = new Map();
            const cny = blankStats(table.dataset.summaryKind || '');
            table.querySelectorAll('tbody tr').forEach((row) => {{
              if (row.style.display === 'none') return;
              const cells = Array.from(row.children);
              if (cells.length !== labels.length) return;
              const currency = (cells[currencyIndex].textContent || '').trim();
              if (!currency || currency === '-') return;
              const rate = Number(fxRatesToCny[currency] || 1);
              const stats = byCurrency.get(currency) || blankStats(table.dataset.summaryKind || '');
              byCurrency.set(currency, stats);
              stats.count += 1;
              cny.count += 1;

              labels.forEach((label, index) => {{
                if (!moneyLabels.has(label)) return;
                const value = numberFromText(cells[index].textContent);
                addMoney(stats, label, value, 1);
                addMoney(cny, label, value, rate);
              }});

              const capital = numberFromText(row.dataset.capital);
              const capitalDays = numberFromText(row.dataset.capitalDays);
              if (Number.isFinite(capital)) {{
                stats.capital += capital;
                cny.capital += capital * rate;
              }}
              if (Number.isFinite(capitalDays)) {{
                stats.capitalDays += capitalDays;
                cny.capitalDays += capitalDays * rate;
              }}
            }});
            return {{ labels, byCurrency, cny }};
          }}

          function footerCellClass(headers, index) {{
            const header = headers[index];
            if (!header) return 'text';
            const classes = Array.from(header.classList).filter((name) => !name.startsWith('sort-'));
            return classes.length ? classes.join(' ') : 'text';
          }}

          function appendRow(tfoot, table, labels, stats, currency, title, isCny) {{
            if (!stats.count) return;
            const headers = Array.from(table.querySelectorAll('thead th'));
            const row = document.createElement('tr');
            row.className = isCny ? 'summary-footer summary-footer-cny' : 'summary-footer';
            labels.forEach((label, index) => {{
              const cell = document.createElement('td');
              cell.className = footerCellClass(headers, index);
              let numeric = null;
              let text = '-';
              if (index === 0) {{
                text = title;
              }} else if (label === '币种') {{
                text = currency;
              }} else if (moneyLabels.has(label)) {{
                numeric = stats.money[label];
                text = formatNumber(numeric);
                cell.className = classForValue(label, numeric, cell.className);
              }} else if (label === '盈亏率' && stats.summaryKind === 'holdings') {{
                const pnl = stats.money['浮动盈亏'];
                const cost = stats.money['持仓成本'];
                numeric = Number.isFinite(pnl) && cost ? pnl / Math.abs(cost) : null;
                text = formatPercent(numeric);
                cell.className = classForValue(label, numeric, cell.className);
              }} else if (label === '个股仓位' && stats.summaryKind === 'holdings') {{
                numeric = 1;
                text = '100.00%';
              }} else if ((label === '总收益率' || label === '综合年化') && (stats.summaryKind === 'stock' || stats.summaryKind === 'annual')) {{
                const pnl = stats.money['总盈亏'];
                numeric = label === '总收益率'
                  ? (Number.isFinite(pnl) && stats.capital ? pnl / stats.capital : null)
                  : (Number.isFinite(pnl) && stats.capitalDays ? pnl * 365 / stats.capitalDays : null);
                text = formatPercent(numeric);
                cell.className = classForValue(label, numeric, cell.className);
              }}
              if (Number.isFinite(numeric)) cell.dataset.sortValue = String(numeric);
              cell.textContent = text;
              row.appendChild(cell);
            }});
            tfoot.appendChild(row);
          }}

          function apply() {{
            document.querySelectorAll('.summary-table[data-summary-kind]').forEach((table) => {{
              let tfoot = table.querySelector('tfoot');
              if (!tfoot) {{
                tfoot = document.createElement('tfoot');
                table.appendChild(tfoot);
              }}
              tfoot.innerHTML = '';
              const {{ labels, byCurrency, cny }} = collectStats(table);
              if (!labels || !labels.length) return;
              byCurrency.forEach((stats, currency) => appendRow(tfoot, table, labels, stats, currency, `${{currency}}汇总`, false));
              appendRow(tfoot, table, labels, cny, '人民币', '人民币折算汇总', true);
            }});
          }}

          function scheduleApply() {{
            requestAnimationFrame(() => {{
              apply();
              if (typeof balanceSummaryTableWidths === 'function') {{
                requestAnimationFrame(balanceSummaryTableWidths);
              }}
            }});
          }}

          const originalUpdateSummaryTable = window.updateSummaryTable;
          if (typeof originalUpdateSummaryTable === 'function' && !originalUpdateSummaryTable.__withCnySettlement) {{
            const wrappedUpdateSummaryTable = function(...args) {{
              const result = originalUpdateSummaryTable.apply(this, args);
              scheduleApply();
              return result;
            }};
            wrappedUpdateSummaryTable.__withCnySettlement = true;
            window.updateSummaryTable = wrappedUpdateSummaryTable;
          }}

          const originalUpdateSummaryTables = window.updateSummaryTables;
          if (typeof originalUpdateSummaryTables === 'function' && !originalUpdateSummaryTables.__withCnySettlement) {{
            const wrappedUpdateSummaryTables = function(...args) {{
              const result = originalUpdateSummaryTables.apply(this, args);
              scheduleApply();
              return result;
            }};
            wrappedUpdateSummaryTables.__withCnySettlement = true;
            window.updateSummaryTables = wrappedUpdateSummaryTables;
          }}

          if (document.readyState === 'loading') {{
            document.addEventListener('DOMContentLoaded', scheduleApply);
          }} else {{
            scheduleApply();
          }}
          window.addEventListener('load', scheduleApply);
        }})();
        </script>
"""
    if "</body>" in html_text:
        return html_text.replace("</body>", script + "</body>", 1)
    return html_text + script
