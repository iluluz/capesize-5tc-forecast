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
