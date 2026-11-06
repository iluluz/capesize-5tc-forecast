"""Step A3: pull the full daily history for the selected ports and the chokepoints.

Ports are pulled one at a time (`portid='...'` is the only filter the service answers reliably),
chokepoints likewise. Each raw file is saved untouched with a UTC stamp.
"""
from pw_common import *

sel = pd.read_csv(INTERIM / "port_selection.csv")
sel = sel[sel["pull"] == 1]          # used ports plus borderline ones a human may switch on
ids = sorted(sel.portid.unique())
fields = ("date,year,month,day,portid,portname,country,ISO3,"
          "portcalls_dry_bulk,import_dry_bulk,export_dry_bulk")

parts = []
for k, pid in enumerate(ids, 1):
    df = cached_query(f"ports_daily_{STAMP[:8]}", pid, PORT_SERVICE, f"portid='{pid}'", fields)
    print(f"  port {k}/{len(ids)} {pid:10s} {df.portname.iloc[0] if len(df) else '-':25s} {len(df):5d} rows",
          flush=True)
    parts.append(df)
daily = pd.concat(parts, ignore_index=True)
p = save_raw(daily, "ports_daily")
print("ports:", len(daily), "rows,", daily.date.min().date(), "to", daily.date.max().date(), "->", p.name)

CHOKEPOINTS = {               # IDs read from the chokepoint list (pw_01 / RUN_LOG)
    "chokepoint7": "Cape of Good Hope",
    "chokepoint1": "Suez Canal",
    "chokepoint4": "Bab el-Mandeb Strait",
    "chokepoint5": "Malacca Strait",
}
ck_parts = []
for cid, name in CHOKEPOINTS.items():
    df = cached_query(f"chokepoints_daily_{STAMP[:8]}", cid, CHOKE_SERVICE, f"portid='{cid}'", "*")
    got = df.portname.iloc[0] if len(df) else "-"
    assert got in ("-", name), f"{cid} is {got}, expected {name}"
    print(f"  {cid:12s} {got:22s} {len(df):5d} rows", flush=True)
    ck_parts.append(df)
ck = pd.concat(ck_parts, ignore_index=True)
p = save_raw(ck, "chokepoints_daily")
print("chokepoints:", len(ck), "rows,", ck.date.min().date(), "to", ck.date.max().date(), "->", p.name)
