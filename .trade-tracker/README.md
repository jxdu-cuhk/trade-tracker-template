# 韭菜账本 Leek Ledger 目录说明

日常使用只需要关注主目录这几个入口：

- `Trade Tracker.html`: 最新韭菜账本看板入口。
- `Trade Tracker.xlsx`: 交易记录工作簿，也是唯一手工数据源。
- `Update Preview.command`: 推荐的一键启动入口，会自动检查虚拟环境和依赖。
- `README.md`: 面向使用者的说明。

隐藏支持目录 `.trade-tracker/` 分工：

- `.trade-tracker/preview/`: 自动生成的网页预览文件。
- `.trade-tracker/history/`: 券商导出的历史交易记录，用来补名称、核对交易和识别分红。
- `.trade-tracker/tools/`: 生成网页所需的脚本和核心程序。
- `.trade-tracker/tools/cache/`: 指数、个股历史行情、期权链等本地缓存。
- `.trade-tracker/logs/`: 本地刷新服务日志。
- `.trade-tracker/security_name_cache.json`: 标的名称缓存，避免每次都重新查询。
- `.trade-tracker/DATA_INTERFACES.md`: 当前看板所有显示数据接口、口径来源和待优化点。
- `.venv/`: 本地 Python 运行环境，由 `Update Preview.command` 自动创建。

核心脚本：

- `.trade-tracker/tools/export_trade_tracker_html.py`: 命令行生成入口。
- `.trade-tracker/tools/preview_server.py`: 本地预览和网页刷新服务。
- `.trade-tracker/tools/install_preview_service.py`: macOS LaunchAgent 后台常驻服务安装脚本。
- `.trade-tracker/tools/export_trade_tracker_core.pyc`: 原始看板生成核心。

主要模块：

- `.trade-tracker/tools/trade_tracker/app.py`: 导出流程编排，负责加载核心模块、生成网页、整理输出。
- `.trade-tracker/tools/trade_tracker/patcher.py`: 把持仓、资金口径、交易标签、汇总、行情、刷新面板等扩展挂到核心生成器上。
- `.trade-tracker/tools/trade_tracker/display_payload.py`: 统一展示数据层，先汇总持仓、分币种折算、最新日浮盈、已实现交易列表、已实现日汇总、交易标签、资金口径和数据质量，再给页面区块复用。
- `.trade-tracker/tools/trade_tracker/transaction_tags.py`: 交易标签读取和展示层，识别 `交易记录` 的 `标签` 列，把标签接到交易时间线、盈亏日历和阶段账单。
- `.trade-tracker/tools/trade_tracker/capital_quality.py`: 持仓页的资金口径 / 数据质量区块，把账户资产、风险敞口、期权资金兜底、行情完整度集中展示。
- `.trade-tracker/tools/trade_tracker/dashboard_layout.py`: 顶部业务分组分页、当前页区块快捷跳转、刷新/统一币种操作区、栏目排序、主/辅区块层级和总收益曲线控制区；分页配置统一驱动排序和前端按钮，避免重复维护。
- `.trade-tracker/tools/trade_tracker/return_curve.py`: 总收益曲线、baseline、超额收益、K 线、缩放拖动、tooltip，以及指数长期缓存和增量补尾。
- `.trade-tracker/tools/trade_tracker/historical_curve.py`: 个股真实历史行情、缓存、未实现盈亏历史曲线，以及按月/按年切片的个股收益 payload。
- `.trade-tracker/tools/trade_tracker/holdings_overview.py`: 当前持仓顶部汇总卡、当日/本月/近三月/本年已实现盈亏。
- `.trade-tracker/tools/trade_tracker/holdings_daily.py`: 当日持仓盈亏分段，A/H 按本地自然日，美股按纽约时间 0 点滚日；只有展示交易日前没有隔夜底仓的当天新开标的按建仓价算，已有隔夜底仓的 T 操作标的继承行情源昨收涨跌。
- `.trade-tracker/tools/trade_tracker/reporting_currency.py`: 看板统一口径币种切换。
- `.trade-tracker/tools/trade_tracker/html_tables.py`: 表格列顺序、分年度个股汇总、汇总行、上下横向滚动条、人民币折算汇总。
- `.trade-tracker/tools/trade_tracker/overview.py`: 总体概览、分币种概览和交易费用汇总。
- `.trade-tracker/tools/trade_tracker/options.py`: 期权和已完成现股收益口径，比如 covered call、short put、缺失保证金兜底和成本回冲。
- `.trade-tracker/tools/trade_tracker/option_analysis.py`: 期权收益分析页面。
- `.trade-tracker/tools/trade_tracker/realized_analysis.py`: 盈亏日历 / 阶段账单，日历可切换已实现、持仓浮动和合计口径，已实现明细可按交易标签筛选；最新交易日浮盈对齐当前持仓汇总，历史日期沿用收益曲线。
- `.trade-tracker/tools/trade_tracker/clearance_analysis.py`: 清仓分析。
- `.trade-tracker/tools/trade_tracker/performance_report.py`: 收益报告。
- `.trade-tracker/tools/trade_tracker/market_data.py`: 东方财富、腾讯、Yahoo、HKEX 行情和汇率获取。
- `.trade-tracker/tools/trade_tracker/names.py`: 标的名称缓存和历史券商文件映射。
- `.trade-tracker/tools/trade_tracker/refresh_panel.py`: 网页里的刷新状态条和刷新进度面板；顶部刷新按钮会共用这一套逻辑。
- `.trade-tracker/tools/trade_tracker/styling.py`: 生成后的 CSS 和表格显示微调。
- `.trade-tracker/tools/trade_tracker/analytics.py`: 持有天数、最后清仓时间等交易分析辅助。

说明：

- `.trade-tracker/preview/` 里的内容会被刷新脚本重新生成，通常不用手动改。
- 数值口径和页面接口先看 `.trade-tracker/DATA_INTERFACES.md`，优先扩展 `display_payload.py`，再改具体模块，避免同一个指标在多个区块里各算一遍；持仓页的资金口径 / 数据质量区块也读这层，不单独推导。
- `.trade-tracker/tools/cache/` 可以删除，刷新时会按需重建；保留它能明显减少行情请求。指数缓存现在按指数长期保存，日常刷新只加载一次缓存、只补缺口和当天实时尾点、最后一次性落盘；科创综指从 `2022-04-11` 起，用中证指数官方接口补腾讯缺失的早期历史。美股现股报价会优先取 Yahoo 盘前/盘后价格，拿不到时再回退到常规价或腾讯行情。
- `.trade-tracker/history/` 里的原始文件建议保留，后续补数据时还能继续用。
- 如果看板没有更新，先直接刷新网页；如果后台服务没有响应，再双击 `Update Preview.command`。
