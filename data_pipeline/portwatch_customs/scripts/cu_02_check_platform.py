"""Check the China Customs platform exports (data/raw/customs/customs_8digit_*.csv, GBK, saved by hand).

Checks: encoding/columns, months per quarter file, duplicate rows, expected HS8 codes present every month
(26011120 fines in particular), units, and monthly totals by HS4 (10k t) for a sanity read.
Writes data/interim/customs_platform_long.csv (tidy, untouched values + parsed numbers).
"""
import pathlib
import re

import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "customs"
INTERIM = ROOT / "data" / "interim"
COLS = ["month", "hs8", "hs8_name", "partner_code", "partner_name", "qty1", "unit1", "qty2", "unit2", "usd"]
MUST = ["26011110", "26011120", "26011190", "26011200", "26060000", "27011210", "27011290", "27021000"]

frames = []
for f in sorted(RAW.glob("customs_8digit_*.csv")):
    df = pd.read_csv(f, encoding="gbk", dtype=str).iloc[:, :10]
    df.columns = COLS
    df["file"] = f.name
    m = re.search(r"(\d{4})Q(\d)", f.name)
    exp = {f"{m[1]}{3 * (int(m[2]) - 1) + k:02d}" for k in (1, 2, 3)}
    got = set(df.month)
    print(f"{f.name}: {len(df)} rows, months {sorted(got)} "
          f"{'OK' if got == exp else 'MISMATCH expected ' + str(sorted(exp))}")
    frames.append(df)

d = pd.concat(frames, ignore_index=True)
for c in ["qty1", "qty2", "usd"]:
    d[c] = pd.to_numeric(d[c].str.replace(",", ""), errors="coerce")
d["hs4"] = d.hs8.str[:4]

dup = d.duplicated(["month", "hs8", "partner_code"]).sum()
print(f"\nduplicate month x hs8 x partner rows: {dup}")
print("unit1 values:", d.unit1.value_counts().to_dict())
print("null qty1 / usd:", int(d.qty1.isna().sum()), int(d.usd.isna().sum()))

pres = d.pivot_table(index="month", columns="hs8", values="usd", aggfunc="count").reindex(columns=MUST)
miss = pres[pres.isna().any(axis=1)]
print("\nmonths missing an expected HS8 code:", "none" if miss.empty else "\n" + miss.to_string())

tot = d[d.unit1 == "千克"].pivot_table(index="month", columns="hs4", values="qty1", aggfunc="sum") / 1e7  # kg -> 10k t
au = d[(d.hs4 == "2601") & (d.partner_code == "601")].groupby("month").qty1.sum() / 1e7
br = d[(d.hs4 == "2601") & (d.partner_code == "410")].groupby("month").qty1.sum() / 1e7
gn = d[(d.hs4 == "2606") & (d.partner_code == "221")].groupby("month").qty1.sum() / 1e7
tot["2601_AU"], tot["2601_BR"], tot["2606_GN"] = au, br, gn
print("\nmonthly totals, 10k t:\n" + tot.round(0).to_string())

d.to_csv(INTERIM / "customs_platform_long.csv", index=False, encoding="utf-8")
print(f"\nwrote {INTERIM / 'customs_platform_long.csv'} ({len(d)} rows)")
