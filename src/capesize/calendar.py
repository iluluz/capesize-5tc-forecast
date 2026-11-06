"""Trading-day grid and the news-window rule (docs/decisions.md, items 1-4)."""
import datetime as dt

import pandas as pd

from capesize.contract import DATE_ONLY_TIME_UTC, NEWS_CUTOFF_UTC


def trading_days_from_series(index) -> pd.DatetimeIndex:
    """The trading-day grid = the dates on which the target series has a published value."""
    days = pd.DatetimeIndex(pd.to_datetime(index)).normalize().unique().sort_values()
    if days.tz is not None:
        days = days.tz_localize(None)
    return days


def to_utc(ts: pd.Series, date_only: pd.Series | None = None) -> pd.Series:
    """Parse timestamps to tz-aware UTC. Rows flagged date_only get DATE_ONLY_TIME_UTC on their date.

    Naive timestamps are treated as already in UTC; convert local times before calling.
    """
    out = pd.to_datetime(ts, utc=True, format="mixed")  # news feeds mix "YYYY-MM-DD" and full timestamps
    if date_only is not None:
        mask = date_only.fillna(False).astype(bool).to_numpy()
        fixed = out[mask].dt.normalize() + pd.Timedelta(
            hours=DATE_ONLY_TIME_UTC.hour, minutes=DATE_ONLY_TIME_UTC.minute, seconds=DATE_ONLY_TIME_UTC.second
        )
        out = out.copy()
        out[mask] = fixed
    return out


def assign_news_day(ts_utc: pd.Series, trading_days: pd.DatetimeIndex,
                    cutoff: dt.time = NEWS_CUTOFF_UTC) -> pd.Series:
    """Map each news timestamp to the trading day t whose window contains it.

    Window W_t = (cutoff on the previous trading day, cutoff on day t], so an item published exactly at the
    cutoff belongs to t, one second later to the next trading day. Weekend and holiday items roll forward.
    Items after the last cutoff in the grid get NaT.
    """
    ts = pd.to_datetime(ts_utc, utc=True)
    days = pd.DatetimeIndex(trading_days).sort_values()
    if days.tz is None:
        days = days.tz_localize("UTC")
    cutoffs = days.normalize() + pd.Timedelta(hours=cutoff.hour, minutes=cutoff.minute)
    pos = cutoffs.searchsorted(ts, side="left")
    valid = pos < len(days)
    out = pd.Series(pd.NaT, index=ts.index, dtype="datetime64[ns]")
    out[valid] = days[pos[valid]].tz_localize(None).normalize()
    return out
