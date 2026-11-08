"""Gate G1 checks (docs/02 3.1, 3.8): point-in-time join, targets, grid. Used by tests/ and the notebook."""
import numpy as np
import pandas as pd

from capesize import config as C
from capesize.pit import brute_force_pit, pit_attach


def g1_checks(g, X, A, srcs, Y, horizons, seed=0, n_dates=20) -> dict:
    """Raise AssertionError on the first failure; return {check: 'PASS'}."""
    res = {}
    # 1) every availability timestamp used is strictly before the decision date
    for col in A.columns:
        used = A[col].dropna()
        bad = int((used >= used.index.to_series()).sum())
        assert bad == 0, f"{col}: {bad} rows use data available on/after the decision date"
    res["avail strictly before decision date (all rows, all lagged features)"] = "PASS"

    # 2) random dates: store == independent brute-force PIT lookup (value AND availability date)
    rng = np.random.default_rng(seed)
    pick = rng.choice(g.index[g.index > "2016-01-01"], n_dates, replace=False)
    n = 0
    for d in map(pd.Timestamp, pick):
        for name, (vals, av) in srcs.items():
            v_bf, a_bf = brute_force_pit(d, vals, av)
            v_fs, a_fs = X.at[d, name], A.at[d, name]
            if pd.isna(v_bf):
                assert pd.isna(v_fs), f"{name}@{d.date()}: store has a value, brute force has none"
            else:
                assert np.isclose(v_bf, v_fs), f"{name}@{d.date()}: {v_bf} != {v_fs}"
                assert a_bf == a_fs and a_fs < d, f"{name}@{d.date()}: availability mismatch"
            n += 1
    res[f"{n_dates} random dates vs brute force ({n} feature-date checks)"] = "PASS"

    # 3) targets: NaN only in the last h rows; realisation date after t
    for h in horizons:
        y = Y[f"y_h{h}"]
        assert y.iloc[:-h].notna().all(), f"y_h{h} has NaN inside the sample"
        assert y.iloc[-h:].isna().all()
        assert (Y[f"tdate_h{h}"].iloc[:-h] > Y.index[:-h]).all()
    res["targets: no NaN inside sample, realisation date > t"] = "PASS"

    # 4) grid = Baltic days with a published 5TC from GRID_START
    assert g.index.is_unique and g.index.is_monotonic_increasing
    assert g["S"].notna().all() and g["S"].gt(0).all()
    gaps = g.index.to_series().diff().dt.days.dropna()
    assert gaps.max() <= 11, f"gap of {gaps.max()} days in grid"
    assert g.index[0] == pd.Timestamp(C.GRID_START)
    res[f"grid: {len(g)} Baltic days {g.index[0].date()} -> {g.index[-1].date()}, max gap {int(gaps.max())}d"] = "PASS"
    return res


def leak_control(g, srcs, feature="cu_ironore_3m_yoy") -> int:
    """Negative control: joining on the REFERENCE period (the mistake the plan forbids) must use
    not-yet-released data on many days. Returns the number of leaking decision dates."""
    vals, av = srcs[feature]
    leaky = pd.Series(vals.index, index=vals.index)          # pretend available at reference period end
    _, used = pit_attach(g.index, vals, leaky)
    true_av = pd.to_datetime(av).cummax()
    used = used.dropna()
    return int(sum(true_av.loc[r] >= d for d, r in used.items()))
