"""Task B: build outputs/6_Capesize_5TC_China_Customs_Monthly.xlsx and run checks 7-9 (+ Comtrade comparison).

Sources
  * China Customs platform (stats.customs.gov.cn), HS8 quarterly exports saved by hand -> 2024-01 onwards (primary)
    (parsed by cu_02_check_platform.py into data/interim/customs_platform_long.csv)
  * UN Comtrade (keyless preview, raw JSON per month from cu_01_fetch.py) -> 2016-01..2023-12; 2024 used as overlap
Rules (handoff 4.5): 10k t, USD kept separately, Jan/Feb split flag, blanks stay blank, month-end dates,
origins + other = total.
"""
import datetime as dt
import glob
import json
import os
import pathlib

import numpy as np
import openpyxl
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "customs"
INTERIM = ROOT / "data" / "interim"
OUT = ROOT / "outputs" / "6_Capesize_5TC_China_Customs_Monthly.xlsx"
# folder holding the team workbooks (licensed, not in Git); set CAPESIZE_WORKBOOKS, else the parent folder
TEAM2 = pathlib.Path(os.environ.get("CAPESIZE_WORKBOOKS", ROOT.parent)) / "2.Capesize_5TC_Iron_Ore_Weekly_Data.xlsx"
SPLICE = "2024-01"            # platform from this month on, Comtrade before
# human-maintained inputs (committed): sailing distances with sources, and the release lag (row LAG,ALL)
PARAMS = pd.read_csv(ROOT / "config" / "customs_parameters.csv", dtype=str).fillna("")
_lag = PARAMS[PARAMS.commodity == "LAG"].iloc[0]
LAG_DAYS, LAG_NOTE = int(_lag.distance_nm), _lag.source
_jan = PARAMS[PARAMS.commodity == "LAGJAN"]
JAN_EXTRA, JAN_NOTE = (int(_jan.iloc[0].distance_nm), _jan.iloc[0].source) if len(_jan) else (0, "")
DIST_IN = {(r.commodity, r.origin): r for r in PARAMS[~PARAMS.commodity.str.startswith("LAG")].itertuples()}

DARK, BLUE, YELLOW = (PatternFill("solid", fgColor=c) for c in ("1F3864", "2E75B6", "FFF2CC"))
WHITE, BOLD = Font(color="FFFFFF", bold=True), Font(bold=True)

COMMOD = {"2601": "IO", "2606": "BX", "2701": "CO", "2702": "CO"}
# origin -> (Comtrade M49 code, China customs partner code)
ORIG = {"AU": (36, "601"), "BR": (76, "410"), "ZA": (710, "244"), "CA": (124, "501"),
        "ID": (360, "112"), "RU": (643, "344"), "MN": (496, "124"), "GN": (324, "221")}
NAMES = {"AU": "Australia", "BR": "Brazil", "ZA": "South Africa", "CA": "Canada", "ID": "Indonesia",
         "RU": "Russia", "MN": "Mongolia", "GN": "Guinea"}
TARGET = {"IO": ["AU", "BR", "ZA", "CA"], "CO": ["AU", "ID", "RU", "MN", "CA"], "BX": ["GN", "AU", "ID"]}
CNAME = {"IO": "Iron ore", "CO": "Coal (2701+2702)", "BX": "Bauxite"}
HS = {"IO": "2601", "CO": "2701+2702", "BX": "2606"}

# ------------------------------------------------------------------------------------------------
# 1. load both sources into one tidy frame: month, com, partner key, kg, usd, source
# ------------------------------------------------------------------------------------------------
m49_to_key = {v[0]: k for k, v in ORIG.items()}
cn_to_key = {v[1]: k for k, v in ORIG.items()}

rows, world = [], []
ct_files = sorted(glob.glob(str(RAW / "comtrade_CN_*.json")))
for f in ct_files:
    for r in json.load(open(f, encoding="utf-8")).get("data", []):
        kg = r["netWgt"] if r["netWgt"] is not None else (r["qty"] if r.get("qtyUnitCode") == 8 else None)
        rec = dict(month=r["period"], hs4=r["cmdCode"], partner=r["partnerCode"], kg=kg, usd=r["primaryValue"])
        (world if r["partnerCode"] == 0 else rows).append(rec)
ct = pd.DataFrame(rows)
ct_world = pd.DataFrame(world)
ct["key"] = ct.partner.map(m49_to_key).fillna("OTHER")
ct["source"] = "UN Comtrade"

pf = pd.read_csv(INTERIM / "customs_platform_long.csv", dtype={"month": str, "hs8": str, "partner_code": str})
pf["hs4"] = pf.hs8.str[:4]
# confirm the platform partner codes by their names
for k, (_, code) in ORIG.items():
    nm = pf.loc[pf.partner_code == code, "partner_name"].drop_duplicates().tolist()
    print(f"platform partner {code} -> {nm}  (expected {NAMES[k]})")
pf = pf.rename(columns={"qty1": "kg"})
pf["key"] = pf.partner_code.map(cn_to_key).fillna("OTHER")
pf["source"] = "China Customs platform"

for d in (ct, pf):
    d["com"] = d.hs4.map(COMMOD)


def by_origin(d):
    g = d.groupby(["month", "com", "key"])[["kg", "usd"]].sum(min_count=1).reset_index()
    tot = d.groupby(["month", "com"])[["kg", "usd"]].sum(min_count=1).reset_index().assign(key="TOTAL")
    return pd.concat([g, tot])


ct_o, pf_o = by_origin(ct), by_origin(pf)

# ------------------------------------------------------------------------------------------------
# 2. overlap 2024: Comtrade vs platform (handoff 4.8.3)
# ------------------------------------------------------------------------------------------------
ov = ct_o[ct_o.month.str.startswith("2024")].merge(
    pf_o[pf_o.month.str.startswith("2024")], on=["month", "com", "key"], suffixes=("_ct", "_pf"))
ov["pct_kg"] = (ov.kg_ct / ov.kg_pf - 1) * 100
ov["pct_usd"] = (ov.usd_ct / ov.usd_pf - 1) * 100
main = ov[ov.key.isin(["AU", "BR", "TOTAL", "GN", "ID"])]
print("\nOVERLAP 2024 (Comtrade / platform - 1, %): by commodity x origin, abs max over 12 months")
summ = main.groupby(["com", "key"]).agg(n=("month", "count"), max_abs_pct_kg=("pct_kg", lambda s: s.abs().max()),
                                         max_abs_pct_usd=("pct_usd", lambda s: s.abs().max()))
print(summ.round(3).to_string())
rng = np.random.default_rng(42)
sample_months = sorted(rng.choice(sorted(ov.month.unique()), 6, replace=False))
samp = ov[ov.month.isin(sample_months) & (ov.key == "TOTAL")][["month", "com", "kg_ct", "kg_pf", "pct_kg", "pct_usd"]]
print("\n6 random months (TOTAL rows):\n" + samp.round(4).to_string(index=False))

# ------------------------------------------------------------------------------------------------
# 3. spliced monthly series
# ------------------------------------------------------------------------------------------------
# Platform wins wherever it has the month. Comtrade fills only months without platform data, and only from
# COMTRADE_MIN: China's 2016-2017 monthly data on Comtrade fail the annual-total check (e.g. bauxite ~0.6-1 Mt/month
# vs ~4-6 Mt; coal 2016 ~167 Mt vs ~256 Mt published), so they are not used.
COMTRADE_MIN = "201801"
pf_months = set(pf_o.month)
use_pf = pf_o.assign(source="China Customs platform")
use_ct = ct_o[(ct_o.month >= COMTRADE_MIN) & ~ct_o.month.isin(pf_months)].assign(source="UN Comtrade")
use = pd.concat([use_ct, use_pf])
months = pd.period_range(pd.Period(use.month.min(), "M"), pd.Period(use.month.max(), "M"), freq="M")

series = []      # (column name, com, key)
for com, keys in TARGET.items():
    for k in keys:
        series.append((f"{CNAME[com]} from {NAMES[k]}", com, k))
    series.append((f"{CNAME[com]} from other origins", com, "OTHER_SUM"))
    series.append((f"{CNAME[com]} total", com, "TOTAL"))

piv_kg = use.pivot_table(index="month", columns=["com", "key"], values="kg", aggfunc="sum")
piv_usd = use.pivot_table(index="month", columns=["com", "key"], values="usd", aggfunc="sum")
grid = pd.DataFrame(index=[p.strftime("%Y%m") for p in months])


def col_of(piv, com, key, div):
    if key == "OTHER_SUM":          # all-countries total minus the listed origins
        listed = sum(piv.get((com, k), pd.Series(0.0, index=piv.index)).fillna(0) for k in TARGET[com])
        s = piv[(com, "TOTAL")] - listed
    else:
        s = piv.get((com, key), pd.Series(np.nan, index=piv.index))
        if key != "TOTAL":           # origin absent in a month where the commodity has data = genuine 0
            s = s.where(s.notna() | piv[(com, "TOTAL")].isna(), 0.0)
    return (s / div).reindex(grid.index)


qty = pd.DataFrame({name: col_of(piv_kg, com, key, 1e7) for name, com, key in series})     # kg -> 10k t
val = pd.DataFrame({name: col_of(piv_usd, com, key, 1e6) for name, com, key in series})    # USD -> USD mn
src = use.groupby("month").source.first().reindex(grid.index).fillna("no source (gap)")
print("\nmonths by source:", src.value_counts().to_dict())


def ranges(ms):
    """['201501','201502','201601'] -> '2015-01..2015-02, 2016-01'"""
    ps = sorted(pd.Period(m, "M") for m in ms)
    out, start = [], None
    for k, p in enumerate(ps):
        start = start or p
        if k == len(ps) - 1 or ps[k + 1] != p + 1:
            out.append(f"{start}" if start == p else f"{start}..{p}")
            start = None
    return ", ".join(out) if out else "none"


COV_PF = ranges([m for m in grid.index if src[m] == "China Customs platform"])
COV_CT = ranges([m for m in grid.index if src[m] == "UN Comtrade"])
COV_GAP = ranges([m for m in grid.index if src[m].startswith("no source")])
print(f"platform: {COV_PF}\nComtrade: {COV_CT}\ngaps: {COV_GAP}")

# ------------------------------------------------------------------------------------------------
# 4. checks 7 and 8
# ------------------------------------------------------------------------------------------------
print("\nCHECK 7  origins + other = total")
c7 = []
for com in TARGET:
    names = [n for n, c, k in series if c == com and k != "TOTAL"]
    diff = (qty[names].sum(axis=1, min_count=1) - qty[f"{CNAME[com]} total"]).abs().max()
    c7.append((com, diff))
    print(f"  {CNAME[com]:18s} max |sum of origins + other - total| = {diff:.2e} (10k t)")
# Comtrade partner sum vs its own World row (value always present; weight often null on the World row)
w = ct_world.copy()
w["com"] = w.hs4.map(COMMOD)
w["kg"] = w.kg.where(w.kg > 0)                              # World weight is often null or 0 (not reported)
w = w.groupby(["month", "hs4"])[["kg", "usd"]].sum(min_count=1).rename(columns={"kg": "kg_world", "usd": "usd_world"})
p = ct.groupby(["month", "hs4"])[["kg", "usd"]].sum(min_count=1)    # compare per HS4 (coal = 2 HS4 codes)
j = p.join(w)
j["pct_usd"] = (j.usd / j.usd_world - 1) * 100
j["pct_kg"] = (j.kg / j.kg_world - 1) * 100
print(f"  Comtrade partner sum vs World row: value max |diff| = {j.pct_usd.abs().max():.3f}%, "
      f"weight max |diff| = {j.pct_kg.abs().max():.3f}% (World weight present in {int(j.kg_world.notna().sum())} "
      f"of {len(j)} month x HS4)")
c7_world = (j.pct_usd.abs().max(), j.pct_kg.abs().max(), int(j.kg_world.notna().sum()), len(j))

print("\nCHECK 8  Jan/Feb: both months reported separately?")
jf = pd.DataFrame({"jan": qty["Iron ore total"][grid.index.str.endswith("01")].values,
                   "feb": qty["Iron ore total"][grid.index.str.endswith("02")].values},
                  index=sorted({m[:4] for m in grid.index if m[4:] in ("01", "02")}))
print(jf.round(0).to_string())
jan_feb_split = pd.Series(0, index=grid.index)    # no combined Jan-Feb figure found in either source

# ------------------------------------------------------------------------------------------------
# 5. check 9: lagged correlations with Wind AU+BR shipments; PortWatch direction of change
# ------------------------------------------------------------------------------------------------
wb2 = openpyxl.load_workbook(TEAM2, data_only=True, read_only=True)
r2 = list(wb2["Weekly Data"].iter_rows(values_only=True))
wind = pd.DataFrame({"fri": pd.to_datetime([r[0] for r in r2[1:]]),
                     "aubr": pd.to_numeric(pd.Series([r[5] for r in r2[1:]]), errors="coerce")}).dropna()
# weekly reference week = Mon..Sun ending Fri - 5 days; spread each week evenly over its 7 days, then sum by
# calendar month (summing whole weeks would give 4- and 5-week months)
days = pd.DataFrame({"day": [f - pd.Timedelta(days=5 + k) for f in wind.fri for k in range(7)],
                     "v": np.repeat(wind.aubr.values / 7, 7)})
days["month"] = days.day.dt.strftime("%Y%m")
cnt = days.groupby("month").day.nunique()
dim = pd.Series({m: pd.Period(m, "M").days_in_month for m in cnt.index})
wind_m = days.groupby("month").v.sum()[cnt == dim]        # complete calendar months only
cust = qty["Iron ore from Australia"] + qty["Iron ore from Brazil"]
lagc = []
print("\nCHECK 9  corr(customs AU+BR iron ore imports_t, Wind AU+BR shipments_t-lag)")
for lag in (0, 1, 2):
    x = pd.concat([cust, wind_m.shift(lag).reindex(cust.index)], axis=1).dropna()
    dx = x.pct_change().dropna()
    lagc.append((lag, x.iloc[:, 0].corr(x.iloc[:, 1]), dx.iloc[:, 0].corr(dx.iloc[:, 1]), len(x)))
    print(f"  lag {lag}: levels r={lagc[-1][1]:.3f}, MoM % change r={lagc[-1][2]:.3f}, n={len(x)}")

daily = pd.read_csv(sorted((RAW.parent / "portwatch").glob("ports_daily_*.csv"))[-1], parse_dates=["date"])
selp = pd.read_csv(INTERIM / "port_selection.csv")
pw = daily.merge(selp[selp.used == 1][["portid", "role"]], on="portid")
pw = pw[pw.role.isin(["AU_IRON", "BR_IRON"])]
pw["month"] = pw.date.dt.strftime("%Y%m")
full = pw.groupby("month").date.apply(lambda s: s.dt.normalize().nunique() == s.iloc[0].days_in_month)
pwm = pw.groupby(["month", "role"]).export_dry_bulk.sum().unstack() / 1e4
pwm = pwm[full.reindex(pwm.index).fillna(False)]
dirc = []
print("  PortWatch exports (month t-lag) vs customs imports (month t): share of months with the same sign of MoM change")
for role, k in (("AU_IRON", "Australia"), ("BR_IRON", "Brazil")):
    for lag in (0, 1, 2):
        a = qty[f"Iron ore from {k}"].diff()
        b = pwm[role].diff().shift(lag).reindex(a.index)
        m = pd.concat([a, b], axis=1).dropna()
        share = (np.sign(m.iloc[:, 0]) == np.sign(m.iloc[:, 1])).mean()
        dirc.append((role, k, lag, share, len(m)))
        print(f"    {role} vs customs {k}, lag {lag}: same direction {share:.0%} of {len(m)} months")

# ------------------------------------------------------------------------------------------------
# 6. workbook
# ------------------------------------------------------------------------------------------------
def header(ws, row, labels, fill=DARK, start_col=1):
    for jx, lab in enumerate(labels, start=start_col):
        c = ws.cell(row=row, column=jx, value=lab)
        c.fill, c.font = fill, WHITE
        c.alignment = Alignment(wrap_text=True, vertical="center")


def widths(ws, ws_w):
    for jx, x in enumerate(ws_w, 1):
        ws.column_dimensions[get_column_letter(jx)].width = x


def month_end(m):
    return pd.Period(m, "M").to_timestamp(how="end").normalize().to_pydatetime()


wb = Workbook()
ws_n = wb.active
ws_n.title = "Notes"

# ---- Parameters ------------------------------------------------------------------------------
ws_p = wb.create_sheet("Parameters")
header(ws_p, 1, ["Series", "Unit", "Default release lag (days)", "Note"])
qnames = [s[0] for s in series]
for i, n in enumerate(qnames, start=2):
    ws_p.cell(i, 1, n); ws_p.cell(i, 2, "10k t/month")
    ws_p.cell(i, 3, LAG_DAYS).fill = YELLOW
    ws_p.cell(i, 4, f"Source: {LAG_NOTE}. Edit config/customs_parameters.csv (row LAG) and rebuild; "
                    "edits made only in this workbook are lost on rebuild.")
n_lag = len(qnames) + 1
jan_row = n_lag + 2
ws_p.cell(jan_row, 1, "Extra lag for January data (days)").font = BOLD
ws_p.cell(jan_row, 2, "days")
ws_p.cell(jan_row, 3, JAN_EXTRA).fill = YELLOW
ws_p.cell(jan_row, 4, f"Added to the release lag when the original date is in January. Source: {JAN_NOTE}")
JAN_CELL = f"Parameters!$C${jan_row}"
dist_row0 = jan_row + 3
ws_p.cell(dist_row0 - 1, 1, "Sailing distance to China (nautical miles) - to be filled from a cited source; "
                            "tonne-mile columns stay blank until all distances of a commodity are filled").font = BOLD
header(ws_p, dist_row0, ["Route", "Unit", "Distance (nm)", "Source (fill in)"])
DIST = [("IO", "AU"), ("IO", "BR"), ("IO", "ZA"), ("IO", "CA"), ("BX", "GN"), ("BX", "AU"), ("BX", "ID")]
dist_cell = {}
for i, (com, k) in enumerate(DIST, start=dist_row0 + 1):
    p_in = DIST_IN.get((com, k))
    route = f"{p_in.load_port} -> {p_in.discharge_port}" if p_in is not None and p_in.load_port else "China"
    ws_p.cell(i, 1, f"{CNAME[com]}: {NAMES[k]} ({route})"); ws_p.cell(i, 2, "nm")
    c3 = ws_p.cell(i, 3, float(p_in.distance_nm) if p_in is not None and p_in.distance_nm else None)
    c3.fill = YELLOW
    ws_p.cell(i, 4, f"{p_in.source} (accessed {p_in.access_date})" if p_in is not None and p_in.source else None).fill = YELLOW
    dist_cell[(com, k)] = f"Parameters!$C${i}"
widths(ws_p, [42, 12, 16, 110])

# ---- Monthly Data -----------------------------------------------------------------------------
ws = wb.create_sheet("Monthly Data")
raw_cols = qnames + ["Source", "jan_feb_split"]
header(ws, 1, ["Month end"] + [f"{c}\n10k t" for c in qnames] + ["Source", "jan_feb_split\n1 = Jan-Feb split equally"])
col = {name: get_column_letter(jx) for jx, name in enumerate(raw_cols, start=2)}
N = len(grid)
for i, m in enumerate(grid.index, start=2):
    ws.cell(i, 1, month_end(m)).number_format = "yyyy-mm-dd"
    for name in qnames:
        v = qty.at[m, name]
        if pd.notna(v):
            ws.cell(i, raw_cols.index(name) + 2, round(float(v), 4))
    ws.cell(i, raw_cols.index("Source") + 2, src.get(m))
    ws.cell(i, raw_cols.index("jan_feb_split") + 2, int(jan_feb_split[m]))

first_d = len(raw_cols) + 2
derived = []
A, B = col["Iron ore from Australia"], col["Iron ore from Brazil"]
derived.append(("Brazil share of iron ore (AU + BR)\n%",
                f'=IF(AND(ISNUMBER({B}{{r}}),ISNUMBER({A}{{r}}),{A}{{r}}+{B}{{r}}>0),{B}{{r}}/({A}{{r}}+{B}{{r}}),"")'))
G, T = col["Bauxite from Guinea"], col["Bauxite total"]
derived.append(("Guinea share of bauxite\n%", f'=IF(AND(ISNUMBER({G}{{r}}),ISNUMBER({T}{{r}}),{T}{{r}}>0),{G}{{r}}/{T}{{r}},"")'))
for name in qnames:
    X = col[name]
    derived.append((f"{name} 3-mo avg\n10k t", f'=IF(AND(ISNUMBER({X}{{r}}),COUNT({X}{{r2}}:{X}{{r}})=3),AVERAGE({X}{{r2}}:{X}{{r}}),"")'))
    derived.append((f"{name} YoY\n%", f'=IF(AND(ISNUMBER({X}{{r}}),ISNUMBER({X}{{r12}}),N({X}{{r12}})<>0),{X}{{r}}/{X}{{r12}}-1,"")'))
for com in ("IO", "BX"):
    ks = [k for c, k in DIST if c == com]
    cells = ",".join(dist_cell[(com, k)] for k in ks)
    terms = "+".join(f"{col[f'{CNAME[com]} from {NAMES[k]}']}{{r}}*{dist_cell[(com, k)]}" for k in ks)
    nums = ",".join(f"{col[f'{CNAME[com]} from {NAMES[k]}']}{{r}}" for k in ks)
    derived.append((f"{CNAME[com]} tonne-mile proxy ({', '.join(ks)})\n10k t x nm",
                    f'=IF(AND(COUNT({cells})={len(ks)},COUNT({nums})={len(ks)}),{terms},"")'))
header(ws, 1, [h for h, _ in derived], fill=BLUE, start_col=first_d)
for i in range(2, N + 2):
    for k, (h, f) in enumerate(derived):
        if ("{r2}" in f and i - 2 < 2) or ("{r12}" in f and i - 12 < 2):
            ws.cell(i, first_d + k, "")
            continue
        c = ws.cell(i, first_d + k, f.format(r=i, r2=i - 2, r12=i - 12))
        if "%" in h:
            c.number_format = "0.0%"
ws.freeze_panes = "B2"
ws.row_dimensions[1].height = 75
widths(ws, [12] + [13] * (len(raw_cols) + len(derived)))

# ---- Monthly Value (USD) -------------------------------------------------------------------------
ws_v = wb.create_sheet("Monthly Value")
header(ws_v, 1, ["Month end"] + [f"{c}\nUSD mn" for c in qnames] + ["Source"])
for i, m in enumerate(grid.index, start=2):
    ws_v.cell(i, 1, month_end(m)).number_format = "yyyy-mm-dd"
    for jx, name in enumerate(qnames, start=2):
        v = val.at[m, name]
        if pd.notna(v):
            ws_v.cell(i, jx, round(float(v), 4))
    ws_v.cell(i, len(qnames) + 2, src.get(m))
ws_v.freeze_panes = "B2"
ws_v.row_dimensions[1].height = 60
widths(ws_v, [12] + [13] * (len(qnames) + 1))

# ---- Long Table ---------------------------------------------------------------------------------
ws_t = wb.create_sheet("Long Table")
header(ws_t, 1, ["Series", "Unit", "Source", "Indicator ID", "Original date", "Value", "Month end",
                 "Release lag (days)", "Estimated available date"])
r = 2
for name, com, key in series:
    for m in grid.index:
        v = qty.at[m, name]
        if pd.isna(v):
            continue
        s = src[m]
        ind = (f"{'customs' if s.startswith('China') else 'comtrade'}:CN:M:{HS[com]}:"
               f"{'all' if key == 'TOTAL' else ('total-minus-listed' if key == 'OTHER_SUM' else NAMES[key])}")
        d0 = month_end(m)
        for jx, x in enumerate([name, "10k t/month", s, ind, d0, round(float(v), 4), d0], start=1):
            c = ws_t.cell(r, jx, x)
            if jx in (5, 7):
                c.number_format = "yyyy-mm-dd"
        ws_t.cell(r, 8, f"=VLOOKUP(A{r},Parameters!$A$2:$C${n_lag},3,FALSE())")
        ws_t.cell(r, 9, f"=E{r}+H{r}+IF(MONTH(E{r})=1,{JAN_CELL},0)").number_format = "yyyy-mm-dd"
        r += 1
n_long = r - 2
ws_t.freeze_panes = "A2"
widths(ws_t, [36, 12, 22, 44, 12, 12, 12, 10, 14])

# ---- Source Comparison ----------------------------------------------------------------------------
ws_s = wb.create_sheet("Source Comparison")
header(ws_s, 1, ["Source", "Coverage", "Used?", "Note"])
src_rows = [
    ["China Customs platform (stats.customs.gov.cn), HS8, exported by hand", COV_PF,
     "Yes, wherever available (preferred)", "Official source; the platform starts in 2015. HS8 codes summed to HS4 (26011110/20/90, 26011200, 26012000; 26060000; 27011100/1210/1290/1900/2000; 27021000/2000). "
     "HS8 sums equal the HS4 values for AU and BR 2024-01..03 (checked)."],
    ["UN Comtrade, China as reporter, HS4, keyless public preview API", f"used: {COV_CT}; downloaded 2016-01..2024-12 (2014-2015 return no records; 2025+ not yet reported)",
     "Yes, only for months without platform data, from 2018-01; 2024 overlap used as cross-check",
     "2016-2017 monthly records fail the annual-total check (bauxite ~0.6-1 Mt/month vs ~4-6 Mt; coal 2016 ~167 Mt vs ~256 Mt published) and are NOT used."],
    ["Gap (no reliable free source)", COV_GAP, "-", "Fill by exporting these quarters from the customs platform (same settings), then rebuild."],
    ["Wind / Choice / iFinD", "-", "Not obtained", "Not needed once the official platform export was available."],
]
for i, row in enumerate(src_rows, start=2):
    for jx, v in enumerate(row, 1):
        ws_s.cell(i, jx, v)
i = len(src_rows) + 3
ws_s.cell(i, 1, "Comtrade vs platform, 2024 overlap (Comtrade / platform - 1)").font = BOLD
i += 1
header(ws_s, i, ["Commodity", "Origin", "Months", "Max |% diff| quantity", "Max |% diff| value"])
for (com, key), rr in summ.iterrows():
    i += 1
    for jx, v in enumerate([CNAME[com], "All countries" if key == "TOTAL" else NAMES.get(key, key), int(rr.n),
                            float(rr.max_abs_pct_kg) / 100, float(rr.max_abs_pct_usd) / 100], 1):
        c = ws_s.cell(i, jx, v)
        if jx in (4, 5):
            c.number_format = "0.000%"
i += 2
ws_s.cell(i, 1, f"6 random months (seed 42): {', '.join(sample_months)}; all-countries totals").font = BOLD
i += 1
header(ws_s, i, ["Month", "Commodity", "Comtrade (10k t)", "Platform (10k t)", "% diff quantity", "% diff value"])
for rr in samp.itertuples():
    i += 1
    for jx, v in enumerate([rr.month, CNAME[rr.com], rr.kg_ct / 1e7, rr.kg_pf / 1e7, rr.pct_kg / 100, rr.pct_usd / 100], 1):
        c = ws_s.cell(i, jx, v)
        if jx in (5, 6):
            c.number_format = "0.000%"
i += 2
ws_s.cell(i, 1, "Check 7: totals").font = BOLD
for com, diff in c7:
    i += 1
    ws_s.cell(i, 1, f"{CNAME[com]}: max |listed origins + other - total| = {diff:.1e} (10k t)")
i += 1
ws_s.cell(i, 1, f"Comtrade sum of partners vs its World row, per HS4: value max |diff| = {c7_world[0]:.4f}%, "
                f"weight max |diff| = {c7_world[1]:.4f}% (World weight reported in {c7_world[2]} of {c7_world[3]} month x HS4)")
i += 2
ws_s.cell(i, 1, "Check 9: corr(customs AU + BR iron ore imports in month t, Wind AU + BR shipments in month t - lag)").font = BOLD
i += 1
header(ws_s, i, ["Lag (months)", "Corr. levels", "Corr. MoM % change", "Months"])
for lag, cl, cd, n in lagc:
    i += 1
    for jx, v in enumerate([lag, cl, cd, n], 1):
        c = ws_s.cell(i, jx, v)
        if jx in (2, 3):
            c.number_format = "0.000"
i += 2
ws_s.cell(i, 1, "PortWatch exports (month t - lag) vs customs imports (month t): share of months with the same sign of month-on-month change").font = BOLD
i += 1
header(ws_s, i, ["PortWatch role", "Customs origin", "Lag (months)", "Same direction", "Months"])
for role, k, lag, share, n in dirc:
    i += 1
    for jx, v in enumerate([role, k, lag, share, n], 1):
        c = ws_s.cell(i, jx, v)
        if jx == 4:
            c.number_format = "0%"
widths(ws_s, [60, 40, 26, 22, 22, 22])

# ---- Raw Series ------------------------------------------------------------------------------------
ws_r = wb.create_sheet("Raw Series")
raw_pf = pd.read_csv(INTERIM / "customs_platform_long.csv", dtype=str)
raw_pf = raw_pf[["file", "month", "hs8", "hs8_name", "partner_code", "partner_name", "qty1", "unit1", "usd"]]
header(ws_r, 1, ["Source", "File", "Month", "Commodity code", "Commodity name", "Partner code", "Partner name",
                 "Quantity", "Unit", "USD"])
i = 1
for rr in raw_pf.itertuples(index=False):
    i += 1
    for jx, v in enumerate(["China Customs platform", rr.file, rr.month, rr.hs8, rr.hs8_name, rr.partner_code,
                            rr.partner_name, float(rr.qty1), rr.unit1, float(rr.usd)], 1):
        ws_r.cell(i, jx, v)
for f in ct_files:
    for rec in json.load(open(f, encoding="utf-8")).get("data", []):
        i += 1
        for jx, v in enumerate(["UN Comtrade", pathlib.Path(f).name, rec["period"], rec["cmdCode"], None,
                                rec["partnerCode"], "World" if rec["partnerCode"] == 0 else None,
                                rec["netWgt"], "kg (netWgt)", rec["primaryValue"]], 1):
            if v is not None:
                ws_r.cell(i, jx, v)
ws_r.freeze_panes = "A2"
widths(ws_r, [22, 40, 9, 12, 40, 10, 22, 16, 12, 16])

# ---- Notes -------------------------------------------------------------------------------------------
today = dt.date.today()
notes = [
    ("Capesize 5TC Forecasting - Item 6: China Imports of Iron Ore, Coal and Bauxite by Origin (Monthly, Cleaned)", True),
    (f"Sources: China Customs statistics query platform (http://stats.customs.gov.cn), HS8, imports, monthly, all partners, "
     f"exported by hand (2026-11-04/05), used for {COV_PF}; UN Comtrade (China as reporter, HS4) via the keyless public "
     f"preview API, accessed 2026-11-04, used for {COV_CT}. Gap (blank): {COV_GAP}. Built {today}.", False),
    ("", False),
    ("Sheets", True),
    ("Monthly Data: month-end grid; raw columns (dark blue) in 10k t; derived features (light blue) are formulas.", False),
    ("Monthly Value: the same series in USD mn (raw, no formulas).", False),
    ("Long Table: one row per monthly observation with source, indicator ID and estimated available date = original date + release lag.", False),
    ("Parameters: release lags and the extra January lag (yellow), sailing distances with sources (yellow). Edit config/customs_parameters.csv and rebuild.", False),
    ("Source Comparison: sources, Comtrade vs platform overlap, check 9 lagged correlations, PortWatch direction test.", False),
    ("Raw Series: unadjusted rows as exported (platform HS8 rows and Comtrade HS4 rows incl. the World row).", False),
    ("", False),
    ("Cleaning method", True),
    ("1. Quantities are the first quantity in kg (net weight for Comtrade) divided by 10,000,000 to give 10k t; USD kept separately.", False),
    ("2. Platform HS8 rows are summed to HS4; coal = 2701 + 2702 (lignite).", False),
    ("3. Source per month: the customs platform wherever it has the month; otherwise Comtrade from 2018-01 (2016-2017 Comtrade "
     "records fail the annual-total check). In the 2024 overlap the two agree within 0.01% (see Source Comparison). Column 'Source' shows the source of each month.", False),
    ("4. Origins: listed origins per commodity; 'other origins' = all-countries total minus listed origins. All-countries total = sum over every partner.", False),
    ("5. An origin with no record in a month in which the commodity has data is a genuine zero (no imports). Months with no data stay blank.", False),
    ("6. January and February are reported separately in both sources for every year covered, so no Jan-Feb split was needed (jan_feb_split = 0 throughout).", False),
    ("7. Each month is placed on its month-end date.", False),
    ("", False),
    ("Derived features (formulas)", True),
    ("- Brazil share of iron ore = Brazil / (Australia + Brazil); Guinea share of bauxite = Guinea / bauxite total.", False),
    ("- 3-month average (needs all 3 months); YoY = value / value 12 months earlier - 1.", False),
    ("- Tonne-mile proxy = sum over origins of tonnes x sailing distance; blank until every distance of that commodity is filled in Parameters.", False),
    ("", False),
    ("Points to note", True),
    (f"- 2014 is not available from free sources (platform starts 2015, Comtrade 2016); the handoff asked for 2014. Blank gap: {COV_GAP}.", False),
    ("- At the source change (Comtrade -> platform) check for level breaks before using long YoY windows; in the 2024 overlap there is none.", False),
    ("- Comtrade's World row often has no weight; totals are sums over partners. Platform partner codes are China's own codes (e.g. 124 = Mongolia), Comtrade uses UN M49 (124 = Canada); both mapped by name.", False),
    (f"- Release lag: {LAG_DAYS} days after month end (online query data open on the 20th, GACC 2026 timetable); "
     f"January data +{JAN_EXTRA} days (opened with February on 20 March). Earlier years' calendars were not checked.", False),
    ("- Sailing distances: searoute (Eurostat MARNET network) between PortWatch port coordinates and Qingdao, Panama/Suez "
     "excluded (Capesize routing). One representative load port per origin; see Parameters. Inputs live in config/customs_parameters.csv.", False),
    ("- Blank formula results are empty text (\"\"); convert to numeric after reading with pandas.", False),
]
for k, (text, b) in enumerate(notes, start=1):
    c = ws_n.cell(k, 1, text)
    if b:
        c.font = BOLD
ws_n.column_dimensions["A"].width = 160

wb.save(OUT)
qty.to_csv(INTERIM / "customs_monthly_qty.csv")
print(f"\nwrote {OUT} ({N} months, {len(derived)} derived columns, {n_long} long-table rows)")
