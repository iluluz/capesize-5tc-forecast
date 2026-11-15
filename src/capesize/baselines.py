import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.model_selection import TimeSeriesSplit

from capesize.features import month_period

RIDGE_FEATURES = ["ffa_basis_m1", "ffa_basis_m2", "ffa_slope", "ffa_m1_chg5",
                  "mom_5", "mom_20", "mom_60", "dev_60", "rv_20", "rv_60"]


def ffa_implied(curve: pd.DataFrame, S: pd.Series, h: int) -> pd.Series:
    """Constant-maturity forward at t+h from M0/M+1/M+2 (+ M+3 for h > 20), as ln(F/S_t).
    Target date T = t + round(h*7/5) calendar days (known at t, no look-ahead).
    Contracts sit at mid-month (15th); ln F is interpolated linearly in time, flat beyond ends.
    Missing M0 (expired on the last trading day of a month) is simply skipped as a node."""
    cur = curve.ffill()                                  # 1 missing curve day (2019-02-27)
    out = pd.Series(np.nan, index=S.index)
    m1 = month_period(cur["m1_month"]).to_numpy()
    cal_days = int(round(h * 7 / 5))
    nodes = ((-1, "M0"), (0, "M+1"), (1, "M+2")) + (((2, "M+3"),) if h > 20 else ())   # h=65 ~ 3 months out
    for i, (t, row) in enumerate(cur.iterrows()):
        if t not in S.index:
            continue
        p1 = m1[i]
        if pd.isna(p1):
            continue
        nodes_t, nodes_v = [], []
        for off, col in nodes:
            v = row[col]
            if pd.notna(v) and v > 0:
                nodes_t.append((p1 + off).to_timestamp() + pd.Timedelta(days=14))
                nodes_v.append(np.log(v))
        if len(nodes_t) < 2:
            continue
        T = t + pd.Timedelta(days=cal_days)
        xs = np.array([x.value for x in nodes_t], dtype=float)
        out[t] = np.interp(float(T.value), xs, nodes_v) - np.log(S[t])
    return out


def seasonal_naive(Xtr_doy, ytr, doy_test, window=3):
    d = np.abs(Xtr_doy[None, :] - doy_test[:, None])
    d = np.minimum(d, 365 - d)
    out = np.zeros(len(doy_test))
    for i in range(len(doy_test)):
        m = d[i] <= window
        out[i] = ytr[m].mean() if m.sum() >= 5 else 0.0
    return out


def ridge_fit_predict(Xtr: pd.DataFrame, ytr: np.ndarray, Xte: pd.DataFrame, h: int):
    med = Xtr.median()
    mu, sd = Xtr.fillna(med).mean(), Xtr.fillna(med).std().replace(0, 1)

    def z(X):
        return ((X.fillna(med) - mu) / sd).values

    cv = TimeSeriesSplit(n_splits=5, gap=h)
    m = RidgeCV(alphas=np.logspace(-1, 4, 16), cv=cv).fit(z(Xtr), ytr)
    return m.predict(z(Xte))
