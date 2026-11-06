"""Shared helpers for the IMF PortWatch (ArcGIS REST) pulls.

Deviations from the handoff document (see RUN_LOG.md):
  * the port service is `Daily_Ports_Data` (`Daily_Trade_Data` returns "Item does not exist").
  * `Daily_Chokepoints_Data` is published as a *table*; its layer-metadata URL returns
    "Invalid URL" while /query works, so `meta()` falls back to defaults.
"""
import json
import pathlib
import random
import time
import datetime as dt

import pandas as pd
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
BASE = "https://services9.arcgis.com/weJ1QsnbMYJlCHdG/arcgis/rest/services"
RAW = ROOT / "data" / "raw" / "portwatch"
INTERIM = ROOT / "data" / "interim"
RAW.mkdir(parents=True, exist_ok=True)
INTERIM.mkdir(parents=True, exist_ok=True)
STAMP = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

PORT_SERVICE = "Daily_Ports_Data"
CHOKE_SERVICE = "Daily_Chokepoints_Data"
SLEEP = 0.5          # seconds between calls (ground rule 3)
HEADERS = {"User-Agent": "capesize-5tc-research/1.0 (academic project)"}

_DEFAULT_META = {"maxRecordCount": 1000, "objectIdField": "ObjectId"}


def layer(service, idx=0):
    return f"{BASE}/{service}/FeatureServer/{idx}"


def get_json(url, params, timeout=120, tries=20):
    # The chokepoint service intermittently answers "Invalid URL" (seen on 2026-11-03, a Tuesday
    # update day): identical requests fail and then succeed, so transient errors are retried.
    for attempt in range(tries):
        try:
            r = requests.get(url, params=params, timeout=timeout, headers=HEADERS)
            r.raise_for_status()
            js = r.json()
            if "error" in js:
                raise RuntimeError(js["error"])
            return js
        except Exception as e:                       # network hiccup: back off and retry
            if attempt == tries - 1:
                raise
            print(f"   retry {attempt + 1} after error: {e}")
            # failures are random (load-balanced nodes), not load-related: short waits work best
            time.sleep(3 + random.random() * 2)


_META_CACHE = {}


def meta(service, idx=0):
    """Layer metadata (cached); tables whose metadata URL fails get sensible defaults."""
    if (service, idx) not in _META_CACHE:
        try:
            _META_CACHE[(service, idx)] = get_json(layer(service, idx), {"f": "json"}, timeout=60, tries=3)
        except Exception:
            _META_CACHE[(service, idx)] = dict(_DEFAULT_META, _fallback=True)
    return _META_CACHE[(service, idx)]


def query(service, where="1=1", fields="*", idx=0, distinct=False, order=None, sleep=SLEEP,
          count_check=True):
    """Page through a query. Stops on a short page (fewer rows than the page size), which does
    not depend on the count endpoint; the count is fetched only as a cross-check."""
    url = layer(service, idx) + "/query"
    m = meta(service, idx)
    page = int(m.get("maxRecordCount", 1000))
    oid = m.get("objectIdField", "ObjectId")
    base = {"where": where, "f": "json", "returnGeometry": "false"}
    if distinct:
        base["returnDistinctValues"] = "true"
    cnt = None
    if count_check and not distinct:
        try:
            cnt = get_json(url, {**base, "returnCountOnly": "true"}, tries=3)["count"]
        except Exception as e:
            print(f"   count unavailable ({e}); paging without it")
    rows, off = [], 0
    while True:
        p = {**base, "outFields": fields, "resultOffset": off, "resultRecordCount": page}
        p["orderByFields"] = order or (fields if distinct else oid)
        js = get_json(url, p)
        feats = js.get("features", [])
        rows += [f["attributes"] for f in feats]
        off += len(feats)
        time.sleep(sleep)
        if len(feats) < page and not js.get("exceededTransferLimit"):
            break
    df = pd.DataFrame(rows)
    if "date" in df.columns:
        if pd.api.types.is_numeric_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"], unit="ms")
        else:
            df["date"] = pd.to_datetime(df["date"])
    if cnt is not None and len(df) != cnt:
        print(f"   WARNING: expected {cnt} rows, got {len(df)}")
    return df


def cached_query(tag, key, service, where, fields, rounds=4):
    """Run `query` once per key and cache the result in data/interim/cache/<tag>/<key>.csv, so a
    rerun after a server failure only fetches what is still missing. Each round retries 8 times;
    between rounds we wait a minute."""
    cache = INTERIM / "cache" / tag
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{key}.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["date"]) if path.stat().st_size > 1 else pd.DataFrame()
    for r in range(rounds):
        try:
            df = query(service, where, fields, count_check=False)
            df.to_csv(path, index=False)
            return df
        except Exception as e:
            print(f"   round {r + 1}/{rounds} failed for {key}: {e}", flush=True)
            time.sleep(60)
    raise RuntimeError(f"giving up on {key}; rerun the script later to resume")


def save_raw(df, name):
    path = RAW / f"{name}_{STAMP}.csv"
    df.to_csv(path, index=False)
    return path


def save_json(obj, name):
    path = RAW / f"{name}_{STAMP}.json"
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def latest(pattern):
    files = sorted(RAW.glob(pattern))
    if not files:
        raise FileNotFoundError(pattern)
    return files[-1]
