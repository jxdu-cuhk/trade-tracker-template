from __future__ import annotations

LAST_CLEAR_DATE_MAP: dict[tuple[str, str], str] = {}
HOLDING_DAYS_MAP: dict[tuple[str, str], str] = {}
SUMMARY_HOLDING_DAYS_MAP: dict[tuple[str, str], int] = {}
ANNUAL_HOLDING_DAYS_MAP: dict[tuple[str, str, str], int] = {}
OPEN_OPTION_MARKS: dict[tuple[str, str, str, str, str, str, str, str], dict[str, str]] = {}
