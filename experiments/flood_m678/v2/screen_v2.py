"""
M6–M8 v2 step 1d: metadata-only screen of joined components (SELECTION.md §2, §5).

    python -m experiments.flood_m678.v2.screen_v2 [reserve|dev|all]     # resumable (STAC cache)

Per lead with an anchor and crest evidence:
- cause rule for sustained_melt (fixed before screening): the station is nival, i.e. >= 60 % of
  its 1984-2021 annual maximum water levels fall in April-June (WSC record; gauge history only);
- crest interval: an agency reading with its UTC offset +/- 15 min, otherwise the local day;
- scene screen: v1's screen (Planetary Computer STAC metadata; Landsat C2 L2, Sentinel-2 L2A,
  Sentinel-1 GRD with a same-orbit baseline), window [crest - 24 h, crest + 72 h] for sustained
  melt and [crest - 24 h, crest + 48 h] otherwise, full 8 km box coverage.
Writes screening.csv. No pixel, label, feature or score is read.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
V1 = os.path.join(HERE, "..")
STAC_CACHE = os.path.expanduser("~/.cache/geowatch/m678v2/stac")
OUT = os.path.join(HERE, "screening.csv")
NIVAL_SHARE = 0.60
FIELDS = ("lead_id", "component", "side", "type", "submode", "date", "nival_share", "crest_utc_min", "crest_utc_max",
          "crest_kind", "optical", "paired_radar", "status")


def nival_shares():
    p = os.path.expanduser("~/.cache/geowatch/m678v2/sources/wsc/annual_peaks.json")
    by = {}
    for f in json.load(open(p)):
        q = f["properties"]
        d = q.get("DATE") or ""
        if d[:4].isdigit() and 1984 <= int(d[:4]) <= 2021:
            by.setdefault(q["STATION_NUMBER"], []).append(int(d[5:7]))
    return {s: sum(4 <= m <= 6 for m in ms) / len(ms) for s, ms in by.items() if len(ms) >= 8}


def crest_bounds(lead):
    """(lo, hi, kind) in UTC from the lead's crest fields."""
    c = lead["crest_local"].strip()
    if not c:
        return None
    if " UTC" in c:
        t, off = c.split(" UTC")
        dt = datetime.fromisoformat(t.strip()).replace(tzinfo=timezone(timedelta(hours=float(off))))
        dt = dt.astimezone(timezone.utc)
        return dt - timedelta(minutes=15), dt + timedelta(minutes=15), "agency_reading"
    day = datetime.fromisoformat(c[:10]).replace(tzinfo=timezone.utc)
    return day - timedelta(hours=12), day + timedelta(hours=36), "agency_day_tz_unknown"   # day in any zone


def screen_lead(lead, lo, hi, session):
    sys.path.insert(0, V1)
    import screen_acquisitions as S
    site = {"type": lead["type"], "subtype": "ice jam" if lead["submode"] == "ice_jam" else lead["submode"],
            "zone": "UTC", "longitude": float(lead["lon"]), "latitude": float(lead["lat"])}
    ev = {"date": lead["date"][:10], "crest_utc_bracket": [lo.isoformat(), hi.isoformat()]}
    return S.screen(ev, site, {}, session, __import__("pathlib").Path(STAC_CACHE))


def main(which="all"):
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
    os.makedirs(STAC_CACHE, exist_ok=True)
    ses = requests.Session()
    ses.mount("https://", HTTPAdapter(max_retries=Retry(total=4, backoff_factor=2, status_forcelist=(429, 500, 502, 503, 504))))
    leads = {r["lead_id"]: r for r in csv.DictReader(open(os.path.join(HERE, "leads.csv")))}
    comp = {}
    for r in csv.DictReader(open(os.path.join(HERE, "clusters.csv"))):
        comp.setdefault(r["component"], []).append(r)
    nival = nival_shares()
    done = {r["lead_id"]: r for r in csv.DictReader(open(OUT))} if os.path.exists(OUT) else {}
    out = dict(done)
    todo = []
    for cid, rs in comp.items():
        status = rs[0]["status"]
        if status == "excluded_v1_reserve":
            continue
        ls = [leads[r["id"]] for r in rs if r["kind"] == "lead" and r["id"] in leads and leads[r["id"]]["lat"]]
        post = any(l["date"] >= "2022-01-01" for l in ls)
        side = "dev" if status == "dev_only_inspected" or not post else "reserve"
        for l in ls:
            if which != "all" and side != which:
                continue
            if side == "reserve" and l["date"] < "2022-01-01":
                continue                       # withheld from DEV, not screened for the reserve
            todo.append((cid, side, l))
    print("to screen", len(todo), "already", len(done), flush=True)
    for k, (cid, side, l) in enumerate(todo):
        if l["lead_id"] in out:
            continue
        row = {"lead_id": l["lead_id"], "component": cid, "side": side, "type": l["type"], "submode": l["submode"],
               "date": l["date"][:10], "nival_share": "", "crest_utc_min": "", "crest_utc_max": "", "crest_kind": "",
               "optical": "", "paired_radar": "", "status": ""}
        stn = l["anchor"].split(" ")[1] if l["anchor"].startswith("WSC") else None
        if l["submode"] == "sustained_melt" and stn:
            ns = nival.get(stn)
            row["nival_share"] = "" if ns is None else round(ns, 2)
            if ns is None or ns < NIVAL_SHARE:
                row["status"] = "not_nival"
                out[l["lead_id"]] = row
                continue
        cb = crest_bounds(l)
        if cb is None:
            row["status"] = "no_crest"
            out[l["lead_id"]] = row
            continue
        lo, hi, kind = cb
        try:
            ev = screen_lead(l, lo, hi, ses)
        except Exception as e:      # noqa: BLE001
            row["status"] = f"screen_error:{type(e).__name__}"
            out[l["lead_id"]] = row
            continue
        opt = sum(s["collection"] != "sentinel-1-grd" for s in ev["scenes"])
        rad = sum(bool(s.get("baseline")) for s in ev["scenes"])
        row.update(crest_utc_min=lo.isoformat(), crest_utc_max=hi.isoformat(), crest_kind=kind, optical=opt,
                   paired_radar=rad, status="timed_footprint" if opt + rad else "no_scene_in_window")
        out[l["lead_id"]] = row
        if k % 25 == 0:
            _write(out)
            print(k, len(out), time.strftime("%H:%M:%S"), flush=True)
    _write(out)
    print("done", len(out))


def _write(out):
    with open(OUT + ".tmp", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(sorted(out.values(), key=lambda r: (r["side"], r["type"], r["date"], r["lead_id"])))
    os.replace(OUT + ".tmp", OUT)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
