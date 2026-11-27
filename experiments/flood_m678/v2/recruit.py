"""
M6–M8 v2 step 1b: event leads from open sources (metadata only), normalised to leads.csv.

    python -m experiments.flood_m678.v2.recruit <source|all>     # resumable; caches raw downloads

Sources (SELECTION.md §6), each an adapter yielding normalised lead rows:
  usgs_peaks  USGS annual peaks, qualification code 3 (dam failure) -> M7, 9 (snowmelt/ice jam/...) -> M8
  wsc_ice     WSC annual maximum water levels flagged "Ice Conditions" -> M8 ice_jam
  wsc_melt    WSC annual maximum water levels in March-July without an ice flag -> M8 sustained_melt
  crid        CRID spring break-up peak (HM) -> M8 ice_jam (1984-2015)
  dfo         DFO cause-matched records (dam/levee -> M7, snowmelt/ice -> M8), from v1's pinned extract
  glof        GLOF v4.2 lake outbursts -> M6 water_release (debris_runout when the record says debris)

Gauge leads need an overbank proxy fixed in advance (no flood stage is published for most
stations): the peak must reach the station's 80th percentile of annual maxima since 1984
(~5-year level). Imagery era only: 1984 onward. Downloads stop when free disk < 15 GB.
"""
from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.expanduser("~/.cache/geowatch/m678v2/sources")
OUT = os.path.join(HERE, "leads.csv")
YIELD = os.path.join(HERE, "yield_leads.json")
FIELDS = ("lead_id", "source", "source_row", "type", "submode", "cause", "date", "crest_local", "crest_kind",
          "lat", "lon", "anchor", "country", "region", "peak_value", "peak_unit", "station_p80")
MIN_YEAR = 1984
P_OVERBANK = 80
STATES = ("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC "
          "ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY PR").split()


def disk_ok():
    return shutil.disk_usage(os.path.expanduser("~")).free / 1e9 >= 15


def fetch(url, path, tries=3):
    if os.path.exists(path):
        return path
    if not disk_ok():
        raise SystemExit("free disk below 15 GB: downloads stopped (owner rule)")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "geowatch-research/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                data = r.read()
            with open(path + ".tmp", "wb") as fh:
                fh.write(data)
            os.replace(path + ".tmp", path)
            return path
        except Exception as e:      # noqa: BLE001
            print(f"fetch {url[:90]}: {type(e).__name__} {str(e)[:80]}", flush=True)
            time.sleep(10 * (k + 1))
    return None


def p80(vals):
    v = [x for x in vals if x is not None and np.isfinite(x)]
    return float(np.percentile(v, P_OVERBANK)) if len(v) >= 8 else None


# ------------------------------------------------------------------ USGS
def _rdb(text):
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    if len(lines) < 2:
        return []
    head = lines[0].split("\t")
    return [dict(zip(head, ln.split("\t"))) for ln in lines[2:]]


def usgs_peaks():
    for st in STATES:
        pk = fetch(f"https://nwis.waterdata.usgs.gov/nwis/peak?state_cd={st.lower()}&group_key=NONE&format=rdb",
                   os.path.join(SRC, "usgs", f"peak_{st}.rdb"))
        sites = fetch(f"https://waterservices.usgs.gov/nwis/site/?format=rdb&stateCd={st.lower()}&siteType=ST",
                      os.path.join(SRC, "usgs", f"site_{st}.rdb"))
        if not pk or not sites:
            continue
        loc = {r["site_no"]: (r.get("dec_lat_va"), r.get("dec_long_va"), r.get("station_nm")) for r in
               _rdb(open(sites, encoding="utf-8", errors="replace").read())}
        rows = _rdb(open(pk, encoding="utf-8", errors="replace").read())
        by = {}
        for r in rows:
            by.setdefault(r["site_no"], []).append(r)
        for site, rs in by.items():
            def gh(r):
                try:
                    return float(r.get("gage_ht") or "nan")
                except ValueError:
                    return float("nan")
            recent = [r for r in rs if (r.get("peak_dt") or "")[:4].isdigit() and int(r["peak_dt"][:4]) >= MIN_YEAR]
            thr = p80([gh(r) for r in recent])
            for r in recent:
                codes = (r.get("peak_cd") or "").replace(" ", "").split(",")
                kind = "M7" if "3" in codes else "M8" if "9" in codes else None
                if not kind or "-00" in r["peak_dt"]:
                    continue
                g = gh(r)
                if kind == "M8" and (thr is None or not np.isfinite(g) or g < thr):
                    continue
                lat, lon, name = loc.get(site, (None, None, ""))
                yield {"source": "usgs_peaks", "source_row": f"{site}:{r['peak_dt']}", "type": kind,
                       "submode": "reservoir_breach" if kind == "M7" else "", "cause": f"USGS peak code {r.get('peak_cd')}",
                       "date": r["peak_dt"], "crest_local": r["peak_dt"] + (" " + r["peak_tm"] if r.get("peak_tm") else ""),
                       "crest_kind": "agency_crest_day", "lat": lat, "lon": lon, "anchor": f"USGS {site} {name}",
                       "country": "USA", "region": st, "peak_value": r.get("gage_ht"), "peak_unit": "ft",
                       "station_p80": thr}


# ------------------------------------------------------------------ WSC
def _wsc_all():
    path = os.path.join(SRC, "wsc", "annual_peaks.json")
    if not os.path.exists(path):
        feats, off = [], 0
        while True:
            u = (f"https://api.weather.gc.ca/collections/hydrometric-annual-peaks/items?f=json&limit=10000&offset={off}"
                 "&DATA_TYPE_EN=Water%20Level&PEAK_CODE_EN=Maximum")
            p = fetch(u, os.path.join(SRC, "wsc", f"page_{off}.json"))
            d = json.load(open(p))
            feats += d["features"]
            if len(d["features"]) < 10000:
                break
            off += 10000
        json.dump(feats, open(path, "w"))
    return json.load(open(path))


def _wsc(kind):
    by = {}
    for f in _wsc_all():
        p = f["properties"]
        if p.get("DATE") and p.get("PEAK") is not None and p["DATE"][:4].isdigit() and int(p["DATE"][:4]) >= MIN_YEAR:
            by.setdefault(p["STATION_NUMBER"], []).append(f)
    for stn, fs in by.items():
        thr = p80([f["properties"]["PEAK"] for f in fs])
        for f in fs:
            p = f["properties"]
            ice = (p.get("SYMBOL_EN") or "").lower().startswith("ice")
            month = int(p["DATE"][5:7])
            if kind == "ice" and not ice:
                continue
            if kind == "melt" and (ice or not 3 <= month <= 7):
                continue
            if thr is None or p["PEAK"] < thr:
                continue
            lon, lat = f["geometry"]["coordinates"][:2]
            yield {"source": f"wsc_{kind}", "source_row": f"{stn}:{p['DATE']}", "type": "M8",
                   "submode": "ice_jam" if kind == "ice" else "sustained_melt",
                   "cause": "WSC annual maximum water level" + (", Ice Conditions" if ice else ", open water, Mar-Jul"),
                   "date": p["DATE"][:10], "crest_local": f"{p['DATE']} UTC{float(p['TIMEZONE_OFFSET']):+g}" if p.get("TIMEZONE_OFFSET") is not None else f"{p['DATE']} (offset unknown)",
                   "crest_kind": "agency_crest_reading" if p.get("TIMEZONE_OFFSET") is not None else "agency_crest_day",
                   "lat": lat, "lon": lon, "anchor": f"WSC {stn} {p['STATION_NAME']}",
                   "country": "Canada", "region": p["PROV_TERR_STATE_LOC"], "peak_value": p["PEAK"], "peak_unit": "m",
                   "station_p80": thr}


def wsc_ice():
    return _wsc("ice")


def wsc_melt():
    return _wsc("melt")


# ------------------------------------------------------------------ CRID
def _iso(d):
    """CRID dates are M/D/YYYY (some ISO)."""
    d = (d or "").strip()
    if not d:
        return None
    if "/" in d:
        m, dd, y = d.split("/")
        return f"{int(y):04d}-{int(m):02d}-{int(dd):02d}"
    return d[:10] if d[:4].isdigit() else None


def crid():
    path = os.path.join(SRC, "crid", "CRID_BDCGF_v5.csv")
    rows = list(csv.reader(open(path, encoding="utf-8-sig", errors="replace")))
    codes = rows[29]
    ix = {c: i for i, c in enumerate(codes)}
    data = [r for r in rows[31:] if r and r[0]]
    by = {}
    for r in data:
        by.setdefault(r[0], []).append(r)

    def num(x):
        try:
            return float(x)
        except ValueError:
            return float("nan")
    for stn, rs in by.items():
        hm = [num(r[ix["HM_EXT_WL"]]) for r in rs if r[ix["START"]].isdigit() and int(r[ix["START"]]) >= MIN_YEAR]
        thr = p80(hm)
        for r in rs:
            d = _iso(r[ix["HM_DATE"]])
            if not d or int(d[:4]) < MIN_YEAR:
                continue
            v = num(r[ix["HM_EXT_WL"]])
            if thr is None or not np.isfinite(v) or v < thr:
                continue
            yield {"source": "crid", "source_row": f"{stn}:{r[ix['ICE_SEASON']]}", "type": "M8", "submode": "ice_jam",
                   "cause": "CRID spring break-up peak water level (HM)", "date": d,
                   "crest_local": d + (" " + r[ix["HM_TIME"]] if r[ix["HM_TIME"]] else ""), "crest_kind": "agency_crest_reading",
                   "lat": r[ix["LATITUDE"]], "lon": r[ix["LONGITUDE"]], "anchor": f"WSC {stn} {r[ix['STATION_NAME']]}",
                   "country": "Canada", "region": stn[:2], "peak_value": v, "peak_unit": "m", "station_p80": thr}


# ------------------------------------------------------------------ DFO and GLOF (v1's pinned extracts)
def _v1_leads():
    from experiments.flood_m678.v2.registry import PINS, show
    return list(csv.DictReader(io.StringIO(show(PINS["v1_reserve_seal"], "experiments/flood_m678/source_leads.csv").decode())))


def dfo():
    for r in _v1_leads():
        if not r["source_row"].startswith("dfo"):
            continue
        d = (r["reported_min"] or r["reported_date"])[:10]
        if not d[:4].isdigit() or int(d[:4]) < MIN_YEAR:
            continue
        cause = r["driver_as_reported"]
        low = cause.lower()
        if r["type"].startswith("M7"):
            if "release" in low and "break" not in low:
                continue                                    # controlled releases are not breaches
            sub = "levee_breach" if "levee" in low or "levy" in low else "reservoir_breach"
            ty = "M7"
        elif r["type"] == "M8":
            ty, sub = "M8", "ice_jam" if "ice" in low else "sustained_melt"
        else:
            continue
        yield {"source": "dfo", "source_row": r["source_row"], "type": ty, "submode": sub, "cause": cause, "date": d,
               "crest_local": "", "crest_kind": "", "lat": r["lat"], "lon": r["lon"], "anchor": "country only",
               "country": r["country"], "region": r["country"], "peak_value": "", "peak_unit": "", "station_p80": ""}


def glof():
    for r in _v1_leads():
        if not r["source_row"].startswith("glof"):
            continue
        d = (r["reported_date"] or r["reported_min"])[:10]
        if not d[:4].isdigit() or int(d[:4]) < MIN_YEAR:
            continue
        yield {"source": "glof", "source_row": r["source_row"], "type": "M6",
               "submode": "debris_runout" if "debris" in r["driver_as_reported"].lower() else "water_release",
               "cause": r["driver_as_reported"], "date": d, "crest_local": "", "crest_kind": "",
               "lat": r["lat"], "lon": r["lon"], "anchor": f"lake {r['place'][:60]}", "country": r["country"],
               "region": r["country"], "peak_value": "", "peak_unit": "", "station_p80": ""}


ADAPTERS = {"usgs_peaks": usgs_peaks, "wsc_ice": wsc_ice, "wsc_melt": wsc_melt, "crid": crid, "dfo": dfo, "glof": glof}


def run(names):
    old = list(csv.DictReader(open(OUT))) if os.path.exists(OUT) else []
    keep = [r for r in old if r["source"] not in names]
    new = []
    for n in names:
        for i, r in enumerate(ADAPTERS[n]()):
            r["lead_id"] = f"{n}:{r['source_row']}"
            new.append({k: r.get(k, "") for k in FIELDS})
        print(n, sum(1 for r in new if r["source"].startswith(n.split("_")[0])), flush=True)
    rows = sorted({r["lead_id"]: r for r in keep + new}.values(), key=lambda r: (r["type"], r["date"], r["lead_id"]))
    with open(OUT + ".tmp", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    os.replace(OUT + ".tmp", OUT)
    y = {}
    for r in rows:
        k = f"{r['type']}/{r['submode'] or '?'}"
        y.setdefault(k, {}).setdefault(r["country"] or "?", 0)
        y[k][r["country"] or "?"] += 1
    json.dump(y, open(YIELD, "w"), indent=1, sort_keys=True)
    print(json.dumps({k: sum(v.values()) for k, v in y.items()}))


if __name__ == "__main__":
    a = sys.argv[1:] or ["all"]
    run(list(ADAPTERS) if a == ["all"] else a)
