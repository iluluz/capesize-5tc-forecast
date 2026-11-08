"""Targets (docs/decisions.md, item 6): y_{t,h} = ln(S_{t+h} / S_t) on the trading-day grid."""
import numpy as np
import pandas as pd

from capesize.contract import HORIZONS


def log_return_target(spot: pd.Series, h: int) -> pd.Series:
    """ln(S_{t+h}/S_t), h in trading days (rows). The last h rows are NaN. Requires S > 0."""
    s = spot.sort_index().astype(float)
    if (s.dropna() <= 0).any():
        raise ValueError("spot must be positive for log returns")
    return np.log(s.shift(-h) / s).rename(f"y_h{h}")


def make_targets(spot: pd.Series, horizons=HORIZONS) -> pd.DataFrame:
    return pd.concat([log_return_target(spot, h) for h in horizons], axis=1)


def residual_target(y: pd.Series, yhat_ml: pd.Series) -> pd.Series:
    """Text-branch target: r_{t,h} = y_{t,h} - out-of-sample ML forecast (aligned on date)."""
    return (y - yhat_ml).rename(f"r_{y.name}" if y.name else "r")


def build_targets(spot: pd.Series, horizons) -> pd.DataFrame:
    """Target block of the feature store, one set of columns per horizon h:
    y_h{h} = ln(S_{t+h}/S_t); tdate_h{h} = date on which y is realised;
    sigma_h{h} = past-only std of y (targets already realised at t, 3-year window);
    cls_h{h} = direction class 0 fall / 1 flat / 2 rise at +-0.5 sigma (docs/02 3.2).
    Rows without a realised S_{t+h} stay NaN (never filled, never dropped silently)."""
    s = spot.sort_index().astype(float)
    t = pd.DataFrame({"S": s})
    dates = pd.Series(s.index, index=s.index)
    for h in horizons:
        y = log_return_target(s, h)
        sig = y.shift(h).rolling(750, min_periods=250).std()
        cls = pd.Series(1.0, index=s.index)
        cls[y > 0.5 * sig] = 2.0
        cls[y < -0.5 * sig] = 0.0
        cls[y.isna() | sig.isna()] = np.nan
        t[f"y_h{h}"] = y
        t[f"tdate_h{h}"] = dates.shift(-h)
        t[f"sigma_h{h}"] = sig
        t[f"cls_h{h}"] = cls
    return t
