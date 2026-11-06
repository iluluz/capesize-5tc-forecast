"""Step A2b: the port selection decision, written to data/interim/port_selection.csv.

Decided from data/interim/port_ranking_2025.csv (printed by pw_02). `used` = goes into the weekly
role aggregates; `pull` = full history is downloaded (also for borderline ports, so a human can flip
`used` without re-downloading). Edit USED/EXCLUDED and rerun pw_02b -> pw_04 -> build_workbooks.
"""
from pw_common import *

rank = pd.read_csv(INTERIM / "port_ranking_2025.csv")

# role -> {portid: reason}
USED = {
    "BR_IRON": {
        "port506":  "Itaqui / Ponta da Madeira (Vale northern system, Carajas ore); largest BR dry bulk exporter",
        "port1328": "Tubarao (Vale southeastern system iron ore and pellets)",
        "port2045": "Itaguai (Sepetiba bay iron ore terminals: Vale CPBS, CSN TECAR). Also imports coal",
        "port422":  "Guaiba Island terminal (Vale iron ore)",
        "port166":  "Porto do Acu (Anglo American Minas-Rio iron ore)",
        "port2368": "Ponta Ubu (Samarco iron ore pellets)",
    },
    "AU_IRON": {
        "port955": "Port Hedland (BHP, FMG, Roy Hill iron ore)",
        "port981": "Port Walcott / Cape Lambert (Rio Tinto iron ore)",
        "port276": "Dampier (Rio Tinto iron ore)",
    },
    "AU_COAL": {
        "port816": "Newcastle (thermal coal)",
        "port458": "Hay Point incl. Dalrymple Bay (metallurgical coal)",
        "port398": "Gladstone (coal; also alumina/bauxite imports)",
        "port0":   "Abbot Point (coal)",
    },
    "AU_BAUX": {
        "port1387": "Weipa (Rio Tinto bauxite, Cape York); added by human decision 2026-11-04",
    },
    "BR_BAUX": {
        "port2373": "Trombetas / Porto Trombetas (MRN bauxite); added by human decision 2026-11-04",
    },
    "ZA_ORE": {
        "port1133": "Saldanha Bay (Sishen iron ore)",
        "port1099": "Richards Bay (mainly thermal coal) - mixed with iron ore under this role, per the handoff regex",
    },
    "CN_IMPORT": {
        "port1069": "Qingdao", "port1105": "Rizhao", "port1195": "Caofeidian (Shougang Jingtang terminal)",
        "port1266": "Tangshan Jingtang", "port1297": "Tianjin", "port644": "Lianyungang",
        "port273": "Dalian", "port1429": "Zhoushan (Majishan, Shulanghu ore transshipment)",
        "port824": "Ningbo", "port1426": "Zhanjiang", "port1410": "Yantai",
        "port154": "Huanghua (87 Mt imports in 2025; iron ore terminal); added by human decision 2026-11-04",
        "port632": "Lanqiao Port (113 Mt imports in 2025); added by human decision 2026-11-04",
    },
}
# pulled but not used
BORDERLINE = {
    "port536":  ("GN_BAUX",   "DROPPED (human decision 2026-11-04): Kamsar - most Guinean bauxite is loaded by offshore "
                              "transshipment and is not captured (~15 Mt/yr here vs ~180 Mt exported)"),
    "port258":  ("GN_BAUX",   "DROPPED (human decision 2026-11-04): Conakry - same Guinea under-count"),
    "port1072": ("CN_IMPORT", "Not used: Qinhuangdao - coal export port, ~0 imports in 2025"),
    "port1368": ("BR_IRON",   "Not used: Vitoria - general port (0.6 Mt exports); the ore terminal is Tubarao"),
}
EXCLUDED_NOTE = {   # the rest of the candidates, for the Port Selection sheet
    "BRA": "Not used: grain/soy, general cargo or other non-iron-ore port",
    "AUS": "Not used: not an iron ore or coal export port",
    "GIN": "Not used: negligible 2025 dry bulk exports",
    "ZAF": "Not used: general/container port with small dry bulk volumes",
    "CHN": "Not used: not on the handoff hint list (river/Yangtze or general port)",
}

rows = []
for role, ports in USED.items():
    for pid, why in ports.items():
        rows.append({"portid": pid, "role": role, "used": 1, "pull": 1, "reason": why})
for pid, (role, why) in BORDERLINE.items():
    rows.append({"portid": pid, "role": role, "used": 0, "pull": 1, "reason": why})
dec = pd.DataFrame(rows)
missing = set(dec.portid) - set(rank.portid)
assert not missing, f"portids not in the ranking: {missing}"

rest = rank[~rank.portid.isin(dec.portid)][["portid", "ISO3"]].copy()
rest["role"] = "-"
rest["used"], rest["pull"] = 0, 0
rest["reason"] = rest.ISO3.map(EXCLUDED_NOTE)
out = pd.concat([dec, rest.drop(columns="ISO3")]).merge(
    rank[["portid", "portname", "ISO3", "export_dry_bulk", "import_dry_bulk", "portcalls_dry_bulk"]], on="portid")
out.to_csv(INTERIM / "port_selection.csv", index=False)
print(out[out.pull == 1].groupby(["role", "used"]).portname.apply(list).to_string())
