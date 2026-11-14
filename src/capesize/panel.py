"""M1/M2: route-level panel LightGBM (plan v2 2.3 / layer 2), aggregated bottom-up to 5TC.

Rows = (date, route). Timecharter routes C8, C9, C10, C14, C16 carry the target in 5TC units,
z_r = (C_{r,t+h} - C_{r,t}) / S_t, so that sum_r w_r z_r = (S_{t+h} - S_t) / S_t exactly (BCI182 weights; the
workbook's spliced 5TC equals the weighted route composite). C16 can be negative, which this form handles.
C3 / C5 voyage routes (auxiliary tasks) use log changes. The 5TC forecast is ln(1 + sum_r w_r z_hat_r).

Residual mode: each route's base is what the 5TC FFA-implied move implies for that route
(TC: C_r/S * (exp(ffa_hat) - 1); voyage: ffa_hat), so the aggregated base equals the 5TC FFA-implied forecast.
"""
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

from capesize import config as C
from capesize import data as D
from capesize import models as ML
from capesize import validation as V

W182 = {"C8": 0.15, "C9": 0.125, "C10": 0.35, "C14": 0.25, "C16": 0.125}
AUX = ("C3", "C5")


def _ln(x):
    return np.log(x.where(x > 0))


def build_panel(store: pd.DataFrame, h: int, common_feats, routes=tuple(W182) + AUX, include_5tc=False):
    full = D.load_spot()
    S = store["S"]
    rows = []
    for k, r in enumerate(routes + (("5TC",) if include_5tc else ())):
        c = (S if r == "5TC" else full[r]).reindex(store.index).astype(float)
        cf = full["S" if r == "5TC" else r].dropna().astype(float)
        own = pd.DataFrame(index=cf.index)
        lc = _ln(cf) if r != "C16" else None
        if lc is not None:
            for m in (5, 20, 60):
                own[f"own_mom{m}"] = lc - lc.shift(m)
            own["own_dev60"] = lc - _ln(cf.rolling(60, min_periods=48).mean())
            own["own_rv20"] = lc.diff().rolling(20, min_periods=15).std()
        else:                                            # C16: changes in 5TC units
            sf = full["S"].reindex(cf.index)
            for m in (5, 20, 60):
                own[f"own_mom{m}"] = (cf - cf.shift(m)) / sf
            own["own_dev60"] = (cf - cf.rolling(60, min_periods=48).mean()) / sf
            own["own_rv20"] = (cf.diff() / sf).rolling(20, min_periods=15).std()
        own = own.reindex(store.index)
        own["own_rel"] = c / S if r in W182 or r == "5TC" else _ln(c) - _ln(S)
        own["route_id"] = float(k)
        fut = c.shift(-h)
        if r in W182 or r == "5TC":
            z = (fut - c) / S
            base = (c / S) * (np.exp(store[f"ffa_hat_h{h}"]) - 1)
        else:
            z = _ln(fut) - _ln(c)
            base = store[f"ffa_hat_h{h}"]
        d = pd.concat([store[list(common_feats)], own], axis=1)
        d["z"], d["base"], d["route"], d["date"] = z.to_numpy(), base.to_numpy(), r, store.index
        rows.append(d.reset_index(drop=True))
    p = pd.concat(rows, ignore_index=True).sort_values(["date", "route_id"], kind="stable").reset_index(drop=True)
    return p


def _fold(panel, feats, tr_dates, te_dates, h, residual, rpd, kw):
    tr = panel[panel.date.isin(tr_dates) & panel.z.notna()]
    if residual:
        tr = tr[tr.base.notna()]
    te = panel[panel.date.isin(te_dates)]
    b_tr = tr.base.to_numpy() if residual else None
    b_te = np.nan_to_num(te.base.to_numpy()) if residual else None
    out = ML.lgbm_fold(tr[feats], tr.z.to_numpy(), te[feats], h, base_tr=b_tr, base_te=b_te, quantiles=(),
                       conformal=False, rpd=rpd, **kw)
    return te[["date", "route"]].assign(zhat=out["yhat"], n_iter=out["n_iter"][0])


def run_panel(store: pd.DataFrame, h: int, common_feats, name="panel", residual=False, routes=tuple(W182) + AUX,
              n_jobs=-1, test_start=C.TEST_START, return_routes=False, **kw):
    panel = build_panel(store, h, common_feats, routes)
    feats = list(common_feats) + [c for c in panel.columns if c.startswith("own_")] + ["route_id"]
    folds = list(V.folds(store, h, test_start))
    rpd = len(routes)
    res = Parallel(n_jobs=n_jobs)(delayed(_fold)(panel, feats, store.index[tr], store.index[te], h, residual, rpd, kw)
                                  for tr, te, _ in folds)
    out = []
    for (_, te, tr_end), r in zip(folds, res, strict=True):
        wz = r[r.route.isin(list(W182))].pivot(index="date", columns="route", values="zhat")[list(W182)]
        agg = np.log1p((wz * pd.Series(W182)).sum(axis=1).clip(lower=-0.95))
        out.append(pd.DataFrame({"date": store.index[te], "h": h, "y_true": store[f"y_h{h}"].to_numpy()[te],
                                 "yhat": agg.reindex(store.index[te]).to_numpy(),
                                 "n_iter": r.n_iter.iloc[0]}).assign(model=name, train_end=store.index[tr_end]))
    P = pd.concat(out, ignore_index=True)
    return (P, pd.concat(res, ignore_index=True)) if return_routes else P
