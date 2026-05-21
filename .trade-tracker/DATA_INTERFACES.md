# 韭菜账本显示数据接口梳理

这份文档只描述当前看板的显示数据接口和口径边界，方便后续一起优化数值统计。真实交易事实仍以 `Trade Tracker.xlsx` 为源头。

## 总体链路

1. `Trade Tracker.xlsx`
   - 主表 `交易记录` 是交易源数据。
   - 可选表 `分红记录` 记录分红、股息税、公司行动等现金事件。
   - `.trade-tracker/history/` 的券商导出只用于补名称、识别分红、补充明细拆分，不应反过来覆盖手工确认的交易事实。

2. 原始核心生成器
   - `.trade-tracker/tools/export_trade_tracker_core.pyc` 读取工作簿，产出基础 `dashboard_data` 和基础 HTML。
   - 主要基础集合：`holdings`、`stock_summary`、`annual_summary`、`curve_series` 以及各种按币种汇总文本。

3. 本项目补丁层
   - `.trade-tracker/tools/trade_tracker/patcher.py` 挂载扩展逻辑。
   - `build_dashboard_data()` 的改写顺序是：期权/已实现/分红成本回冲，当前持仓当日盈亏分段，真实历史行情收益曲线，曲线资金口径补充，最后生成统一展示 payload。
   - `render_dashboard_html()` 再插入或重排：当前持仓顶部卡、盈亏日历、清仓分析、期权收益分析、收益报告、总收益曲线样式、总体概览拆分、分页、刷新面板等。

4. 前端二次计算
   - 页面中有几份 JSON / DOM 数据会被浏览器脚本再次计算，例如 `data-return-curve-json`、`data-realized-payload`、`data-display-payload`、`data-option-payload`、`data-performance-stock-payload`。
   - 还有少量指标保留 HTML 表格兜底读取，例如旧版持仓表兼容和表格汇总行。

## 工作簿接口

`交易记录` 当前约定列：

| 列 | 含义 | 主要使用方 |
| --- | --- | --- |
| `类型` | 股票/买入/卖出 | 方向、期权收益、现金流 |
| `开仓` | 建仓或买入日期 | 持仓天数、曲线、收益率 |
| `到期` | 期权到期日 | 未平仓期权、期权收益 |
| `平仓` | 平仓或卖出日期 | 已实现、清仓、曲线 |
| `代码` | 标的代码 | 所有区块 |
| `事件` | 现股/认购/认沽 | 股票、期权分类 |
| `行权价` | 期权 strike | 期权行情、资金口径 |
| `数量` | 股数或合约张数 | 持仓、市值、期权 |
| `开仓价` | 买入价或权利金 | 成本、收益 |
| `平仓价` | 卖出价或回补权利金 | 已实现收益 |
| `费用` | 手续费/交易费 | 交易费用、收益 |
| `占用本金` | 显式策略资金或保证金 | 期权资金口径优先级最高 |
| `盈亏`、`天数`、`收益率`、`年化收益` | 公式或核心计算结果 | 已实现、清仓、期权分析 |
| `备注` | 来源、拆分、说明 | 名称补全、券商导出明细 |
| `乘数` | 期权合约乘数 | 期权收益和资金 |
| `币种` | 人民币/港币/美元 | 分币种和折算 |
| `年份` | 年度切片 | 年度汇总 |
| `标签` | 可选交易标签，支持 `，`、`;`、`|`、空格、换行分隔多个标签 | 交易时间线、盈亏日历、阶段账单 |

`分红记录` 当前进入 `dividends.py`，会作为已实现现金事件参与成本回冲和收益曲线。

## 共享内存接口

`.trade-tracker/tools/trade_tracker/state.py` 里有几份跨模块状态：

| 名称 | 内容 | 写入方 | 读取方 |
| --- | --- | --- | --- |
| `LAST_CLEAR_DATE_MAP` | 每只标的最后清仓日 | `analytics.py` | 个股汇总表 |
| `HOLDING_DAYS_MAP` | 当前持仓天数 | `analytics.py`、卖出认沽补仓位 | 当前持仓表 |
| `SUMMARY_HOLDING_DAYS_MAP` | 总体个股持有天数 | `analytics.py` | 个股汇总表 |
| `ANNUAL_HOLDING_DAYS_MAP` | 年度切片持有天数 | `analytics.py` | 分年度汇总表 |
| `OPEN_OPTION_MARKS` | 未平仓期权现价、浮盈、占用本金 | `options.py` | 期权表、卖出认沽仓位 |
| `PERFORMANCE_STOCK_PAYLOAD` | 月度/年度个股表现切片 | `historical_curve.py` | 收益报告 |
| `DISPLAY_PAYLOAD` | 持仓、币种折算、当日浮盈、已实现交易与日汇总的统一展示层 | `display_payload.py` / `patcher.py` | 当前持仓顶部卡、盈亏日历 |
| `TRANSACTION_TAGS_BY_ROW` / `TRANSACTION_TAGS_PAYLOAD` | 交易行号到标签的映射和标签计数 | `transaction_tags.py` / `patcher.py` | 交易时间线、已实现 payload、标签筛选 |

## Dashboard Data 接口

`data` 是最核心的 Python 字典，目前主要字段如下：

| 字段 | 类型 | 含义 | 主要改写方 |
| --- | --- | --- | --- |
| `holdings` | list[dict] | 当前持仓行 | `options.py`、`holdings_daily.py` |
| `stock_summary` | list[dict] | 按标的汇总收益 | `options.py`、`historical_curve.py` 对齐 |
| `annual_summary` | list[dict] | 按年度和标的汇总 | `options.py`、`html_tables.py` |
| `curve_series` | list[dict] | 分币种历史收益曲线 | `historical_curve.py` |
| `market_value_text` | str | 当前市值按币种汇总 | `options.py` 重算 |
| `cost_text` | str | 持仓成本按币种汇总 | `options.py` 重算 |
| `unrealized_pnl_text` | str | 持仓浮盈按币种汇总 | `options.py` 重算 |
| `daily_pnl_text` | str | 当前持仓当日盈亏按币种汇总 | `options.py`、`holdings_daily.py` |
| `totals_note` | str | 口径说明 | `options.py` |
| `display_payload` | dict | 统一展示 payload 的快照 | `display_payload.py` |

### `holdings` 行字段

| 字段 | 页面名称 | 口径 |
| --- | --- | --- |
| `ticker` | 代码 | 标准化代码 |
| `name` | 名称 | 工作簿、缓存或线上名称 |
| `currency` | 币种 | 显示币种 |
| `side` | 方向 | 多头/空头/卖出认沽 |
| `qty` | 持股数 | 当前未平仓数量，卖出认沽可显示为腿数 |
| `last_price` | 现价 | 当前公开行情，缺失时 `-` |
| `market_value` | 最新市值 | 现价 × 数量；卖出认沽会把占用本金作为市值敞口 |
| `all_in_cost` | 持仓成本 | 原始成本，扣减本轮持仓起始日之后的部分卖出、已平仓期权和分红净收益后显示 |
| `avg_cost` | 持仓均价 | `all_in_cost / abs(qty)` |
| `float_pnl` | 浮动盈亏 | `market_value - adjusted cost`，空头方向反向处理 |
| `float_pnl_pct` | 盈亏率 | `float_pnl / abs(adjusted cost)` |
| `daily_pnl` | 当日盈亏 | 行情源昨收涨跌；完全新开标的按建仓价到现价 |
| `breakeven` | 回本空间 | 当前价到持仓均价的距离，盈利时显示 `-` |
| `last_buy` / `recent_buy` | 最近买入 | 当前持仓最近买入日 |

当日盈亏特殊规则：只有展示交易日前没有隔夜底仓、且展示交易日当天才建仓的标的，才按建仓价到现价算；已有隔夜底仓的标的即使当天做 T 或卖出后买回，也继承行情源的昨收涨跌。

核心盈亏不变量：逐行平仓盈亏按 `现股：(平仓价 - 开仓价) × 数量 - 费用`（空头反向）和 `期权：开仓权利金 - 平仓权利金 - 费用`（买入期权反向）计算；标的 `总盈亏 = 已实现现股/期权盈亏 + 分红净额 + 当前未平仓纯浮盈`。当前持仓表的 `all_in_cost` 只回冲本轮持仓起始日之后的部分卖出、已平仓期权和分红；如果标的曾经清仓归零，清仓前的历史收益不进入新一轮持仓 `float_pnl`。

## 统一展示 Payload

`.trade-tracker/tools/trade_tracker/display_payload.py` 会在 `build_dashboard_data()` 的末尾生成 `data["display_payload"]`，并同步到 `state.DISPLAY_PAYLOAD`。这层的目标是把页面常用的展示口径先在 Python 里算清楚，前端只负责渲染和交互。

当前字段：

| 字段 | 含义 |
| --- | --- |
| `ratesToCny` | 人民币、港币、美元到人民币的实时/兜底汇率 |
| `holdings` | 当前持仓行的标准化数值，包含原币种和人民币折算 |
| `holdingsTotals` | 持仓总资产、绝对市值、成本、浮盈、当日盈亏、卖出认沽占用，统一折人民币 |
| `holdingsByCurrency` | 按原币种拆分的持仓资产、成本、浮盈和当日盈亏 |
| `dailyPnl.current` | 最新展示交易日的持仓浮盈变动，供盈亏日历和顶部卡共用 |
| `realized.trades` | 已实现交易明细的标准化列表，等价于旧 `data-realized-payload` 的来源 |
| `realized.daily` / `realizedDaily` | 已实现盈亏按平仓日和币种汇总；`realizedDaily` 是兼容别名 |
| `realized.months` / `realized.currencies` | 已实现交易涉及的月份和币种，供控件生成 |
| `tags` | 交易标签计数和已打标签行数 |
| `capital` | 账户资产、风险敞口、持仓成本、已实现闭仓本金和期权资金来源 |
| `dataQuality` | 持仓现价、未平仓期权行情、期权资金口径和缓存状态的健康检查 |

已接入：

- 当前持仓顶部卡优先读 `state.DISPLAY_PAYLOAD["holdingsTotals"]`，读不到时才回退解析 HTML 表格。
- 资金口径 / 数据质量区块读 `state.DISPLAY_PAYLOAD["capital"]` 和 `["dataQuality"]`，只负责展示资金分母、期权兜底和行情完整度。
- 盈亏日历的已实现日汇总、最新展示交易日浮盈优先读 `data-display-payload`，旧明细重算、旧表格和顶部卡只作为兜底；交易标签来自 `realized.trades[].tags`。

## 页面分页分组

顶部分页按使用路径分组，而不是每个区块一个按钮：

| 分页 | 包含区块 | 主视图 |
| --- | --- | --- |
| `持仓` | 当前持仓、资金口径 / 数据质量、未平仓期权 | 当前持仓 |
| `收益` | 总收益曲线、总体概览、收益报告 | 总收益曲线 |
| `复盘` | 盈亏日历 / 阶段账单、清仓分析、期权收益分析 | 盈亏日历 / 阶段账单 |
| `明细` | 分年度个股汇总、交易时间线、工作表入口 | 分年度个股汇总 |
| `全部` | 所有区块 | 按业务顺序展开 |

分页配置在 `dashboard_layout.py` 的 `PAGE_GROUPS` 中维护，`SECTION_ORDER` 由这份配置生成；前端按钮、页面显示、页内快捷跳转和排序都读同一份定义。非 `全部` 分页里，第一个区块会标记为主工作区，后续区块标记为辅助区块并降低视觉权重。顶部会根据当前分页生成区块快捷按钮，长页面可直接跳到下游分析区块。

## 页面区块接口

| 页面区块 | 入口模块 | 数据入口 | 输出/显示字段 | 当前口径风险 |
| --- | --- | --- | --- | --- |
| 当前持仓表 | `html_tables.py` | `data["holdings"]` | 代码、名称、市值、浮盈、收益率、仓位、天数、回本空间 | 成本只回冲本轮持仓内的已实现收益和分红，和原始买入成本不同；清仓前收益不进入新仓浮盈 |
| 当前持仓顶部卡 | `holdings_overview.py` | `state.DISPLAY_PAYLOAD`、交易行、历史行情；HTML 表格兜底 | 持仓总资产、总盈亏、总市值、现持仓浮盈、已实现 | 现持仓历史区间仍会临时拉个股历史行情 |
| 资金口径 / 数据质量 | `capital_quality.py` | `state.DISPLAY_PAYLOAD["capital"]`、`["dataQuality"]` | 账户资产口径、风险敞口、成本/占用、持仓浮盈、期权资金来源、行情健康 | 只展示已统一的资金口径，不替代后续曲线收益率 payload |
| 未平仓期权 | `options.py`、`html_tables.py` | 未平仓期权行、公开期权行情 | 现价、浮动盈亏、占用本金 | short put 会推导 cash-secured capital；short call 不自动虚构本金 |
| 总体概览 | `overview.py` | 原始 metric cards、交易行、汇率 | 总盈亏、收益率、年化、交易费用、分币种概览 | 人民币汇总来自各币种卡片反推和折算，收益率分母可能不直观 |
| 盈亏日历 / 阶段账单 | `realized_analysis.py` | `data-display-payload`、`data-realized-payload`、`data-return-curve-json` | 已实现、浮盈、合计三种日历口径，已实现明细标签筛选 | 已实现日汇总和最新交易日浮盈读统一 payload；历史浮盈来自曲线点差 |
| 清仓分析 | `clearance_analysis.py` | 股票交易行 | 清仓周期、盈亏、本金、收益率、年化 | 只看现股清仓周期，不包含期权归因 |
| 期权收益分析 | `option_analysis.py` | `data-option-payload` | 期权总览、标的拆分、明细 | 只统计已平仓/到期的期权，未平仓只在未平仓期权表显示 |
| 总收益曲线 | `historical_curve.py`、`return_curve.py` | `data["curve_series"]`、指数缓存、汇率 | 汇总/A股/港股/美股曲线、baseline、超额、K线 | 曲线金额、收益率、资金流、资金分母仍需继续向统一 payload 收敛 |
| 收益报告 | `performance_report.py` | `data-return-curve-json`、`data-realized-payload`、`data-performance-stock-payload` | 最大增长/回撤、盈亏对比、日历、个股盈亏 | 个股月/年收益率来自后端 App 口径 payload，报告前端只负责展示和排序 |
| 分年度个股汇总 | `html_tables.py`、`historical_curve.py` | `annual_summary`、`PERFORMANCE_STOCK_PAYLOAD` | 年度内盈亏、收益率、年化、持有天数 | 已按年切片；`nativeRealizedPnl` 是交易已实现，`nativeDividendPnl` 是分红/扣税，`nativePnl` 是总盈亏；仍持仓标的收益率用 `总盈亏 / abs(期末市值 - 总盈亏)`，对齐券商 App 持仓盈亏率 |
| 交易时间线 | `transaction_tags.py`、核心生成器 | `TRANSACTION_TAGS_BY_ROW`、核心 HTML 表格 | 逐笔交易、标签列、标签筛选 | 标签按 `交易记录` 行号对齐；不要在没有 `标签` 表头时把其他空白扩展列当标签 |

## 曲线 JSON 接口

`return_curve.py` 会把 `curve_series` 合成为 `data-return-curve-json`。每个 series 当前形状：

```json
{
  "currency": "人民币折算",
  "code": "CNY",
  "scope": "all",
  "scopeLabel": "汇总",
  "defaultBenchmark": "sse",
  "capital": 0,
  "points": [],
  "benchmarks": [],
  "benchmark": {}
}
```

`points` 里的关键字段：

| 字段 | 含义 |
| --- | --- |
| `date` / `iso` / `serial` | 显示日期、ISO 日期、Excel serial |
| `value` | 累计总盈亏，当前等于 realized + unrealized |
| `float_value` | 累计持仓浮盈 |
| `realized_value` | 累计已实现盈亏 |
| `total_value` | 累计总盈亏 |
| `market_value` | 当日未平仓市值 |
| `capital` | 当日活跃持仓成本/占用资金 |
| `principal` | 根据现金流推导的本金基准 |
| `net_flow` | 当日净资金流，买入为正、卖出为负的显示口径 |

前端会按这些点再推导：

- 金额模式：使用 `value` / `total_value` 等累计金额。
- 收益率模式：使用点上的 `capital` 或携带资本作为分母。
- 超额收益：个人同口径值减当前 baseline。
- K 线：对收益点按日/周/月/年聚合，K 线模式不展示 baseline。

曲线核验边界：每个币种最新 `points[-1].value` 应和同币种 `stock_summary.total_pnl` 汇总一致；折人民币后的差异只允许来自实时汇率重取和小数四舍五入。

## 当前最值得优化的口径点

1. 资金分母需要统一命名。
   - 现在同时存在 `capital`、`capital_raw`、`capital_days_raw`、`principal`、`market_value`、`all_in_cost`、`option_reserve`。
   - 建议明确拆成：原始投入成本、当前占用资金、策略资金、现金流本金、展示折算资金。

2. 统一展示 payload 需要继续扩面。
   - 当前已覆盖持仓总计、分币种持仓、最新日浮盈、已实现交易列表、已实现日汇总、交易标签、资金口径和数据质量。
   - 后续收益曲线、总体概览、收益报告也应逐步读 `display_payload`，减少 DOM 反读和前端重复推导。

3. 曲线收益率分母应继续显式化。
   - 总收益曲线已经使用账户级资金流；个股月/年收益率已经对齐券商 App 持仓盈亏率口径，仍持仓标的用调整后持仓成本，已清仓标的用投入本金。
   - 下一步建议让曲线点直接带 `daily_return`、`cumulative_return`、`return_basis`，减少前端临时推导。

4. 已实现、浮盈、合计需要全站同一来源。
   - 当前最新日浮盈来自当前持仓表，历史日浮盈来自曲线点差，已实现来自平仓 payload。
   - 建议建立一份 `daily_pnl_payload`，所有日历、报告、顶部卡都读它。

5. 期权资金口径要显式展示。
   - 持仓页已经新增资金口径 / 数据质量区块，short put 的 cash-secured capital 会标成兜底资金，不是真实入金。
   - short call / spread / 组合策略需要继续补 “保证金/策略资金/最大亏损” 的来源字段。

6. 分币种和统一展示币种要区分。
   - 当前很多字段先按原币种计算，再按实时汇率折算展示。
   - 建议所有折算展示字段都带原币种金额、汇率、折算币种，避免用户误以为源数据已经换币。

7. 交易标签只描述交易事实，不参与收益口径。
   - 标签列可以用于复盘筛选，例如 `建仓`、`T操作`、`AI`、`事件驱动`。
   - 后续如果要做标签维度盈亏统计，应基于 `display_payload["realized"]["trades"][].tags` 聚合，避免重新解析 HTML。

## 下一步优化建议

统一 Python payload 已经起步，后续继续把分散口径迁入：

```text
display_payload
  holdings
  holdingsTotals
  holdingsByCurrency
  daily_pnl
  realized.trades
  realized.daily
  realizedDaily
  tags
  capital
  dataQuality
  curve_points
  stock_periods
  option_positions
  overview_totals
```

每个区块只负责渲染，不再自己重新发明口径。这样后面要调收益率、当日盈亏、期权占用资金时，只改一个 payload 层，页面自然一致。
