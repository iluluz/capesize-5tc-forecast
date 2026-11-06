"""Step A4: quality checks and weekly aggregation.

Weekly rule (same as the Wind Australia + Brazil series): reference week = Monday..Sunday, labelled by
its Sunday (`week_sun`, the Original date); grid label `week_fri` = Sunday + 5 days.
Units: PortWatch import/export are metric tons (dataset description) -> divided by 10,000 (10k t).
Writes data/interim/portwatch_weekly_by_role.csv, portwatch_weekly_chokepoints.csv and qa_checks.txt.
"""
from pw_common import *
import numpy as np

UNIT_DIV = 1e4          # metric tons -> 10k t (unit confirmed in pw_01 from the item description)
TODAY = pd.Timestamp(dt.datetime.now(dt.timezone.utc).date())
qa = []


def log(s=""):
    print(s)
    qa.append(str(s))


daily = pd.read_csv(latest("ports_daily_*.csv"), parse_dates=["date"])
sel = pd.read_csv(INTERIM / "port_selection.csv")
sel = sel[sel.used == 1][["portid", "role"]].drop_duplicates()
d = daily.merge(sel, on="portid")
log(f"ports_daily file: {latest('ports_daily_*.csv').name}; {len(daily)} rows; "
    f"{daily.portid.nunique()} ports")

# --- check 1: continuity per port --------------------------------------------------------------
log("\nCHECK 1  rows vs calendar days per port (gaps = missing dates)")
gaps_all = []
for pid, g in daily.groupby("portid"):
    first, last = g.date.min(), g.date.max()
    span = (last - first).days + 1
    have = g.date.dt.normalize().nunique()
    dup = len(g) - have
    missing = pd.date_range(first, last).difference(g.date.dt.normalize())
    gaps_all += [(pid, m.date()) for m in missing]
    log(f"  {pid:10s} {g.portname.iloc[0][:22]:22s} {first.date()}..{last.date()} "
        f"days={span} rows={len(g)} duplicates={dup} missing={len(missing)}")
log(f"  total missing port-days: {len(gaps_all)}")

# --- check 2: negatives and zeros ---------------------------------------------------------------
log("\nCHECK 2  negative values / zeros")
for c in ["portcalls_dry_bulk", "import_dry_bulk", "export_dry_bulk"]:
    log(f"  {c:20s} negatives={int((daily[c] < 0).sum())}  zeros={int((daily[c] == 0).sum())}  "
        f"nulls={int(daily[c].isna().sum())}")

# --- check 3: recency --------------------------------------------------------------------------
last_date = daily.date.max()
log(f"\nCHECK 3  last available date {last_date.date()}, {(TODAY - last_date).days} days before "
    f"{TODAY.date()} (UTC). Last 3 weekly observations flagged 'may be revised'.")

# --- check 4: rows per port per year -------------------------------------------------------------
log("\nCHECK 4  rows per port per year")
log(daily.pivot_table(index="portid", columns="year", values="date", aggfunc="count").to_string())

# --- weekly aggregation by role --------------------------------------------------------------
def add_weeks(frame):
    frame = frame.copy()
    frame["week_sun"] = (frame["date"] + pd.to_timedelta(6 - frame["date"].dt.day_of_week, unit="D")).dt.normalize()
    frame["week_fri"] = frame["week_sun"] + pd.Timedelta(days=5)
    return frame


d = add_weeks(d)
nports = d.groupby("role")["portid"].nunique().rename("n_ports")
g = (d.groupby(["role", "week_sun", "week_fri"])
       .agg(export=("export_dry_bulk", "sum"), imp=("import_dry_bulk", "sum"),
            calls=("portcalls_dry_bulk", "sum"), rows=("date", "count"))
       .reset_index().merge(nports, on="role"))
g["complete"] = g["rows"] == 7 * g["n_ports"]
for c in ["export", "imp"]:
    g[c] = g[c] / UNIT_DIV
last_weeks = sorted(g[g.complete].week_sun.unique())[-3:]   # the last 3 COMPLETE weeks
g["may_be_revised"] = g.week_sun.isin(last_weeks)
g.to_csv(INTERIM / "portwatch_weekly_by_role.csv", index=False)
log(f"\nweekly by role: {len(g)} rows; incomplete role-weeks: {int((~g.complete).sum())}")
log(g[~g.complete][["role", "week_sun", "rows", "n_ports"]].to_string(index=False))

# spot-check 3 weeks by hand (check 3 of the acceptance list)
log("\nSPOT CHECK  weekly sum recomputed directly from the daily rows")
rng = np.random.default_rng(7)
for _, row in g.sample(3, random_state=7).iterrows():
    mask = (d.role == row.role) & (d.date >= row.week_sun - pd.Timedelta(days=6)) & (d.date <= row.week_sun)
    direct = d.loc[mask, "export_dry_bulk"].sum() / UNIT_DIV
    log(f"  {row.role:9s} Mon {(row.week_sun - pd.Timedelta(days=6)).date()} .. Sun {row.week_sun.date()} "
        f"-> Fri {row.week_fri.date()}: weekly={row.export:.2f} direct={direct:.2f} "
        f"{'OK' if abs(direct - row.export) < 1e-9 else 'MISMATCH'}")

# --- chokepoints -------------------------------------------------------------------------------
ck = pd.read_csv(latest("chokepoints_daily_*.csv"), parse_dates=["date"])
ck = add_weeks(ck)
log(f"\nchokepoints_daily file: {latest('chokepoints_daily_*.csv').name}; {len(ck)} rows")
for pid, gg in ck.groupby("portid"):
    missing = pd.date_range(gg.date.min(), gg.date.max()).difference(gg.date.dt.normalize())
    log(f"  {pid:12s} {gg.portname.iloc[0]:22s} {gg.date.min().date()}..{gg.date.max().date()} "
        f"rows={len(gg)} missing={len(missing)} negatives={int((gg.n_dry_bulk < 0).sum())}")
gc = (ck.groupby(["portid", "portname", "week_sun", "week_fri"])
        .agg(n_dry_bulk=("n_dry_bulk", "sum"), capacity_dry_bulk=("capacity_dry_bulk", "sum"),
             rows=("date", "count")).reset_index())
gc["complete"] = gc["rows"] == 7
gc["may_be_revised"] = gc.week_sun.isin(sorted(gc[gc.complete].week_sun.unique())[-3:])
gc.to_csv(INTERIM / "portwatch_weekly_chokepoints.csv", index=False)
log(f"weekly chokepoints: {len(gc)} rows; incomplete: {int((~gc.complete).sum())}")

(INTERIM / "qa_checks.txt").write_text("\n".join(qa), encoding="utf-8")
