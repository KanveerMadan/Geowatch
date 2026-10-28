"""
Item 33 (C19): the known-pixel denominator, observed_fraction, and the two
groups of Decision 14 -- never merged, never summed by the producer.

OBSERVABILITY defines the denominator. A pixel is OBSERVED when it has at
least MIN_VALID_OBS clear Sentinel-2 observations in the window, where a
clear observation is one that is none of the occlusion causes below. Every
fraction's value is over observed pixels only, and `observed_fraction` --
the observed share of the AOI -- is emitted beside it, always.

    cloud_nodata     SCL 8, 9, 10 (cloud, cirrus) and 0, 1 (no data,
                     saturated). Removed from the composite.
    fully_shadowed   SCL 3 (cloud shadow). Removed. Decision 14 (a)'s
                     estimator is SCL plus solar geometry; solar geometry is
                     not built and the full/partial boundary is undecided, so
                     this field is a `placeholder`. Partial shadow stays in
                     the denominator and is never reported (shadow rule,
                     2026-09-24).
    transient_snow   SCL 11. Removed. There is no permanent-snow layer to
                     tell transient from permanent snow, so every SCL snow
                     observation is treated as transient: `placeholder`.
    fire_smoke       no producer: not_computed, `placeholder`.
    ships            no producer: not_computed, `placeholder`.

Each cause is reported as the share of the AOI's (pixel, scene)
observations it removed. The shares are independent: they are NOT summed,
and they do not add up to 1 - observed_fraction (a pixel can lose some
scenes to cloud and others to shadow and still be observed).

ESTIMATE QUALITY never touches the denominator: the per-fraction
regression prediction interval and paved's derivation uncertainty. Neither
has a producer before item 21, so both are not_computed. Nothing in this
module reads them, which is the structural guarantee.
"""
from __future__ import annotations

import numpy as np

from analysis import contract as C

SCL_CAUSES = {"cloud_nodata": (0, 1, 8, 9, 10), "fully_shadowed": (3,), "transient_snow": (11,)}
# Removed from the composite by occlusion_filter() (cloud/no-data is removed
# downstream by ingestion.sentinel2.mask_s2_clouds as before).
OCCLUSION_MASKED_SCL = (3, 11)
NOT_COMPUTED_CAUSES = ("fire_smoke", "ships")
CAUSE_LABEL = {"cloud_nodata": "experimental", "fully_shadowed": "placeholder",
               "transient_snow": "placeholder"}
CAUSE_METHOD = {"cloud_nodata": "Sentinel-2 SCL classes 0, 1, 8, 9, 10",
                "fully_shadowed": "Sentinel-2 SCL class 3 (cloud shadow); solar geometry not built",
                "transient_snow": "Sentinel-2 SCL class 11; no permanent-snow layer to exclude"}


def occlusion_filter(col):
    """Collection filter (vector.fractions.s2_index_composite's
    `collection_filter`): drop shadow and snow observations per pixel, so
    they leave the median and the clear-observation count."""
    def mask(img):
        scl = img.select("SCL")
        bad = scl.eq(OCCLUSION_MASKED_SCL[0])
        for c in OCCLUSION_MASKED_SCL[1:]:
            bad = bad.Or(scl.eq(c))
        return img.updateMask(bad.Not())
    return col.map(mask)


def fetch_cause_counts(layer, transform, shape, window: dict, cloud_cover_threshold: int) -> dict:
    """Per-pixel counts, over the window's scenes, of scenes with an SCL value
    (n_scene) and of scenes in each cause. Earth Engine; raises on its errors."""
    import ee
    from ingestion.sentinel2 import get_sentinel2_collection
    H, W = shape
    aoi = ee.Geometry.Rectangle(list(layer.bbox))
    col = get_sentinel2_collection(aoi, window["start"], window["end"], cloud_cover_threshold)

    def per_image(img):
        scl = img.select("SCL")
        bands = [scl.mask().rename("n_scene")]
        for name, codes in SCL_CAUSES.items():
            m = scl.eq(codes[0])
            for c in codes[1:]:
                m = m.Or(scl.eq(c))
            bands.append(m.rename(name))
        return ee.Image.cat(bands).toFloat()

    img = col.map(per_image).sum().unmask(0).toFloat()
    grid = {"dimensions": {"width": W, "height": H},
            "affineTransform": {"scaleX": transform.a, "shearX": 0, "translateX": transform.c,
                                "shearY": 0, "scaleY": transform.e, "translateY": transform.f},
            "crsCode": layer.crs.to_string()}
    arr = ee.data.computePixels({"expression": img, "fileFormat": "NUMPY_NDARRAY", "grid": grid})
    return {k: np.asarray(arr[k], dtype=np.float64) for k in ("n_scene", *SCL_CAUSES)}


def aoi_mask(layer, transform, shape) -> np.ndarray:
    from rasterio.features import rasterize
    from shapely.geometry import mapping
    return rasterize([(mapping(layer.aoi), 1)], out_shape=shape, transform=transform,
                     fill=0, dtype="uint8").astype(bool)


def observed_fraction(valid_obs, inside) -> float:
    """THE denominator's share of the AOI. Reads only the clear-observation
    count: no estimate-quality quantity can reach it."""
    from vector.fractions import MIN_VALID_OBS
    n = int(inside.sum())
    return float(((np.asarray(valid_obs) >= MIN_VALID_OBS) & inside).sum() / n) if n else 0.0


def cause_shares(counts: dict, inside) -> dict:
    """{cause: share of the AOI's (pixel, scene) observations it removed}."""
    total = float(counts["n_scene"][inside].sum())
    return {c: (float(counts[c][inside].sum()) / total if total else None) for c in SCL_CAUSES}


def outputs(valid_obs, inside, counts_outcome: dict, fset: dict, window: dict, mv: dict) -> tuple:
    """(observability group, estimate_quality group) as contract outputs."""
    s2 = [f"COPERNICUS/S2_SR_HARMONIZED SCL {window['start']}..{window['end']}"]
    of = observed_fraction(valid_obs, inside)
    from vector.fractions import MIN_VALID_OBS
    obs = {"observed_fraction": C.output(
        round(of, 6), validation_status="experimental",
        coverage=C.coverage(of, "this IS the denominator: pixels with >= "
                                f"{MIN_VALID_OBS} clear observations, as a share of the AOI"),
        data_sources=s2, model_version=mv, unit="share of AOI pixels",
        denominator_excludes=["cloud_nodata", "fully_shadowed", "transient_snow"])}
    if counts_outcome["status"] == "ok":
        shares = cause_shares(counts_outcome["value"], inside)
        for c, v in shares.items():
            kw = dict(validation_status=CAUSE_LABEL[c], data_sources=s2, model_version=mv,
                      method=CAUSE_METHOD[c], unit="share of AOI pixel-scene observations",
                      group="observability")
            if v is None:
                obs[c] = C.absent("insufficient_observation", reason="no scenes in window", **kw)
            else:
                obs[c] = C.output(round(v, 6), coverage=C.coverage(
                    1.0, "every scene's SCL over the AOI"), **kw)
    else:
        for c in SCL_CAUSES:
            obs[c] = C.absent(counts_outcome["status"],
                              reason=f"observability stage {counts_outcome['status']}: "
                                     f"{counts_outcome.get('error')}",
                              validation_status=CAUSE_LABEL[c], data_sources=s2,
                              model_version=mv, method=CAUSE_METHOD[c], group="observability")
    for c in NOT_COMPUTED_CAUSES:
        obs[c] = C.absent("not_computed", reason="no producer for this occlusion cause",
                          validation_status="placeholder", data_sources=["none: not computed"],
                          model_version=mv, group="observability")

    eq = {"prediction_interval": {}}
    for f in (*fset["fractions"], *fset["not_computed"]):
        eq["prediction_interval"][f] = C.absent(
            "not_computed", reason="regression prediction intervals need item 21's regressors; "
                                   "the stand-ins are thresholds and have none",
            validation_status="placeholder", data_sources=["none: not computed"],
            model_version=mv, group="estimate_quality", touches_denominator=False)
    eq["paved_derivation_uncertainty"] = C.absent(
        "not_computed", reason="paved is not computed before item 21",
        validation_status="placeholder", data_sources=["none: not computed"], model_version=mv,
        group="estimate_quality", touches_denominator=False)
    return obs, eq
