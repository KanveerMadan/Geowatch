"""
Round 3, Phase 2: label rules v3 (the same for every method, baselines included).

Four label states per 30 m cell: FLOODED (1), DRY (0), UNOBSERVED (-1),
PERMANENT WATER (-2). Only FLOODED and DRY are scored; the rest is outside
the scoring domain.

Every rule below comes from how the labels are made (Phase 1, DIAGNOSIS.md).
None was chosen by comparing methods.

Sentinel-1 VV change label (our own; replaces round 4's rule)
-------------------------------------------------------------
R3-S1-1 **Baseline.** The same relative orbit's median over [t0 - 60 d, t0 - 6 d].
  - Round 4 used 1 Jan - 31 Mar of the event year. That baseline contains the flood for January-March events and is wet-season for many others (8 of 50 burned S1 units).
  - With fewer than 2 images in that window, the median over the same calendar window one year earlier is used.
R3-S1-2 **Open water.** A 10 m pixel is water when VV(post) - VV(baseline) <= -3 dB AND VV(post) <= -15 dB.
  - Smooth open water is a specular reflector, and its VV backscatter sits well below -15 dB at IW incidence angles.
  - A drop alone also fires on wet soil, harvest and speckle. Round 2's rain labels flooded high ground at the same rate as low ground: P(flooded | HAND > 20 m) = P(flooded | HAND < 3 m), Phase 1c.
R3-S1-3 **Maximum extent.** Every pass inside the type's window [t_peak, t_peak + MAX_LAG[type]] counts.
  - A cell is flooded if it is water in any pass where it was observed.
  - It is dry only if it was observed in at least one pass and was never water.
R3-S1-4 **Cell rule.** A 30 m cell is observed when >= 50 % of its 10 m pixels are observed. It is flooded when >= 50 % of its observed 10 m pixels are water (as round 4).

Observability (radar sources: our S1 and EMS products made from SAR)
----------------------------------------------------------------------
R3-O-1 **High ground.** MERIT HAND > 15 m is UNOBSERVED.
  - This is GFM's exclusion rule (Copernicus Global Flood Monitoring excludes HAND > 15 m): radar water detection there is dominated by false positives.
  - Phase 1c: S1 labels flood 2-2.6 % of cells above HAND 30 m. EMS SAR products flood 0.01-0.15 %.
R3-O-2 **Built-up.** Built-up cells are UNOBSERVED for radar: GHSL or WorldCover built share >= 0.5.
  - Double bounce from walls raises backscatter where streets flood, so a VV drop cannot see that flooding.
  - Phase 1d: in built-up cells the flood rate is 1/10 to 1/70 of the open-ground rate in every type.
  - An urban-capable label (coherence drop, VHR optical, surveyed marks) lifts this rule for the cells it covers.
R3-O-3 **Possible shadow or layover.** GLO-30 slope > 20 deg is UNOBSERVED for radar.
  - Layover needs a sensor-facing slope steeper than the incidence angle (29-46 deg for IW). Shadow needs a slope facing away steeper than 90 deg minus it.
  - So no cell at 20 deg or less is in either, and 20 deg is a conservative cut.
  - Phase 1d: it touches 0.4 % of labelled flash-flood cells.
R3-O-4 **Permanent water.** JRC occurrence >= 80 % is PERMANENT WATER (as before).

Optical and analyst products (EMS from optical or VHR imagery, UNOSAT)
-----------------------------------------------------------------------
- Kept as published: flooded inside the observed-flood layer, dry inside the product extent, unobserved outside.
- R3-O-4 applies. R3-O-1 to R3-O-3 do not, because they describe radar.

Image timing
------------
MAX_LAG_DAYS[type]: the latest label image counted after the driver peak. It is set in DIAGNOSIS.md §b from the burned units and fixed before the reserve is sealed.
"""
from __future__ import annotations

import datetime as dt

import numpy as np

FLOODED, DRY, UNOBSERVED, PERMANENT = 1, 0, -1, -2
DROP_DB = -3.0
WATER_DB = -15.0
BASE_DAYS = (60, 6)                 # baseline window: [t0 - 60 d, t0 - 6 d]
HAND_EXCLUDE_M = 15.0
BUILT_SHARE = 0.5
SLOPE_EXCLUDE_DEG = 20.0
PERMANENT_PCT = 80.0
COVER_MIN = 0.5
S1 = "COPERNICUS/S1_GRD"
RADAR_SENSORS = ("Sentinel-1", "COSMO-SkyMed", "RADARSAT-2", "TerraSAR-X", "TanDEM-X", "PAZ", "ICEYE",
                 "SAOCOM", "RCM", "Capella", "ALOS-2", "Umbra")


def is_radar(sensors) -> bool:
    return any(any(r.lower() in (s or "").lower() for r in RADAR_SENSORS) or "SAR" in (s or "") for s in sensors)


def _col(ee, aoi):
    return (ee.ImageCollection(S1).filterBounds(aoi)
            .filter(ee.Filter.eq("instrumentMode", "IW"))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV"))
            .select("VV"))


def s1_passes(ee, bbox, t0: str, t1: str) -> list:
    """[(date, relative orbit)] of S1 IW passes over bbox with date in [t0, t1]."""
    aoi = ee.Geometry.Rectangle(list(bbox))
    c = _col(ee, aoi).filterDate(t0, (dt.date.fromisoformat(t1) + dt.timedelta(days=1)).isoformat())
    info = ee.List([c.aggregate_array("system:time_start"), c.aggregate_array("relativeOrbitNumber_start")]).getInfo()
    out = sorted({(dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date().isoformat(), int(o))
                  for t, o in zip(*info)})
    return out


def s1_label(ee, bbox, t0: str, t1: str, transform, shape, crs: str) -> dict:
    """R3-S1-1..4 max-extent water / observed shares on the grid. Returns
    {"water_share", "obs_share", "passes", "baselines"} (arrays on the grid)."""
    from susceptibility.hydro_rasters import compute_pixels
    aoi = ee.Geometry.Rectangle(list(bbox))
    col = _col(ee, aoi)
    passes = s1_passes(ee, bbox, t0, t1)
    if not passes:
        raise LookupError(f"no S1 IW pass over {bbox} in [{t0}, {t1}]")
    water_any, obs_any, used, bases = None, None, [], []
    a = dt.date.fromisoformat(t0)
    for d, orb in passes:
        dd = dt.date.fromisoformat(d)
        post = col.filterDate(d, (dd + dt.timedelta(days=1)).isoformat()).filter(
            ee.Filter.eq("relativeOrbitNumber_start", orb)).mosaic()
        b0, b1 = a - dt.timedelta(days=BASE_DAYS[0]), a - dt.timedelta(days=BASE_DAYS[1])
        base_c = col.filter(ee.Filter.eq("relativeOrbitNumber_start", orb)).filterDate(b0.isoformat(), b1.isoformat())
        n = base_c.size().getInfo()
        tag = "pre"
        if n < 2:
            y0, y1 = b0 - dt.timedelta(days=365), b1 - dt.timedelta(days=365)
            base_c = col.filter(ee.Filter.eq("relativeOrbitNumber_start", orb)).filterDate(y0.isoformat(), y1.isoformat())
            n = base_c.size().getInfo()
            tag = "year_before"
        if n < 2:
            continue
        base = base_c.median()
        water = post.subtract(base).lte(DROP_DB).And(post.lte(WATER_DB))
        obs = post.mask().reduce(ee.Reducer.min()).gt(0)
        w = water.unmask(0).And(obs)
        water_any = w if water_any is None else water_any.Or(w)
        obs_any = obs.unmask(0) if obs_any is None else obs_any.Or(obs.unmask(0))
        used.append({"date": d, "orbit": orb})
        bases.append({"orbit": orb, "baseline": tag, "images": int(n)})
    if water_any is None:
        raise LookupError(f"no S1 pass with a baseline over {bbox} in [{t0}, {t1}]")
    obs10 = obs_any.rename("obs").toFloat()
    wat10 = water_any.And(obs_any).rename("wat").toFloat()
    img = ee.Image.cat([obs10, wat10]).reproject(crs=crs, scale=10).reduceResolution(ee.Reducer.mean(), maxPixels=64)
    arr = compute_pixels(img, transform, shape, crs, "s1 v3 label")
    obs_share = np.asarray(arr["obs"], np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        water_share = np.where(obs_share > 0, np.asarray(arr["wat"], np.float64) / obs_share, np.nan)
    return {"water_share": water_share, "obs_share": obs_share, "passes": used, "baselines": bases}


def observability(ee, transform, shape, crs: str) -> dict:
    """MERIT HAND, GLO-30 slope, built share, JRC occurrence on the grid (one request)."""
    from experiments.flood_learned import fetch as F
    from susceptibility.hydro_rasters import compute_pixels, grid_lonlat_bounds
    ll = grid_lonlat_bounds(transform, shape, crs)
    region = ee.Geometry.Rectangle(list(ll))
    dem = F._mosaic(F.GLO30_ASSET, region, "DEM")
    wc = ee.ImageCollection("ESA/WorldCover/v200").first().select("Map")
    wcb = wc.eq(50).toFloat().setDefaultProjection(wc.projection()).reduceResolution(ee.Reducer.mean(), maxPixels=64)
    img = ee.Image.cat([
        ee.Image(F.MERIT_ASSET).select("hnd").rename("hand"),
        ee.Terrain.slope(dem).rename("slope"),
        wcb.rename("wc_built"),
        ee.Image(F.GHSL_BUILT_S).select(0).divide(F.GHSL_CELL_M2).rename("ghsl_built"),
        ee.Image(F.JRC_ASSET).select("occurrence").unmask(0).rename("occ"),
    ])
    return {k: np.asarray(v, np.float64) for k, v in compute_pixels(img, transform, shape, crs, "observability").items()}


def apply_states(flooded: np.ndarray, observed: np.ndarray, obs: dict, radar: bool) -> np.ndarray:
    """The four states from a source's flooded/observed masks and the observability layers."""
    y = np.where(observed, np.where(flooded, FLOODED, DRY), UNOBSERVED).astype(np.int8)
    if radar:
        built = np.fmax(np.nan_to_num(obs["wc_built"]), np.nan_to_num(obs["ghsl_built"])) >= BUILT_SHARE
        y[(np.nan_to_num(obs["hand"], nan=0.0) > HAND_EXCLUDE_M) | built
          | (np.nan_to_num(obs["slope"], nan=0.0) > SLOPE_EXCLUDE_DEG)] = UNOBSERVED
    y[np.nan_to_num(obs["occ"], nan=0.0) >= PERMANENT_PCT] = PERMANENT
    return y


def s1_states(lab: dict, obs: dict) -> np.ndarray:
    observed = np.nan_to_num(lab["obs_share"], nan=0.0) >= COVER_MIN
    flooded = np.nan_to_num(lab["water_share"], nan=0.0) >= COVER_MIN
    return apply_states(flooded, observed, obs, radar=True)
