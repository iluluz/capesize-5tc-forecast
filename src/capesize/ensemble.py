"""M4 dynamic ensembles and M5 adaptive intervals, computed on out-of-sample forecast streams.

Information rule: on decision date t only forecasts whose targets are already realised (tdate < t) are used to
set weights or calibrate intervals.
"""
import numpy as np
import pandas as pd
from scipy.optimize import nnls


def _wide(P: pd.DataFrame, store: pd.DataFrame, h: int, members) -> pd.DataFrame:
    w = P[(P.h == h) & P.model.isin(members)].pivot_table(index="date", columns="model", values="yhat")
    w = w[list(members)].dropna()
    w["y"] = store[f"y_h{h}"].reindex(w.index)
    w["tdate"] = store[f"tdate_h{h}"].reindex(w.index)
    return w


def dynamic_oos(P, store, h, members, name, method="invmse", window=250, halflife=125, min_rows=120):
    """Re-weight members every day from their realised past errors.
    invmse: weights proportional to 1 / EW-MSE over the last `window` realised rows (half-life `halflife`).
    stack:  non-negative least squares on the last `window` realised rows (no intercept), normalised to sum 1.
    Equal weights until min_rows realised rows exist."""
    w = _wide(P, store, h, members)
    F, y, td, idx = w[list(members)].to_numpy(), w["y"].to_numpy(), w["tdate"].to_numpy(), w.index
    yhat, W = np.zeros(len(w)), np.zeros((len(w), len(members)))
    for i, t in enumerate(idx):
        past = np.flatnonzero(td < t)[-window:]
        if len(past) < min_rows:
            wt = np.full(len(members), 1 / len(members))
        elif method == "invmse":
            age = len(past) - 1 - np.arange(len(past))
            ew = 0.5 ** (age / halflife)
            mse = (ew[:, None] * (y[past, None] - F[past]) ** 2).sum(0) / ew.sum()
            wt = (1 / mse) / (1 / mse).sum()
        else:
            wt, _ = nnls(F[past], y[past])
            wt = wt / wt.sum() if wt.sum() > 0 else np.full(len(members), 1 / len(members))
        W[i], yhat[i] = wt, F[i] @ wt
    out = pd.DataFrame({"date": idx, "h": h, "y_true": y, "yhat": yhat})
    for j, m in enumerate(members):
        out[f"w_{m}"] = W[:, j]
    return out.assign(model=name)


def aci_interval(P_model: pd.DataFrame, store: pd.DataFrame, h: int, alpha=0.2, gamma=0.01, window=500,
                 scale_col=None, name=None) -> pd.DataFrame:
    """M5: adaptive conformal (Gibbs & Candes 2021) on top of a quantile forecast stream (q10/q90).
    Scores s_i = max(q10_i - y_i, y_i - q90_i) [/ scale_i]; on day t the half-width is the (1 - a_t) quantile of
    realised scores (tdate < t, last `window`), and a_t is updated with the realised miss indicators:
    a_{t+1} = a_t + gamma * (alpha - err). Delayed feedback: an error enters only once its target is realised."""
    d = P_model[P_model.h == h].set_index("date").sort_index()
    y, lo, hi = d["y_true"].to_numpy(), d["q10"].to_numpy(), d["q90"].to_numpy()
    lo, hi = np.minimum(lo, hi), np.maximum(lo, hi)
    sc = np.ones(len(d)) if scale_col is None else store[scale_col].reindex(d.index).bfill().to_numpy()
    td = store[f"tdate_h{h}"].reindex(d.index).to_numpy()
    s = np.maximum(lo - y, y - hi) / sc
    a_t, q_used, done = alpha, np.full(len(d), np.nan), np.zeros(len(d), dtype=bool)
    L, U = np.zeros(len(d)), np.zeros(len(d))
    for i, t in enumerate(d.index):
        newly = np.flatnonzero((td < t) & ~done & ~np.isnan(q_used))
        for k in newly:                                   # feedback from realised targets, in order
            err = float(s[k] > q_used[k])
            a_t = float(np.clip(a_t + gamma * (alpha - err), 0.01, 0.6))
            done[k] = True
        past = np.flatnonzero(td < t)[-window:]
        q = np.quantile(s[past], 1 - a_t) if len(past) >= 60 else 0.0   # warm-up: base interval, no look-ahead
        q_used[i] = q
        L[i], U[i] = lo[i] - q * sc[i], hi[i] + q * sc[i]
    out = d.reset_index()[["date", "h", "y_true", "yhat", "q10", "q50", "q90", "train_end"]].copy()
    out["lo80"], out["hi80"] = L, U
    return out.assign(model=name or f"{P_model.model.iloc[0]}_aci")
