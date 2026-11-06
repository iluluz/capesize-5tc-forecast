"""Step A2: rank 2025 dry bulk volumes by port and match ports to roles.

Deviation from the handoff: `Daily_Ports_Data` rejects/times out on `ISO3 IN (...)` filters
(full-table scans), so the candidate list comes from the small `PortWatch_ports_database` table and
2025 daily data is pulled by `portid` in small batches.

Outputs
  data/interim/ports_database.csv            all ~2,065 ports with country, industry, vessel counts
  data/interim/port_ranking_2025.csv         2025 sums for candidate ports
  data/interim/port_selection_candidates.csv regex matches per role (for human review)
"""
import sys

from pw_common import *

COUNTRIES = ["BRA", "AUS", "GIN", "ZAF", "CHN"]
ROLES = {   # role: (ISO3, name regex); names are hints, verified against the ranking below
    "BR_IRON":   ("BRA", r"tubar|vitoria|vitória|madeira|sao luis|são luís|itaqui|itaguai|itaguaí|sepetiba|guaiba|guaíba|ponta da|ubu|acu|açu"),
    "AU_IRON":   ("AUS", r"hedland|dampier|walcott|lambert"),
    "AU_COAL":   ("AUS", r"hay point|dalrymple|newcastle|gladstone|abbot"),
    "GN_BAUX":   ("GIN", r"kamsar|conakry|bok|dapilon|kassa"),
    "ZA_ORE":    ("ZAF", r"saldanha|richards"),
    "CN_IMPORT": ("CHN", r"qingdao|rizhao|caofeidian|jingtang|tangshan|qinhuangdao|lianyungang|dalian|tianjin|zhoushan|ningbo|zhanjiang|yantai"),
}

# --- 1. port list ---------------------------------------------------------------------------
if (INTERIM / "ports_database.csv").exists():          # resume: list already fetched
    ports = pd.read_csv(INTERIM / "ports_database.csv")
else:
    ports = query("PortWatch_ports_database",
                  fields="portid,portname,country,ISO3,fullname,lat,lon,vessel_count_dry_bulk,"
                         "industry_top1,industry_top2,industry_top3,share_country_maritime_export,"
                         "share_country_maritime_import,LOCODE")
    save_raw(ports, "ports_database")
    ports.to_csv(INTERIM / "ports_database.csv", index=False)
print(len(ports), "ports in PortWatch_ports_database")

cand = ports[ports.ISO3.isin(COUNTRIES)].copy()
cand["role_hint"] = ""
for role, (iso, pat) in ROLES.items():
    hit = (cand.ISO3 == iso) & cand.portname.str.contains(pat, case=False, regex=True)
    cand.loc[hit, "role_hint"] = role
top = (cand.sort_values("vessel_count_dry_bulk", ascending=False)
           .groupby("ISO3").head(12))                       # context: the biggest dry bulk ports
cand = cand[(cand.role_hint != "") | cand.portid.isin(top.portid)]
print(len(cand), "candidate ports:", cand.groupby("ISO3").size().to_dict())

# --- 2. 2025 daily data for the candidates, in batches of 5 ports -----------------------------
fields = "date,year,portid,portname,ISO3,portcalls_dry_bulk,import_dry_bulk,export_dry_bulk"
ids = list(cand.portid)
parts = []
for k, pid in enumerate(ids, 1):     # one port per request: multi-port IN filters fail often
    part = cached_query("ranking_2025", pid, PORT_SERVICE, f"portid='{pid}' AND year=2025", fields)
    print(f"  {k}/{len(ids)} {pid}: {len(part)} rows", flush=True)
    parts.append(part)
df = pd.concat(parts, ignore_index=True)
save_raw(df, "ports_2025_ranking_pull")

rank = (df.groupby(["ISO3", "portid", "portname"])
          .agg(export_dry_bulk=("export_dry_bulk", "sum"), import_dry_bulk=("import_dry_bulk", "sum"),
               portcalls_dry_bulk=("portcalls_dry_bulk", "sum"), days=("date", "nunique"))
          .reset_index()
          .merge(cand[["portid", "role_hint", "industry_top1", "industry_top2", "fullname"]], on="portid"))
rank.to_csv(INTERIM / "port_ranking_2025.csv", index=False)

for role, (iso, _) in ROLES.items():
    key = "import_dry_bulk" if role == "CN_IMPORT" else "export_dry_bulk"
    sub = rank[rank.ISO3 == iso].sort_values(key, ascending=False)
    print(f"\n== {iso}: candidates ranked by 2025 {key} (Mt); role hint {role} ==")
    show = sub.assign(export_Mt=sub.export_dry_bulk / 1e6, import_Mt=sub.import_dry_bulk / 1e6)
    print(show[["portid", "portname", "role_hint", "export_Mt", "import_Mt", "portcalls_dry_bulk",
                "days", "industry_top1"]].to_string(index=False, float_format="%.1f"))
rank[rank.role_hint != ""].to_csv(INTERIM / "port_selection_candidates.csv", index=False)
