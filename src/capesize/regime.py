"""F7: Markov regime-switching probabilities (plan v2, layer 4), strictly past-only.

2-regime Markov switching model on daily 5TC log returns with switching mean and variance.
Parameters are re-estimated at the start of each month on data before that month (history from 1999);
within the month the FILTERED probabilities (Hamilton filter, information up to t) are used, never the
smoothed ones. Regimes are labelled by variance after each fit (regime 1 = high volatility).
Results are cached in data/processed/regime_probs.parquet (depends only on the spot series).
"""
import warnings

import numpy as np
import pandas as pd
from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression

from capesize import config as C
from capesize import data as D

CACHE = C.PROCESSED / "regime_probs.parquet"
FIT_YEARS = 10          # rolling estimation window (years), keeps fits fast and adaptive


def _fit(r: pd.Series, start_params=None):
    mod = MarkovRegression(r.to_numpy() * 100, k_regimes=2, trend="c", switching_variance=True)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = mod.fit(start_params=start_params, disp=False, maxiter=200)
    return mod, res


def _compute(grid: pd.DatetimeIndex) -> pd.DataFrame:
    S = D.load_spot()["S"].dropna()
    r = np.log(S).diff().dropna()
    months = pd.period_range(grid[0].to_period("M"), grid[-1].to_period("M"), freq="M")
    out = []
    sp = None
    for m in months:
        start = m.to_timestamp()
        hist = r[(r.index < start) & (r.index >= start - pd.DateOffset(years=FIT_YEARS))]
        _, res = _fit(hist, sp)
        sp = res.params
        p = np.asarray(res.params)
        # params order: p[0->0], p[1->0], const0, const1, sigma2_0, sigma2_1
        hv = int(np.argmax(p[-2:]))
        # filter through the month with fixed parameters (filtered = uses data up to t only)
        upto = r[(r.index >= start - pd.DateOffset(years=FIT_YEARS)) & (r.index <= m.to_timestamp(how="end"))]
        mod_m = MarkovRegression(upto.to_numpy() * 100, k_regimes=2, trend="c", switching_variance=True)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fr = mod_m.filter(p)
        probs = pd.Series(np.asarray(fr.filtered_marginal_probabilities)[:, hv], index=upto.index)
        mu = p[2:4]
        blk = pd.DataFrame({"rg_p_highvol": probs, "rg_mu_spread": float(mu[hv] - mu[1 - hv])}, index=upto.index)
        out.append(blk[blk.index >= start])
    return pd.concat(out)


def regime_features(grid: pd.DatetimeIndex) -> pd.DataFrame:
    if CACHE.exists():
        rp = pd.read_parquet(CACHE)
    else:
        rp = _compute(grid)
        C.PROCESSED.mkdir(parents=True, exist_ok=True)
        rp.to_parquet(CACHE)
    f = rp.reindex(grid)
    f["rg_p_highvol_avg5"] = f["rg_p_highvol"].rolling(5, min_periods=3).mean()
    return f
