"""Walk-forward runner: expanding window, monthly refit, purge h + embargo h (docs/02 3.6).

Fold boundaries come from splits.walk_forward_splits (shared, unit-tested). Rows whose target is not yet
realised are dropped from both train and test of each fold.
"""
import numpy as np
import pandas as pd

from capesize import config as C
from capesize.splits import walk_forward_splits


def folds(store: pd.DataFrame, h: int, test_start=C.TEST_START, test_end=None):
    """Yield (train_rows, test_rows, train_end_row) with NaN targets removed; test blocks starting on or
    after test_end are not generated (the 2016-2018 extra test)."""
    y = store[f"y_h{h}"].to_numpy()
    stop = None if test_end is None else store.index.searchsorted(pd.Timestamp(test_end))
    for tr, te in walk_forward_splits(store.index, test_start, h, refit="M", min_train=C.MIN_TRAIN,
                                      embargo=C.EMBARGO_MULT * h):
        if stop is not None and te[0] >= stop:
            break
        tr_end = tr[-1]
        tr = tr[~np.isnan(y[tr])]
        te = te[~np.isnan(y[te])]
        if len(te) and len(tr) >= C.MIN_TRAIN:
            yield tr, te, tr_end


def walk_forward(store: pd.DataFrame, h: int, fit_predict, model_name: str,
                 test_start=C.TEST_START, test_end=None) -> pd.DataFrame:
    """fit_predict(train_rows, test_rows) -> array (yhat) or dict/DataFrame of columns incl. 'yhat'.

    Returns long OOS predictions: date, h, y_true, yhat[, extra columns], model, train_end.
    """
    y = store[f"y_h{h}"].to_numpy()
    out = []
    for tr, te, tr_end in folds(store, h, test_start, test_end):
        res = fit_predict(tr, te)
        cols = pd.DataFrame(res) if isinstance(res, (dict, pd.DataFrame)) else pd.DataFrame({"yhat": res})
        cols = cols.reset_index(drop=True)
        base = pd.DataFrame({"date": store.index[te], "h": h, "y_true": y[te]})
        out.append(pd.concat([base, cols], axis=1).assign(model=model_name, train_end=store.index[tr_end]))
    return pd.concat(out, ignore_index=True)
