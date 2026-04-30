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
