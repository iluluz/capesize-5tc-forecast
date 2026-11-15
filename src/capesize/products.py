"""M6 forecast products and M7 economic value (plan v2 2.2, 6.4, 7.1-7.3).

* Turning points: P(a major peak / trough of 5TC within the next H trading days).
  Peak at j: S_j is the maximum of S over [j-20, j+20] and S falls >= 15% within the next 20 days
  (trough: minimum and rises >= 15%). The label for t looks at (t, t+H], so it is known at t+H+20.
* Monthly average vs FFA: target m_t = ln(average 5TC over the M+1 contract month) - ln(M+1 price used at t)
  (the FFA forecast error for next month's settlement). Benchmark: 0 (= the FFA price itself).
* Overlay / hedging backtests on the first trading day of each month (non-overlapping monthly trades).
"""
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd
from joblib import Parallel, delayed
from scipy import stats
from sklearn.metrics import roc_auc_score

from capesize import features as F
from capesize import models as ML
from capesize import validation as V

TP_WIN, TP_MOVE = 20, 0.15


# ---------------------------------------------------------------- labels
def turning_point_labels(S: pd.Series, H=20, win=TP_WIN, move=TP_MOVE) -> pd.DataFrame:
    s = S.to_numpy(dtype=float)
    n = len(s)
    peak, trough = np.zeros(n, bool), np.zeros(n, bool)
    for j in range(win, n - win):
        w = s[j - win: j + win + 1]
        if s[j] == w.max() and s[j + 1: j + win + 1].min() <= s[j] * (1 - move):
            peak[j] = True
        if s[j] == w.min() and s[j + 1: j + win + 1].max() >= s[j] * (1 + move):
            trough[j] = True
    out = pd.DataFrame(index=S.index)
    for nm, ev in (("peak", peak), ("trough", trough)):
        lab = np.full(n, np.nan)
        for t in range(n - H - win):
            lab[t] = float(ev[t + 1: t + H + 1].any())
        out[f"tp_{nm}_{H}"] = lab
    return out


def monthly_ffa_target(store: pd.DataFrame, curve: pd.DataFrame) -> pd.DataFrame:
    """m_t = ln(mean S over the M+1 contract month) - ln(M+1 price on t) and the realisation date (last trading
    day of that month). curve = the lagged curve on the grid (as used by the features)."""
    S = store["S"]
    mon = F.month_period(curve["m1_month"].reindex(store.index))
    mavg = S.groupby(S.index.to_period("M")).mean()
    mend = pd.Series(S.index, index=S.index).groupby(S.index.to_period("M")).max()
    complete = S.index.to_period("M").max()            # last month in data may be incomplete
    f1 = curve["M+1"].reindex(store.index)
    tgt = np.log(mon.map(mavg).astype(float)) - np.log(f1.where(f1 > 0))
    tgt[(mon >= complete) | mon.isna()] = np.nan
    return pd.DataFrame({"m_target": tgt, "m_tdate": mon.map(mend), "m_month": mon, "m_price": f1})


# ---------------------------------------------------------------- binary classifier (turning points)
def lgbm_bin_fold(Xtr, ytr, Xte, h, grid=ML.GRID):
    ok = ~np.isnan(ytr)
    Xtr, yb = Xtr[ok], ytr[ok].astype(int)
    cols = ML.drop_corr(Xtr)
    Xtr, Xte = Xtr[cols], Xte[cols]
    folds = ML.inner_splits(len(Xtr), h)
    base_rate = float(yb.mean())

    def fit(p, X, y, n=None, val=None):
        m = lgb.LGBMClassifier(objective="binary", **{**ML.BASE_PARAMS, **p, **({"n_estimators": n} if n else {})})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if val is None:
                m.fit(X, y)
                return m, n, np.nan
            m.fit(X, y, eval_set=[val], eval_metric="binary_logloss",
                  callbacks=[lgb.early_stopping(100, verbose=False)])
        return m, max(int(m.best_iteration_ or m.n_estimators), 20), m.best_score_["valid_0"]["binary_logloss"]

    if yb.sum() < 10:
        return {"p": np.full(len(Xte), base_rate), "clim": np.full(len(Xte), base_rate)}
    best = None
    for p in grid:
        res = [fit(p, Xtr.iloc[a], yb[a], val=(Xtr.iloc[v], yb[v])) for a, v in folds if yb[a].sum() >= 5]
        if not res:
            continue
        sc, it = float(np.mean([r[2] for r in res])), int(np.median([r[1] for r in res]))
        if best is None or sc < best[2]:
            best = (p, it, sc)
    m, _, _ = fit(best[0], Xtr, yb, n=best[1])
    return {"p": m.predict_proba(Xte)[:, 1], "clim": np.full(len(Xte), base_rate)}


def run_turning_points(store: pd.DataFrame, feats, H=20, n_jobs=-1, test_start="2019-01-01") -> pd.DataFrame:
    lab = turning_point_labels(store["S"], H)
    h_eff = H + TP_WIN                                    # label known at t + H + 20
    st = store.copy()
    out = []
    for nm in ("peak", "trough"):
        y = lab[f"tp_{nm}_{H}"]
        st[f"y_h{h_eff}"] = y
        X = st[list(feats)]
        folds = list(V.folds(st, h_eff, test_start))
        res = Parallel(n_jobs=n_jobs)(delayed(lgbm_bin_fold)(X.iloc[tr], y.to_numpy()[tr], X.iloc[te], h_eff)
                                      for tr, te, _ in folds)
        for (_, te, tr_end), r in zip(folds, res, strict=True):
            out.append(pd.DataFrame({"date": st.index[te], "event": nm, "y_true": y.to_numpy()[te], "p": r["p"],
                                     "clim": r["clim"], "train_end": st.index[tr_end]}))
    return pd.concat(out, ignore_index=True)


def tp_table(T: pd.DataFrame, h_eff=40) -> pd.DataFrame:
    from capesize import metrics as M
    rows = []
    for nm, d in T.groupby("event"):
        y, p, c = d.y_true.to_numpy(), d.p.to_numpy(), d.clim.to_numpy()
        bm, bc = (p - y) ** 2, (c - y) ** 2
        dm, dp = M.diebold_mariano(np.sqrt(bm), np.sqrt(bc), h_eff)     # squared -> Brier loss differential
        top = p >= np.quantile(p, 0.9)
        rows.append({"event": nm, "n": len(y), "base_rate": y.mean(), "AUC": roc_auc_score(y, p),
                     "Brier": bm.mean(), "Brier_clim": bc.mean(), "BSS": 1 - bm.mean() / bc.mean(),
                     "DM_vs_clim_stat": dm, "DM_vs_clim_p": dp, "hit_rate_top10pct": y[top].mean()})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- monthly target + backtests
def first_days(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(index, index=index)
    return pd.DatetimeIndex(s.groupby(index.to_period("M")).min().to_numpy())


def deflated_sharpe(sr: float, n_obs: int, n_trials: int, skew: float, kurt: float, sr_var: float) -> float:
    """Bailey & Lopez de Prado (2014): P(true SR > 0 | best of n_trials). sr per period (not annualised)."""
    emc = 0.5772156649
    q1, q2 = stats.norm.ppf(1 - 1 / n_trials), stats.norm.ppf(1 - 1 / (n_trials * np.e))
    sr0 = np.sqrt(sr_var) * ((1 - emc) * q1 + emc * q2)
    z = (sr - sr0) * np.sqrt(n_obs - 1) / np.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr ** 2)
    return float(stats.norm.cdf(z))


def overlay_backtest(pred: pd.Series, mt: pd.DataFrame, cost=0.01, n_trials=1) -> dict:
    """Monthly FFA overlay: on the first trading day of each month take sign(pred) in the M+1 contract when
    |pred| > cost; PnL = sign * (avg settlement / F - 1) - cost (fraction of notional)."""
    d = pd.DataFrame({"pred": pred}).join(mt).dropna(subset=["pred", "m_target"])
    d = d.loc[d.index.intersection(first_days(d.index))]
    ret = np.exp(d.m_target) - 1
    pos = np.sign(d.pred) * (d.pred.abs() > cost)
    pnl = pos * ret - cost * (pos != 0)
    traded = pnl[pos != 0]
    sr = traded.mean() / traded.std() if len(traded) > 2 else np.nan
    eq = pnl.cumsum()
    return {"months": len(d), "trades": int((pos != 0).sum()), "hit_rate": float((traded > 0).mean()),
            "mean_pnl_pct": 100 * float(pnl.mean()), "sharpe_ann": float(sr * np.sqrt(12)) if sr == sr else np.nan,
            "max_dd_pct": 100 * float((eq - eq.cummax()).min()),
            "deflated_sharpe_prob": deflated_sharpe(sr, len(traded), max(n_trials, 2), stats.skew(traded),
                                                    stats.kurtosis(traded, fisher=False), 1 / max(len(traded), 2))
            if len(traded) > 10 else np.nan}


def hedging_backtest(pred: pd.Series, mt: pd.DataFrame) -> pd.DataFrame:
    """Charterer: each month either fix next month's freight at the M+1 FFA price (hedge) or pay the average spot.
    Model rule: hedge when the forecast average exceeds the FFA price (pred > 0). Costs in % of the FFA price."""
    d = pd.DataFrame({"pred": pred}).join(mt).dropna(subset=["pred", "m_target"])
    d = d.loc[d.index.intersection(first_days(d.index))]
    spot_cost = np.exp(d.m_target) - 1                    # avg spot relative to F
    rules = {"always hedge (FFA)": np.zeros(len(d)), "never hedge (spot)": spot_cost.to_numpy(),
             "model rule": np.where(d.pred > 0, 0.0, spot_cost)}
    return pd.DataFrame([{"strategy": k, "months": len(d), "mean_cost_vs_FFA_pct": 100 * v.mean(),
                          "std_pct": 100 * v.std(), "worst_month_pct": 100 * v.max()} for k, v in rules.items()])
