"""Point-in-time (PIT) helpers.

Every non-daily feature is a (value, avail) pair indexed by reference period. `avail` is the
estimated public availability date. A feature value is visible on decision date t only if
avail < t (STRICT: Baltic publishes around midday London, so same-day releases are excluded).
`avail` is forced monotone (cummax) so a rolling-window feature is never visible before all
the inputs that went into it.
"""
import numpy as np
import pandas as pd


def pit_attach(grid: pd.DatetimeIndex, values: pd.Series, avail: pd.Series):
    """Return (value_on_grid, avail_used_on_grid) as two Series indexed by grid."""
    df = pd.DataFrame({"avail": pd.to_datetime(avail).cummax(), "v": values})
    df = df.dropna(subset=["v"]).sort_values("avail")
    left = pd.DataFrame({"date": grid}).sort_values("date")
    right = df.reset_index(drop=True).rename(columns={"avail": "avail_used"})
    right["avail_key"] = right["avail_used"]
    m = pd.merge_asof(left, right, left_on="date", right_on="avail_key",
                      direction="backward", allow_exact_matches=False)
    m = m.set_index("date")
    return m["v"], m["avail_used"]


def brute_force_pit(date, values: pd.Series, avail: pd.Series):
    """Independent (slow) re-implementation used by the G1 test."""
    a = pd.to_datetime(avail).cummax()
    ok = values.notna() & (a < date)
    if not ok.any():
        return np.nan, pd.NaT
    # latest availability; ties -> latest reference period
    cand = a[ok]
    best = cand[cand == cand.max()].index.max()
    return values[best], a[best]
