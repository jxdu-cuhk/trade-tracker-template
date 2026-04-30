---
name: trade-tracker
description: Use this skill when maintaining the Trade Tracker dashboard template, importing trade rows, regenerating the local HTML preview, or preparing a privacy-safe public release with no personal trading data.
---

# Trade Tracker

## Core workflow

1. Work from the repository root.
2. Keep personal trading data in a private copy only.
3. Use `Trade Tracker.xlsx` as the workbook source of truth.
4. Regenerate the preview with `Update Preview.command`, or run `python3 .trade-tracker/tools/export_trade_tracker_html.py`.
5. Check `Trade Tracker.html` and `.trade-tracker/preview/index.html` after changes.

## Data rules

- Public templates must keep `Trade Tracker.xlsx` blank except for header rows.
- Do not commit broker exports, screenshots, account files, logs, history folders, or local caches.
- Do not commit `security_name_cache.json`; symbol-name caches belong in private/local use only.
- For options, closed contracts may be included in realized P/L for the related underlying. Open option legs should remain separate until closed or expired.
- Use calendar days for holding period calculations unless the user explicitly asks for trading days.

## Importing trades with AI

The intended workflow is to let an AI assistant help turn plain-language orders, broker exports, or screenshots into workbook rows.

Ask the user for the minimum fields needed to append a row:

- Stock or ETF buy/sell: action, trade date, ticker, name if known, quantity, price, fee, currency.
- Short sale: action, open date, ticker, quantity, short price, fee, currency, and whether it is still open.
- Option trade: open date, expiry date, underlying ticker, option type, strike, contracts, multiplier, premium per share, fee, currency, and close/expiry status if known.
- Dividend or corporate action: date, ticker, net amount, currency, and note.

When the user provides screenshots, extract the visible values first, then summarize the rows back to the user before writing if any field is ambiguous. If a broker export is provided, ignore cash transfers, collateral transfers, and other non-trading ledger events unless the user explicitly asks to track them.

Append confirmed trades to `Trade Tracker.xlsx`, keeping raw user files outside the repository. Formula-derived columns such as P/L, days, annualized return, summaries, and dashboard metrics should be calculated by the project scripts where possible instead of manually typed.

Example user input:

```text
Buy, 2026-01-15, TICKER_A, 100 shares, 12.34, fee 1.23, CNY
Covered call, 2026-01-16, expiry 2026-01-30, TICKER_A, call, strike 13.00, 1 contract, premium 0.20/share, fee 3.00, CNY
```

After importing, regenerate the preview and verify:

1. New rows appear in the transaction timeline.
2. Current holdings and open options match the user's expectation.
3. Realized P/L only includes closed trades and expired/closed options.
4. Public-template privacy checks still pass before any public push.

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

- The public repository contains the app code, empty workbook, preview files, README, and this skill.
- The private repository may contain real local data, but must stay private.
- After pushing, clone the public repository fresh and repeat the privacy checks against the remote copy.
