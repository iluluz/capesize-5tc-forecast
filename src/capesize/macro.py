"""Macro / FX features from FRED (public data; downloaded once into data/raw/fred/, gitignored).

Series: broad dollar index, AUD, BRL, CNY (H.10, updated weekly on FRED -> available 8 calendar days after the
observation date, conservative), Brent spot (EIA, weekly update -> 10 days) as a bunker-cost proxy.
Features: 20- and 60-observation log changes, computed on the observation axis and attached on the available
date (pit_attach), like every other weekly source.
"""
import io
import urllib.request

import numpy as np
import pandas as pd

from capesize.io import REPO
from capesize.pit import pit_attach

RAW = REPO / "data" / "raw" / "fred"
SERIES = {  # FRED id: (feature stem, sign so that "up" = stronger commodity currency / dearer bunker, lag days)
    "DTWEXBGS": ("mc_usd", 1, 8),
    "DEXUSAL": ("mc_aud", 1, 8),        # USD per AUD
    "DEXBZUS": ("mc_brl", -1, 8),       # BRL per USD -> flip
    "DEXCHUS": ("mc_cny", -1, 8),       # CNY per USD -> flip
    "DCOILBRENTEU": ("mc_brent", 1, 10),
}


def fetch(sid: str) -> pd.Series:
    RAW.mkdir(parents=True, exist_ok=True)
    path = RAW / f"{sid}.csv"
    if not path.exists():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
        req = urllib.request.Request(url, headers={"User-Agent": "capesize-forecast-research/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            path.write_bytes(r.read())
    d = pd.read_csv(io.StringIO(path.read_text()))
    d.columns = ["date", "value"]
    s = pd.to_numeric(d["value"], errors="coerce")
    return pd.Series(s.to_numpy(), index=pd.to_datetime(d["date"])).dropna()


def macro_features(grid):
    out, avs, src = {}, {}, {}
    for sid, (stem, sign, lag) in SERIES.items():
        s = fetch(sid)
        ls = sign * np.log(s.where(s > 0))
        avail = pd.Series(s.index + pd.Timedelta(days=lag), index=s.index)
        for k in (20, 60):
            v = ls - ls.shift(k)
            out[f"{stem}_chg{k}"], avs[f"{stem}_chg{k}"] = pit_attach(grid, v, avail)
            src[f"{stem}_chg{k}"] = (v, avail)
    return pd.DataFrame(out), pd.DataFrame(avs), src
