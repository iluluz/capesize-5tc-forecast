"""Task B (customs) - UN Comtrade: China (reporter 156) monthly imports by origin, HS 2601/2606/2701/2702.

Two modes:
  * no COMTRADE_KEY  -> keyless public preview endpoint (tested 2026-11-04): ONE period per call,
                        max 500 records, rate-limited (HTTP 429 when calls are < ~10 s apart).
  * COMTRADE_KEY set -> keyed endpoint (free key from comtradeplus.un.org), 12 periods per call.

Findings 2026-11-04: China monthly by-partner data exist on Comtrade up to 2024-12; 2025 months returned
0 records (not yet reported). Recent months must come from Wind/Choice/iFinD or the customs platform.
netWgt is in kg; primaryValue in USD. The World row (partner 0) sometimes has netWgt = null.

Every response is saved untouched to data/raw/customs/. Resumable: periods already saved are skipped.
Usage: python cu_01_fetch.py [first_year] [last_year]     (default 2014 2024)
"""
import datetime as dt
import json
import os
import pathlib
import re
import sys
import time

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "customs"
RAW.mkdir(parents=True, exist_ok=True)

KEY = os.environ.get("COMTRADE_KEY")
CMD = "2601,2606,2701,2702"          # iron ore, bauxite, coal, lignite
Y0, Y1 = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) == 3 else (2014, 2024)
SLEEP = 3 if KEY else 15


def stamp():
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def get(params, url, headers):
    attempt = 0
    while attempt < 8:
        try:
            r = requests.get(url, params=params, headers=headers, timeout=120)
        except requests.exceptions.RequestException as e:   # DNS / connection drop: wait and retry
            attempt += 1
            print(f"   network error ({type(e).__name__}); waiting 120s", flush=True)
            time.sleep(120)
            continue
        if r.status_code == 200:
            return r.json()
        m = re.search(r"replenished in (\d+):(\d+):(\d+)", r.text)
        if r.status_code == 403 and m:                 # call-volume quota (~50 calls per window): wait it out
            wait = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + 60
            print(f"   quota exhausted; sleeping {wait}s until it is replenished", flush=True)
            time.sleep(wait)
            continue
        attempt += 1
        wait = 60 * attempt if r.status_code == 429 else 20
        print(f"   HTTP {r.status_code}: {r.text[:120]!r}; waiting {wait}s")
        time.sleep(wait)
    raise SystemExit("giving up; rerun later (resumable)")


done = {p.name.split("_")[2] for p in RAW.glob("comtrade_CN_*_*.json")}
if KEY:
    url, headers = "https://comtradeapi.un.org/data/v1/get/C/M/HS", {"Ocp-Apim-Subscription-Key": KEY}
    batches = [[f"{y}{m:02d}" for m in range(1, 13)] for y in range(Y0, Y1 + 1)]
else:
    url, headers = "https://comtradeapi.un.org/public/v1/preview/C/M/HS", {}
    batches = [[f"{y}{m:02d}"] for y in range(Y0, Y1 + 1) for m in range(1, 13)]

for periods in batches:
    tag = periods[0] if len(periods) == 1 else f"{periods[0][:4]}all"
    if tag in done:
        continue
    js = get({"reporterCode": 156, "flowCode": "M", "cmdCode": CMD, "period": ",".join(periods)}, url, headers)
    (RAW / f"comtrade_CN_{tag}_{stamp()}.json").write_text(json.dumps(js), encoding="utf-8")
    n = len(js.get("data", []))
    print(tag, n, "records", "(LIMIT REACHED - split the call)" if n >= 500 else "", flush=True)
    time.sleep(SLEEP)
print("done")
