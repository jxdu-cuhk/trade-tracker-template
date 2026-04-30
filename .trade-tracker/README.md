# 韭菜账本 Leek Ledger 目录说明

日常使用只需要关注主目录这几个入口：

- `Trade Tracker.html`: 直接打开最新韭菜账本看板。
- `Trade Tracker.xlsx`: 交易记录工作簿。
- `Update Preview.command`: 后台服务异常时的备用启动入口。

隐藏支持目录 `.trade-tracker/` 分工：

- `.trade-tracker/preview/`: 自动生成的网页预览文件。
- `.trade-tracker/history/`: 券商导出的历史交易记录，用来补名称和核对交易。
- `.trade-tracker/tools/`: 生成网页所需的脚本和核心程序。
- `.trade-tracker/security_name_cache.json`: 标的名称缓存，避免每次都重新查询。
- `.venv/`: 本地 Python 运行环境。

代码框架：

- `.trade-tracker/tools/export_trade_tracker_html.py`: 很薄的命令入口，保留原来的运行方式。
- `.trade-tracker/tools/trade_tracker/app.py`: 导出流程编排，负责加载核心模块、生成网页、整理输出。
- `.trade-tracker/tools/trade_tracker/patcher.py`: 把我们自己的持仓、汇总、行情、刷新面板逻辑挂到核心生成器上。
- `.trade-tracker/tools/trade_tracker/options.py`: 期权和已完成现股收益口径，比如已平仓 covered call、T 出利润归入对应标的并回冲当前持仓成本。
- `.trade-tracker/tools/trade_tracker/market_data.py`: Futu、东方财富、腾讯行情和汇率获取。
- `.trade-tracker/tools/trade_tracker/names.py`: 标的名称缓存和历史券商文件映射。
- `.trade-tracker/tools/trade_tracker/html_tables.py`: 表格列顺序、汇总行、排序和人民币折算汇总。
- `.trade-tracker/tools/trade_tracker/overview.py`: 总体概览和分币种概览卡片。
- `.trade-tracker/tools/trade_tracker/refresh_panel.py`: 网页里的“刷新看板”进度面板。
- `.trade-tracker/tools/trade_tracker/styling.py`: 生成后的 CSS 和表格显示微调。
- `.trade-tracker/tools/trade_tracker/analytics.py`: 持有天数、最后清仓时间等交易分析辅助。

说明：

- `.trade-tracker/preview/` 里的内容会被刷新脚本重新生成，通常不用手动改。
- `.trade-tracker/history/` 里的原始文件建议保留，后续补数据时还能继续用。
- 如果看板没有更新，先直接刷新网页；如果后台服务没有响应，再双击 `Update Preview.command`。
