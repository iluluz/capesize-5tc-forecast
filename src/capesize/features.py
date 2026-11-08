"""Feature store. build_feature_store() -> (X, A, sources)
X: features on the decision grid; A: availability timestamp actually used per feature;
sources: {feature: (values, avail)} on the reference-period axis (used by the G1 test)."""
import numpy as np
import pandas as pd

from capesize import config as C
from capesize import data as D
from capesize.pit import pit_attach

CNY = pd.to_datetime(["2013-02-10", "2014-01-31", "2015-02-19", "2016-02-08", "2017-01-28",
                      "2018-02-16", "2019-02-05", "2020-01-25", "2021-02-12", "2022-02-01",
                      "2023-01-22", "2024-02-10", "2025-01-29", "2026-02-17", "2027-02-06",
                      "2028-01-26"])


def get_grid():
    s = D.load_spot()
    g = s.loc[C.GRID_START:].dropna(subset=["S"])
    return g


def _ln(x):
    return np.log(x.where(x > 0))


# ---------------------------------------------------------------- daily, same-day (no lag)
def spot_features(g: pd.DataFrame) -> pd.DataFrame:
    full = D.load_spot().dropna(subset=["S"])        # use pre-2014 history for rolling windows
    S = full["S"]
    lr = _ln(S).diff()
    f = pd.DataFrame(index=full.index)
    for k in (5, 20, 60):
        f[f"mom_{k}"] = _ln(S) - _ln(S.shift(k))
    for w in (60, 250):
        f[f"dev_{w}"] = _ln(S) - _ln(S.rolling(w, min_periods=int(w * 0.8)).mean())
    f["rv_20"] = lr.rolling(20, min_periods=15).std() * np.sqrt(252)
    f["rv_60"] = lr.rolling(60, min_periods=45).std() * np.sqrt(252)
    f["c14_c10"] = _ln(full["C14"]) - _ln(full["C10"])
    f["c3_c5"] = full["C3"] / full["C5"]
    f["c16_neg"] = (full["C16"] < 0).astype(float).where(full["C16"].notna())
    return f.loc[g.index]


def month_period(s: pd.Series) -> pd.Series:
    """'2014-06' / Timestamp -> monthly Period (NaT where missing)."""
    return pd.to_datetime(s.astype("string"), errors="coerce").dt.to_period("M")


def ffa_curve(lag: int = 0) -> pd.DataFrame:
    """FFA curve on its own assessment calendar; lag=1 -> each date carries the previous assessment."""
    cc = D.load_ffa_curve()
    cc = cc[~cc.index.duplicated()]
    return cc.shift(lag) if lag else cc


def ffa_features(g: pd.DataFrame, lag: int = 0):
    cc = ffa_curve(lag)
    c = cc.reindex(g.index)                          # 2019-02-27 FFA missing -> NaN row
    S = g["S"]
    f = pd.DataFrame(index=g.index)
    f["ffa_basis_m1"] = _ln(c["M+1"]) - _ln(S)
    f["ffa_basis_m2"] = _ln(c["M+2"]) - _ln(S)
    f["ffa_slope"] = _ln(c["M+2"]) - _ln(c["M+1"])
    f["ffa_qstruct"] = _ln(c["Q+1"]) - _ln(c["M+1"])
    f["ffa_fwd_year"] = _ln(c["Cal+1"]) - _ln(S)
    # 5-day change of the *same* contract as today's M+1 (5 assessment days)
    mon = month_period(cc["m1_month"])
    prev_mon = mon.shift(5)
    same = mon == prev_mon
    nxt = mon == prev_mon + 1
    prev_val = pd.Series(np.nan, index=cc.index)
    prev_val[same] = _ln(cc["M+1"]).shift(5)[same]
    prev_val[nxt] = _ln(cc["M+2"]).shift(5)[nxt]
    f["ffa_m1_chg5"] = (_ln(cc["M+1"]) - prev_val).reindex(g.index)
    return f, c


def ffa_weekly_features(grid):
    w = D.load_ffa_weekly()
    # volume is a Fri-close number, OI is dated Monday; both treated as available the Monday after
    avail = pd.Series(w.index + pd.Timedelta(days=3), index=w.index)
    oi_chg = w["OI 4-week change"]
    vol_oi = w["Volume / OI"]
    out, av, src = {}, {}, {}
    for name, ser in (("ffa_oi_chg4w", oi_chg), ("ffa_vol_oi", vol_oi)):
        out[name], av[name] = pit_attach(grid, ser, avail)
        src[name] = (ser, avail)
    return pd.DataFrame(out), pd.DataFrame(av), src


# ---------------------------------------------------------------- weekly / monthly sources
def _weekly(df):
    idx = pd.date_range(df.index.min(), df.index.max(), freq="W-FRI")
    return df.reindex(idx)


def _yoy_log(x, win, lag):
    num = x.rolling(win, min_periods=win).sum()
    return _ln(num) - _ln(num.shift(lag))


def ironore_features(grid):
    raw, lags = D.load_ironore()
    W = _weekly(raw)
    inv, outf = W["Port iron ore inventory"], W["Port daily outflow"]
    hm, ship = W["Daily hot metal output (247 mills)"], W["Australia + Brazil iron ore shipments"]
    # inventory vs mean of same week in previous 5 years (52-week shifts), >=3 of 5 years
    past = pd.concat([inv.shift(52 * k) for k in range(1, 6)], axis=1)
    inv5 = past.mean(axis=1).where(past.notna().sum(axis=1) >= 3)
    feats = {
        "io_inv_vs_5y": (inv / inv5 - 1, lags["Port iron ore inventory"]),
        "io_hotmetal_yoy": (_ln(hm) - _ln(hm.shift(52)), lags["Daily hot metal output (247 mills)"]),
        "io_shipments_4w_yoy": (_yoy_log(ship, 4, 52), lags["Australia + Brazil iron ore shipments"]),
        "io_inv_cover_days": (inv / outf, max(lags["Port iron ore inventory"], lags["Port daily outflow"])),
    }
    return _attach_all(grid, feats, W.index)


def portwatch_features(grid):
    raw, lags = D.load_portwatch()
    W = _weekly(raw)
    br, au = W["BR iron ore ports exports"], W["AU iron ore ports exports"]
    cal = W["Port calls China"]
    cape, suez = W["Cape of Good Hope dry bulk transits"], W["Suez dry bulk transits"]
    au_br = au + br
    tot4 = au_br.rolling(4, min_periods=4).sum()
    feats = {
        "pw_aubr_exports_4w_yoy": (_yoy_log(au_br, 4, 52), lags["BR iron ore ports exports"]),
        "pw_brazil_share_4w": (br.rolling(4, min_periods=4).sum() / tot4,
                               lags["BR iron ore ports exports"]),
        "pw_china_calls_4w_yoy": (_yoy_log(cal, 4, 52), lags["Port calls China"]),
        "pw_cape_share_4w": (cape.rolling(4, min_periods=4).sum() /
                             (cape + suez).rolling(4, min_periods=4).sum(),
                             lags["Cape of Good Hope dry bulk transits"]),
    }
    X, A, S = _attach_all(grid, feats, W.index)
    # flag = any PortWatch value visible yet (plan 3.4); features are NaN before that
    X["portwatch_available"] = A["pw_brazil_share_4w"].notna().astype(float)
    return X, A, S


def fleet_features(grid):
    d, lag = D.load_fleet()
    d = d.loc["1996":]
    fl = d["fleet_dwt"]
    feats = {
        "fl_net_growth_12m": ((fl / fl.shift(12) - 1), lag),
        "fl_orderbook_fleet": (d["ob_dwt"] / fl, lag),
        # plan's "deliveries next 12m share" needs historical delivery schedules, which the
        # workbook does not have (single snapshot) -> trailing-12m deliveries / fleet instead.
        "fl_deliveries_12m_fleet": (d["deliv_dwt"].rolling(12, min_periods=12).sum() / fl, lag),
    }
    return _attach_all(grid, feats, d.index)


def customs_features(grid):
    d, lag, jan_extra, dist = D.load_customs()

    def iron(o):
        return d[f"Iron ore from {o}"]

    au, br, za, ca = iron("Australia"), iron("Brazil"), iron("South Africa"), iron("Canada")
    tot = d["Iron ore total"]

    def roll3(x):
        return x.rolling(3, min_periods=3).sum()

    dk = {k.split(":")[1].split("(")[0].strip(): v for k, v in dist.items() if k.startswith("Iron ore")}
    tm = au * dk["Australia"] + br * dk["Brazil"] + za * dk["South Africa"] + ca * dk["Canada"]
    guin, baux = d["Bauxite from Guinea"], d["Bauxite total"]
    feats = {
        "cu_ironore_3m_yoy": (_ln(roll3(tot)) - _ln(roll3(tot).shift(12)), None),
        "cu_brazil_share_3m": (roll3(br) / (roll3(au) + roll3(br)), None),
        "cu_guinea_share_3m": (roll3(guin) / roll3(baux), None),
        "cu_tonnemile_3m_yoy": (_ln(roll3(tm)) - _ln(roll3(tm).shift(12)), None),
    }
    avail = pd.Series(d.index + pd.Timedelta(days=lag), index=d.index)
    avail[d.index.month == 1] += pd.Timedelta(days=jan_extra)
    out, av, src = {}, {}, {}
    for k, (v, _) in feats.items():
        out[k], av[k] = pit_attach(grid, v, avail)
        src[k] = (v, avail)
    return pd.DataFrame(out), pd.DataFrame(av), src


def _attach_all(grid, feats, ref_index):
    out, av, src = {}, {}, {}
    for k, (v, lag) in feats.items():
        avail = pd.Series(v.index + pd.Timedelta(days=int(lag)), index=v.index)
        out[k], av[k] = pit_attach(grid, v, avail)
        src[k] = (v, avail)
    return pd.DataFrame(out), pd.DataFrame(av), src


def calendar_features(grid):
    f = pd.DataFrame(index=grid)
    doy = grid.day_of_year.values
    for k in (1, 2):
        f[f"cal_sin{k}"] = np.sin(2 * np.pi * k * doy / 365.25)
        f[f"cal_cos{k}"] = np.cos(2 * np.pi * k * doy / 365.25)
    nxt = CNY.searchsorted(grid, side="left")
    f["cal_days_to_cny"] = (CNY[nxt] - grid).days.values
    me = grid + pd.offsets.MonthEnd(0)
    qe = grid + pd.offsets.QuarterEnd(0)
    f["cal_month_end"] = ((me - grid).days <= 2).astype(float)
    f["cal_quarter_end"] = ((qe - grid).days <= 2).astype(float)
    return f


def build_feature_store(ffa_lag: int | None = None):
    """Returns (g, X, A, sources, curve_on_grid). ffa_lag defaults to config.FFA_LAG."""
    ffa_lag = C.FFA_LAG if ffa_lag is None else ffa_lag
    g = get_grid()
    grid = g.index
    parts, avs, srcs = [], [], {}
    parts.append(spot_features(g))
    f, curve = ffa_features(g, ffa_lag)
    parts.append(f)
    for fn in (ffa_weekly_features, ironore_features, portwatch_features, fleet_features,
               customs_features):
        X, A, S = fn(grid)
        parts.append(X)
        avs.append(A)
        srcs.update(S)
    parts.append(calendar_features(grid))
    X = pd.concat(parts, axis=1)
    A = pd.concat(avs, axis=1)
    return g, X, A, srcs, curve
