"""Trading-day grid for the news pipeline.

Preferred grid (decisions.md C1): the dates on which the 5TC series has a published value, via
capesize.calendar.trading_days_from_series. Pass those dates as a CSV with --trading-days.
Until the workbook-1 loader exists, provisional_trading_days() gives London business days
(weekdays minus England & Wales bank holidays). Check it against the real 5TC dates once available.
"""
import logging
from datetime import date
from pathlib import Path

import pandas as pd

from capesize.calendar import trading_days_from_series

# England & Wales bank holidays, gov.uk/bank-holidays
BANK_HOLIDAYS = pd.to_datetime([
    "2025-08-25", "2025-12-25", "2025-12-26",
    "2026-01-01", "2026-04-03", "2026-04-06", "2026-05-04", "2026-05-25", "2026-08-31",
    "2026-12-25", "2026-12-28",
])


def provisional_trading_days(start: date, end: date) -> pd.DatetimeIndex:
    days = pd.bdate_range(start, end)
    return trading_days_from_series(days[~days.isin(BANK_HOLIDAYS)])


def load_trading_days(start: date, end: date, path: Path | None = None) -> pd.DatetimeIndex:
    """Real grid from a CSV whose first column holds the 5TC publication dates, else the provisional grid."""
    if path is not None:
        dates = pd.read_csv(path).iloc[:, 0]
        return trading_days_from_series(dates)
    logging.getLogger("news").warning(
        "Using the PROVISIONAL trading-day grid (London business days). "
        "Pass --trading-days with the 5TC dates once workbook 1 is loaded.")
    return provisional_trading_days(start, end)
