---
name: leek-ledger
description: Use this skill when maintaining Leek Ledger, recording trades from user instructions, screenshots, or broker exports, refreshing the local dashboard, or keeping the public template and private ledger workflows consistent without exposing personal trading data.
---

# 韭菜账本 Leek Ledger

## Working stance

The user usually knows which positions are current, which are closed, and which trades should be added. Treat those instructions as the source of truth. Do not spend a long time re-deriving portfolio intent from the dashboard when the user has already said what to record.

Default loop: listen carefully, extract the needed fields, search only for missing ticker/name/market details, append the workbook rows, refresh, and check that the result matches the user's stated intent.

Ask only when a missing value would change the row: trade date, side, ticker, quantity, price, fee, currency, option expiry, strike, option type, multiplier, or whether the trade is open/closed. If a detail is merely descriptive, search or leave it blank rather than blocking.

## Repository rules

- Work from the repository root.
- Keep this skill privacy-safe and identical in the public template repo and private ledger repo.
- Public templates must keep `Trade Tracker.xlsx` blank except for headers or intentional template rows.
- Private repos may contain real workbook data, broker exports, screenshots, logs, and caches, but they must stay private.
- Do not commit broker exports, screenshots, account files, logs, history folders, local caches, or `security_name_cache.json` to the public repo.
- Do not write personal holdings, account numbers, broker IDs, screenshots, or exact private portfolio examples into this skill.

## Data rules

- `Trade Tracker.xlsx` is the workbook source of truth.
- The main sheet is `交易记录`; optional dividends/corporate actions live in `分红记录` when present.
- Main row columns are: `类型`, `开仓`, `到期`, `平仓`, `代码`, `事件`, `行权价`, `数量`, `开仓价`, `平仓价`, `费用`, `占用本金`, `盈亏`, `天数`, `日均盈亏`, `收益率`, `年化收益`, `备注`, `乘数`, `币种`, `年份`.
- Stock/ETF rows normally use `类型=股票`, `事件=现股`.
- Sold option rows use `类型=卖出`, with `事件=认购` for calls and `事件=认沽` for puts. Bought option rows use `类型=买入`.
- Open trades leave `平仓` and `平仓价` blank. Closed trades fill the close date and close price when known.
- For options, use premium per share/unit in `开仓价` and `平仓价`; use contract count in `数量`; use the contract multiplier in `乘数`.
- Preserve formulas and existing formatting. Formula-derived columns such as P/L, days, returns, and year should be copied from the adjacent pattern or left for the project scripts when that is the established workbook behavior.
- Closed stock/ETF P/L and closed option P/L can be assigned back to the related underlying for displayed holding-cost adjustment. Open option legs remain separate until closed or expired.
- Open options may display current price, floating P/L, and occupied capital from public online sources. If a quote cannot be matched, leave current price and floating P/L as `-`; do not block the entry.
- Use calendar days for holding period calculations unless the user explicitly asks for trading days.

## Trade-entry workflow

Use this flow for plain-language orders, broker exports, screenshots, or quick corrections.

1. Parse the user's instruction first. If they say a position is current, closed, or to be opened, use that classification.
2. Build a compact list of rows to add or update. Keep rows grouped by ticker and currency.
3. Search only to fill gaps such as official name, ticker normalization, market suffix, currency, or option multiplier. Search results must not override user-provided trade facts.
4. Append or update `Trade Tracker.xlsx`.
5. Refresh the preview.
6. Verify the dashboard against the user's expectation: current holdings, closed positions, open option legs, and realized P/L buckets.
7. Report what changed and any fields that were assumed or left blank.

Minimum fields by row type:

- Stock or ETF buy/sell: action, trade date, ticker, name if known, quantity, price, fee, currency.
- Short sale: action, open date, ticker, quantity, short price, fee, currency, and whether it is still open.
- Option trade: open date, expiry date, underlying ticker, option type, strike, contracts, multiplier, premium per share, fee, currency, and close/expiry status if known.
- Dividend or corporate action: date, ticker, net amount, currency, and note.

When the user provides screenshots, extract visible values first. If the screenshot is complete enough, record directly; only summarize back before writing when a field is ambiguous or conflicts with the user's typed instruction.

If a broker export is provided, ignore cash transfers, collateral transfers, funding records, interest, and other non-trading ledger events unless the user explicitly asks to track them.

## Refresh and validation

Regenerate the preview with `Update Preview.command`, the webpage refresh button, or:

```bash
python3 .trade-tracker/tools/export_trade_tracker_html.py
```

After importing, check:

1. New rows appear in the transaction timeline.
2. Current holdings match the user's stated current positions.
3. Positions the user said are closed no longer appear as open holdings.
4. Open options match the user's stated open contracts and expiry dates.
5. Realized P/L only includes closed trades and expired/closed options.

When changing code or data logic, run focused tests before a full refresh:

```bash
python3 -m unittest discover -s .trade-tracker/tests -v
```

Benchmark and curve maintenance notes:

- Total return baselines live in `.trade-tracker/tools/trade_tracker/return_curve.py`.
- Index history should be cached by benchmark and reused across refreshes; load the benchmark cache once per payload build, only fetch missing gaps, and save once after all benchmark updates are merged.
- Keep benchmark cache compact. After migrating old range-style cache entries into benchmark entries, prune the duplicate range entries so refreshes do not repeatedly parse stale copies.
- For A-share baselines, prefer Tencent for normal history and real-time tail points. Do not make Eastmoney the primary dependency for 科创综指 because it is easy to block.
- 科创综指 should clamp to its official available start, `2022-04-11`; use the official CSIndex endpoint with a short timeout to fill Tencent's early-history gap, then use Tencent real-time data for today's tail point.
- Period stock performance must be sliced by the period boundary. Annual and monthly stock summaries should use `state.PERFORMANCE_STOCK_PAYLOAD["years"]` / `["months"]`, not lifetime stock-summary rows or the final clearing month/year. Cross-year holdings compare the period end value against the previous period-end value.
- Daily holding P/L uses market-local calendar days rather than local refresh time. CNY/HKD holdings roll on the China/Hong Kong calendar day; USD holdings roll at New York midnight. Lots opened on the displayed market-local day use entry price to current price for daily P/L; lots opened before that day inherit quote-source previous-close movement. USD stock quotes should prefer Yahoo pre-market/post-market fields before falling back to regular-market or Tencent quotes.
- The realized P/L calendar should keep realized trades, daily floating P/L, and total daily movement as explicit selectable modes. Latest-trading-day floating P/L should align with the current holdings table/summary card; older dates can fall back to return-curve day points so open positions and currency conversion stay visible. Because the calendar section renders before the return curve section, its browser script must reload curve JSON after `DOMContentLoaded`.
- After curve-source changes, update `README.md`, `.trade-tracker/README.md`, and this skill so operational rules stay aligned.

## Examples

Example user input:

```text
Buy, 2026-01-15, TICKER_A, 100 shares, 12.34, fee 1.23, CNY
Covered call, 2026-01-16, expiry 2026-01-30, TICKER_A, call, strike 13.00, 1 contract, premium 0.20/share, fee 3.00, CNY
```

Preferred behavior: turn these into workbook rows, search the missing display name if needed, refresh, then confirm the holding and open option are visible.

Example correction:

```text
These three are already closed; this one is still current; add the new put I sold today.
```

Preferred behavior: trust the classification, update close fields or append open rows accordingly, and use the dashboard only as verification.

## Privacy check before publishing

Run these checks before pushing a public release:

```bash
rg -a -n "PRIVATE_TICKER|PRIVATE_SECURITY_NAME|BROKER_EXPORT_NAME|LOCAL_USER_NAME|/Users/" .
```

```bash
find . -path "./.git" -prune -o -type f \( -path "*/history/*" -o -path "*/logs/*" -o -path "*/cache/*" -o -name "security_name_cache.json" -o -name "*.csv" -o -name "*.jpg" -o -name "*.png" \) -print
```

Inspect the workbook and confirm every sheet has only the header row or intentionally blank template rows.

## Release checklist

- The public repository contains the app code, empty workbook, preview files, README, tests, and this skill.
- The private repository may contain real local data, but must stay private.
- This skill is the same in both repos.
- After pushing, clone the public repository fresh and repeat the privacy checks against the remote copy.
