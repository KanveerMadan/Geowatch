"""
Item 25 — change over time, for built, vegetation and water ONLY.

    built       Open Buildings 2.5D Temporal (GOOGLE/Research/open-buildings-
                temporal/v1), `building_presence` averaged onto the 10 m grid.
                Its years (2016-2023) and coverage were verified live per AOI
                before use. Presence is a model score in [0, 1], so a unit's
                value is mean presence: a built PROXY, not footprint area.
    vegetation  Sentinel-2 index-threshold proxies (vector.fractions), from
    water       median composites over the SAME calendar window in two years.

impervious_total, paved and bare are emitted as status "not_computed".

Every change names its fraction. There is no combined "something changed".

PRE-REGISTERED 2026-10-27, before any change data was fetched:
    significance   |delta| > K_NOISE * noise_f, per fraction f
    noise, veg/water  std over units of (half A - half B), where the halves
                   are disjoint split-half composites of the same window
                   (days 1-15 vs 16-31 of each month). They contain no real
                   change, and a half-composite is noisier than a full one,
                   so this OVERSTATES noise (conservative).
    noise, built   std over units of (presence 2023 - presence 2022).
                   Includes any real one-year change, so it is conservative.
    observation    an epoch whose AOI-level clear-observation share is below
                   MIN_EPOCH_VALID_PCT makes every unit "epoch_unreliable";
                   a unit below MIN_EPOCH_UNIT_COVERAGE in either epoch is
                   "insufficient_observation". Neither can report a change.
"""
from __future__ import annotations

import numpy as np

from vector import fractions, units

K_NOISE = 3.0
MIN_EPOCH_UNIT_COVERAGE = 0.8
MIN_EPOCH_VALID_PCT = 50.0

CHANGE_FRACTIONS = ("built", "vegetation", "water")
NOT_COMPUTED = ("impervious_total", "paved", "bare")

OB_TEMPORAL_ASSET = "GOOGLE/Research/open-buildings-temporal/v1"

# The item 25 AOI and epochs, fixed before results.
CHANGE_AOI = {"name": "navi_mumbai_airport",
              # OSM way 455547086 (aeroway=aerodrome) bounds, fetched live 2026-10-27.
              "bbox": (73.0354526, 18.9794632, 73.0938152, 19.0033178),
              "expectation": "where change is detected, vegetation mostly DECREASES "
                             "(site cleared and built over 2019-2024)"}
EPOCHS = {
    "s2": (("2019-01-01", "2019-03-31"), ("2024-01-01", "2024-03-31")),   # same season
    "built": (2019, 2023),
    "built_noise": (2022, 2023),
}


# ── pure parts ──────────────────────────────────────────────────────────

def unit_values(polys, raster, observed, transform, shape):
    """(value, coverage) per unit for one fraction raster, using the same
    fine-grid aggregation as item 22."""
    labels = units._labels(polys, transform, shape)
    inside = labels >= 0
    lab = labels[inside]
    n = len(polys)
    val = units._upsample(raster)[inside]
    obs = units._upsample(observed)[inside] & np.isfinite(val)
    area = np.bincount(lab, minlength=n).astype(float)
    o = np.bincount(lab, weights=obs.astype(float), minlength=n)
    s = np.bincount(lab, weights=np.where(obs, val, 0.0), minlength=n)
    value = np.where(o > 0, s / np.maximum(o, 1), np.nan)
    cov = np.where(area > 0, o / np.maximum(area, 1), 0.0)
    return value, cov


def noise_from_pair(va, vb, ca, cb) -> float:
    """Std over units of (a - b), using units well observed in both."""
    ok = np.isfinite(va) & np.isfinite(vb) & (ca >= MIN_EPOCH_UNIT_COVERAGE) & (cb >= MIN_EPOCH_UNIT_COVERAGE)
    if ok.sum() < 2:
        raise ValueError("too few well-observed units to estimate noise")
    return float(np.std(va[ok] - vb[ok], ddof=1))


def detect(fraction: str, va, vb, ca, cb, noise: float, *, epoch_ok=(True, True)) -> dict:
    """Per-unit change status for ONE fraction."""
    thr = K_NOISE * noise
    delta = vb - va
    status = np.full(va.shape, "no_detectable_change", dtype=object)
    sig = np.abs(delta) > thr
    status[sig & (delta > 0)] = "increase"
    status[sig & (delta < 0)] = "decrease"
    status[(ca < MIN_EPOCH_UNIT_COVERAGE) | (cb < MIN_EPOCH_UNIT_COVERAGE)
           | ~np.isfinite(va) | ~np.isfinite(vb)] = "insufficient_observation"
    if not all(epoch_ok):
        status[:] = "epoch_unreliable"
    counts = {s: int((status == s).sum()) for s in
              ("increase", "decrease", "no_detectable_change", "insufficient_observation",
               "epoch_unreliable")}
    units_out = [{"unit_index": i, "fraction": fraction,
                  "delta": (float(delta[i]) if np.isfinite(delta[i]) else None),
                  "status": str(status[i])} for i in range(len(va))]
    return {"fraction": fraction, "noise": noise, "k": K_NOISE, "threshold": thr,
            "counts": counts, "units": units_out}


def not_computed_block():
    return {f: {"status": "not_computed",
                "reason": "requires item 21's spectral regression, not built"} for f in NOT_COMPUTED}


# ── Earth Engine parts ──────────────────────────────────────────────────

def ob_temporal_presence(layer, year: int):
    """Mean `building_presence` per 10 m pixel for one Open Buildings
    Temporal year, on fractions.grid_for(layer). Raises NoDataError when the
    year has no image over the AOI."""
    import datetime
    import ee
    from ingestion.errors import NoDataError
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    transform, (H, W) = fractions.grid_for(layer)
    aoi = ee.Geometry.Rectangle(list(layer.bbox))
    t0 = int(datetime.datetime(year, 1, 1, tzinfo=datetime.timezone.utc).timestamp())
    t1 = int(datetime.datetime(year + 1, 1, 1, tzinfo=datetime.timezone.utc).timestamp())
    col = (ee.ImageCollection(OB_TEMPORAL_ASSET).filterBounds(aoi)
           .filter(ee.Filter.gte("inference_time_epoch_s", t0))
           .filter(ee.Filter.lt("inference_time_epoch_s", t1)))
    n = col.size().getInfo()
    if n == 0:
        raise NoDataError(f"no Open Buildings Temporal image for {year} over {layer.name}")
    proj = col.first().select("building_presence").projection()
    img = (col.select("building_presence").mosaic().setDefaultProjection(proj)
           # The asset's native grid is 0.5 m (measured live 2026-10-27: Earth
           # Engine reported 400 input pixels per 10 m output pixel), so a
           # 10 m mean needs >= 400. 1024 leaves headroom for grid misalignment.
           .reduceResolution(ee.Reducer.mean(), maxPixels=1024)
           .unmask(-9999).toFloat())
    grid = {"dimensions": {"width": W, "height": H},
            "affineTransform": {"scaleX": transform.a, "shearX": 0, "translateX": transform.c,
                                "shearY": 0, "scaleY": transform.e, "translateY": transform.f},
            "crsCode": layer.crs.to_string()}
    arr = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "grid": grid})
    a = arr["building_presence"].astype(np.float32)
    a = np.where(a == -9999, np.nan, a)
    return {"presence": a, "observed": np.isfinite(a), "transform": transform, "shape": (H, W),
            "images": int(n), "year": year}


def _half(which):
    import ee
    lo, hi = (1, 15) if which == "A" else (16, 31)
    return lambda col: col.filter(ee.Filter.calendarRange(lo, hi, "day_of_month"))


def run_change(layer) -> dict:
    """Two epochs, one AOI, per fraction, on item 22's grid units."""
    tr, shape = fractions.grid_for(layer)
    polys = units.grid_units(layer, tr)
    out = {"aoi": layer.name, "unit_type": "grid", "n_units": len(polys),
           "grid_cell_m": units.GRID_CELL_M, "pre_registration": {
               "k": K_NOISE, "min_epoch_unit_coverage": MIN_EPOCH_UNIT_COVERAGE,
               "min_epoch_valid_pct": MIN_EPOCH_VALID_PCT, "epochs": EPOCHS,
               "expectation": CHANGE_AOI["expectation"]},
           "fractions": {}, "not_computed": not_computed_block()}

    # built
    yrs = EPOCHS["built"]
    pres = {y: ob_temporal_presence(layer, y) for y in sorted(set(yrs) | set(EPOCHS["built_noise"]))}
    vals = {y: unit_values(polys, p["presence"], p["observed"], tr, shape) for y, p in pres.items()}
    (n_va, n_ca), (n_vb, n_cb) = (vals[y] for y in EPOCHS["built_noise"])
    nz = noise_from_pair(n_va, n_vb, n_ca, n_cb)
    b = detect("built", vals[yrs[0]][0], vals[yrs[1]][0], vals[yrs[0]][1], vals[yrs[1]][1], nz)
    b["epochs"] = {"a": yrs[0], "b": yrs[1], "source": OB_TEMPORAL_ASSET,
                   "images": {y: pres[y]["images"] for y in yrs}}
    b["noise_basis"] = f"std(presence {EPOCHS['built_noise'][1]} - {EPOCHS['built_noise'][0]}) over units"
    b["method"] = "open_buildings_temporal_mean_presence (built proxy)"
    out["fractions"]["built"] = b

    # vegetation, water
    (a0, a1), (b0, b1) = EPOCHS["s2"]
    full = {e: fractions.s2_index_composite(layer, s, t) for e, (s, t) in (("a", (a0, a1)), ("b", (b0, b1)))}
    halves = {h: fractions.s2_index_composite(layer, a0, a1, collection_filter=_half(h)) for h in "AB"}
    quality = {e: full[e]["observation_quality"] for e in full}
    epoch_ok = tuple((quality[e].get("valid_observation_pct") or 0) >= MIN_EPOCH_VALID_PCT for e in ("a", "b"))
    for f in ("vegetation", "water"):
        def v(c):
            cls = fractions.classify_indices(c["ndvi"], c["mndwi"], c["valid_obs"])
            return unit_values(polys, cls[f], cls["observed"], tr, shape)
        (va, ca), (vb, cb) = v(full["a"]), v(full["b"])
        (ha, hca), (hb, hcb) = v(halves["A"]), v(halves["B"])
        nz = noise_from_pair(ha, hb, hca, hcb)
        r = detect(f, va, vb, ca, cb, nz, epoch_ok=epoch_ok)
        r["epochs"] = {"a": {"window": [a0, a1], "images": full["a"]["source_image_count"],
                             "observation_quality": quality["a"]},
                       "b": {"window": [b0, b1], "images": full["b"]["source_image_count"],
                             "observation_quality": quality["b"]}}
        r["noise_basis"] = (f"std(split-half A - B) over units, window {a0}..{a1}, "
                            f"halves {halves['A']['source_image_count']}+{halves['B']['source_image_count']} images")
        r["method"] = fractions.PROXY_METHOD[f]
        r["producer"] = fractions.PRODUCER[f]
        out["fractions"][f] = r
    return layer.stamp(out)
