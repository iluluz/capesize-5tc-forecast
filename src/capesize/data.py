"""Loaders. Derived (formula) columns in the workbooks are NOT trusted: several have no cached
values (files 3 and 6) and the plan wants only past-window transforms anyway. We read raw
levels + the release-lag tables and rebuild every feature ourselves."""
import functools

import pandas as pd

from capesize import config as C


@functools.lru_cache(maxsize=None)
def _sheet(n: int, sheet: str, **kw) -> pd.DataFrame:
    if "parse_dates" in kw:
        kw["parse_dates"] = list(kw["parse_dates"])
    return pd.read_excel(C.workbook(n), sheet, **kw)


def read(n: int, sheet: str, parse_dates=None, header=0) -> pd.DataFrame:
    """Cached read of one sheet (a copy, so callers may modify it)."""
    kw = {"header": header}
    if parse_dates:
        kw["parse_dates"] = tuple(parse_dates)
    return _sheet(n, sheet, **kw).copy()


def _clean(cols):
    return [str(c).split("\n")[0].strip() for c in cols]


def load_spot() -> pd.DataFrame:
    d = read(1, "Spliced Series", parse_dates=["Date"]).set_index("Date")
    d = d.rename(columns={
        "5TC (182 basis, spliced) $/day": "S",
        "C8 (182 basis) $/day": "C8", "C9 (182 basis) $/day": "C9",
        "C10 (182 basis) $/day": "C10", "C14 (182 basis) $/day": "C14",
        "C16 (182 basis) $/day": "C16",
        "C3 Tubarao–Qingdao $/t": "C3", "C5 W Australia–Qingdao $/t": "C5",
        "BCI index": "BCI"})
    return d[["S", "C8", "C9", "C10", "C14", "C16", "C3", "C5", "BCI"]]


def load_ffa_curve() -> pd.DataFrame:
    d = read(1, "FFA Curve", parse_dates=["Date"]).set_index("Date")
    d.columns = _clean(d.columns)
    keep = ["Curve source", "M+1 contract month", "Current month M0", "M+1", "M+2", "M+3",
            "M+4", "M+5", "Current quarter Q0", "Q+1", "Q+2", "Q+3", "Q+4",
            "Cal+1", "Cal+2", "Cal+3", "Cal+4", "Cal+5"]
    d = d[keep].rename(columns={"Current month M0": "M0", "Current quarter Q0": "Q0",
                                "M+1 contract month": "m1_month"})
    return d


def load_ffa_weekly() -> pd.DataFrame:
    d = read(1, "FFA Volume & OI Weekly", parse_dates=["Week ending (Fri)"])
    d.columns = _clean(d.columns)
    return d.set_index("Week ending (Fri)")


def _release_lags(n: int, sheet="Release Lags") -> dict:
    r = read(n, sheet).iloc[:, :3]
    r.columns = ["series", "unit", "lag"]
    r = r.dropna(subset=["lag"])
    r = r[pd.to_numeric(r["lag"], errors="coerce").notna()]
    return dict(zip(r["series"], r["lag"].astype(int), strict=True))


def load_ironore():
    d = read(2, "Weekly Data", parse_dates=["Week ending (Fri)"]).set_index("Week ending (Fri)")
    d.columns = _clean(d.columns)
    raw = d.iloc[:, :7]          # first 7 columns = raw series; the rest are formula features
    return raw, _release_lags(2)


def load_portwatch():
    d = read(3, "Weekly Data", parse_dates=["Week ending (Fri)"]).set_index("Week ending (Fri)")
    d.columns = _clean(d.columns)
    raw = d.iloc[:, :13]
    return raw, _release_lags(3)


def load_fleet():
    d = read(4, "Monthly Data", parse_dates=["Month (end)"]).set_index("Month (end)")
    names = {"Fleet m dwt": "fleet_dwt", "Deliveries m dwt": "deliv_dwt", "Demolition m dwt": "demol_dwt",
             "Orderbook m dwt": "ob_dwt"}
    pick = {names[k]: d[c] for c in d.columns if (k := str(c).replace("\n", " ")) in names}
    p = read(4, "Parameters", header=None)
    lag = int(p.iloc[2, 1])      # 'Release lag (days after month end)'
    return pd.DataFrame(pick), lag


def load_customs():
    d = read(6, "Monthly Data", parse_dates=["Month end"]).set_index("Month end")
    d.columns = _clean(d.columns)
    p = read(6, "Parameters", header=None)
    lag = int(p.iloc[1, 2])
    jan_extra = int(p[p[0].astype(str).str.startswith("Extra lag for January")].iloc[0, 2])
    dist = {}
    for _, r in p.iterrows():
        if str(r[1]).strip() == "nm":          # distance rows have unit 'nm' in column 1
            dist[str(r[0])] = float(r[2])
    return d, lag, jan_extra, dist
