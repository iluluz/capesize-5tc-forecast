"""Check 10 for workbook 6: scan a recalculated copy for formula errors and recompute every derived column in pandas.

Usage: python verify_workbook6.py <recalculated copy .xlsx>   (never overwrite the output itself)
"""
import sys

import numpy as np
import openpyxl
import pandas as pd

wb = openpyxl.load_workbook(sys.argv[1], data_only=True, read_only=True)
ERRORS = ("#REF!", "#DIV/0!", "#NAME?", "#VALUE!", "#N/A", "#NUM!", "#NULL!")
bad = 0
for ws in wb.worksheets:
    n = sum(1 for row in ws.iter_rows(values_only=True) for v in row if isinstance(v, str) and v.strip() in ERRORS)
    bad += n
    print(f"{ws.title:18s} error cells: {n}")

rows = list(wb["Monthly Data"].iter_rows(values_only=True))
hdr = [str(h).split("\n")[0] for h in rows[0]]
df = pd.DataFrame(rows[1:], columns=hdr).replace("", np.nan)
num = lambda c: pd.to_numeric(df[c], errors="coerce")
raw = [h for h in hdr[1:hdr.index("Source")]]

checks = []


def comp(name, exp):
    got = num(name)
    both = got.notna() & exp.notna()
    only = int((got.notna() != exp.notna()).sum())
    diff = float((got[both] - exp[both]).abs().max()) if both.any() else 0.0
    ok = only == 0 and diff < 1e-9
    checks.append(ok)
    if not ok:
        print(f"  CHECK {name}: presence mismatches={only} max|diff|={diff:.2e}")


au, br = num("Iron ore from Australia"), num("Iron ore from Brazil")
comp("Brazil share of iron ore (AU + BR)", (br / (au + br)).where((au + br) > 0))
comp("Guinea share of bauxite", (num("Bauxite from Guinea") / num("Bauxite total")).where(num("Bauxite total") > 0))
for c in raw:
    x = num(c)
    comp(f"{c} 3-mo avg", x.rolling(3, min_periods=3).mean())
    prev = x.shift(12)
    comp(f"{c} YoY", (x / prev - 1).where(prev.notna() & (prev != 0)))
# Parameters: January extra lag and distances (column A label, column C value)
par = {str(r[0]): r[2] for r in wb["Parameters"].iter_rows(values_only=True) if r[0] is not None}
jan_extra = next(v for k, v in par.items() if k.startswith("Extra lag for January"))
dist = {k: v for k, v in par.items() if "->" in k or "(" in k and ": " in k}
NAMES = {"Iron ore": ["Australia", "Brazil", "South Africa", "Canada"], "Bauxite": ["Guinea", "Australia", "Indonesia"]}
for com, origins in NAMES.items():
    d = [next((v for k, v in dist.items() if k.startswith(f"{com}: {o} (")), None) for o in origins]
    h = next(x for x in hdr if x.startswith(f"{com} tonne-mile proxy"))
    if any(v is None for v in d):
        exp = pd.Series(np.nan, index=df.index)
    else:
        q = [num(f"{com} from {o}") for o in origins]
        exp = sum(qi * di for qi, di in zip(q, d))
    comp(h, exp)
print(f"\nDerived columns checked (incl. tonne-mile): {len(checks)}, all equal to pandas: {all(checks)}")

lt = pd.DataFrame(list(wb["Long Table"].iter_rows(values_only=True))[1:],
                  columns=["Series", "Unit", "Source", "ID", "Orig", "Value", "Month", "Lag", "Avail"])
orig = pd.to_datetime(lt.Orig)
expect_days = lt.Lag + np.where(orig.dt.month == 1, jan_extra, 0)
lag_ok = lt.Lag.notna().all() and (pd.to_datetime(lt.Avail) - orig).dt.days.eq(expect_days).all()
print(f"Long Table: {len(lt)} rows; lag values {sorted(lt.Lag.unique())}, January extra {jan_extra}; "
      f"available = original + lag (+ January extra): {lag_ok}")
print("\nRESULT:", "PASS" if bad == 0 and all(checks) and lag_ok else "FAIL")
