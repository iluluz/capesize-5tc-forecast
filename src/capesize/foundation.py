"""M9: time-series foundation models, zero-shot (plan v2, layer 3): Chronos-Bolt and Chronos-2.

No training on our data, so there is nothing to leak through fitting: on each decision date t the model sees only
the 5TC history up to t (context) and forecasts the next h trading days. Chronos-2 can also take past covariates;
the 'cov' variant feeds the lagged FFA-implied forecasts and FFA basis (known at t) as past-only covariates.
Outputs y-scale quantiles: yhat = ln(q50_{t+h} / S_t), q10/q90 likewise.
"""
import numpy as np
import pandas as pd

CONTEXT = 1024


def _dates(store, test_start, every=1):
    idx = store.index[store.index >= pd.Timestamp(test_start)]
    return idx[::every]


def chronos_bolt(store: pd.DataFrame, horizons, model_id="amazon/chronos-bolt-base", test_start="2019-01-01",
                 batch=64, name="chronos_bolt") -> pd.DataFrame:
    import torch
    from chronos import BaseChronosPipeline
    pipe = BaseChronosPipeline.from_pretrained(model_id, device_map="cpu", torch_dtype=torch.float32)
    lnS = np.log(store["S"].astype(float))
    pos = {d: i for i, d in enumerate(store.index)}
    dates = _dates(store, test_start)
    H = max(horizons)
    rows = []
    for b in range(0, len(dates), batch):
        ds = dates[b: b + batch]
        ctx = [torch.tensor(lnS.to_numpy()[max(0, pos[d] + 1 - CONTEXT): pos[d] + 1], dtype=torch.float32) for d in ds]
        q, _ = pipe.predict_quantiles(ctx, prediction_length=H, quantile_levels=[0.1, 0.5, 0.9])
        q = q.numpy()                                       # (batch, H, 3) on the ln S scale
        for j, d in enumerate(ds):
            last = lnS.iloc[pos[d]]
            for h in horizons:
                rows.append({"date": d, "h": h, "q10": q[j, h - 1, 0] - last, "q50": q[j, h - 1, 1] - last,
                             "q90": q[j, h - 1, 2] - last})
    out = pd.DataFrame(rows)
    out["yhat"] = out["q50"]
    return _finish(out, store, name)


def chronos2(store: pd.DataFrame, horizons, covariates=(), model_id="amazon/chronos-2", test_start="2019-01-01",
             batch=32, name="chronos2") -> pd.DataFrame:
    from chronos import Chronos2Pipeline
    pipe = Chronos2Pipeline.from_pretrained(model_id, device_map="cpu")
    lnS = np.log(store["S"].astype(float)).to_numpy()
    cov = {c: store[c].ffill().fillna(0).to_numpy(dtype=float) for c in covariates}
    pos = {d: i for i, d in enumerate(store.index)}
    dates = _dates(store, test_start)
    H = max(horizons)
    rows = []
    for b in range(0, len(dates), batch):
        ds = dates[b: b + batch]
        inputs = []
        for d in ds:
            lo, hi = max(0, pos[d] + 1 - CONTEXT), pos[d] + 1
            item = {"target": lnS[lo:hi]}
            if cov:
                item["past_covariates"] = {c: v[lo:hi] for c, v in cov.items()}
            inputs.append(item)
        qs, _ = pipe.predict_quantiles(inputs, prediction_length=H, quantile_levels=[0.1, 0.5, 0.9])
        for j, d in enumerate(ds):
            q = np.asarray(qs[j]).reshape(-1, H, 3)[0]       # (H, 3) for the single target
            last = lnS[pos[d]]
            for h in horizons:
                rows.append({"date": d, "h": h, "q10": q[h - 1, 0] - last, "q50": q[h - 1, 1] - last,
                             "q90": q[h - 1, 2] - last})
    out = pd.DataFrame(rows)
    out["yhat"] = out["q50"]
    return _finish(out, store, name)


def _finish(out, store, name):
    out["y_true"] = [store.at[d, f"y_h{h}"] for d, h in zip(out.date, out.h, strict=True)]
    out = out.dropna(subset=["y_true"])
    out["train_end"] = out["date"]                      # zero-shot: no training window
    return out.assign(model=name)
