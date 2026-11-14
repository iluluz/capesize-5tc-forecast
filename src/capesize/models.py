"""Main model (docs/02 3.4): LightGBM per horizon, point (Huber) + quantiles 0.1/0.5/0.9,
split-conformal 80% interval (CQR) calibrated on the last 12 months of each training window.

Optional residual mode: with `base_tr/base_te` (e.g. the FFA-implied forecast, known at t) the model learns
r = y - base and predicts base + r_hat (quantiles likewise).

Everything inside `lgbm_fold` sees only the training rows of one walk-forward fold:
correlation filter, hyper-parameter choice, early stopping and conformal calibration.
"""
import warnings

import lightgbm as lgb
import numpy as np
import pandas as pd

FEATURE_GROUPS = {
    "ffa": ("ffa_",),
    "spot": ("mom_", "dev_", "rv_", "c14_c10", "c3_c5", "c16_neg"),
    "ironore": ("io_",),
    "portwatch": ("pw_", "portwatch_available"),
    "fleet": ("fl_",),
    "customs": ("cu_",),
    "calendar": ("cal_",),
    # v2 groups (ml-v1.1 candidates; absent from the v1 store, so v1 runs are unchanged)
    "bias": ("fb_",),
    "route": ("rt_",),
    "path": ("pth_",),
    "util": ("ut_",),
    "regime": ("rg_",),
    "macro": ("mc_",),
}
ABLATIONS = {                      # docs/02 3.7: -FFA, -spot dynamics, -PortWatch, -fundamentals (2/4/6)
    "-ffa": ("ffa",),
    "-spot": ("spot",),
    "-portwatch": ("portwatch",),
    "-fundamentals": ("ironore", "fleet", "customs"),
}
MONOTONE_POS = ("ffa_basis_m1", "ffa_basis_m2")   # forward above spot -> higher expected change

BASE_PARAMS = dict(learning_rate=0.03, feature_fraction=0.7, bagging_fraction=0.8, bagging_freq=1,
                   lambda_l2=1.0, max_depth=-1, n_estimators=1500, verbose=-1, n_jobs=1, seed=0)
GRID = [dict(num_leaves=nl, min_data_in_leaf=md) for nl in (7, 15) for md in (50, 100, 200)]
QUANTILES = (0.1, 0.5, 0.9)
INNER_FOLDS = 3        # inner time-ordered folds for grid choice and early stopping
INNER_VAL = 250        # rows (~12 months) per inner validation block, each after a purge of h rows
CONFORMAL_ROWS = 250   # last ~12 months of the training window
ALPHA = 0.2            # 80% interval


def feature_columns(columns, drop_groups=()):
    """All model features, minus the listed groups."""
    prefixes = [p for g, ps in FEATURE_GROUPS.items() if g not in drop_groups for p in ps]
    return [c for c in columns if any(c.startswith(p) for p in prefixes)]


def group_of(col: str) -> str:
    for g, ps in FEATURE_GROUPS.items():
        if any(col.startswith(p) for p in ps):
            return g
    return "other"


def drop_corr(Xtr: pd.DataFrame, thr: float = 0.9) -> list[str]:
    """Drop constant/all-NaN columns, then one of any pair with |corr| > thr (first one kept)."""
    Xtr = Xtr.loc[:, Xtr.nunique() >= 2]
    cols = list(Xtr.columns)
    c = Xtr.corr().abs().fillna(0).to_numpy()
    keep = []
    for i in range(len(cols)):
        if all(c[i, j] <= thr for j in keep):
            keep.append(i)
    return [cols[i] for i in keep]


def _model(objective: str, params: dict, cols, **extra) -> lgb.LGBMRegressor:
    if objective != "quantile":          # LightGBM does not support monotone constraints for quantile loss
        extra = {**extra, "monotone_constraints": [1 if c in MONOTONE_POS else 0 for c in cols]}
    return lgb.LGBMRegressor(objective=objective, **{**BASE_PARAMS, **params, **extra})


def _fit(objective, params, cols, X, y, w=None, n=None, val=None, **extra):
    """Fit; with val=(Xv, yv) early-stop and return (model, best_iter, best_score), else (model, n, nan)."""
    if n is not None:
        extra["n_estimators"] = n
    m = _model(objective, params, cols, **extra)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        if val is None:
            m.fit(X, y, sample_weight=w)
            return m, n, np.nan
        metric = "quantile" if objective == "quantile" else "l2"
        m.fit(X, y, sample_weight=w, eval_set=[val], eval_metric=metric,
              callbacks=[lgb.early_stopping(100, verbose=False)])
    best_it = max(int(m.best_iteration_ or m.n_estimators), 20)
    return m, best_it, m.best_score_["valid_0"][metric]


def inner_splits(n: int, h: int, k: int = INNER_FOLDS, val: int = INNER_VAL, min_inner: int = 250):
    """k expanding inner folds (oldest first): train [0, v0 - h) | purge h | validate [v0, v0 + val).

    Small-sample fallback (only when the standard rule gives fewer than k folds, i.e. the 2016-2018 extra test):
    k shorter blocks of (n - 150 - h) // k rows (>= 50) with >= 150 inner training rows."""
    out = []
    for j in range(k, 0, -1):
        v0 = n - j * val
        if v0 - h >= min_inner:
            out.append((np.arange(0, v0 - h), np.arange(v0, v0 + val)))
    if len(out) < k and min_inner > 150:
        small = (n - 150 - h) // k
        if small >= 50:
            return inner_splits(n, h, k, small, min_inner=150)
    return out


def recency_weights(n: int, halflife: int | None):
    return None if not halflife else 0.5 ** ((n - 1 - np.arange(n)) / halflife)


def stability_select(Xtr: pd.DataFrame, t: np.ndarray, h: int, folds, k_max=35, k_min=15, seed=0) -> list[str]:
    """F8: in-window stability selection. On each inner fold fit a small Huber LightGBM (early-stopped), compute
    permutation importance (increase in validation MSE) per feature; keep features with positive importance in at
    least 2 of the folds, ranked by mean importance, capped at k_max (at least k_min). Training rows only."""
    rng = np.random.default_rng(seed)
    cols = list(Xtr.columns)
    imp = np.zeros((len(folds), len(cols)))
    p = dict(num_leaves=7, min_data_in_leaf=100)
    for j, (a, v) in enumerate(folds):
        m, _, _ = _fit("huber", p, cols, Xtr.iloc[a], t[a], val=(Xtr.iloc[v], t[v]), alpha=float(np.std(t[a])))
        Xv = Xtr.iloc[v].copy()
        base = np.mean((t[v] - m.predict(Xv)) ** 2)
        for i, c in enumerate(cols):
            keep = Xv[c].to_numpy().copy()
            Xv[c] = rng.permutation(keep)
            imp[j, i] = np.mean((t[v] - m.predict(Xv)) ** 2) - base
            Xv[c] = keep
    votes = (imp > 0).sum(axis=0)
    order = np.argsort(-imp.mean(axis=0))
    need = max(2, len(folds) - 1)
    chosen = [cols[i] for i in order if votes[i] >= need][:k_max]
    if len(chosen) < k_min:
        chosen = [cols[i] for i in order[:k_min]]
    return chosen


def lgbm_fold(Xtr: pd.DataFrame, ytr: np.ndarray, Xte: pd.DataFrame, h: int, base_tr=None, base_te=None,
              grid=GRID, quantiles=QUANTILES, conformal=True, halflife=None, return_model=False, select=None,
              params_scale=None, rpd=1):
    """One walk-forward fold. Returns dict of test-row columns: yhat, q10, q50, q90, lo80, hi80 (+ meta)."""
    ytr = np.asarray(ytr, dtype=float)
    b_tr = np.zeros(len(ytr)) if base_tr is None else np.asarray(base_tr, dtype=float)
    b_te = np.zeros(len(Xte)) if base_te is None else np.nan_to_num(np.asarray(base_te, dtype=float))
    t = ytr - b_tr                                     # target (residual over the base if one is given)
    ok = ~np.isnan(t)
    Xtr, t = Xtr[ok], t[ok]
    cols = drop_corr(Xtr)
    Xtr, Xte = Xtr[cols], Xte[cols]
    n = len(Xtr)
    w = recency_weights(n, halflife)
    huber = dict(alpha=float(np.std(t)))              # Huber delta ~ 1 sd (LightGBM default 0.9 ~ L2 here)
    # rpd = rows per date (route panel): purge / validation blocks are scaled so they stay in calendar time
    folds = inner_splits(n, h * rpd, val=INNER_VAL * rpd, min_inner=250 * rpd) if rpd > 1 else inner_splits(n, h)
    if select:
        cols = stability_select(Xtr, t, h, folds, k_max=select)
        Xtr, Xte = Xtr[cols], Xte[cols]
    if params_scale:                                   # robustness (plan v2 6.5): scale grid parameters
        grid = [{k: max(2, int(round(v * params_scale.get(k, 1.0)))) for k, v in p.items()} for p in grid]

    def sub(idx):
        return None if w is None else w[idx]

    # grid choice: mean early-stopped validation loss over the inner folds
    best = None
    for p in grid:
        res = [_fit("huber", p, cols, Xtr.iloc[a], t[a], sub(a), val=(Xtr.iloc[v], t[v]), **huber)
               for a, v in folds]
        sc, it = float(np.mean([r[2] for r in res])), int(np.median([r[1] for r in res]))
        if best is None or sc < best[2]:
            best = (p, it, sc)
    params, n_point = best[0], best[1]
    point, _, _ = _fit("huber", params, cols, Xtr, t, w, n=n_point, **huber)
    out = {"yhat": b_te + point.predict(Xte)}

    q_iter = {}
    for q in quantiles:
        q_iter[q] = int(np.median([_fit("quantile", params, cols, Xtr.iloc[a], t[a], sub(a), alpha=q,
                                        val=(Xtr.iloc[v], t[v]))[1] for a, v in folds]))
        m, _, _ = _fit("quantile", params, cols, Xtr, t, w, n=q_iter[q], alpha=q)
        out[f"q{int(round(q * 100))}"] = b_te + m.predict(Xte)

    if conformal and 0.1 in quantiles and 0.9 in quantiles:
        # CQR: quantile models fit on the proper training set (purged), scores on the last 12 months
        p_end, c_start = n - CONFORMAL_ROWS - h, n - CONFORMAL_ROWS
        pr = np.arange(p_end)
        lo_m, _, _ = _fit("quantile", params, cols, Xtr.iloc[pr], t[pr], sub(pr), n=q_iter[0.1], alpha=0.1)
        hi_m, _, _ = _fit("quantile", params, cols, Xtr.iloc[pr], t[pr], sub(pr), n=q_iter[0.9], alpha=0.9)
        Xc, tc = Xtr.iloc[c_start:], t[c_start:]
        scores = np.maximum(lo_m.predict(Xc) - tc, tc - hi_m.predict(Xc))
        k = min(1.0, (1 - ALPHA) * (len(tc) + 1) / len(tc))
        qhat = float(np.quantile(scores, k, method="higher"))
        lo, hi = np.minimum(out["q10"], out["q90"]), np.maximum(out["q10"], out["q90"])
        out["lo80"], out["hi80"] = lo - qhat, hi + qhat

    meta = {"num_leaves": params["num_leaves"], "min_data_in_leaf": params["min_data_in_leaf"],
            "n_iter": n_point, "n_features": len(cols)}
    out.update({k: np.full(len(Xte), v) for k, v in meta.items()})
    if return_model:
        return out, point, cols
    return out


CLASSES = 3   # 0 fall / 1 flat / 2 rise (targets.build_targets)


def lgbm_cls_fold(Xtr: pd.DataFrame, ctr: np.ndarray, Xte: pd.DataFrame, h: int, grid=GRID):
    """Optional 3-class direction classifier (docs/02 3.4), same fold discipline as `lgbm_fold`:
    correlation filter, grid by mean early-stopped multi-logloss over the inner folds, refit at the median
    best iteration. Returns p0, p1, p2 (fall / flat / rise) and clim0..2 = training class frequencies
    (the no-skill reference forecast)."""
    ctr = np.asarray(ctr, dtype=float)
    ok = ~np.isnan(ctr)
    Xtr, c = Xtr[ok], ctr[ok].astype(int)
    cols = drop_corr(Xtr)
    Xtr, Xte = Xtr[cols], Xte[cols]
    folds = inner_splits(len(Xtr), h)

    def fit(p, X, y, n=None, val=None):
        m = lgb.LGBMClassifier(objective="multiclass", num_class=CLASSES,
                               **{**BASE_PARAMS, **p, **({"n_estimators": n} if n else {})})
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if val is None:
                m.fit(X, y)
                return m, n, np.nan
            m.fit(X, y, eval_set=[val], eval_metric="multi_logloss",
                  callbacks=[lgb.early_stopping(100, verbose=False)])
        return m, max(int(m.best_iteration_ or m.n_estimators), 20), m.best_score_["valid_0"]["multi_logloss"]

    best = None
    for p in grid:
        res = [fit(p, Xtr.iloc[a], c[a], val=(Xtr.iloc[v], c[v])) for a, v in folds]
        sc, it = float(np.mean([r[2] for r in res])), int(np.median([r[1] for r in res]))
        if best is None or sc < best[2]:
            best = (p, it, sc)
    m, _, _ = fit(best[0], Xtr, c, n=best[1])
    prob = np.zeros((len(Xte), CLASSES))
    prob[:, m.classes_] = m.predict_proba(Xte)
    clim = np.bincount(c, minlength=CLASSES) / len(c)
    out = {f"p{k}": prob[:, k] for k in range(CLASSES)}
    out.update({f"clim{k}": np.full(len(Xte), clim[k]) for k in range(CLASSES)})
    out.update({"num_leaves": np.full(len(Xte), best[0]["num_leaves"]), "n_iter": np.full(len(Xte), best[1])})
    return out


def gain_importance(model: lgb.LGBMRegressor, cols) -> pd.Series:
    imp = model.booster_.feature_importance(importance_type="gain")
    return pd.Series(imp / max(imp.sum(), 1e-12), index=cols).sort_values(ascending=False)
