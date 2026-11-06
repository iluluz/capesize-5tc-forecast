"""Build outputs/3_Capesize_5TC_PortWatch_Weekly_Data.xlsx from the interim PortWatch files.

Mirrors the teammates' conventions (file 2): week-ending-Friday grid, raw columns dark blue
(1F3864), formula columns light blue (2E75B6), yellow editable release lags looked up by VLOOKUP,
blank = missing, Long Table with estimated available dates, Notes and Source Comparison sheets.
"""
import datetime as dt
import os
import pathlib

import numpy as np
import openpyxl
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from pw_common import INTERIM, RAW, ROOT, latest

OUT = ROOT / "outputs" / "3_Capesize_5TC_PortWatch_Weekly_Data.xlsx"
# folder holding the team workbooks (licensed, not in Git); set CAPESIZE_WORKBOOKS, else the parent folder
TEAM2 = pathlib.Path(os.environ.get("CAPESIZE_WORKBOOKS", ROOT.parent)) / "2.Capesize_5TC_Iron_Ore_Weekly_Data.xlsx"
OUT.parent.mkdir(exist_ok=True)

DARK = PatternFill("solid", fgColor="1F3864")
BLUE = PatternFill("solid", fgColor="2E75B6")
YELLOW = PatternFill("solid", fgColor="FFF2CC")
WHITE = Font(color="FFFFFF", bold=True)
BOLD = Font(bold=True)
SOURCE = "IMF PortWatch"

# --------------------------------------------------------------------------------------------
# 1. load interim data
# --------------------------------------------------------------------------------------------
wk = pd.read_csv(INTERIM / "portwatch_weekly_by_role.csv", parse_dates=["week_sun", "week_fri"])
ck = pd.read_csv(INTERIM / "portwatch_weekly_chokepoints.csv", parse_dates=["week_sun", "week_fri"])
sel = pd.read_csv(INTERIM / "port_selection.csv")
daily_file = latest("ports_daily_*.csv")
ck_file = latest("chokepoints_daily_*.csv")
daily = pd.read_csv(daily_file, parse_dates=["date"])
ck_daily = pd.read_csv(ck_file, parse_dates=["date"])
access_date = dt.datetime.strptime(daily_file.stem.split("_")[-1], "%Y%m%dT%H%M%SZ").date()

# raw series: (column header, unit, role or chokepoint id, field, lag key, indicator id)
SERIES = [
    ("BR iron ore ports exports", "10k t/week", "BR_IRON", "export", "volume"),
    ("AU iron ore ports exports", "10k t/week", "AU_IRON", "export", "volume"),
    ("AU coal ports exports", "10k t/week", "AU_COAL", "export", "volume"),
    ("GN bauxite ports exports", "10k t/week", "GN_BAUX", "export", "volume"),   # dropped 2026-11-04 (role unused)
    ("AU bauxite ports exports (Weipa)", "10k t/week", "AU_BAUX", "export", "volume"),
    ("BR bauxite ports exports (Trombetas)", "10k t/week", "BR_BAUX", "export", "volume"),
    ("ZA ore ports exports", "10k t/week", "ZA_ORE", "export", "volume"),
    ("China main ports imports", "10k t/week", "CN_IMPORT", "imp", "volume"),
    ("Port calls BR iron ore", "calls/week", "BR_IRON", "calls", "count"),
    ("Port calls AU iron ore", "calls/week", "AU_IRON", "calls", "count"),
    ("Port calls China", "calls/week", "CN_IMPORT", "calls", "count"),
    ("Cape of Good Hope dry bulk transits", "count/week", "chokepoint7", "n_dry_bulk", "count"),
    ("Suez dry bulk transits", "count/week", "chokepoint1", "n_dry_bulk", "count"),
    ("Cape of Good Hope dry bulk capacity", "DWT/week", "chokepoint7", "capacity_dry_bulk", "count"),
]
roles_present = set(wk.role)
SERIES = [s for s in SERIES if s[2].startswith("chokepoint") or s[2] in roles_present]

# weekly grid: every Friday from the first PortWatch week to the last
fridays = pd.date_range(min(wk.week_fri.min(), ck.week_fri.min()),
                        max(wk.week_fri.max(), ck.week_fri.max()), freq="W-FRI")
grid = pd.DataFrame({"week_fri": fridays})
long_rows = []
for name, unit, key, field, lagkey in SERIES:
    if key.startswith("chokepoint"):
        src = ck[ck.portid == key]
        ind = f"Daily_Chokepoints_Data:{key}:{field}"
    else:
        src = wk[wk.role == key]
        f_name = {"export": "export_dry_bulk", "imp": "import_dry_bulk", "calls": "portcalls_dry_bulk"}[field]
        ind = f"Daily_Ports_Data:{f_name}:{key}"
    src = src.copy()
    src.loc[~src.complete, field] = np.nan             # incomplete weeks stay blank
    grid = grid.merge(src[["week_fri", field]].rename(columns={field: name}), on="week_fri", how="left")
    for _, r in src.dropna(subset=[field]).iterrows():
        long_rows.append([name, unit, SOURCE, ind, r.week_sun.to_pydatetime(), float(r[field]),
                          r.week_fri.to_pydatetime()])

revised_weeks = set(wk[wk.may_be_revised].week_fri) | set(ck[ck.may_be_revised].week_fri)
grid["May be revised (last 3 weeks)"] = grid.week_fri.isin(revised_weeks).astype(int)
role_complete = wk.pivot_table(index="week_fri", columns="role", values="complete", aggfunc="min")
grid["All port roles complete"] = grid.week_fri.map(role_complete.all(axis=1).astype(int))

# --------------------------------------------------------------------------------------------
# 2. cross-check against the teammates' Wind series (file 2)
# --------------------------------------------------------------------------------------------
def team2_series():
    wb = openpyxl.load_workbook(TEAM2, data_only=True, read_only=True)
    rows = list(wb["Weekly Data"].iter_rows(values_only=True))
    hdr = rows[0]
    df = pd.DataFrame(rows[1:], columns=[str(h) for h in hdr])
    out = pd.DataFrame({"week_fri": pd.to_datetime(df.iloc[:, 0]),
                        "wind_aubr": pd.to_numeric(df.iloc[:, 5], errors="coerce"),
                        "implied_arrivals": pd.to_numeric(df.iloc[:, 10], errors="coerce")})
    return out, str(hdr[5]).replace("\n", " "), str(hdr[10]).replace("\n", " ")


def corr_pair(a, b):
    m = pd.concat([a, b], axis=1).dropna()
    return (m.iloc[:, 0].corr(m.iloc[:, 1]) if len(m) > 10 else np.nan), len(m), m


def avg4(s):
    return s.rolling(4, min_periods=3).mean().where(s.notna())


checks = []
t2, wind_name, arr_name = team2_series()
cmp = grid.merge(t2, on="week_fri", how="left").set_index("week_fri")
if {"BR iron ore ports exports", "AU iron ore ports exports"} <= set(grid.columns):
    pw_aubr = cmp["BR iron ore ports exports"] + cmp["AU iron ore ports exports"]
    c_lvl, n_lvl, m = corr_pair(pw_aubr, cmp.wind_aubr)
    c_4w, n_4w, _ = corr_pair(avg4(pw_aubr), avg4(cmp.wind_aubr))
    ratio = m.iloc[:, 0].mean() / m.iloc[:, 1].mean()
    checks.append(("PortWatch BR_IRON + AU_IRON exports", f"Wind: {wind_name} (file 2, col F)",
                   c_lvl, c_4w, ratio, n_lvl))
if "China main ports imports" in grid.columns:
    c_lvl, n_lvl, m = corr_pair(cmp["China main ports imports"], cmp.implied_arrivals)
    c_4w, n_4w, _ = corr_pair(avg4(cmp["China main ports imports"]), avg4(cmp.implied_arrivals))
    ratio = m.iloc[:, 0].mean() / m.iloc[:, 1].mean()
    checks.append(("PortWatch CN_IMPORT imports", f"{arr_name} (file 2, col K)", c_lvl, c_4w, ratio, n_lvl))
THRESH = 0.8
pd.DataFrame(checks, columns=["portwatch", "teammate", "corr_level", "corr_4wk", "ratio_of_means", "n_weeks"]) \
  .to_csv(INTERIM / "cross_check.csv", index=False)
for c in checks:
    print(f"cross-check {c[0]} vs {c[1]}: level r={c[2]:.3f}, 4-wk r={c[3]:.3f}, ratio={c[4]:.2f}, n={c[5]}")

# --------------------------------------------------------------------------------------------
# 3. workbook
# --------------------------------------------------------------------------------------------
def header(ws, row, labels, fill=DARK, start_col=1):
    for j, lab in enumerate(labels, start=start_col):
        c = ws.cell(row=row, column=j, value=lab)
        c.fill, c.font = fill, WHITE
        c.alignment = Alignment(wrap_text=True, vertical="center")


def widths(ws, w):
    for j, x in enumerate(w, 1):
        ws.column_dimensions[get_column_letter(j)].width = x


wb = Workbook()
ws_notes = wb.active
ws_notes.title = "Notes"

# ---- Weekly Data --------------------------------------------------------------------------
ws = wb.create_sheet("Weekly Data")
raw_cols = [s[0] for s in SERIES] + ["May be revised (last 3 weeks)", "All port roles complete"]
unit_of = {s[0]: s[1] for s in SERIES}
unit_of.update({"May be revised (last 3 weeks)": "1 = yes", "All port roles complete": "1 = yes"})
col = {name: get_column_letter(j) for j, name in enumerate(raw_cols, start=2)}
header(ws, 1, ["Week ending (Fri)"] + [f"{c}\n{unit_of[c]}" for c in raw_cols])
n = len(grid)
records = grid.to_dict("records")
for i, rec in enumerate(records, start=2):
    ws.cell(i, 1, rec["week_fri"].to_pydatetime()).number_format = "yyyy-mm-dd"
    for j, name in enumerate(raw_cols, start=2):
        v = rec[name]
        if pd.notna(v):
            ws.cell(i, j, round(float(v), 4) if "10k" in unit_of[name] else int(v))

derived = []   # (header, formula template using {r}, {r3} (r-3), {r52} (r-52))
B, C = col.get("BR iron ore ports exports"), col.get("AU iron ore ports exports")
first_derived = len(raw_cols) + 2
L = lambda k: get_column_letter(first_derived + k)
if B and C:
    derived += [
        ("AU + BR iron ore exports\n10k t/week", f'=IF(AND(ISNUMBER({B}{{r}}),ISNUMBER({C}{{r}})),{B}{{r}}+{C}{{r}},"")'),
        ("Brazil share of AU + BR\n%", f'=IF(AND(ISNUMBER({B}{{r}}),ISNUMBER({C}{{r}}),{B}{{r}}+{C}{{r}}>0),{B}{{r}}/({B}{{r}}+{C}{{r}}),"")'),
    ]
    k_sum = 0
    derived += [
        ("AU + BR exports 4-wk avg\n10k t/week", f'=IF(AND(ISNUMBER({L(k_sum)}{{r}}),COUNT({L(k_sum)}{{r3}}:{L(k_sum)}{{r}})>=3),AVERAGE({L(k_sum)}{{r3}}:{L(k_sum)}{{r}}),"")'),
    ]
    k_avg = len(derived) - 1
    derived += [
        ("AU + BR 4-wk avg YoY\n%", f'=IF(AND(ISNUMBER({L(k_avg)}{{r}}),ISNUMBER({L(k_avg)}{{r52}})),{L(k_avg)}{{r}}/{L(k_avg)}{{r52}}-1,"")'),
    ]
CN = col.get("China main ports imports")
if CN:
    derived += [("China imports 4-wk avg\n10k t/week", f'=IF(AND(ISNUMBER({CN}{{r}}),COUNT({CN}{{r3}}:{CN}{{r}})>=3),AVERAGE({CN}{{r3}}:{CN}{{r}}),"")')]
    k_cn = len(derived) - 1
    derived += [("China imports 4-wk avg YoY\n%", f'=IF(AND(ISNUMBER({L(k_cn)}{{r}}),ISNUMBER({L(k_cn)}{{r52}})),{L(k_cn)}{{r}}/{L(k_cn)}{{r52}}-1,"")')]
J, K = col.get("Cape of Good Hope dry bulk transits"), col.get("Suez dry bulk transits")
if J and K:
    derived += [("Cape share of Cape + Suez dry bulk transits\n%", f'=IF(AND(ISNUMBER({J}{{r}}),ISNUMBER({K}{{r}}),{J}{{r}}+{K}{{r}}>0),{J}{{r}}/({J}{{r}}+{K}{{r}}),"")')]
    k_cs = len(derived) - 1
    derived += [("Cape share 4-wk avg\n%", f'=IF(AND(ISNUMBER({L(k_cs)}{{r}}),COUNT({L(k_cs)}{{r3}}:{L(k_cs)}{{r}})>=3),AVERAGE({L(k_cs)}{{r3}}:{L(k_cs)}{{r}}),"")')]
header(ws, 1, [h for h, _ in derived], fill=BLUE, start_col=first_derived)
for i in range(2, n + 2):
    for k, (_, f) in enumerate(derived):
        needs3, needs52 = "{r3}" in f, "{r52}" in f
        if (needs3 and i - 3 < 2) or (needs52 and i - 52 < 2):
            ws.cell(i, first_derived + k, "")
            continue
        c = ws.cell(i, first_derived + k, f.format(r=i, r3=i - 3, r52=i - 52))
        if "%" in derived[k][0]:
            c.number_format = "0.0%"
ws.freeze_panes = "B2"
ws.row_dimensions[1].height = 60
widths(ws, [12] + [14] * (len(raw_cols) + len(derived)))

# ---- Release Lags -----------------------------------------------------------------------------
ws_l = wb.create_sheet("Release Lags")
header(ws_l, 1, ["Series", "Unit", "Default release lag (days)", "Note"])
LAG = {"count": (2, "PortWatch publishes on Tuesday, covering the previous week; reference week ends Sunday, so +2 days."),
       "volume": (21, "Trade estimates are revised upward for several days after first release; a 3-week lag is used in published research. Check against your own weekly snapshots.")}
for i, (name, unit, _, _, lagkey) in enumerate(SERIES, start=2):
    ws_l.cell(i, 1, name); ws_l.cell(i, 2, unit)
    ws_l.cell(i, 3, LAG[lagkey][0]).fill = YELLOW
    ws_l.cell(i, 4, LAG[lagkey][1])
n_lag = len(SERIES) + 1
ws_l.cell(n_lag + 2, 1, "Yellow cells are adjustable assumptions; the estimated availability dates in Long Table update automatically.")
widths(ws_l, [38, 12, 14, 100])

# ---- Long Table ------------------------------------------------------------------------------
ws_t = wb.create_sheet("Long Table")
header(ws_t, 1, ["Series", "Unit", "Source", "Indicator ID", "Original date", "Value", "Week ending (Fri)",
                 "Release lag (days)", "Estimated available date"])
long_rows.sort(key=lambda x: (x[0], x[4]))
for i, row in enumerate(long_rows, start=2):
    for j, v in enumerate(row, start=1):
        c = ws_t.cell(i, j, v)
        if j in (5, 7):
            c.number_format = "yyyy-mm-dd"
    ws_t.cell(i, 8, f"=VLOOKUP(A{i},'Release Lags'!$A$2:$C${n_lag},3,FALSE())")
    ws_t.cell(i, 9, f"=E{i}+H{i}").number_format = "yyyy-mm-dd"
ws_t.freeze_panes = "A2"
widths(ws_t, [38, 12, 14, 44, 12, 12, 12, 10, 14])

# ---- Port Selection --------------------------------------------------------------------------
ws_p = wb.create_sheet("Port Selection")
header(ws_p, 1, ["Role", "ISO3", "portid", "portname", "2025 export (10k t)", "2025 import (10k t)",
                 "Used?", "Reason"])
for i, r in enumerate(sel.sort_values(["role", "used", "export_dry_bulk"], ascending=[True, False, False])
                      .itertuples(index=False), start=2):
    vals = [r.role, r.ISO3, r.portid, r.portname, round(r.export_dry_bulk / 1e4, 1),
            round(r.import_dry_bulk / 1e4, 1), "Yes" if r.used == 1 else "No", r.reason]
    for j, v in enumerate(vals, 1):
        ws_p.cell(i, j, v)
ws_p.freeze_panes = "A2"
widths(ws_p, [11, 6, 10, 26, 14, 14, 7, 90])

# ---- Source Comparison -----------------------------------------------------------------------
ws_s = wb.create_sheet("Source Comparison")
header(ws_s, 1, ["Source", "Series", "Original field / service", "Start", "End", "Observations (weeks)",
                 "Used?", "Corr. with teammate series (levels)", "Corr. (4-wk avg)", "Ratio of means", "Note"])
cmp_by = {c[0]: c for c in checks}
rows = []
for name, unit, key, field, lagkey in SERIES:
    s = grid.set_index("week_fri")[name].dropna()
    note, used, cl, c4, rt = "", "Yes", None, None, None
    if name in ("BR iron ore ports exports", "AU iron ore ports exports"):
        c = cmp_by.get("PortWatch BR_IRON + AU_IRON exports")
        if c:
            cl, c4, rt = c[2], c[3], c[4]
            used = "Yes" if c[3] > THRESH else "No (calls only)"
            note = (f"Tested as AU+BR sum vs {c[1]}; rule: use volumes only if 4-wk corr > {THRESH}. "
                    f"Level difference expected: PortWatch dry bulk includes all dry bulk cargo at these ports.")
    elif name == "China main ports imports":
        c = cmp_by.get("PortWatch CN_IMPORT imports")
        if c:
            cl, c4, rt = c[2], c[3], c[4]
            used = "Yes" if c[3] > THRESH else "No (calls only)"
            note = f"Tested vs {c[1]} (a derived series); rule: 4-wk corr > {THRESH}."
    elif lagkey == "volume":
        note = "No teammate series to test against; AIS-derived estimate, revised. Use with caution."
        used = "Candidate"
    rows.append([SOURCE, f"{name} ({unit})", f"{'Daily_Chokepoints_Data' if key.startswith('chokepoint') else 'Daily_Ports_Data'}: {key} {field}",
                 s.index.min().to_pydatetime() if len(s) else None, s.index.max().to_pydatetime() if len(s) else None,
                 len(s), used, cl, c4, rt, note])
rows += [
    [SOURCE, "Bab el-Mandeb and Malacca dry bulk transits", "Daily_Chokepoints_Data: chokepoint4, chokepoint5",
     None, None, None, "Not used", None, None, None, "Pulled into Raw Chokepoints for reference; not in the 5.1 column list."],
    [SOURCE, "Other cargo types (container, tanker, ro-ro, general cargo)", "Daily_Ports_Data", None, None, None,
     "Not used", None, None, None, "Not relevant to Capesize dry bulk."],
    [SOURCE, "PortWatch trade estimates by vessel size", "-", None, None, None, "Not available", None, None, None,
     "PortWatch does not split dry bulk by vessel size (Capesize vs smaller)."],
]
for i, row in enumerate(rows, start=2):
    for j, v in enumerate(row, 1):
        c = ws_s.cell(i, j, v)
        if j in (4, 5) and v is not None:
            c.number_format = "yyyy-mm-dd"
        if j in (8, 9, 10) and isinstance(v, float):
            c.number_format = "0.000"
widths(ws_s, [14, 44, 44, 11, 11, 10, 14, 12, 12, 10, 90])

# ---- Raw sheets ------------------------------------------------------------------------------
def raw_sheet(title, df):
    w = wb.create_sheet(title)
    header(w, 1, list(df.columns))
    for i, row in enumerate(df.itertuples(index=False), start=2):
        for j, v in enumerate(row, 1):
            if isinstance(v, pd.Timestamp):
                w.cell(i, j, v.to_pydatetime()).number_format = "yyyy-mm-dd"
            elif pd.notna(v):
                w.cell(i, j, v.item() if hasattr(v, "item") else v)
    w.freeze_panes = "A2"


rd = daily.merge(sel[sel.used == 1][["portid", "role"]], on="portid", how="left")
raw_sheet("Raw Daily", rd.sort_values(["role", "portid", "date"]))
raw_sheet("Raw Chokepoints", ck_daily.sort_values(["portid", "date"]))

# ---- Notes -----------------------------------------------------------------------------------
last_date = daily.date.max().date()
used = sel[sel.used == 1]
role_lines = [f"• {role}: " + ", ".join(f"{r.portname} ({r.portid})" for r in g.itertuples())
              for role, g in used.groupby("role")]
cc_lines = [f"• {c[0]} vs {c[1]}: correlation of levels {c[2]:.2f}, of 4-week averages {c[3]:.2f}, "
            f"ratio of means {c[4]:.2f} ({c[5]} weeks). Verdict: "
            f"{'use volumes' if c[3] > THRESH else 'keep port calls only'} (rule: 4-wk corr > {THRESH})."
            for c in checks]
notes = [
    ("Capesize 5TC Forecasting — Item 3: IMF PortWatch Dry Bulk Port Activity and Chokepoint Transits (Weekly, Cleaned)", True),
    (f"Source: IMF PortWatch (portwatch.imf.org), ArcGIS REST services Daily_Ports_Data and Daily_Chokepoints_Data; "
     f"accessed {access_date} (UTC); latest daily data {last_date}. Citation: \"Sources: UN Global Platform; IMF PortWatch (portwatch.imf.org).\" "
     f"Terms: https://www.imf.org/external/terms.htm", False),
    ("", False),
    ("Sheets", True),
    ("Weekly Data: the selected series aligned to a week-ending-Friday grid from the first PortWatch week; blue-header columns on the right are formula-based derived features.", False),
    ("Long Table: one row per weekly observation, keeping the original date (the Sunday that ends the reference week), source, indicator ID and estimated available date, for point-in-time alignment.", False),
    ("Release Lags: release lag assumptions for each series (yellow cells are editable).", False),
    ("Port Selection: every candidate port with its role, 2025 volumes, whether it is used and why.", False),
    ("Source Comparison: all candidate series, with the cross-checks against the teammates' Wind series and the verdicts.", False),
    ("Raw Daily / Raw Chokepoints: unadjusted daily rows as downloaded. Updating the workbook only requires re-running the scripts.", False),
    ("", False),
    ("Ports per role", True),
] + [(x, False) for x in role_lines] + [
    ("", False),
    ("Cleaning method", True),
    ("1. Daily rows are pulled per port; port-days with no record stay missing (never filled). Genuine zeros (no vessel that day) are kept.", False),
    ("2. Weekly aggregation: reference week Monday–Sunday, labelled by its Sunday (Original date); the grid label Week ending (Fri) is Sunday + 5 days, the same rule as the Wind Australia + Brazil shipments series.", False),
    ("3. A role-week is kept only if every port in the role has all 7 days; incomplete weeks are left blank. 'All port roles complete' shows this per grid week.", False),
    ("4. Units: PortWatch import/export estimates are in metric tons (stated in the dataset description); divided by 10,000 to give 10k t, as in the teammates' files.", False),
    ("5. Chokepoint transits are weekly sums of daily dry bulk vessel counts (n_dry_bulk) and their capacity (capacity_dry_bulk, deadweight tonnes).", False),
    ("", False),
    ("Derived features (formulas)", True),
    ("• AU + BR iron ore exports = BR + AU iron ore ports exports; Brazil share = BR / (AU + BR).", False),
    ("• 4-week averages require at least 3 of the last 4 weeks; YoY compares with the value 52 weeks earlier.", False),
    ("• Cape share = Cape of Good Hope / (Cape of Good Hope + Suez) dry bulk transits, a rerouting signal (Red Sea).", False),
    ("", False),
    ("Cross-checks", True),
] + [(x, False) for x in cc_lines] + [
    ("", False),
    ("Points to note", True),
    ("• PortWatch dry bulk is not split by vessel size: it includes Panamax, Supramax and smaller ships, and all dry bulk cargo at these ports (e.g. grains at Brazilian ports).", False),
    ("• Trade volumes are AIS-derived estimates (draft change × deadweight) and are revised after first publication. The history in this workbook is the REVISED version, so backtests carry look-ahead bias that the 21-day volume lag only partly removes. Save a full re-download every week (same scripts) to build real-time vintages.", False),
    ("• The last 3 weekly observations are flagged 'may be revised'.", False),
    ("• PortWatch data start on 2019-01-01, so the joint sample with the 5TC/FFA features is about 2019–2026.", False),
    ("• Release lags are assumptions; check actual release times and edit them.", False),
    ("• Blank formula results are empty text (\"\"); convert to numeric after reading with pandas.", False),
]
for i, (text, bold) in enumerate(notes, start=1):
    c = ws_notes.cell(i, 1, text)
    if bold:
        c.font = BOLD
ws_notes.column_dimensions["A"].width = 160

wb.save(OUT)
print("wrote", OUT, f"({n} weeks, {len(long_rows)} long-table rows)")
