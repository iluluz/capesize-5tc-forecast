import numpy as np
import pandas as pd
import pytest

from capesize.splits import walk_forward_splits
from capesize.targets import log_return_target, make_targets


def test_log_return_target():
    s = pd.Series([100.0, 110.0, 121.0, 133.1], index=pd.bdate_range("2026-01-05", periods=4))
    y = log_return_target(s, 2)
    assert y.iloc[0] == pytest.approx(np.log(1.21))
    assert y.iloc[-2:].isna().all()
    assert list(make_targets(s, (1, 2)).columns) == ["y_h1", "y_h2"]


def test_log_return_rejects_non_positive():
    with pytest.raises(ValueError):
        log_return_target(pd.Series([1.0, 0.0]), 1)


@pytest.mark.parametrize("h", [5, 20])
def test_walk_forward_purge_and_order(h):
    d = pd.bdate_range("2018-01-01", "2020-12-31")
    folds = list(walk_forward_splits(d, "2019-01-01", h=h))
    assert folds, "expected at least one fold"
    covered = np.concatenate([te for _, te in folds])
    assert d[covered[0]] >= pd.Timestamp("2019-01-01")
    assert len(np.unique(covered)) == len(covered)            # test blocks do not overlap
    for tr, te in folds:
        assert tr.max() + h < te.min()                         # no training target reaches the test block
        assert d[te].to_period("M").nunique() == 1             # one block per month
