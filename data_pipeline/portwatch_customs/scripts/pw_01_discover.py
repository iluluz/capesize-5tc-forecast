"""Step A1: confirm services, field definitions, units and licence; list ports and chokepoints."""
from pw_common import *

# --- which port service works ----------------------------------------------------------------
for cand in ["Daily_Trade_Data", "Daily_Ports_Data"]:
    m = meta(cand)
    print(f"{cand:20s}", "usable" if m.get("fields") else "NOT usable")
m = meta(PORT_SERVICE)
assert m.get("fields"), "Port service not usable"
save_json(m, f"meta_{PORT_SERVICE}")
print("maxRecordCount:", m.get("maxRecordCount"))

# --- item description (holds the unit statement) and licence ---------------------------------
svc = get_json(f"{BASE}/{PORT_SERVICE}/FeatureServer", {"f": "json"})
item = get_json(f"https://www.arcgis.com/sharing/rest/content/items/{svc['serviceItemId']}", {"f": "json"})
save_json(item, f"item_{PORT_SERVICE}")
desc = item.get("description", "")
for key in ["import_dry_bulk:", "export_dry_bulk:", "portcalls_dry_bulk:"]:
    i = desc.find(key)
    print(desc[i:i + 160] if i >= 0 else f"{key} NOT FOUND in description")
print("licence:", item.get("licenseInfo"))

# --- chokepoints: metadata URL fails (table), so read field names from one record -------------
mc = meta(CHOKE_SERVICE)
print("chokepoint metadata fallback used:", mc.get("_fallback", False))
sample = get_json(layer(CHOKE_SERVICE) + "/query",
              {"where": "portid='chokepoint7'", "outFields": "*", "resultRecordCount": 1,
               "returnGeometry": "false", "f": "json"})
save_json(sample, f"sample_{CHOKE_SERVICE}")
print("chokepoint fields:", list(sample["features"][0]["attributes"].keys()))
csvc = get_json(f"{BASE}/{CHOKE_SERVICE}/FeatureServer", {"f": "json"})
citem = get_json(f"https://www.arcgis.com/sharing/rest/content/items/{csvc['serviceItemId']}", {"f": "json"})
save_json(citem, f"item_{CHOKE_SERVICE}")

# --- lists ----------------------------------------------------------------------------------
try:
    chokes = query(CHOKE_SERVICE, fields="portid,portname", distinct=True)
    save_raw(chokes, "chokepoints_list")
    print(len(chokes), "chokepoints")
    print(chokes.to_string(index=False))
except Exception as e:      # service flaky on update days; pw_03 retries the list itself
    print("chokepoint list not retrieved this run:", e)
