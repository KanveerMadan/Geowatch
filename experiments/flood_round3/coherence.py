"""
Round 3, rain (R29): Sentinel-1 InSAR coherence drop as an urban rain-flood label, made by ASF HyP3
(INSAR_ISCE_BURST, 10x2 looks ~40 m, 1 credit a pair). Earthdata login comes from ~/.netrc via hyp3_sdk and is
never printed or logged.

Validation first (`validate`): before coherence can label any non-US event, it must rank 311 reports on DEV
storms. Coherence comes from SAR; the reports come from people, so the two are independent.
- Storms: DEV 311 storms (NYC, Chicago) with a Sentinel-1 burst acquisition on the rain-peak day or the day
  after (UTC); an image before the rain is a pre-event image, not a label.
- Pairs per burst: co-event (previous same-track acquisition, post) and pre-event (the one before, previous).
- Score per report cell: coh_pre - coh_co (a drop). The AUC of flood reports vs dry reports (R29 classes, city-wide)
  is the validation number.

    python -m experiments.flood_round3.coherence storms      # metadata: storms with a usable post pass
    python -m experiments.flood_round3.coherence submit      # HyP3 jobs (credits), resumable
    python -m experiments.flood_round3.coherence validate    # download, sample, AUC -> results/coherence_validation.json
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import sys
import time
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results")
CACHE = os.path.expanduser("~/.cache/geowatch/flood_round3/coherence")
LOOKS = "10x2"
PROJECT = "geowatch_r3_coh"


def _asf():
    import asf_search as asf
    return asf


def bursts(bbox, d0, d1):
    """VV SLC bursts intersecting bbox with start time in [d0, d1): list of dicts (cached)."""
    os.makedirs(CACHE, exist_ok=True)
    p = os.path.join(CACHE, f"bursts_{'_'.join(f'{x:.3f}' for x in bbox)}_{d0}_{d1}.json")
    if os.path.exists(p):
        return json.load(open(p))
    asf = _asf()
    w, s, e, n = bbox
    wkt = f"POLYGON(({w} {s},{e} {s},{e} {n},{w} {n},{w} {s}))"
    for k in range(4):
        try:
            r = asf.search(dataset=asf.DATASET.SLC_BURST, intersectsWith=wkt, start=d0, end=d1, polarization="VV")
            break
        except Exception as ex:          # noqa: BLE001
            print("asf:", type(ex).__name__, str(ex)[:100], flush=True)
            time.sleep(20 * (k + 1))
    else:
        raise RuntimeError("asf search failed")
    out = [{"granule": x.properties["sceneName"], "time": x.properties["startTime"][:19],
            "burst": x.properties["burst"]["fullBurstID"], "path": x.properties.get("pathNumber")} for x in r]
    json.dump(out, open(p, "w"))
    time.sleep(1)
    return out


def storms():
    from experiments.flood_round3 import rain311 as R3
    evs = json.load(open(os.path.join(OUT, "r311_events.json")))
    res = []
    for city, rows in evs.items():
        bb = R3.CITIES[city]["bbox"]
        for e in rows:
            if e.get("split") != "dev" or not e.get("type"):
                continue
            pk = dt.date.fromisoformat(e["rain_peak_day"])
            post = bursts(bb, pk.isoformat(), (pk + dt.timedelta(days=2)).isoformat())
            if not post:
                continue
            day = min(b["time"][:10] for b in post)
            post = [b for b in post if b["time"][:10] == day]
            pairs = []
            for b in post:
                prev = [x for x in bursts(bb, (pk - dt.timedelta(days=40)).isoformat(), (pk - dt.timedelta(days=1)).isoformat())
                        if x["burst"] == b["burst"]]
                prev.sort(key=lambda x: x["time"])
                if len(prev) < 2:
                    continue
                p1, p2 = prev[-1], prev[-2]
                pairs.append({"burst": b["burst"], "post": b["granule"], "pre1": p1["granule"], "pre2": p2["granule"],
                              "dt_co_days": (dt.date.fromisoformat(b["time"][:10]) - dt.date.fromisoformat(p1["time"][:10])).days,
                              "dt_pre_days": (dt.date.fromisoformat(p1["time"][:10]) - dt.date.fromisoformat(p2["time"][:10])).days})
            if pairs:
                res.append({"city": city, "event": e["event"], "type": e["type"], "peak": e["rain_peak_day"],
                            "post_day": day, "window": e["window"], "pairs": pairs})
                print(city, e["event"], day, len(pairs), "bursts", flush=True)
    json.dump(res, open(os.path.join(OUT, "coherence_storms.json"), "w"), indent=1)
    return 0


def submit():
    import hyp3_sdk as sdk
    h = sdk.HyP3()
    st = json.load(open(os.path.join(OUT, "coherence_storms.json")))
    jp = os.path.join(CACHE, "jobs.json")
    jobs = json.load(open(jp)) if os.path.exists(jp) else {}
    for s in st:
        for p in s["pairs"]:
            for kind, (ref, sec) in (("co", (p["pre1"], p["post"])), ("pre", (p["pre2"], p["pre1"]))):
                key = f"{ref}__{sec}"
                if key in jobs:
                    continue
                b = h.submit_insar_isce_burst_job(ref, sec, name=PROJECT, looks=LOOKS)
                jobs[key] = b.jobs[0].job_id if hasattr(b, "jobs") else b.job_id
                json.dump(jobs, open(jp, "w"), indent=1)
                time.sleep(0.5)
    print(len(jobs), "jobs; credits left", h.check_credits(), flush=True)
    return 0


def _download(h, job_id):
    d = os.path.join(CACHE, "products", job_id)
    if glob.glob(os.path.join(d, "**", "*_corr.tif"), recursive=True):
        return glob.glob(os.path.join(d, "**", "*_corr.tif"), recursive=True)[0]
    j = h.get_job_by_id(job_id)
    if not j.succeeded():
        return None
    os.makedirs(d, exist_ok=True)
    for f in j.download_files(d):
        if str(f).endswith(".zip"):
            with zipfile.ZipFile(f) as z:
                for m in z.namelist():
                    if m.endswith("_corr.tif"):
                        z.extract(m, d)
            os.remove(f)
    g = glob.glob(os.path.join(d, "**", "*_corr.tif"), recursive=True)
    return g[0] if g else None


def _sample(tif, lon, lat):
    import rasterio
    from pyproj import Transformer
    with rasterio.open(tif) as s:
        x, y = Transformer.from_crs(4326, s.crs, always_xy=True).transform(lon, lat)
        v = np.array([a[0] for a in s.sample(list(zip(x, y)))], np.float64)
        if s.nodata is not None:
            v[v == s.nodata] = np.nan
    v[(v <= 0) | (v > 1)] = np.nan
    return v


def validate():
    import hyp3_sdk as sdk
    from sklearn.metrics import roc_auc_score
    from experiments.flood_round3 import rain311 as R3
    h = sdk.HyP3()
    st = json.load(open(os.path.join(OUT, "coherence_storms.json")))
    jobs = json.load(open(os.path.join(CACHE, "jobs.json")))
    res = []
    for s in st:
        rep = R3.reports(s["city"], {"event": s["event"], "window": s["window"]})
        lon = np.array([r[1] for r in rep])
        lat = np.array([r[2] for r in rep])
        cls = np.array([r[0] for r in rep])
        drop = np.full(len(rep), np.nan)
        for p in s["pairs"]:
            tc = _download(h, jobs.get(f"{p['pre1']}__{p['post']}", ""))
            tp = _download(h, jobs.get(f"{p['pre2']}__{p['pre1']}", ""))
            if tc is None or tp is None:
                continue
            d = _sample(tp, lon, lat) - _sample(tc, lon, lat)
            drop = np.where(np.isnan(drop), d, np.fmax(drop, d))
        ok = np.isfinite(drop) & np.isin(cls, ("flood", "other"))
        y = (cls[ok] == "flood").astype(int)
        r = {"city": s["city"], "event": s["event"], "post_day": s["post_day"], "peak": s["peak"],
             "flood_reports": int(y.sum()), "dry_reports": int((y == 0).sum())}
        if y.sum() >= 20 and (y == 0).sum() >= 20:
            r["auc_drop"] = round(float(roc_auc_score(y, drop[ok])), 3)
        res.append(r)
        print(json.dumps(r), flush=True)
    json.dump(res, open(os.path.join(OUT, "coherence_validation.json"), "w"), indent=1)
    return 0


def main(argv=None):
    a = argv or sys.argv[1:]
    return {"storms": storms, "submit": submit, "validate": validate}[a[0]]()


if __name__ == "__main__":
    raise SystemExit(main())
