import numpy as np
from scipy import stats
from sklearn.metrics import f1_score


def theil_u(y, yhat):
    """RMSE(model) / RMSE(random walk, yhat=0). < 1 beats the random walk."""
    return np.sqrt(np.mean((y - yhat) ** 2)) / np.sqrt(np.mean(y ** 2))


def pesaran_timmermann(y, yhat):
    """PT directional-accuracy test. NB: overlapping h-day targets -> p-values are optimistic."""
    y, yhat = np.asarray(y), np.asarray(yhat)
    m = (y != 0) & (yhat != 0)
    y, yhat = y[m] > 0, yhat[m] > 0
    n = len(y)
    if n < 30 or yhat.all() or (~yhat).all():
        return np.nan, np.nan
    P = np.mean(y == yhat)
    py, px = y.mean(), yhat.mean()
    Ps = py * px + (1 - py) * (1 - px)
    vP = Ps * (1 - Ps) / n
    vPs = ((2 * py - 1) ** 2 * px * (1 - px) + (2 * px - 1) ** 2 * py * (1 - py)
           + 4 * py * px * (1 - py) * (1 - px) / n) / n
    if vP - vPs <= 0:
        return np.nan, np.nan
    z = (P - Ps) / np.sqrt(vP - vPs)
    return z, 1 - stats.norm.cdf(z)          # one-sided: better than chance


def diebold_mariano(e_a, e_b, h, power=2):
    """H0: equal predictive accuracy. d = |e_a|^p - |e_b|^p, HAC (Bartlett, h-1 lags) variance,
    Harvey-Leybourne-Newbold small-sample correction, t(T-1). stat > 0  =>  B is better."""
    d = np.abs(np.asarray(e_a)) ** power - np.abs(np.asarray(e_b)) ** power
    T = len(d)
    dbar = d.mean()
    dc = d - dbar
    var = np.dot(dc, dc) / T
    for j in range(1, h):
        w = 1 - j / h
        var += 2 * w * np.dot(dc[j:], dc[:-j]) / T
    if var <= 0:
        return np.nan, np.nan
    dm = dbar / np.sqrt(var / T)
    hln = np.sqrt((T + 1 - 2 * h + h * (h - 1) / T) / T)
    stat = dm * hln
    return stat, 2 * (1 - stats.t.cdf(abs(stat), df=T - 1))


def direction_f1(y_cls, yhat, sigma):
    thr = 0.5 * sigma
    c = np.where(yhat > thr, 2, np.where(yhat < -thr, 0, 1))
    return f1_score(y_cls.astype(int), c, average="macro")
