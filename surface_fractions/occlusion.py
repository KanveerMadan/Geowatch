"""
Item 21 Phase A, part 2 — occlusion masking (Decision 14's observability
group).

Causes, each its own field, never merged into one "unknown" (Decision 14):

  cloud           SCL 8, 9, 10
  nodata          SCL 0, 1, or no scene at all
  shadow_full     status "not_computed": the full/partial boundary is UNSET
                  (Decisions 11/14). SCL 3 is cloud shadow only and is NOT
                  used as full shadow (Phase A ruling, 2026-09-25).
  transient_snow  SCL 11, except on `snow_ice` pixels, where snow is the
                  surface (a fraction, not occlusion)
  fire            FIRMS active fire on the scene's date
  smoke, ships    status "no_producer"

Partially shadowed pixels are not touched here: they stay in the denominator
with no explicit term (shadow rule, locked 2026-09-24).

How a composite is attributed (Phase A ruling): masking is per scene. Each
observation gets exactly one category, by the precedence in
configs/fractions.yaml `occlusion.precedence`. A pixel is occluded when it
has no usable observation; it is attributed to one cause only if every
removed observation had that cause, otherwise to `multiple_causes`. Per-cause
shares of removed OBSERVATIONS are reported alongside the pixel shares.

Earth Engine produces per-pixel observation counts per category and two
medians (valid only; valid + snow). Everything after that is local numpy in
`resolve_occlusion`, which is where the rules live and are tested.
"""

from __future__ import annotations

import numpy as np

from ingestion.sentinel2 import S2_BAND_NAMES

COUNT_CATEGORIES = ("nodata", "cloud", "fire", "snow", "valid")
COUNT_BANDS = ["n_total"] + [f"n_{c}" for c in COUNT_CATEGORIES]
COMPOSITE_VALID_BANDS = [f"cv_{b}" for b in S2_BAND_NAMES]
COMPOSITE_VALID_SNOW_BANDS = [f"cvs_{b}" for b in S2_BAND_NAMES]
OBSERVATION_BANDS = COUNT_BANDS + COMPOSITE_VALID_BANDS + COMPOSITE_VALID_SNOW_BANDS

# The fields of the observability group, in reporting order.
CAUSES = ("cloud", "nodata", "shadow_full", "transient_snow", "fire", "smoke", "ships")


# ── Earth Engine side ───────────────────────────────────────────────────────

def _any_code(scl, codes):
    codes = list(codes)
    m = scl.eq(codes[0])
    for c in codes[1:]:
        m = m.Or(scl.eq(c))
    return m


def build_observation_image(region, window: dict, cfg: dict):
    """-> (ee.Image with OBSERVATION_BANDS, provenance dict).

    Same scene selection as the part 1 composite
    (sentinel2.get_sentinel2_collection), so both describe one set of scenes.
    """
    import ee
    from ingestion.sentinel2 import S2_BANDS, get_sentinel2_collection

    occ = cfg["occlusion"]
    scl_codes = occ["scl_codes"]
    precedence = occ["precedence"]
    if list(precedence) != [c for c in COUNT_CATEGORIES if c != "valid"]:
        raise ValueError(f"occlusion.precedence {precedence} does not match "
                         f"COUNT_CATEGORIES {COUNT_CATEGORIES}")
    firms = ee.ImageCollection(occ["fire"]["collection"])
    firms_band = occ["fire"]["band"]

    collection = get_sentinel2_collection(region, window["start"], window["end"],
                                          cfg["sentinel2"]["cloud_cover_threshold"])

    def per_scene(img):
        scl = img.select("SCL")
        day = ee.Date(img.get("system:time_start"))
        fire_day = firms.filterDate(day.update(hour=0, minute=0, second=0),
                                    day.update(hour=0, minute=0, second=0).advance(1, "day"))
        fire = ee.Image(ee.Algorithms.If(
            fire_day.size().gt(0),
            fire_day.select(firms_band).max().mask().gt(0).unmask(0),
            ee.Image(0))).rename("fire_raw")

        nodata = _any_code(scl, scl_codes["nodata"])
        cloud = _any_code(scl, scl_codes["cloud"]).And(nodata.Not())
        fire_c = fire.And(nodata.Not()).And(cloud.Not())
        snow = _any_code(scl, scl_codes["snow"]).And(nodata.Not()).And(cloud.Not()).And(fire_c.Not())
        valid = nodata.Or(cloud).Or(fire_c).Or(snow).Not()

        refl = img.select(S2_BANDS, list(S2_BAND_NAMES)).divide(10000)
        return (ee.Image.cat([
                    ee.Image(1).rename("n_total"),
                    nodata.rename("n_nodata"), cloud.rename("n_cloud"),
                    fire_c.rename("n_fire"), snow.rename("n_snow"),
                    valid.rename("n_valid"),
                    refl.updateMask(valid).rename(COMPOSITE_VALID_BANDS),
                    refl.updateMask(valid.Or(snow)).rename(COMPOSITE_VALID_SNOW_BANDS)])
                .set("firms_images", fire_day.size()))

    scenes = collection.map(per_scene)
    counts = scenes.select(COUNT_BANDS).sum().unmask(0)
    comp_valid = scenes.select(COMPOSITE_VALID_BANDS).median()
    comp_valid_snow = scenes.select(COMPOSITE_VALID_SNOW_BANDS).median()
    image = ee.Image.cat([counts, comp_valid, comp_valid_snow]).select(OBSERVATION_BANDS)

    dates = collection.aggregate_array("system:time_start").getInfo()
    firms_counts = scenes.aggregate_array("firms_images").getInfo()
    prov = {
        "scene_count": len(dates),
        "scene_dates": [ee.Date(d).format("YYYY-MM-dd").getInfo() for d in dates],
        "scl_codes": scl_codes,
        "precedence": list(precedence),
        "fire": {"collection": occ["fire"]["collection"], "band": firms_band,
                 "native_resolution_m": occ["fire"]["native_resolution_m"],
                 "match": "same UTC calendar date as the Sentinel-2 scene",
                 "confidence_filter": None,
                 "scenes_without_firms_image": sum(1 for n in firms_counts if n == 0)},
    }
    return image, prov


# ── Local side: the rules ───────────────────────────────────────────────────

def resolve_occlusion(counts: dict, snow_ice: np.ndarray | None,
                      firms_complete: bool = True) -> dict:
    """Apply the attribution rules to per-pixel observation counts.

    counts: {"n_total", "n_nodata", "n_cloud", "n_fire", "n_snow", "n_valid"}
            -> int arrays (NaN-free).
    snow_ice: 0/1 array of permanent-snow pixels, or None if the snow_ice
            detector is not_computed. Where snow_ice is 1, snow observations
            are the surface and count as usable.

    Returns {"known", "use_snow_composite", "pixels": {cause: bool array},
             "fields": {...observability group...}}.
    """
    n = {k: np.asarray(v, dtype=np.int64) for k, v in counts.items()}
    shape = n["n_total"].shape
    total_px = int(np.prod(shape))
    n_snow = n["n_snow"]

    if snow_ice is None:
        snow_is_surface = np.zeros(shape, dtype=bool)
        snow_unresolved = n_snow > 0
    else:
        snow_is_surface = np.asarray(snow_ice).astype(bool)
        snow_unresolved = np.zeros(shape, dtype=bool)

    usable = n["n_valid"] + np.where(snow_is_surface, n_snow, 0)
    known = usable > 0
    occluded = ~known

    # Removed observations by cause, per pixel. Snow on a snow_ice pixel is
    # not a removal; snow where snow_ice is unknown is its own unresolved
    # removal rather than being guessed transient or permanent.
    transient = np.where(snow_is_surface | snow_unresolved, 0, n_snow)
    unresolved = np.where(snow_unresolved, n_snow, 0)
    no_scene = n["n_total"] == 0
    removed = {
        "cloud": n["n_cloud"],
        "nodata": n["n_nodata"],
        "transient_snow": transient,
        "fire": n["n_fire"],
        "snow_unresolved": unresolved,
    }
    n_causes = sum((v > 0).astype(np.int64) for v in removed.values())

    pixels = {}
    for cause, r in removed.items():
        pixels[cause] = occluded & (r > 0) & (n_causes == 1)
    # A pixel no scene ever covered is no-data by definition.
    pixels["nodata"] = pixels["nodata"] | (occluded & no_scene)
    pixels["multiple_causes"] = occluded & (n_causes > 1)
    attributed = sum(p.astype(np.int64) for p in pixels.values())
    assert int(attributed.max(initial=0)) <= 1, "a pixel was attributed twice"
    assert np.array_equal(attributed.astype(bool), occluded), \
        "an occluded pixel has no cause, or a known pixel has one"

    total_obs = int(n["n_total"].sum())

    def field(cause, **extra):
        px = pixels[cause]
        out = {"status": "computed",
               "pixel_share": float(px.sum()) / total_px if total_px else None,
               "pixels": int(px.sum())}
        if cause in removed:
            out["removed_observation_share"] = (float(removed[cause].sum()) / total_obs
                                                if total_obs else None)
        out.update(extra)
        return out

    fields = {
        "cloud": field("cloud"),
        "nodata": field("nodata"),
        "shadow_full": {"status": "not_computed",
                        "reason": "full/partial shadow boundary is UNSET "
                                  "(Decisions 11/14); SCL 3 is cloud shadow "
                                  "only and is not used"},
        "transient_snow": field("transient_snow") if snow_ice is not None or not snow_unresolved.any()
        else {"status": "not_computed",
              "reason": "snow_ice not computed, so SCL 11 cannot be split into "
                        "permanent and transient; see snow_unresolved"},
        "fire": field("fire", producer="FIRMS",
                      **({} if firms_complete else
                         {"caveat": "some scenes had no FIRMS image for their date"})),
        "smoke": {"status": "no_producer"},
        "ships": {"status": "no_producer"},
        "multiple_causes": field("multiple_causes"),
    }
    if snow_unresolved.any():
        fields["snow_unresolved"] = field("snow_unresolved")

    missing = [c for c in CAUSES if fields[c]["status"] != "computed"]
    return {
        "known": known,
        "use_snow_composite": snow_is_surface,
        "pixels": pixels,
        "fields": {
            "observed_fraction": float(known.sum()) / total_px if total_px else None,
            "known_pixels": int(known.sum()),
            "total_pixels": total_px,
            "total_observations": total_obs,
            "causes": fields,
            "denominator_caveat": (
                "known-pixel denominator is an UPPER BOUND: these causes are "
                f"not removed because they have no producer yet: {missing}"
                if missing else None),
        },
    }


def observable_composite(bands: dict, occ: dict) -> dict:
    """Per-pixel Sentinel-2 reflectance from usable observations only:
    valid-only median, or valid + snow median on snow_ice pixels. NaN where
    the pixel is not known."""
    out = {}
    for b in S2_BAND_NAMES:
        v = np.where(occ["use_snow_composite"], bands[f"cvs_{b}"], bands[f"cv_{b}"])
        out[b] = np.where(occ["known"], v, np.nan).astype(np.float32)
    return out


def check_config(cfg: dict) -> None:
    """Refuse a config that sets a criterion this code does not implement.
    A value appearing in config must never be silently ignored."""
    occ = cfg["occlusion"]
    if occ["shadow_full"]["criterion"] is not None:
        raise NotImplementedError(
            "occlusion.shadow_full.criterion is set, but no full-shadow "
            "producer is implemented. Build the producer before setting it.")
    if occ["fire"]["confidence_min"] is not None:
        raise NotImplementedError(
            "occlusion.fire.confidence_min is set, but no FIRMS confidence "
            "filter is implemented.")


def export_observations(aoi_cfg: dict, cfg: dict, grid, run_dir: str) -> tuple:
    """Build and export the observation image on `grid`; -> (bands, prov)."""
    import os
    from ingestion.tiler import export_image_local
    from surface_fractions.grid import grid_region
    from surface_fractions.inputs import NODATA, read_stack

    check_config(cfg)
    region = grid_region(grid)
    image, prov = build_observation_image(region, aoi_cfg["composite_window"], cfg)
    path = os.path.join(run_dir, "observations.tif")
    export_image_local(image.toFloat().unmask(NODATA), region, path, crs=grid.crs,
                       crs_transform=list(grid.transform), band_names=OBSERVATION_BANDS)
    bands = read_stack(path, grid, OBSERVATION_BANDS)
    prov["path"] = path
    return bands, prov
