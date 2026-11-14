"""Truncation test for the daily v2 features (no publication lag to check, so test causality directly):
recompute the features with all raw data after date d removed; the value on d must not change."""
import numpy as np
import pandas as pd
import pytest

from capesize import io as cio

pytestmark = pytest.mark.skipif(not cio.data_dir().exists(), reason="workbooks not available")


def _trunc(monkeypatch, D, d):
    full_spot, full_curve = D.load_spot(), D.load_ffa_curve()
    full_read = D.read

    monkeypatch.setattr(D, "load_spot", lambda: full_spot.loc[:d])
    monkeypatch.setattr(D, "load_ffa_curve", lambda: full_curve.loc[:d])

    def read(n, sheet, **kw):
        x = full_read(n, sheet, **kw)
        if sheet == "FFA Volume Daily":
            x = x[pd.to_datetime(x["Date"]) <= d]
        return x
    monkeypatch.setattr(D, "read", read)


@pytest.mark.parametrize("d", ["2016-03-15", "2019-07-02", "2022-11-21", "2026-04-08"])
def test_daily_v2_features_are_causal(monkeypatch, d):
    from capesize import baselines as B
    from capesize import config as C
    from capesize import data as D
    from capesize import features as F
    from capesize import features_v2 as F2
    from capesize.targets import build_targets

    d = pd.Timestamp(d)

    def compute():
        g = F.get_grid()
        fx, _, _ = F2.ffa_extra_features(g, C.FFA_LAG)
        st = pd.concat([build_targets(g["S"], C.HORIZONS)], axis=1)
        _, curve = F.ffa_features(g, C.FFA_LAG)
        for h in C.HORIZONS:
            st[f"ffa_hat_h{h}"] = B.ffa_implied(curve, g["S"], h)
        return pd.concat([fx, F2.route_features(g), F2.path_features(g), F2.ffa_bias_features(st)], axis=1)

    full = compute().loc[d]
    with monkeypatch.context() as m:
        _trunc(m, D, d)
        cut = compute().loc[d]
    both = full.notna() & cut.notna()
    assert (full.notna() == cut.notna()).all(), list(full.index[full.notna() != cut.notna()])
    assert np.allclose(full[both].astype(float), cut[both].astype(float)), \
        list(full.index[both][~np.isclose(full[both].astype(float), cut[both].astype(float))])
