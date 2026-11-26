"""GEOGloWS v2 retrospective daily discharge peaks as a last-resort crest day (metadata only).

Used only where no gauge, agency crest or published reading exists, and never for a dam or
lake failure, which the model does not simulate (DECISIONS 2026-11-27). The reach is the
GEOGloWS reach with the largest upstream area inside the 8 km study box. The crest day is the
UTC day of the largest daily mean in the incident's search window. A tie or a maximum at a
window edge leaves the incident unresolved.

    python geoglows_crests.py
"""
import json
import os
import time
import urllib.request
from datetime import date, datetime, timedelta, timezone

import numpy as np

from screen_acquisitions import HERE, IDENTITY_FIELDS, study_box, write_file

REACHES = os.path.expanduser("~/.cache/geowatch/flood_round3/geoglows/reaches.npz")   # round 3's reach index
API = "https://geoglows.ecmwf.int/api/v2/retrospectivedaily/{}?format=json"
CACHE = os.path.expanduser("~/.cache/geowatch/flood_m678/geoglows")
NOT_FOR = ("dam", "lake", "glacial", "outburst", "tailings")


def reach(ix, bbox):
    w, s, e, n = bbox
    m = (ix["lon"] >= w) & (ix["lon"] <= e) & (ix["lat"] >= s) & (ix["lat"] <= n)
    if not m.any():
        return None
    i = np.flatnonzero(m)[int(np.argmax(ix["dsarea"][m]))]
    return {"link": int(ix["link"][i]), "dsarea_km2": round(float(ix["dsarea"][i]) / 1e6, 1)}


def series(link):
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"{link}.json")
    if not os.path.exists(p):
        with urllib.request.urlopen(API.format(link), timeout=180) as r:
            d = json.load(r)
        tmp = p + ".tmp"
        json.dump({"t": [x[:10] for x in d["datetime"]], "q": d[str(link)]}, open(tmp, "w"))
        os.replace(tmp, p)
        time.sleep(0.5)
    d = json.load(open(p))
    return d["t"], np.asarray(d["q"], float)


def peak_day(t, q, a, b):
    idx = [i for i, x in enumerate(t) if a <= x <= b]
    if len(idx) < 3:
        return {"status": "geoglows_no_series"}
    v = q[idx]
    top = np.flatnonzero(v == v.max())
    if len(top) > 1:
        return {"status": "geoglows_tied_maximum"}
    k = int(top[0])
    if k in (0, len(idx) - 1):
        return {"status": "geoglows_maximum_at_window_edge"}
    d = datetime.combine(date.fromisoformat(t[idx[k]]), datetime.min.time(), timezone.utc)
    return {"status": "geoglows_day", "start": d.isoformat(), "end": (d + timedelta(days=1)).isoformat(),
            "peak_m3s": round(float(v[k]), 1)}


def main():
    data = json.loads((HERE / "event_evidence.json").read_text())
    ix = {k: v for k, v in np.load(REACHES).items()}
    out = {}
    for ev in data["events"]:
        if not ev.get("geoglows_window_days"):
            continue
        site = dict(zip(IDENTITY_FIELDS, data["sites"][ev["site"]], strict=True))
        if any(w in site["subtype"] for w in NOT_FOR) and "levee" not in site["subtype"]:
            raise ValueError(f"{ev['site']}: GEOGloWS cannot time a {site['subtype']}")
        eid = ev["site"] + "-" + ev["date"]
        r = reach(ix, study_box(site["longitude"], site["latitude"]).bounds)
        if r is None:
            out[eid] = {"status": "geoglows_no_reach"}
            continue
        t, q = series(r["link"])
        a, b = ev["geoglows_window_days"]
        out[eid] = {**peak_day(t, q, a, b), **r, "window": [a, b], "source": API.format(r["link"])}
    write_file(HERE / "geoglows_crests.json", json.dumps(out, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
