"""Runners and evaluation for the ML part (docs/02 3.3, 3.6, 3.7).

All predictions are walk-forward out-of-sample, in long format:
date, h, y_true, yhat[, q10, q50, q90, lo80, hi80, ...], model, train_end.
"""
import datetime as dt
import functools
import subprocess

import numpy as np
import pandas as pd
import statsmodels.api as sm
from joblib import Parallel, delayed
from scipy.optimize import nnls

from capesize import baselines as B
from capesize import config as C
from capesize import metrics as M
from capesize import models as ML
from capesize import validation as V
from capesize.io import REPO


# ------------------------------------------------------------------ runners
def build_store(ffa_lag: int | None = None, horizons=C.HORIZONS + C.STRETCH_HORIZONS):
    """Feature store + targets + FFA-implied forecasts (ffa_hat_h{h}, known at t; also used as features).
    Returns (store, parts) with parts = dict(g, X, A, srcs, curve) for the G1 checks."""
    from capesize import features as F
    from capesize.targets import build_targets
    g, X, A, srcs, curve = F.build_feature_store(ffa_lag)
    store = pd.concat([X, build_targets(g["S"], horizons)], axis=1)
    for h in C.HORIZONS:
        store[f"ffa_hat_h{h}"] = B.ffa_implied(curve, g["S"], h)
    return store, dict(g=g, X=X, A=A, srcs=srcs, curve=curve)


def with_stretch_ffa(store: pd.DataFrame, curve: pd.DataFrame, horizons=C.STRETCH_HORIZONS) -> pd.DataFrame:
    """Copy of the store with ffa_hat_h{h} for the stretch horizons (h = 40/65). Kept out of the main store so
    the h = 5/20 models do not gain extra features."""
    st = store.copy()
    for h in horizons:
        st[f"ffa_hat_h{h}"] = B.ffa_implied(curve, st["S"], h)
    return st


def run_baselines(store: pd.DataFrame, horizons=C.HORIZONS, test_start=C.TEST_START, test_end=None) -> pd.DataFrame:
    doy = store.index.day_of_year.to_numpy()
    preds = []
    for h in horizons:
        def wf(fn, name, h=h):
            return V.walk_forward(store, h, fn, name, test_start, test_end)

        yv = store[f"y_h{h}"].to_numpy()
        f = store[f"ffa_hat_h{h}"].fillna(0).to_numpy()
        Xr = store[B.RIDGE_FEATURES]
        preds += [
            wf(lambda tr, te: np.zeros(len(te)), "random_walk"),
            wf(lambda tr, te, yv=yv: B.seasonal_naive(doy[tr], yv[tr], doy[te]), "seasonal_naive"),
            wf(lambda tr, te, f=f: f[te], "ffa_implied"),
            wf(lambda tr, te, yv=yv, h=h, Xr=Xr: B.ridge_fit_predict(Xr.iloc[tr], yv[tr], Xr.iloc[te], h), "ridge"),
            wf(lambda tr, te, yv=yv, h=h, Xr=Xr, f=f: f[te] + B.ridge_fit_predict(
                Xr.iloc[tr], yv[tr] - f[tr], Xr.iloc[te], h), "ridge_resid"),
        ]
    return pd.concat(preds, ignore_index=True)


def _lgbm_task(X, y, base, tr, te, h, kw):
    if base is not None:
        tr = tr[~np.isnan(base[tr])]
        return ML.lgbm_fold(X.iloc[tr], y[tr], X.iloc[te], h, base_tr=base[tr],
                            base_te=np.nan_to_num(base[te]), **kw)
    return ML.lgbm_fold(X.iloc[tr], y[tr], X.iloc[te], h, **kw)


def run_lgbm(store: pd.DataFrame, h: int, name="lgbm", drop_groups=(), residual=False, n_jobs=-1,
             test_start=C.TEST_START, test_end=None, **kw) -> pd.DataFrame:
    """Walk-forward LightGBM for one horizon; folds run in parallel (each fold sees only its train rows).
    residual=True: learn y - ffa_hat_h{h} and predict ffa_hat + r_hat."""
    feats = ML.feature_columns(store.columns, drop_groups)
    X, y = store[feats], store[f"y_h{h}"].to_numpy()
    base = store[f"ffa_hat_h{h}"].to_numpy() if residual else None
    folds = list(V.folds(store, h, test_start, test_end))
    res = Parallel(n_jobs=n_jobs)(delayed(_lgbm_task)(X, y, base, tr, te, h, kw) for tr, te, _ in folds)
    out = []
    for (_, te, tr_end), r in zip(folds, res, strict=True):
        base_df = pd.DataFrame({"date": store.index[te], "h": h, "y_true": y[te]})
        out.append(pd.concat([base_df, pd.DataFrame(r)], axis=1).assign(model=name, train_end=store.index[tr_end]))
    return pd.concat(out, ignore_index=True)


def run_lgbm_cls(store: pd.DataFrame, h: int, name="lgbm_cls", drop_groups=(), n_jobs=-1,
                 test_start=C.TEST_START, test_end=None) -> pd.DataFrame:
    """Walk-forward 3-class direction classifier (fall / flat / rise at +-0.5 sigma_h, past-only sigma)."""
    feats = ML.feature_columns(store.columns, drop_groups)
    X, c = store[feats], store[f"cls_h{h}"].to_numpy()
    folds = list(V.folds(store, h, test_start, test_end))
    res = Parallel(n_jobs=n_jobs)(delayed(ML.lgbm_cls_fold)(X.iloc[tr], c[tr], X.iloc[te], h) for tr, te, _ in folds)
    out = []
    for (_, te, tr_end), r in zip(folds, res, strict=True):
        base_df = pd.DataFrame({"date": store.index[te], "h": h, "cls_true": c[te]})
        out.append(pd.concat([base_df, pd.DataFrame(r)], axis=1).assign(model=name, train_end=store.index[tr_end]))
    return pd.concat(out, ignore_index=True)


def class_table(Pc: pd.DataFrame, P: pd.DataFrame, store: pd.DataFrame, reg_models, horizons=C.HORIZONS,
                name="lgbm_cls") -> pd.DataFrame:
    """Direction metrics on common rows: macro-F1 and accuracy for the classifier (argmax), the climatology
    (training majority class) and regression forecasts mapped to classes at the same +-0.5 sigma thresholds;
    multi-class log loss and Brier for the probabilistic forecasts; DM on per-row log loss vs climatology
    (stat > 0 => climatology better)."""
    from sklearn.metrics import accuracy_score, f1_score
    rows = []
    for h in horizons:
        d = Pc[(Pc.h == h) & (Pc.model == name)].dropna(subset=["cls_true"]).set_index("date")
        w = common_wide(P, h, reg_models).reindex(d.index).dropna()
        d = d.loc[w.index]
        c = d["cls_true"].to_numpy().astype(int)
        sig = store.loc[d.index, f"sigma_h{h}"].to_numpy()
        prob = d[["p0", "p1", "p2"]].to_numpy()
        clim = d[["clim0", "clim1", "clim2"]].to_numpy()
        onehot = np.eye(3)[c]

        def ll(pr, c=c):
            return -np.log(np.clip(pr[np.arange(len(c)), c], 1e-12, 1))

        ll_m, ll_c = ll(prob), ll(clim)
        dm, dp = M.diebold_mariano(ll_m, ll_c, h, power=1)
        preds = {name: prob.argmax(1), "climatology (majority)": clim.argmax(1)}
        for m in reg_models:
            yh = w[m].to_numpy()
            preds[m] = np.where(yh > 0.5 * sig, 2, np.where(yh < -0.5 * sig, 0, 1))
        for m, pc in preds.items():
            r = {"h": h, "model": m, "n": len(c), "macro_F1": f1_score(c, pc, average="macro"),
                 "accuracy": accuracy_score(c, pc), "share_pred_fall/flat/rise": "/".join(
                     f"{np.mean(pc == k):.2f}" for k in range(3))}
            if m == name:
                r.update(logloss=ll_m.mean(), brier=np.mean(np.sum((prob - onehot) ** 2, 1)),
                         DM_logloss_vs_clim_stat=dm, DM_logloss_vs_clim_p=dp)
            if m.startswith("climatology"):
                r.update(logloss=ll_c.mean(), brier=np.mean(np.sum((clim - onehot) ** 2, 1)))
            rows.append(r)
        rows.append({"h": h, "model": "(actual class shares)", "n": len(c),
                     "share_pred_fall/flat/rise": "/".join(f"{np.mean(c == k):.2f}" for k in range(3))})
    return pd.DataFrame(rows)


def average_oos(P: pd.DataFrame, models, name: str, interval_model: str | None = None) -> pd.DataFrame:
    """Equal-weight average of OOS point forecasts (no fitted weights, so nothing to leak).
    interval_model: take q10/q50/q90/lo80/hi80 from that model, shifted by (average - its point forecast)."""
    d = P[P.model.isin(models)]
    w = d.pivot_table(index=["h", "date"], columns="model", values="yhat")[list(models)].dropna()
    meta = d[d.model == models[0]].set_index(["h", "date"])[["y_true", "train_end"]]
    out = w.mean(axis=1).rename("yhat").to_frame().join(meta)
    if interval_model:
        iv = P[P.model == interval_model].set_index(["h", "date"])
        shift = out["yhat"] - iv["yhat"].reindex(out.index)
        for c in ("q10", "q50", "q90", "lo80", "hi80"):
            out[c] = iv[c].reindex(out.index) + shift
    return out.reset_index().assign(model=name)


def combine_oos(P: pd.DataFrame, store: pd.DataFrame, h: int, a="ffa_implied", b="lgbm",
                name=None, min_rows=250) -> pd.DataFrame:
    """'FFA + ML' combination (docs/02 3.7) fitted OUT OF SAMPLE: for each test month, non-negative weights
    (no intercept) on past OOS forecasts whose targets were realised before the month starts.
    Equal weights until min_rows past rows exist."""
    w = P[(P.h == h) & P.model.isin([a, b])].pivot_table(index="date", columns="model", values="yhat").dropna()
    w["y"] = P[(P.h == h) & (P.model == a)].set_index("date")["y_true"].reindex(w.index)
    w["tdate"] = store[f"tdate_h{h}"].reindex(w.index)
    rows = []
    for _, blk in w.groupby(w.index.to_period("M")):
        past = w[w["tdate"] < blk.index[0]]
        if len(past) >= min_rows:
            wt, _ = nnls(past[[a, b]].to_numpy(), past["y"].to_numpy())
        else:
            wt = np.array([0.5, 0.5])
        rows.append(pd.DataFrame({"date": blk.index, "h": h, "y_true": blk["y"].to_numpy(),
                                  "yhat": blk[[a, b]].to_numpy() @ wt, "w_a": wt[0], "w_b": wt[1]}))
    out = pd.concat(rows, ignore_index=True)
    train_end = P[(P.h == h) & (P.model == b)].set_index("date")["train_end"]
    return out.assign(model=name or f"{a}+{b}", train_end=out["date"].map(train_end))


def encompassing(P: pd.DataFrame, h: int, a="ffa_implied", b="lgbm") -> pd.DataFrame:
    """Forecast-encompassing regression y = c + beta_a * yhat_a + beta_b * yhat_b, HAC(h) errors.
    beta_b significantly > 0 => model b carries information not in a."""
    w = P[(P.h == h) & P.model.isin([a, b])].pivot_table(index="date", columns="model", values="yhat").dropna()
    y = P[(P.h == h) & (P.model == a)].set_index("date")["y_true"].reindex(w.index)
    r = sm.OLS(y.to_numpy(), sm.add_constant(w[[a, b]].to_numpy())).fit(cov_type="HAC", cov_kwds={"maxlags": h})
    return pd.DataFrame({"h": h, "term": ["const", a, b], "coef": r.params, "se": r.bse, "p": r.pvalues,
                         "n": len(y)})


# ------------------------------------------------------------------ metrics
def highvol_flag(store: pd.DataFrame) -> pd.Series:
    """Top quintile of 20-day realised vol, threshold from an expanding past-only window."""
    rv = store["rv_20"]
    thr = rv.expanding(min_periods=250).quantile(0.8).shift(1)
    return rv > thr


def pinball(y, q, tau):
    d = y - q
    return float(np.mean(np.maximum(tau * d, (tau - 1) * d)))


def common_wide(P: pd.DataFrame, h: int, models) -> pd.DataFrame:
    w = P[(P.h == h) & P.model.isin(models)].pivot_table(index="date", columns="model", values="yhat")
    w = w[list(models)].dropna()
    w["y_true"] = P[(P.h == h)].drop_duplicates("date").set_index("date")["y_true"].reindex(w.index)
    return w


def metrics_table(P: pd.DataFrame, store: pd.DataFrame, models, bench="ffa_implied",
                  horizons=C.HORIZONS) -> pd.DataFrame:
    """One row per (h, model), all models on the SAME rows. DM stat > 0 => benchmark is better."""
    hv = highvol_flag(store)
    rows = []
    for h in horizons:
        w = common_wide(P, h, models)
        y = w["y_true"].to_numpy()
        sig = store.loc[w.index, f"sigma_h{h}"].to_numpy()
        cls = store.loc[w.index, f"cls_h{h}"].to_numpy()
        ok = ~np.isnan(sig)
        hvm = hv.reindex(w.index).fillna(False).to_numpy(dtype=bool)
        e_b = y - w[bench].to_numpy()
        for m in models:
            yh = w[m].to_numpy()
            e = y - yh
            dm, dp = M.diebold_mariano(e, e_b, h) if m != bench else (np.nan, np.nan)
            nz = yh != 0
            row = {"h": h, "model": m, "n": len(y), "MAE": np.mean(np.abs(e)), "RMSE": np.sqrt(np.mean(e ** 2)),
                   "TheilU_vs_RW": M.theil_u(y, yh),
                   "hit_rate": np.mean(np.sign(yh[nz]) == np.sign(y[nz])) if nz.any() else np.nan,
                   "F1_3class": M.direction_f1(cls[ok], yh[ok], sig[ok]), "PT_p": M.pesaran_timmermann(y, yh)[1],
                   f"DM_vs_{bench}_stat": dm, f"DM_vs_{bench}_p": dp,
                   "TheilU_calm": M.theil_u(y[~hvm], yh[~hvm]), "TheilU_highvol": M.theil_u(y[hvm], yh[hvm])}
            q = P[(P.h == h) & (P.model == m)].set_index("date").reindex(w.index)
            if {"q10", "q50", "q90"} <= set(q.columns) and q["q10"].notna().all():
                row["pinball"] = np.mean([pinball(y, q[f"q{t}"].to_numpy(), t / 100) for t in (10, 50, 90)])
                row["cover_q10_q90"] = np.mean((y >= q["q10"]) & (y <= q["q90"]))
            if {"lo80", "hi80"} <= set(q.columns) and q["lo80"].notna().all():
                row["coverage80"] = np.mean((y >= q["lo80"]) & (y <= q["hi80"]))
                row["width80"] = np.mean(q["hi80"] - q["lo80"])
            rows.append(row)
    return pd.DataFrame(rows)


def theil_by_year(P: pd.DataFrame, models, horizons=C.HORIZONS) -> pd.DataFrame:
    out = []
    for h in horizons:
        w = common_wide(P, h, models)
        for yr, blk in w.groupby(w.index.year):
            out.append({"h": h, "year": yr, "n": len(blk),
                        **{m: M.theil_u(blk["y_true"].to_numpy(), blk[m].to_numpy()) for m in models}})
    return pd.DataFrame(out)


def g3_check(T: pd.DataFrame, model="lgbm", bench="ffa_implied", level=0.05) -> pd.DataFrame:
    """G3: Theil's U < 1 at every h, and not significantly worse than FFA (DM, two-sided p)."""
    r = T[T.model == model][["h", "TheilU_vs_RW", f"DM_vs_{bench}_stat", f"DM_vs_{bench}_p"]].copy()
    r["U<1"] = r["TheilU_vs_RW"] < 1
    r["not_worse_than_ffa"] = ~((r[f"DM_vs_{bench}_stat"] > 0) & (r[f"DM_vs_{bench}_p"] < level))
    r["PASS"] = r["U<1"] & r["not_worse_than_ffa"]
    return r


# ------------------------------------------------------------------ logging / export
@functools.lru_cache(maxsize=1)
def git_commit() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO, capture_output=True,
                             text=True, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "src"], cwd=REPO, capture_output=True,
                               text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unknown"


def append_results(T: pd.DataFrame, P: pd.DataFrame, author: str, notes: str = "", part="ML",
                   target="ln(S_t+h/S_t) 5TC") -> pd.DataFrame:
    """Append one row per (h, model) of a metrics table to experiments/results.csv (never edits old rows)."""
    path = REPO / "experiments" / "results.csv"
    old = pd.read_csv(path)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = []
    for _, r in T.iterrows():
        d = P[(P.h == r.h) & (P.model == r.model)]["date"]
        rows.append({"run_id": f"{now}_{r.model}_h{r.h}", "date_utc": now, "git_commit": git_commit(),
                     "author": author, "part": part, "model": r.model, "target": target, "horizon": r.h,
                     "test_start": d.min().date(), "test_end": d.max().date(), "n_test": r.n,
                     "mae": r.MAE, "rmse": r.RMSE, "theil_u": r.TheilU_vs_RW, "hit_rate": r.hit_rate,
                     "pinball": r.get("pinball", np.nan), "coverage80": r.get("coverage80", np.nan),
                     "dm_p_vs_ffa": r.get("DM_vs_ffa_implied_p", np.nan), "notes": notes})
    new = pd.DataFrame(rows, columns=old.columns)
    new.to_csv(path, mode="a", header=False, index=False)
    return new


def oos_export(P: pd.DataFrame, model: str, model_version: str) -> pd.DataFrame:
    """Hand-over table for the text branch (decisions.md C7)."""
    d = P[P.model == model].copy()
    d["model_version"] = model_version
    cols = ["date", "h", "y_true", "yhat", "q10", "q50", "q90", "model_version", "train_end"]
    return d[cols].sort_values(["h", "date"]).reset_index(drop=True)
