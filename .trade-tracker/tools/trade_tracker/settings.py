from __future__ import annotations

TYPE_TO_CORE_CODE = {
    "卖出": "sell",
    "SELL": "sell",
    "Sell": "sell",
    "sell": "sell",
    "买入": "buy",
    "BUY": "buy",
    "Buy": "buy",
    "buy": "buy",
}

OPTION_EVENTS = {"认购", "认沽", "call", "put", "CALL", "PUT", "Call", "Put"}

HOLDINGS_COLUMN_ORDER = [
    "代码",
    "名称",
    "最新市值",
    "浮动盈亏",
    "盈亏率",
    "持股数",
    "现价",
    "持仓成本",
    "当日盈亏",
    "个股仓位",
    "持股天数",
    "持仓均价",
    "回本空间",
    "方向",
    "币种",
    "最近买入",
]

STOCK_SUMMARY_COLUMN_ORDER = [
    "最后清仓时间",
    "代码",
    "名称",
    "已实现盈亏",
    "总盈亏",
    "总收益率",
    "综合年化",
    "持有天数",
    "持仓浮盈亏",
    "分红净额",
    "已平仓笔数",
    "币种",
    "当前方向",
    "当前仓位",
]

ANNUAL_STOCK_SUMMARY_COLUMN_ORDER = ["年份", *STOCK_SUMMARY_COLUMN_ORDER]

OVERVIEW_METRIC_ORDER = [
    "总盈亏",
    "总收益率",
    "综合年化",
    "当前市值",
    "持仓成本",
    "持仓浮盈亏",
    "持仓当日盈亏",
    "已实现盈亏",
    "当前持仓标的",
    "未平仓期权腿",
    "最近交易日期",
    "行情刷新日期",
]

OVERVIEW_METRIC_CLASSES = {
    "总盈亏": "metric-card-hero",
    "总收益率": "metric-card-return",
    "综合年化": "metric-card-annual",
    "当前市值": "metric-card-broad",
    "持仓成本": "metric-card-broad",
    "持仓浮盈亏": "metric-card-broad",
    "持仓当日盈亏": "metric-card-broad",
    "已实现盈亏": "metric-card-broad",
    "当前持仓标的": "metric-card-mini",
    "未平仓期权腿": "metric-card-mini",
    "最近交易日期": "metric-card-mini",
    "行情刷新日期": "metric-card-mini",
}

OVERVIEW_HIDDEN_METRICS = {"分红净额"}

FX_RATE_SECIDS_TO_CNY = {
    "港币": "133.HKDCNH",
    "美元": "133.USDCNH",
}

FX_RATE_YAHOO_SYMBOLS_TO_CNY = {
    "港币": "HKDCNY=X",
    "美元": "USDCNY=X",
}

FX_RATE_FALLBACKS_TO_CNY = {
    "人民币": 1.0,
    "港币": 0.92,
    "美元": 7.20,
}

OVERVIEW_CURRENCIES = ["人民币", "港币", "美元"]

OVERVIEW_CURRENCY_METRIC_ORDER = [
    "总盈亏",
    "总收益率",
    "综合年化",
    "当前市值",
    "持仓成本",
    "已实现盈亏",
    "持仓浮盈亏",
    "持仓当日盈亏",
]

