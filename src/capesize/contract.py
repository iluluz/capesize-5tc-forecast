"""Shared contract between the ML part and the text branch.

Every value here mirrors docs/decisions.md. Change it only through a PR that also edits that file
and is approved by both the ML and the text-branch owners. Status of each value: see decisions.md.
"""
import datetime as dt

# Horizons in Baltic trading days; a forecast is issued every trading day for each horizon.
HORIZONS: tuple[int, ...] = (5, 20)
PRIMARY_HORIZON: int = 5

# News published up to and including this UTC time on trading day t is usable for the forecast made on t.
NEWS_CUTOFF_UTC: dt.time = dt.time(12, 0)

# Items that carry a date but no time are placed at this time of their date (falls after the cutoff,
# so they are used on the next trading day: conservative, no look-ahead).
DATE_ONLY_TIME_UTC: dt.time = dt.time(23, 59, 59)

# Target column in workbook 1 (5TC, 182 basis). [verify the exact header when the loader is written]
TARGET_SERIES: str = "5TC"
