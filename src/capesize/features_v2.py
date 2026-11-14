"""Feature store v2 (ml-v1.1 candidates): v1 features + the extra groups F1-F7 of the v1.1 plan.

All extra features are past-only on the trading-day grid:
* same-day spot/route values (published with 5TC at the decision time),
* FFA values lagged like v1 (config.FFA_LAG),
* weekly/monthly sources attached on their estimated available date (pit_attach),
* statistics over history use expanding/rolling windows that end at t (or at t - h for realised targets).

Groups (prefix -> group in models.FEATURE_GROUPS):
  fb_   FFA bias tracking (F1)          ffa_  extra curve shape / momentum / volume (F2)
  rt_   route structure (F3)            pth_  path / turning-point (F4)
  ut_   utilisation proxy (F5)          io_ pw_ cu_ fl_  unused series (F6)
  rg_   Markov regime probabilities (F7, see regime.py)   mc_  macro / FX from FRED (see macro.py)
"""
import numpy as np
import pandas as pd

from capesize import config as C
from capesize import data as D
from capesize import features as F
from capesize.pit import pit_attach

_ln = F._ln


# ---------------------------------------------------------------- F1: FFA bias tracking
def ffa_bias_features(store: pd.DataFrame, horizons=C.HORIZONS) -> pd.DataFrame:
    """Realised FFA-implied errors e_i = y_{i,h} - ffa_hat_{i,h}, used only once realised (i <= t - h):
    rolling means (20/60/250 rows), and the mean past error of the same calendar month."""
    f = pd.DataFrame(index=store.index)
    for h in horizons:
        e = store[f"y_h{h}"] - store[f"ffa_hat_h{h}"]
        known = e.shift(h)                               # realised at i + h <= t
        for w in (20, 60, 250):
            f[f"fb_err{w}_h{h}"] = known.rolling(w, min_periods=int(w * 0.6)).mean()
        # same-calendar-month bias: expanding mean of realised errors whose decision month = this month
        m = store.index.month
        same = known.groupby(m).transform(lambda s: s.expanding(min_periods=40).mean())
        f[f"fb_season_h{h}"] = same
        f[f"fb_absrmse60_h{h}"] = np.sqrt((known ** 2).rolling(60, min_periods=36).mean())
    return f


# ---------------------------------------------------------------- F2: curve shape, momentum, volume
def _same_contract_change(cc: pd.DataFrame, k: int) -> pd.Series:
    mon = F.month_period(cc["m1_month"])
    prev_mon = mon.shift(k)
    prev_val = pd.Series(np.nan, index=cc.index)
    same, nxt = mon == prev_mon, mon == prev_mon + 1
    prev_val[same] = _ln(cc["M+1"]).shift(k)[same]
    prev_val[nxt] = _ln(cc["M+2"]).shift(k)[nxt]
    return _ln(cc["M+1"]) - prev_val


def ffa_extra_features(g: pd.DataFrame, lag: int) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    cc = F.ffa_curve(lag)
    c = cc.reindex(g.index)
    S = g["S"]
    f = pd.DataFrame(index=g.index)
    m1, m2, m3 = _ln(c["M+1"]), _ln(c["M+2"]), _ln(c["M+3"])
    f["ffa_level3"] = (m1 + m2 + m3) / 3 - _ln(S)                 # fixed-form "PCA": level / slope / curvature
    f["ffa_slope31"] = m3 - m1
    f["ffa_curv"] = m1 + m3 - 2 * m2
    f["ffa_longend"] = _ln(c["Cal+2"]) - _ln(c["Cal+1"])
    f["ffa_m1_chg20"] = _same_contract_change(cc, 20).reindex(g.index)
    # seasonally adjusted basis: basis minus the past mean basis of the same calendar month (expanding, to t-1)
    b = f["ffa_level3"]
    past_same = b.groupby(g.index.month).transform(lambda s: s.shift(1).expanding(min_periods=40).mean())
    f["ffa_basis_sa"] = b - past_same
    f["ffa_basis_z250"] = (b - b.rolling(250, min_periods=150).mean().shift(1)) / \
        b.rolling(250, min_periods=150).std().shift(1)
    # daily FFA volume (published with the curve -> same lag), z-score vs past 60 days
    v = D.read(1, "FFA Volume Daily", parse_dates=["Date"]).set_index("Date").iloc[:, 0]
    v = v[~v.index.duplicated()].astype(float)
    lv = np.log1p(v.where(v >= 0))
    z = (lv - lv.rolling(60, min_periods=40).mean().shift(1)) / lv.rolling(60, min_periods=40).std().shift(1)
    z = z.shift(lag) if lag else z
    f["ffa_volume_z60"] = z.reindex(g.index)
    return f, pd.DataFrame(index=g.index), {}


# ---------------------------------------------------------------- F3: route structure
def route_features(g: pd.DataFrame) -> pd.DataFrame:
    full = D.load_spot().dropna(subset=["S"])
    S = full["S"]
    f = pd.DataFrame(index=full.index)
    f["rt_atl_pac"] = _ln((full["C8"] + full["C9"]) / 2) - _ln(full["C10"])
    f["rt_front_back"] = (full["C9"] - full["C16"]) / S                 # C16 can be negative
    f["rt_c16_rel"] = full["C16"] / S
    moms = pd.concat({r: _ln(full[r]) - _ln(full[r].shift(20)) for r in ("C8", "C9", "C10", "C14")}, axis=1)
    f["rt_mom_disp20"] = moms.std(axis=1)
    f["rt_atl_mom20"] = moms[["C8", "C9"]].mean(axis=1) - moms["C10"]
    f["rt_c14_rel_mom20"] = moms["C14"] - (_ln(S) - _ln(S.shift(20)))
    for r in ("C3", "C5"):
        f[f"rt_{r.lower()}_mom5"] = _ln(full[r]) - _ln(full[r].shift(5))
        f[f"rt_{r.lower()}_rel_mom20"] = (_ln(full[r]) - _ln(full[r].shift(20))) - (_ln(S) - _ln(S.shift(20)))
    return f.loc[g.index]


# ---------------------------------------------------------------- F4: path / turning point
def path_features(g: pd.DataFrame) -> pd.DataFrame:
    full = D.load_spot().dropna(subset=["S"])
    ls = _ln(full["S"])
    r = ls.diff()
    f = pd.DataFrame(index=full.index)
    f["pth_dd60"] = ls - ls.rolling(60, min_periods=40).max()
    f["pth_up60"] = ls - ls.rolling(60, min_periods=40).min()
    f["pth_hi250"] = ls - ls.rolling(250, min_periods=200).max()
    f["pth_lo250"] = ls - ls.rolling(250, min_periods=200).min()
    f["pth_days_since_max60"] = ls.rolling(60, min_periods=40).apply(lambda a: len(a) - 1 - np.argmax(a), raw=True) / 60
    f["pth_skew60"] = r.rolling(60, min_periods=40).skew()
    rv20 = r.rolling(20, min_periods=15).std()
    f["pth_volvol60"] = rv20.rolling(60, min_periods=40).std() / rv20.rolling(60, min_periods=40).mean()
    f["pth_rv_ratio"] = rv20 / r.rolling(60, min_periods=45).std()
    up = r.clip(lower=0).rolling(60, min_periods=40).std()
    dn = r.clip(upper=0).rolling(60, min_periods=40).std()
    f["pth_updown60"] = _ln(up) - _ln(dn)
    f["pth_accel"] = (ls - ls.shift(5)) - (ls.shift(5) - ls.shift(10))
    return f.loc[g.index]


# ---------------------------------------------------------------- F5: utilisation proxy + divergence
def utilisation_features(grid, basis: pd.Series):
    """U proxy = China seaborne tonne-miles (customs: iron ore + bauxite, 3-month sum) / fleet dwt, monthly.
    Available on the later of the two release dates. Divergence = basis minus an expanding past-only OLS
    fit basis ~ a + b * U (fitted on days < t)."""
    d, lag_c, jan_extra, dist = D.load_customs()
    fl, lag_f = D.load_fleet()
    # tonne-miles = sum over origins of volume x distance (the workbook's proxy columns are empty formulas)
    tm = 0
    for key, nm in dist.items():
        comm, origin = key.split(":")[0].strip(), key.split(":")[1].split("(")[0].strip()
        tm = tm + d[f"{comm} from {origin}"].fillna(0) * nm
    tm = tm.where(d["Iron ore total"].notna())
    tm3 = tm.rolling(3, min_periods=3).sum()
    fleet = fl["fleet_dwt"].reindex(tm3.index, method="nearest", tolerance=pd.Timedelta(days=5))
    U = _ln(tm3) - _ln(fleet)
    U = U - U.rolling(36, min_periods=24).mean()                       # vs 3-year past mean
    av_c = pd.Series(d.index + pd.Timedelta(days=lag_c), index=d.index)
    av_c[d.index.month == 1] += pd.Timedelta(days=jan_extra)
    av = np.maximum(av_c, pd.Series(d.index + pd.Timedelta(days=lag_f), index=d.index))
    feats = {"ut_level": U, "ut_chg3m": U - U.shift(3)}
    out, avs, src = {}, {}, {}
    for k, v in feats.items():
        out[k], avs[k] = pit_attach(grid, v, av)
        src[k] = (v, av)
    X = pd.DataFrame(out)
    # divergence: expanding OLS of basis on U using rows < t (cumulative sums, then shift 1)
    u, b = X["ut_level"], basis.reindex(grid)
    ok = u.notna() & b.notna()
    n = ok.cumsum()
    su, sb = u.where(ok, 0).cumsum(), b.where(ok, 0).cumsum()
    suu, sub = (u * u).where(ok, 0).cumsum(), (u * b).where(ok, 0).cumsum()
    beta = (sub - su * sb / n) / (suu - su * su / n)
    alpha = sb / n - beta * su / n
    beta, alpha = beta.shift(1).where(n.shift(1) >= 250), alpha.shift(1).where(n.shift(1) >= 250)
    X["ut_divergence"] = b - (alpha + beta * u)
    return X, pd.DataFrame(avs), src


# ---------------------------------------------------------------- F6: unused series
def extra_weekly_features(grid):
    io_raw, io_lags = D.load_ironore()
    W = F._weekly(io_raw)
    pw_raw, pw_lags = D.load_portwatch()
    P = F._weekly(pw_raw)

    def yoy4(x):
        return F._yoy_log(x, 4, 52)

    def lagof(lags, col):
        return lags.get(col, max(lags.values()))

    feats = {
        "io_outflow_4w_yoy": (yoy4(W["Port daily outflow"]), lagof(io_lags, "Port daily outflow")),
        "io_mill_inv_yoy": (_ln(W["Mill imported ore inventory"]) - _ln(W["Mill imported ore inventory"].shift(52)),
                            lagof(io_lags, "Mill imported ore inventory")),
        "io_bf_rate_dev52": (W["Blast furnace operating rate (247 mills)"]
                             - W["Blast furnace operating rate (247 mills)"].rolling(52, min_periods=40).mean(),
                             lagof(io_lags, "Blast furnace operating rate (247 mills)")),
        "pw_cape_transits_4w_yoy": (yoy4(P["Cape of Good Hope dry bulk transits"]),
                                    lagof(pw_lags, "Cape of Good Hope dry bulk transits")),
        "pw_suez_transits_4w_yoy": (yoy4(P["Suez dry bulk transits"]), lagof(pw_lags, "Suez dry bulk transits")),
        "pw_calls_aubr_4w_yoy": (yoy4(P["Port calls BR iron ore"] + P["Port calls AU iron ore"]),
                                 lagof(pw_lags, "Port calls BR iron ore")),
        "pw_china_imports_4w_yoy": (yoy4(P["China main ports imports"]), lagof(pw_lags, "China main ports imports")),
        "pw_coal_au_4w_yoy": (yoy4(P["AU coal ports exports"]), lagof(pw_lags, "AU coal ports exports")),
        "pw_bauxite_4w_yoy": (yoy4(P["AU bauxite ports exports (Weipa)"] + P["BR bauxite ports exports (Trombetas)"]),
                              lagof(pw_lags, "AU bauxite ports exports (Weipa)")),
    }
    X, A, S = F._attach_all(grid, feats, W.index)
    return X, A, S


def extra_monthly_features(grid):
    d, lag, jan_extra, _ = D.load_customs()
    val = D.read(6, "Monthly Value", parse_dates=["Month end"]).set_index("Month end")
    val.columns = D._clean(val.columns)

    def roll3(x):
        return x.rolling(3, min_periods=3).sum()

    uv = roll3(val["Iron ore total"].reindex(d.index)) / roll3(d["Iron ore total"])   # USD per 10k t -> price proxy
    coal = d["Coal (2701+2702) total"]
    feats = {
        "cu_ore_unitvalue_3m_yoy": _ln(uv) - _ln(uv.shift(12)),
        "cu_ore_unitvalue_3m_chg": _ln(uv) - _ln(uv.shift(3)),
        "cu_coal_3m_yoy": _ln(roll3(coal)) - _ln(roll3(coal).shift(12)),
    }
    avail = pd.Series(d.index + pd.Timedelta(days=lag), index=d.index)
    avail[d.index.month == 1] += pd.Timedelta(days=jan_extra)
    out, avs, src = {}, {}, {}
    for k, v in feats.items():
        out[k], avs[k] = pit_attach(grid, v, avail)
        src[k] = (v, avail)
    # fleet: average age and 12m demolition rate (same release lag as v1 fleet features)
    m = D.read(4, "Monthly Data", parse_dates=["Month (end)"]).set_index("Month (end)")
    m.columns = [str(c).replace("\n", " ") for c in m.columns]
    _, lag_f = D.load_fleet()
    av_f = pd.Series(m.index + pd.Timedelta(days=lag_f), index=m.index)
    demol = m["Demolition m dwt"].rolling(12, min_periods=12).sum() / m["Fleet m dwt"]
    for k, v in {"fl_avg_age": m["Average age years"], "fl_demol_rate_12m": demol}.items():
        out[k], avs[k] = pit_attach(grid, v.astype(float), av_f)
        src[k] = (v.astype(float), av_f)
    return pd.DataFrame(out), pd.DataFrame(avs), src


# ---------------------------------------------------------------- assembly
def build_feature_store_v2(ffa_lag: int | None = None, regime=True, macro=True):
    """Returns (g, X, A, sources, curve). X = v1 features + extras (F2-F7). F1 (bias) needs targets and the
    FFA-implied forecasts, so it is added in evaluation.build_store_v2."""
    from capesize import macro as MC
    from capesize import regime as RG
    ffa_lag = C.FFA_LAG if ffa_lag is None else ffa_lag
    g, X, A, srcs, curve = F.build_feature_store(ffa_lag)
    grid = g.index
    parts, avs = [X], [A]
    fx, _, _ = ffa_extra_features(g, ffa_lag)
    parts += [fx, route_features(g), path_features(g)]
    for fn in (extra_weekly_features, extra_monthly_features):
        Xe, Ae, Se = fn(grid)
        parts.append(Xe)
        avs.append(Ae)
        srcs.update(Se)
    Xu, Au, Su = utilisation_features(grid, X["ffa_basis_m1"])
    parts.append(Xu)
    avs.append(Au)
    srcs.update(Su)
    if regime:
        parts.append(RG.regime_features(grid))
    if macro:
        Xm, Am, Sm = MC.macro_features(grid)
        parts.append(Xm)
        avs.append(Am)
        srcs.update(Sm)
    X2 = pd.concat(parts, axis=1)
    return g, X2, pd.concat(avs, axis=1), srcs, curve
