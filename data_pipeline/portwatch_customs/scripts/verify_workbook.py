"""Acceptance check 10: scan a recalculated copy of the workbook for formula errors and compare
the derived columns with the same quantities computed in pandas.

Usage: python verify_workbook.py <recalculated copy .xlsx>
(Recalculate with LibreOffice `soffice --headless --convert-to xlsx`, or with Excel: open, full
recalculation, save as a copy. Never overwrite the output itself.)
"""
import sys

import numpy as np
import openpyxl
import pandas as pd

path = sys.argv[1]
wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
ERRORS = ("#REF!", "#DIV/0!", "#NAME?", "#VALUE!", "#N/A", "#NUM!", "#NULL!")
bad = 0
for ws in wb.worksheets:
    n = 0
    for row in ws.iter_rows(values_only=True):
        n += sum(1 for v in row if isinstance(v, str) and v.strip() in ERRORS)
    bad += n
    print(f"{ws.title:18s} error cells: {n}")

rows = list(wb["Weekly Data"].iter_rows(values_only=True))
hdr = [str(h).split("\n")[0] for h in rows[0]]
df = pd.DataFrame(rows[1:], columns=hdr).replace("", np.nan)
df = pd.concat([df.iloc[:, :1], df.iloc[:, 1:].apply(pd.to_numeric, errors="coerce")], axis=1)


def comp(name, expected):
    got = pd.to_numeric(df[name], errors="coerce")
    both = got.notna() & expected.notna()
    only = (got.notna() != expected.notna()).sum()
    diff = (got[both] - expected[both]).abs().max() if both.any() else 0.0
    ok = only == 0 and diff < 1e-9
    print(f"  {name:45s} n={int(both.sum()):4d} presence mismatches={only} max|diff|={diff:.2e} "
          f"{'OK' if ok else 'CHECK'}")
    return ok


print("\nDerived columns vs pandas")
br, au = df["BR iron ore ports exports"], df["AU iron ore ports exports"]
s = br + au
a4 = s.rolling(4, min_periods=3).mean().where(s.notna())
cn = df["China main ports imports"]
c4 = cn.rolling(4, min_periods=3).mean().where(cn.notna())
cape, suez = df["Cape of Good Hope dry bulk transits"], df["Suez dry bulk transits"]
cs = (cape / (cape + suez)).where((cape + suez) > 0)
ok = all([
    comp("AU + BR iron ore exports", s),
    comp("Brazil share of AU + BR", (br / s).where(s > 0)),
    comp("AU + BR exports 4-wk avg", a4),
    comp("AU + BR 4-wk avg YoY", a4 / a4.shift(52) - 1),
    comp("China imports 4-wk avg", c4),
    comp("China imports 4-wk avg YoY", c4 / c4.shift(52) - 1),
    comp("Cape share of Cape + Suez dry bulk transits", cs),
    comp("Cape share 4-wk avg", cs.rolling(4, min_periods=3).mean().where(cs.notna())),
])

lt = pd.DataFrame(list(wb["Long Table"].iter_rows(values_only=True))[1:],
                  columns=["Series", "Unit", "Source", "ID", "Orig", "Value", "Fri", "Lag", "Avail"])
lag_ok = lt.Lag.notna().all() and (pd.to_datetime(lt.Avail) - pd.to_datetime(lt.Orig)).dt.days.eq(lt.Lag).all()
print(f"\nLong Table: {len(lt)} rows; lags resolved for all rows and available = original + lag: {lag_ok}")
print(f"  lag values used: {sorted(lt.Lag.dropna().unique())}")
print("\nRESULT:", "PASS" if bad == 0 and ok and lag_ok else "FAIL")
