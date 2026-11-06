"""Sailing distances load port -> Qingdao for the tonne-mile proxy (workbook 6, Parameters).

Method: searoute (Python, Apache-2.0; shortest path on the Eurostat SeaRoute / MARNET maritime network) between
PortWatch port coordinates (ports_database raw file). Capesize routing: Panama and Suez excluded (Capesizes do
not transit Panama; Suez is rarely used and avoided since the Red Sea crisis), so Atlantic origins go via the
Cape of Good Hope. Writes the distances into config/customs_parameters.csv (load_port, distance_nm, source,
access_date) and prints alternatives for reference.
"""
import datetime as dt
import pathlib

import pandas as pd
import searoute as sr

ROOT = pathlib.Path(__file__).resolve().parents[1]
DB = sorted((ROOT / "data" / "raw" / "portwatch").glob("ports_database_*.csv"))[-1]
CFG = ROOT / "config" / "customs_parameters.csv"
db = pd.read_csv(DB).set_index("portid")

DEST = "port1069"   # Qingdao Port
CHOICE = {          # (commodity, origin) -> representative load port (PortWatch portid)
    ("IO", "AU"): "port955",    # Port Hedland
    ("IO", "BR"): "port1328",   # Tubarao (Baltic C3 benchmark load port)
    ("IO", "ZA"): "port1133",   # Saldanha Bay
    ("IO", "CA"): "port1181",   # Sept-Iles
    ("BX", "GN"): "port536",    # Kamsar
    ("BX", "AU"): "port1387",   # Weipa
    ("BX", "ID"): "port925",    # Pontianak (West Kalimantan; proxy for Ketapang/Kendawangan)
}
ALTERNATIVES = ["port506", "port938"]   # Itaqui (Ponta da Madeira), Port Cartier - printed only
RESTRICT = ["panama", "suez", "northwest", "northeast"]


def dist(pid):
    o, d = db.loc[pid], db.loc[DEST]
    route = sr.searoute([o.lon, o.lat], [d.lon, d.lat], units="naut", restrictions=RESTRICT)
    return round(route.properties["length"]), route.properties.get("traversed_passages", "")


cfg = pd.read_csv(CFG, dtype=str).fillna("")
today = dt.date.today().isoformat()
for (com, org), pid in CHOICE.items():
    nm, via = dist(pid)
    name = db.loc[pid, "portname"]
    print(f"{com} {org}: {name} -> Qingdao = {nm} nm  passages={via}")
    m = (cfg.commodity == com) & (cfg.origin == org)
    cfg.loc[m, "load_port"] = name
    cfg.loc[m, "distance_nm"] = str(nm)
    cfg.loc[m, "source"] = (f"searoute 1.6.0 (Eurostat MARNET network), PortWatch port coordinates "
                            f"({DB.name}); Panama/Suez excluded")
    cfg.loc[m, "access_date"] = today
for pid in ALTERNATIVES:
    nm, via = dist(pid)
    print(f"alternative: {db.loc[pid, 'portname']} -> Qingdao = {nm} nm  passages={via}")
cfg.to_csv(CFG, index=False)
print("updated", CFG)
