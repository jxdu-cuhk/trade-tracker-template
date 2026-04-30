from __future__ import annotations

import re
from pathlib import Path


PRODUCT_TITLE = "韭菜账本 Leek Ledger"
PRODUCT_TAGLINE = "一个本地优先的交易记录、盈亏复盘与持仓看板。记录每一次被市场教育的痕迹。"
PRODUCT_DETAIL = "由 Trade Tracker.xlsx 生成，集中展示当前持仓、未平仓期权、个股汇总和交易时间线。"


def brand_dashboard_html(html_text: str) -> str:
    text = html_text.replace("<title>交易看板预览</title>", f"<title>{PRODUCT_TITLE}</title>")
    text = text.replace(
        '<h1 class="index-title">交易看板预览</h1>',
        f'<h1 class="index-title">{PRODUCT_TITLE}</h1>',
    )
    text = text.replace(
        "未平仓期权暂未计入实时估值。",
        "未平仓期权会在期权表尝试展示现价和浮动盈亏，收益曲线暂不计入实时估值。",
    )
    return re.sub(
        r'<p class="index-text">.*?</p>',
        f'<p class="index-text">{PRODUCT_TAGLINE}{PRODUCT_DETAIL}</p>',
        text,
        count=1,
        flags=re.S,
    )


def brand_launcher_html(html_text: str) -> str:
    text = html_text.replace("<title>交易看板</title>", f"<title>{PRODUCT_TITLE}</title>")
    text = text.replace("<h1>交易看板</h1>", f"<h1>{PRODUCT_TITLE}</h1>")
    return re.sub(
        r"<p>正在打开由 Trade Tracker\.xlsx 生成的最新看板。如果没有自动跳转，请点 (.*?)。</p>",
        r"<p>正在打开本地优先的交易记录、盈亏复盘与持仓看板。如果没有自动跳转，请点 \1。</p>",
        text,
        count=1,
        flags=re.S,
    )


def brand_preview_index(output_dir: Path) -> None:
    html_path = output_dir / "index.html"
    if not html_path.exists():
        return
    try:
        html_path.write_text(brand_dashboard_html(html_path.read_text(encoding="utf-8")), encoding="utf-8")
    except OSError:
        return
