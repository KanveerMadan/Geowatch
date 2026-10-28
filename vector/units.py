"""
Item 22 — aggregation units. Three partitions of the AOI, in the manual's
order:

  1. grid        regular GRID_CELL_M squares on the 10 m pixel grid
  2. footprint   one unit per building: a centroid-Voronoi tessellation of
                 the footprints, clipped to the AOI (momepy's morphological
                 tessellation is not installed; this is its simpler
                 centroid form, stated as such)
  3. path        the item 19 layer's blocks(), polygons delineated by the
                 road network

Every unit carries, per fraction, {value, status, coverage}:
  value     area-weighted mean fraction over the unit's observed part
  coverage  share of the unit's area that is observed for that fraction
  status    "available" | "insufficient_observation" | "not_computed"
built/vegetation/water only. impervious_total is always status
"not_computed" with value None and coverage 0.0, NEVER 0.

Every unit also carries the item 20 coverage regime (`osm_coverage`). It is
inherited from the AOI-level score (basis "aoi"): a per-unit density rank
over a 1 ha cell is noise, not signal.

Aggregation runs on a fine sub-grid (SUBSAMPLE x per 10 m axis). Each fine
cell takes its parent pixel's fraction and is assigned to one unit by
rasterising the unit polygons. Fraction-area totals are therefore directly
comparable across unit types, which is the consistency check.
"""
from __future__ import annotations

import numpy as np
from shapely.geometry import box

from vector.fractions import FRACTIONS, NOT_COMPUTED, PIXEL_M

GRID_CELL_M = 100.0
SUBSAMPLE = 5                     # 2 m sub-cells
MIN_UNIT_COVERAGE = 0.5           # below this a unit's value is not "available"
CONSISTENCY_TOLERANCE_SHARE = 0.005   # of AOI area, per fraction (fixed 2026-10-27)

UNIT_TYPES = ("grid", "footprint", "path")


def grid_units(layer, transform) -> list:
    x0, y1 = transform.c, transform.f
    minx, miny, maxx, maxy = layer.aoi.bounds
    out = []
    y = y1
    while y > miny:
        x = x0
        while x < maxx:
            cell = box(x, y - GRID_CELL_M, x + GRID_CELL_M, y).intersection(layer.aoi)
            if not cell.is_empty and cell.area > 0:
                out.append(cell)
            x += GRID_CELL_M
        y -= GRID_CELL_M
    return out


def footprint_units(layer) -> list:
    from shapely import voronoi_polygons
    from shapely.geometry import MultiPoint
    pts = [p.representative_point() for p in layer.footprints
           if p.representative_point().within(layer.aoi)]
    if len(pts) < 2:
        return [layer.aoi] if pts else []
    cells = voronoi_polygons(MultiPoint(pts), extend_to=layer.aoi.buffer(1000))
    return [c.intersection(layer.aoi) for c in cells.geoms
            if not c.intersection(layer.aoi).is_empty]


def path_units(layer) -> list:
    return layer.blocks()


def _labels(units, transform, shape):
    """Fine-grid unit index per sub-cell (-1 = no unit)."""
    from rasterio.features import rasterize
    from rasterio.transform import Affine
    from shapely.geometry import mapping
    H, W = shape
    fine = transform * Affine.scale(1.0 / SUBSAMPLE)
    return rasterize(((mapping(u), i) for i, u in enumerate(units)),
                     out_shape=(H * SUBSAMPLE, W * SUBSAMPLE), transform=fine,
                     fill=-1, dtype="int32")


def _upsample(a):
    return np.repeat(np.repeat(a, SUBSAMPLE, axis=0), SUBSAMPLE, axis=1)


def aggregate(units, fr: dict, osm_coverage: dict, aoi_mask_fine=None) -> dict:
    """Per-unit {value, status, coverage} for each fraction, plus per-type
    fraction-area totals for the consistency check."""
    labels = _labels(units, fr["transform"], fr["shape"])
    cell_m2 = (PIXEL_M / SUBSAMPLE) ** 2
    n = len(units)
    in_unit = labels >= 0
    lab = labels[in_unit]
    area_cells = np.bincount(lab, minlength=n).astype(float)

    per_fraction = {}
    totals = {}
    for f in FRACTIONS:
        val = _upsample(fr["rasters"][f])[in_unit]
        obs = _upsample(fr["observed"][f])[in_unit] & np.isfinite(val)
        obs_cells = np.bincount(lab, weights=obs.astype(float), minlength=n)
        frac_sum = np.bincount(lab, weights=np.where(obs, val, 0.0), minlength=n)
        per_fraction[f] = (frac_sum, obs_cells)
        totals[f] = {"fraction_area_m2": float(frac_sum.sum() * cell_m2),
                     "observed_area_m2": float(obs_cells.sum() * cell_m2)}

    out_units = []
    for i in range(n):
        u = {"unit_index": i, "area_m2": float(area_cells[i] * cell_m2),
             "osm_coverage": osm_coverage}
        for f in FRACTIONS:
            s, o = per_fraction[f][0][i], per_fraction[f][1][i]
            cov = float(o / area_cells[i]) if area_cells[i] else 0.0
            u[f] = {"value": float(s / o) if o else None,
                    "status": "available" if cov >= MIN_UNIT_COVERAGE else "insufficient_observation",
                    "coverage": round(cov, 4)}
        for f in NOT_COMPUTED:
            u[f] = {"value": None, "status": "not_computed", "coverage": 0.0}
        out_units.append(u)
    return {"units": out_units, "totals": totals,
            "unit_area_total_m2": float(area_cells.sum() * cell_m2)}


def build_units(layer, fr: dict, osm_coverage: dict) -> dict:
    """All three unit types over one AOI, plus the consistency check."""
    makers = {"grid": lambda: grid_units(layer, fr["transform"]),
              "footprint": lambda: footprint_units(layer),
              "path": lambda: path_units(layer)}
    by_type = {}
    for t in UNIT_TYPES:
        polys = makers[t]()
        if not polys:
            by_type[t] = {"status": "unavailable", "reason": f"no {t} units could be formed",
                          "units": [], "totals": None}
            continue
        agg = aggregate(polys, fr, osm_coverage)
        by_type[t] = {"status": "available", "n_units": len(polys), **agg}
        if t == "path":
            # Blocks are delineated by every way: a missing clause merges blocks.
            fs = layer.fetch_status("network")
            by_type[t]["fetch"] = fs
            if fs["status"] != "complete":
                by_type[t]["status"] = "partial_fetch"
    return layer.stamp({"by_type": by_type,
                        "consistency": consistency_check(by_type, layer.aoi.area),
                        "method": fr["method"], "producer": fr["producer"]})


def consistency_check(by_type: dict, aoi_area_m2: float) -> dict:
    """Each unit type must reproduce the same fraction-area totals over the
    same area, within CONSISTENCY_TOLERANCE_SHARE of the AOI area."""
    avail = {t: v for t, v in by_type.items() if v["status"] in ("available", "partial_fetch")}
    rows = {}
    ok = True
    for f in FRACTIONS:
        vals = {t: v["totals"][f]["fraction_area_m2"] for t, v in avail.items()}
        spread = (max(vals.values()) - min(vals.values())) if vals else 0.0
        share = spread / aoi_area_m2
        rows[f] = {"fraction_area_m2_by_type": vals, "max_spread_share_of_aoi": share,
                   "within_tolerance": share <= CONSISTENCY_TOLERANCE_SHARE}
        ok &= share <= CONSISTENCY_TOLERANCE_SHARE
    area = {t: v["unit_area_total_m2"] / aoi_area_m2 for t, v in avail.items()}
    return {"result": "PASS" if ok and len(avail) == len(by_type) else "FAIL",
            "tolerance_share_of_aoi": CONSISTENCY_TOLERANCE_SHARE,
            "fractions": rows, "unit_area_over_aoi_area": area,
            "unit_types_compared": sorted(avail)}
