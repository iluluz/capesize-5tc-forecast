"""M3: statistical layer (plan v2, layers 0-1): VECM (spot + constant-maturity FFA) and ARMA on daily returns.

Both are refit monthly on the training rows of each walk-forward fold; within the test month the fitted
parameters are applied to data observed up to each decision date t (no refit, no look-ahead).
"""
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.vector_ar.vecm import VECM

from capesize import validation as V

FFA_TENOR = 20      # constant-maturity forward used in the VECM (ffa_hat_h20: ~28 calendar days)


def _vecm_forecast(res, hist: np.ndarray, h: int) -> float:
    """h-step forecast of ln S (column 0) from the last k_ar_diff+1 levels in `hist`, by iterating
    dy_{s+1} = alpha (beta' y_s + c) + sum_i Gamma_i dy_{s+1-i}."""
    p = res.k_ar - 1
    alpha, beta = res.alpha, res.beta
    c = res.det_coef_coint.ravel() if res.det_coef_coint.size else np.zeros(beta.shape[1])
    gam = res.gamma
    K = hist.shape[1]
    y = list(hist[-(p + 1):])
    dys = [y[i + 1] - y[i] for i in range(p)]
    for _ in range(h):
        ect = beta.T @ y[-1] + c
        dy = alpha @ ect
        for i in range(p):
            dy = dy + gam[:, i * K:(i + 1) * K] @ dys[-1 - i]
        y.append(y[-1] + dy)
        dys.append(dy)
    return float(y[-1][0] - hist[-1][0])


def run_vecm(store: pd.DataFrame, h: int, k_ar_diff=2, name="vecm", test_start=None) -> pd.DataFrame:
    lnS = np.log(store["S"])
    lnF = store[f"ffa_hat_h{FFA_TENOR}"] + lnS
    Y = pd.concat([lnS, lnF], axis=1).to_numpy()
    ok = ~np.isnan(Y).any(axis=1)
    checked = []

    def fp(tr, te):
        rows = np.arange(0, tr[-1] + 1)
        rows = rows[ok[rows]]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = VECM(Y[rows], k_ar_diff=k_ar_diff, coint_rank=1, deterministic="ci").fit()
        if not checked:                               # self-check of the recursion against statsmodels
            mine = _vecm_forecast(res, Y[rows], h)
            ref = float(res.predict(steps=h)[-1, 0] - Y[rows][-1, 0])
            assert abs(mine - ref) < 1e-8, (mine, ref)
            checked.append(True)
        out = np.zeros(len(te))
        for j, t in enumerate(te):
            hist = Y[: t + 1]
            hist = hist[~np.isnan(hist).any(axis=1)]
            out[j] = _vecm_forecast(res, hist, h)
        return out

    kw = {} if test_start is None else {"test_start": test_start}
    return V.walk_forward(store, h, fp, name, **kw)


def run_arma(store: pd.DataFrame, h: int, order=(1, 0, 1), name="arma", test_start=None) -> pd.DataFrame:
    r = np.log(store["S"]).diff().to_numpy() * 100

    def fp(tr, te):
        rows = np.arange(1, tr[-1] + 1)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res = ARIMA(r[rows], order=order, trend="c").fit()
            out = np.zeros(len(te))
            for j, t in enumerate(te):
                rr = res.apply(r[1: t + 1])
                out[j] = rr.forecast(h).sum() / 100
        return out

    kw = {} if test_start is None else {"test_start": test_start}
    return V.walk_forward(store, h, fp, name, **kw)
