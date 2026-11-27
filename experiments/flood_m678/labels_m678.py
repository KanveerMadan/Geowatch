"""
M6–M8 labels on a 20 km search square, then round 4's place() rule for the 8 km box.

Run from the pinned round-3 checkout so round 3's modules are the ones imported:

    cd ~/gw-r3pin && PYTHONPATH=.:$HOME/gw-m678/experiments/flood_m678 python -B -m labels_m678 dev [incident ...]

Label states (rule 4 of the brief; round 3's v3 codes plus one):
  1 FLOODED, 0 DRY, -1 UNOBSERVED, -2 PERMANENT or normal water, -3 AMBIGUOUS.
Only 1 and 0 are scored.

Sources, per incident, from the scenes the sealed screen listed (scene ids and times only):
- Radar: round 3's R3-S1-1..4 (labels_r3.s1_label) restricted to the screened Sentinel-1 passes
  that have a same-orbit baseline, and its observability rules R3-O-1..4 (HAND > 15 m, built-up,
  slope > 20 deg unobserved; JRC >= 80 % permanent).
- Optical (Landsat C2 L2, Sentinel-2 L2A): Codex's Midland rule, generalised:
  * water needs the sensor's own water class AND MNDWI > 0;
  * dry needs a clear land class AND MNDWI < 0 AND NDVI <= 0.3 (green canopy hides water);
  * cloud, shadow, cirrus, saturation, snow and no-data are unobserved, anything else ambiguous;
  * new water only: a cell is FLOODED only if a clear pre-event observation in
    [t0 - 60 d, t0 - 6 d] (same sensor) shows land; water before and after is PERMANENT
    (normal channel water); water after with no clear pre-event view is AMBIGUOUS;
  * built-up cells (GHSL or WorldCover >= 0.5) are UNOBSERVED (they cannot be seen as dry);
  * every clear scene in the window counts (maximum extent, as R3-S1-3).
- Snow and ice: MODIS Terra MOD10A1 NDSI snow cover >= 10 on the image day is UNOBSERVED for
  every source (brief rule 4 for M8; applied to all types because snow cannot be judged).
- Label (owner rule, DECISIONS 2026-11-27): optical first; where optical is neither FLOODED nor
  DRY (cloud, shadow, ambiguity), the cell takes the Sentinel-1 radar state from a screened
  same-orbit pass. Both source labels are kept, and their agreement (kappa) is the label QA.

Box: round 4's s1_flood_centre on the primary label's flooded and valid cells of the search square,
then an 8 km square (R25) cropped on the same 30 m lattice. No flooded cell, no box (a dropout).
Every scene's lag to the crest interval (hours, both bounds) is recorded.
"""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.expanduser("~/.cache/geowatch/flood_m678")
REFS = os.path.join(CACHE, "refs")
LOCK = "/private/tmp/geowatch-change-round2-ee.lock"
SEARCH_M, BOX_M = 20000.0, 8000.0
AMBIGUOUS = -3
NDVI_GREEN = 0.3
SNOW_NDSI = 10
_lock = {"on": False}


def install_exclusive_lock():
    """Every EE call from M6–M8 takes the exclusive lock, so none overlaps a round-3 call
    (round 3 takes the shared lock). Round 3's own shared-lock patch is disabled here."""
    if _lock["on"]:
        return
    import ee.data as D
    from experiments.flood_round3 import ee_lock as R3L
    R3L._done["v"] = True
    orig = D._execute_cloud_call

    def locked(*a, **k):
        with open(LOCK, "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                return orig(*a, **k)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    D._execute_cloud_call = locked
    _lock["on"] = True


def init_ee():
    import ee
    from dotenv import dotenv_values
    install_exclusive_lock()
    env = dotenv_values(os.path.expanduser("~/geowatch/.env"))
    project = env.get("GEE_PROJECT_ID") or os.environ.get("GEE_PROJECT_ID")
    if project:
        os.environ["GEE_PROJECT_ID"] = project      # round 3's ingestion.gee_client reads the environment
    ee.Initialize(project=project)
    return ee


def _utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def lag_hours(scene_utc, crest):
    t = _utc(scene_utc)
    lo, hi = (_utc(x) for x in crest)
    return round((t - hi).total_seconds() / 3600, 2), round((t - lo).total_seconds() / 3600, 2)


# ---------------------------------------------------------------- optical
def _landsat_ids(scene_id):
    """Planetary Computer Landsat C2 L2 id -> (EE collection, system:index)."""
    p = scene_id.split("_")                                 # LC08_L2SP_044034_20200520_02_T1
    tier = p[-1] if p[-1] in ("T1", "T2") else "T1"
    return f"LANDSAT/{p[0]}/C02/{tier}_L2", f"{p[0]}_{p[2]}_{p[3]}"


def _landsat_bands(img, sat):
    sr = img.select("SR_B.*").multiply(0.0000275).add(-0.2)
    if sat in ("LC08", "LC09"):
        g, r, n, s = "SR_B3", "SR_B4", "SR_B5", "SR_B6"
    else:
        g, r, n, s = "SR_B2", "SR_B3", "SR_B4", "SR_B5"
    mndwi = sr.normalizedDifference([g, s])
    ndvi = sr.normalizedDifference([n, r])
    qa = img.select("QA_PIXEL")
    bit = lambda b: qa.bitwiseAnd(1 << b).neq(0)        # noqa: E731
    bad = bit(1).Or(bit(2)).Or(bit(3)).Or(bit(4)).Or(bit(5)).Or(bit(0))
    sat_ = img.select("QA_RADSAT").neq(0)
    unobs = bad.Or(sat_)
    water = bit(7).And(mndwi.gt(0)).And(unobs.Not())
    land = bit(6).And(bit(7).Not()).And(mndwi.lt(0)).And(unobs.Not())
    return water, land, ndvi, unobs, bit(5)


def _s2_bands(img):
    b = img.select(["B3", "B4", "B8", "B11"]).divide(10000)
    mndwi = b.normalizedDifference(["B3", "B11"])
    ndvi = b.normalizedDifference(["B8", "B4"])
    scl = img.select("SCL")
    unobs = scl.remap([0, 1, 3, 8, 9, 10, 11], [1] * 7, 0).eq(1)
    water = scl.eq(6).And(mndwi.gt(0))
    land = scl.eq(4).Or(scl.eq(5)).And(mndwi.lt(0))
    return water, land, ndvi, unobs, scl.eq(11)


def _s2l1c_bands(img):
    """L1C fallback where Earth Engine holds no L2A (outside Europe before December 2018):
    s2cloudless probability >= 40 % is unobserved; water needs MNDWI > 0 AND NDWI > 0, land both < 0."""
    b = img.select(["B3", "B4", "B8", "B11"]).divide(10000)
    mndwi = b.normalizedDifference(["B3", "B11"])
    ndwi = b.normalizedDifference(["B3", "B8"])
    ndvi = b.normalizedDifference(["B8", "B4"])
    ndsi_snow = mndwi.gt(0.4).And(b.select("B3").gt(0.15)).And(ndwi.lt(0.1))
    unobs = img.select("probability").gte(40).Or(ndsi_snow)
    water = mndwi.gt(0).And(ndwi.gt(0)).And(unobs.Not())
    land = mndwi.lt(0).And(ndwi.lt(0)).And(unobs.Not())
    return water, land, ndvi, unobs, ndsi_snow


def _with_prob(ee, c):
    p = ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY")
    j = ee.Join.saveFirst("cp").apply(c, p, ee.Filter.equals(leftField="system:index", rightField="system:index"))
    return ee.ImageCollection(j).map(lambda im: ee.Image(im).addBands(ee.Image(ee.Image(im).get("cp")).select("probability")))


def _optical_scene(ee, scene):
    """(collection-filter-able image, family) for one screened optical scene."""
    if scene["collection"] == "landsat-c2-l2":
        coll, idx = _landsat_ids(scene["scene"])
        return ee.Image(f"{coll}/{idx}"), scene["scene"][:4]
    # Sentinel-2: Planetary Computer id S2A_MSIL2A_20190329T163901_R126_T15TUL_20201004T...
    t = _utc(scene["utc"])
    tile = [p for p in scene["scene"].split("_") if p.startswith("T") and len(p) == 6][0][1:]
    span = ((t - dt.timedelta(minutes=30)).isoformat(), (t + dt.timedelta(minutes=30)).isoformat())
    c = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterDate(*span).filter(ee.Filter.eq("MGRS_TILE", tile))
    if c.size().getInfo() > 0:
        return c.mosaic().set("system:time_start", int(t.timestamp() * 1000)), "S2"
    c = _with_prob(ee, ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterDate(*span).filter(ee.Filter.eq("MGRS_TILE", tile)))
    if c.size().getInfo() == 0:
        raise LookupError(f"no Sentinel-2 L2A or L1C image in Earth Engine for {scene['scene']}")
    return c.mosaic().set("system:time_start", int(t.timestamp() * 1000)), "S2L1C"


def _pre_land_water(ee, family, region, t0):
    """Clear pre-event land / water views, same sensor, [t0 - 60 d, t0 - 6 d]."""
    a, b = t0 - dt.timedelta(days=60), t0 - dt.timedelta(days=6)
    if family == "S2":
        c = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(region).filterDate(a.isoformat(), b.isoformat())
        fn = lambda im: _s2_bands(im)            # noqa: E731
    elif family == "S2L1C":
        c = _with_prob(ee, ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(region).filterDate(a.isoformat(), b.isoformat()))
        fn = lambda im: _s2l1c_bands(im)         # noqa: E731
    else:
        c = ee.ImageCollection(f"LANDSAT/{family}/C02/T1_L2").merge(ee.ImageCollection(f"LANDSAT/{family}/C02/T2_L2"))
        c = c.filterBounds(region).filterDate(a.isoformat(), b.isoformat())
        fn = lambda im: _landsat_bands(im, family)   # noqa: E731

    def per(im):
        w, land, _, _, _ = fn(im)
        return ee.Image.cat([land.unmask(0).rename("land"), w.unmask(0).rename("water")])
    s = c.map(per)
    return s.select("land").max().unmask(0), s.select("water").max().unmask(0), c.size()


def optical_label(ee, scenes, t0, transform, shape, crs):
    """Max-extent optical label over the screened scenes: dict of 30 m share arrays."""
    from susceptibility.hydro_rasters import compute_pixels, grid_lonlat_bounds
    ll = grid_lonlat_bounds(transform, shape, crs)
    region = ee.Geometry.Rectangle(list(ll))
    out = None
    used = []
    for sc in scenes:
        try:
            img, fam = _optical_scene(ee, sc)
        except LookupError as e:
            used.append({"scene": sc["scene"], "error": str(e)})
            continue
        water, land, ndvi, unobs, _snow = (_s2_bands(img) if fam == "S2" else _s2l1c_bands(img) if fam == "S2L1C"
                                           else _landsat_bands(img, fam))
        pre_land, pre_water, npre = _pre_land_water(ee, fam, region, t0)
        green = ndvi.gt(NDVI_GREEN)
        flooded = water.And(pre_land).And(pre_water.Not())
        perm = water.And(pre_water)
        dry = land.And(green.Not())
        valid = img.select(0).mask().gt(0)
        st = ee.Image.cat([
            flooded.unmask(0).rename("f"), dry.unmask(0).rename("d"), perm.unmask(0).rename("p"),
            unobs.Or(valid.Not()).unmask(1).rename("u")]).toFloat()
        scale = 10 if fam.startswith("S2") else 30
        st = st.reproject(crs=crs, scale=scale).reduceResolution(ee.Reducer.mean(), maxPixels=64)
        a = compute_pixels(st, transform, shape, crs, f"optical {sc['scene'][:40]}")
        a = {k: np.nan_to_num(np.asarray(v, float), nan=0.0) for k, v in a.items()}
        a["n_pre"] = int(npre.getInfo())
        used.append({"scene": sc["scene"], "collection": sc["collection"], "utc": sc["utc"], "family": fam,
                     "pre_event_images": a["n_pre"]})
        if out is None:
            out = {k: a[k].copy() for k in ("f", "d", "p", "u")}
            out["seen"] = (a["u"] < 0.5).astype(float)
        else:
            out["f"] = np.fmax(out["f"], a["f"])
            out["p"] = np.fmax(out["p"], a["p"])
            out["d"] = np.where(a["u"] < 0.5, np.fmin(np.where(out["seen"] > 0, out["d"], 1.0), a["d"]), out["d"])
            out["seen"] = np.fmax(out["seen"], (a["u"] < 0.5).astype(float))
    return out, used


def optical_states(o, obs):
    from experiments.flood_round3 import labels_r3 as L
    y = np.full(o["f"].shape, AMBIGUOUS, np.int8)
    seen = o["seen"] > 0
    y[~seen] = L.UNOBSERVED
    y[seen & (o["d"] >= 0.5)] = L.DRY
    y[seen & (o["p"] >= 0.5)] = L.PERMANENT
    y[seen & (o["f"] >= 0.5)] = L.FLOODED
    built = np.fmax(np.nan_to_num(obs["wc_built"]), np.nan_to_num(obs["ghsl_built"])) >= L.BUILT_SHARE
    y[built] = L.UNOBSERVED
    y[np.nan_to_num(obs["occ"], nan=0.0) >= L.PERMANENT_PCT] = L.PERMANENT
    return y


# ---------------------------------------------------------------- radar
def radar_label(ee, bbox, scenes, t0, transform, shape, crs):
    """Round 3's s1_label restricted to the screened passes (its own pass search is replaced)."""
    from experiments.flood_round3 import labels_r3 as L
    passes = sorted({(_utc(s["utc"]).date().isoformat(), int(s["scene_orbit"])) for s in scenes})
    orig = L.s1_passes
    L.s1_passes = lambda *a, **k: passes
    try:
        day = t0.date().isoformat()
        return L.s1_label(ee, list(bbox), day, day, transform, shape, crs)
    finally:
        L.s1_passes = orig


def snow_mask(ee, days, transform, shape, crs):
    from susceptibility.hydro_rasters import compute_pixels
    c = ee.ImageCollection("MODIS/061/MOD10A1").select("NDSI_Snow_Cover")
    imgs = [c.filterDate(d, (dt.date.fromisoformat(d) + dt.timedelta(days=1)).isoformat()).max().unmask(0)
            for d in sorted(set(days))]
    snow = ee.ImageCollection(imgs).max().gte(SNOW_NDSI).rename("snow").toFloat()
    a = compute_pixels(snow, transform, shape, crs, "modis snow")
    return np.nan_to_num(np.asarray(a["snow"], float), nan=0.0) >= 0.5


# ---------------------------------------------------------------- driver
def s1_relative_orbit(scene_id):
    """Relative orbit from the absolute orbit in a Sentinel-1 product id (ESA's orbit cycle)."""
    p = scene_id.split("_")
    absolute = int(p[6])
    offset = {"S1A": 73, "S1B": 27, "S1C": 172}[p[0]]
    return (absolute - offset) % 175 + 1


def kappa(a, b):
    m = np.isin(a, (0, 1)) & np.isin(b, (0, 1))
    if m.sum() < 50:
        return None, int(m.sum())
    x, y = a[m] == 1, b[m] == 1
    po = float((x == y).mean())
    pe = float(x.mean() * y.mean() + (1 - x.mean()) * (1 - y.mean()))
    return (round((po - pe) / (1 - pe), 3) if pe < 1 else None), int(m.sum())


def build(rec, ee=None):
    from experiments.flood_round3 import labels_r3 as L
    from experiments.flood_validation import references as R
    from experiments.flood_validation.harness_round4 import s1_flood_centre, window_in
    from susceptibility.hydro_rasters import utm_grid
    os.makedirs(REFS, exist_ok=True)
    n = rec["incident"]
    out_p = os.path.join(REFS, f"{n}.npz")
    if os.path.exists(out_p):
        return json.loads(str(np.load(out_p, allow_pickle=False)["meta"]))
    ee = ee or init_ee()
    lat, lon = rec["reach_point"]
    sq = R.square_bbox(lat, lon, SEARCH_M)
    t, shape, crs = utm_grid(sq)
    t0 = _utc(rec["window_utc"][0])
    obs = L.observability(ee, t, shape, crs)
    radar = [dict(s, scene_orbit=s1_relative_orbit(s["scene"])) for s in rec["scenes"]
             if s["collection"] == "sentinel-1-grd" and s.get("baseline")]
    optical = [s for s in rec["scenes"] if s["collection"] != "sentinel-1-grd"]
    labels, meta_src = {}, {}
    if radar:
        try:
            lab = radar_label(ee, sq, radar, t0, t, shape, crs)
            labels["radar"] = L.s1_states(lab, obs)
            meta_src["radar"] = {"passes": lab["passes"], "baselines": lab["baselines"]}
        except LookupError as e:
            meta_src["radar"] = {"error": str(e)}
    if optical:
        o, used = optical_label(ee, optical, t0, t, shape, crs)
        if o is not None:
            labels["optical"] = optical_states(o, obs)
        meta_src["optical"] = {"scenes": used}
    days = [_utc(s["utc"]).date().isoformat() for s in radar + optical]
    snow = snow_mask(ee, days, t, shape, crs) if days else np.zeros(shape, bool)
    for k in labels:
        labels[k][snow & (labels[k] != L.PERMANENT)] = L.UNOBSERVED
    # Owner rule (DECISIONS 2026-11-27): optical first; Sentinel-1 radar fills, cell by cell, where
    # optical gives neither FLOODED nor DRY (cloud, shadow, ambiguity). Identical for DEV and reserve.
    if "optical" in labels and "radar" in labels:
        o_, r_ = labels["optical"], labels["radar"]
        labels["merged"] = np.where(np.isin(o_, (L.FLOODED, L.DRY)), o_,
                                    np.where(np.isin(r_, (L.FLOODED, L.DRY)), r_, o_)).astype(np.int8)
        primary = "merged"
    else:
        primary = "optical" if "optical" in labels else "radar" if "radar" in labels else None
    meta = {"incident": n, "type": rec["type"], "subtype": rec["subtype"], "cluster": rec["cluster"],
            "event": rec["date"], "crest_utc": rec["crest_utc"], "crest_kind": rec["crest_kind"],
            "window_utc": rec["window_utc"], "search_square": list(sq), "sources": meta_src, "primary": primary,
            "lags_hours": {s["scene"]: lag_hours(s["utc"], rec["crest_utc"]) for s in radar + optical},
            "snow_cells_search_square": int(snow.sum())}
    if primary is None:
        meta["dropout"] = "no label source built"
        np.savez_compressed(out_p, meta=np.array(json.dumps(meta)))
        return meta
    y = labels[primary]
    if primary == "merged":
        meta["merge"] = {"optical_cells": int(np.isin(labels["optical"], (0, 1)).sum()),
                         "radar_fill_cells": int((np.isin(labels["radar"], (0, 1)) & ~np.isin(labels["optical"], (0, 1))).sum())}
    other = ["radar"] if primary == "merged" else []
    if other:
        meta["qa_kappa"], meta["qa_cells"] = kappa(labels["optical"], labels["radar"])
    centre = s1_flood_centre(y == L.FLOODED, np.isin(y, (0, 1)), t, crs)
    if centre is None:
        meta["dropout"] = "no flooded cell in the search square"
        np.savez_compressed(out_p, meta=np.array(json.dumps(meta)))
        return meta
    box = R.square_bbox(*centre, BOX_M)
    bt, bshape, bcrs = utm_grid(box)
    if bcrs != crs:
        raise ValueError(f"{n}: box CRS {bcrs} differs from search square {crs}")
    r0, c0 = window_in(t, shape, bt, bshape)
    yb = y[r0:r0 + bshape[0], c0:c0 + bshape[1]]
    ob = {k: v[r0:r0 + bshape[0], c0:c0 + bshape[1]] for k, v in labels.items()}
    meta.update(centre=list(centre), bbox=list(box), side_m=BOX_M,
                grid={"crs": bcrs, "transform": list(bt)[:6], "shape": list(bshape)}, block=1,
                flooded_cells=int((yb == L.FLOODED).sum()), dry_cells=int((yb == L.DRY).sum()),
                ambiguous_cells=int((yb == AMBIGUOUS).sum()), unobserved_cells=int((yb == L.UNOBSERVED).sum()),
                permanent_cells=int((yb == L.PERMANENT).sum()))
    if other:
        meta["qa_kappa_box"], meta["qa_cells_box"] = kappa(ob["optical"], ob["radar"])
    extra = {f"y_{k}": v.astype(np.int8) for k, v in ob.items()}
    np.savez_compressed(out_p + ".tmp.npz", flooded=(yb == L.FLOODED), valid=np.isin(yb, (0, 1)), y3=yb.astype(np.int8),
                        meta=np.array(json.dumps(meta, default=str)), **extra)
    os.replace(out_p + ".tmp.npz", out_p)
    return meta


def records(split):
    f = {"dev": "dev_m678.json", "reserve": "reserve_m678.json"}[split]
    d = json.load(open(os.path.join(HERE, f)))
    pool = d["dev"] if split == "dev" else d["reserve"]
    return [r for t in sorted(pool) for c in sorted(pool[t]) for r in pool[t][c]]


def main(argv=None):
    a = argv or sys.argv[1:]
    split = a[0]
    if split == "reserve" and not os.path.exists(os.path.join(HERE, "FREEZE_M678.txt")):
        raise SystemExit("reserve labels are built only after the freeze tag (PREREGISTRATION_M678.md)")
    only = set(a[1:])
    ee = None
    for r in records(split):
        if only and r["incident"] not in only:
            continue
        try:
            ee = ee or init_ee()
            m = build(r, ee)
            print(r["incident"], json.dumps({k: m.get(k) for k in ("primary", "flooded_cells", "dry_cells", "qa_kappa_box", "dropout")}), flush=True)
        except Exception as e:      # noqa: BLE001
            print(r["incident"], "ERROR", type(e).__name__, str(e)[:300], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
