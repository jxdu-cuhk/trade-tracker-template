# 韭菜账本 Leek Ledger

一个本地优先的交易记录、盈亏复盘与持仓看板。

记录每一次被市场教育的痕迹。

韭菜账本可以手动录入交易，也可以把券商导出的成交记录交给 Codex 等 AI 工具清洗后导入：AI 会帮你过滤银证转账、担保品划转等非交易流水，整理股票、ETF、期权、分红等字段，并写入本地工作簿。

这个公开版本只保留可运行框架和合成示例工作簿，不包含任何真实交易记录、券商导出、标的缓存或个人数据。示例数据只用于展示看板外观，克隆后可以直接清空 `交易记录` 工作表再录入自己的交易。

## 来源与致谢

本项目基于 B 站 / YouTube UP 主 @靠卖期权实现早日自由 推荐的 Google 表格模板，并使用 Codex 进一步开发为本地 Excel + HTML 看板版本。

原始 Google 表格模板：[Ultimate Options Tracking Spreadsheet - Version 2](https://docs.google.com/spreadsheets/d/1Oe_ETcQWmCRg07Vc_hJb8wrnGS8GGR5yclYFnRpmcd4/copy)

## 使用方式

1. 打开 `Trade Tracker.xlsx`，可以先查看内置合成示例；正式使用前清空 `交易记录` 工作表里的示例行，再录入自己的交易。
2. 双击 `Update Preview.command` 启动本地预览服务。
3. 打开 `Trade Tracker.html` 查看生成后的看板。

工作簿和入口文件暂时保留 `Trade Tracker` 文件名，是为了兼容原始模板和现有启动脚本；项目名称统一为「韭菜账本 Leek Ledger」。

刷新看板时会优先用公开行情源更新现股和期权价格：港股期权会尝试走 HKEX 延迟行情，Futu OpenD 仅作为兜底。未平仓 covered call / cash-secured put 会展示现价、浮动盈亏和占用本金；取不到期权行情时会显示 `-`，不会阻塞页面生成。

## 用 AI 导入券商交易

你可以把券商导出的 `.csv` / `.xlsx` 成交记录提供给 Codex 等 AI 工具，让它按下面流程整理：

1. 读取成交记录和费用字段。
2. 忽略银证转账、担保品划转、资金流水等非交易事件。
3. 识别股票、ETF、期权、分红和公司行动。
4. 补齐日期、代码、名称、数量、价格、费用、币种等字段。
5. 写入 `Trade Tracker.xlsx` 后刷新看板。

如果使用真实交易数据，建议放在 private 仓库或本地私有目录里，不要提交到公开仓库。

## 轻量测试

核心数据逻辑可以先跑单元测试，不必每次完整刷新网页：

```bash
python3 -m unittest discover -s .trade-tracker/tests -v
```

## 目录说明

- `Trade Tracker.xlsx`: 带合成示例的交易记录模板，用来展示完整看板外观。
- `Trade Tracker.html`: 看板入口页。
- `Update Preview.command`: 本地预览服务启动脚本。
- `.trade-tracker/tools/`: 看板生成和刷新脚本。
- `.trade-tracker/tests/`: 轻量单元测试，覆盖成本回冲等核心数据点。
- `.trade-tracker/preview/`: 由合成示例模板生成的静态预览。
- `skills/leek-ledger/SKILL.md`: 给 AI 助手使用的项目维护流程。

## 隐私说明

公开版本不会提交 `.trade-tracker/history/`、`.trade-tracker/logs/`、`.trade-tracker/tools/cache/` 或真实的 `security_name_cache.json`。如果你基于这个模板记录自己的交易，建议把包含真实数据的仓库设为 private。
