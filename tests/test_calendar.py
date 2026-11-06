import pandas as pd

from capesize.calendar import assign_news_day, to_utc

# Thu 2026-03-05, Fri 03-06, (weekend), Mon 03-09
DAYS = pd.DatetimeIndex(["2026-03-05", "2026-03-06", "2026-03-09"])


def _assign(stamps):
    return list(assign_news_day(to_utc(pd.Series(stamps)), DAYS))


def test_cutoff_boundary_is_inclusive():
    got = _assign(["2026-03-06 12:00:00", "2026-03-06 12:00:01"])
    assert got == [pd.Timestamp("2026-03-06"), pd.Timestamp("2026-03-09")]


def test_previous_afternoon_goes_to_next_day():
    assert _assign(["2026-03-05 15:30"]) == [pd.Timestamp("2026-03-06")]


def test_weekend_rolls_to_monday():
    assert _assign(["2026-03-07 09:00", "2026-03-08 23:00", "2026-03-09 11:59"]) == [pd.Timestamp("2026-03-09")] * 3


def test_after_last_cutoff_is_nat():
    assert pd.isna(_assign(["2026-03-09 13:00"])[0])


def test_timezone_is_converted():
    # 13:30 in UTC+8 = 05:30 UTC -> same day
    assert _assign(["2026-03-06 13:30:00+08:00"]) == [pd.Timestamp("2026-03-06")]


def test_date_only_items_go_to_next_day():
    ts = to_utc(pd.Series(["2026-03-05", "2026-03-05 08:00"]), date_only=pd.Series([True, False]))
    got = list(assign_news_day(ts, DAYS))
    assert got == [pd.Timestamp("2026-03-06"), pd.Timestamp("2026-03-05")]
