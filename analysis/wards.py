"""
Ward-level aggregation (item 22's units, plus administrative wards).

Unit types:
    grid, footprint, path   item 22's three partitions of the AOI
    ward:<boundary_id>      an ingested boundary layer (boundaries/ingestion.py),
                            each ward clipped to the AOI

Per unit, every producer fraction and every per-pixel flood susceptibility
(pluvial; since Phase 4 Step B also fluvial, flash flood and waterlogging)
are aggregated by vector.units.aggregate (area-weighted over the unit's
observed part). A flood type with no per-pixel map (coastal) is an AOI-wide
scalar, applied to every unit and labelled as such.

Units are STORED compact (units.json beside result.json): footprint units
number in the tens of thousands, and repeating the full contract in each
would make the file tens of MB. `materialize()` expands one unit into
contract outputs when it is served, and the tests check the expanded form.
"""
from __future__ import annotations

import json
import os

import numpy as np

from analysis import contract as C

VECTOR_UNIT_TYPES = ("grid", "footprint", "path")
BOUNDARY_ROOT = os.path.join("data", "boundaries")
PLUVIAL = "pluvial_susceptibility"
HAZARDS = ("pluvial", "fluvial", "coastal", "flash_flood", "waterlogging")


def hazard_key(h: str) -> str:
    """A flood type's per-unit key (and map name)."""
    return f"{h}_susceptibility"


def classify_pluvial(score):
    """A score's tier. The five modules share one set of breaks (checked in
    tests/test_flood_layers.py), so this classifies every flood type."""
    from configs.pluvial_constants import SUSCEPTIBILITY_CLASS_BREAKS
    if score is None:
        return None
    for label, (lo, hi) in SUSCEPTIBILITY_CLASS_BREAKS.items():
        if lo <= score < hi:
            return label
    return "very_high"


def load_boundary_units(layer, boundary_id: str, root: str = BOUNDARY_ROOT) -> list:
    """[(unit_id, unit_name, utm_polygon)] for the wards of an ingested
    boundary layer that intersect the AOI, clipped to it."""
    import geopandas as gpd
    from shapely.ops import transform as shp_transform
    import pyproj
    d = os.path.join(root, boundary_id)
    with open(os.path.join(d, "manifest.json")) as fh:
        man = json.load(fh)
    gdf = gpd.read_file(os.path.join(d, "boundary.geojson")).to_crs("EPSG:4326")
    to_utm = pyproj.Transformer.from_crs("EPSG:4326", layer.crs, always_xy=True).transform
    out = []
    for _, row in gdf.iterrows():
        g = shp_transform(to_utm, row.geometry)
        if not g.is_valid:
            g = g.buffer(0)
        clip = g.intersection(layer.aoi)
        if clip.is_empty or clip.area <= 0:
            continue
        out.append((str(row[man["unit_id_field"]]), str(row[man["unit_name_field"]]), clip,
                    float(g.area)))
    return out


def _to_geojson(geom, crs):
    import pyproj
    import shapely
    from shapely.geometry import mapping
    from shapely.ops import transform as shp_transform
    to_ll = pyproj.Transformer.from_crs(crs, "EPSG:4326", always_xy=True).transform
    return mapping(shapely.set_precision(shp_transform(to_ll, geom), 1e-6))


def build_unit_sets(layer, fset: dict, osm_regime: dict, hazards_10m: dict | None = None,
                    boundary_id: str | None = None, boundary_root: str = BOUNDARY_ROOT) -> dict:
    """{unit_type: {"status", "n_units", "units": [compact unit], ...}}

    `hazards_10m`: {hazard_key(h): per-pixel score on the fraction grid} for
    every flood type with a per-pixel map."""
    from vector import units as vu
    fr = {"rasters": dict(fset["rasters"]), "observed": dict(fset["observed"]),
          "transform": fset["transform"], "shape": fset["shape"]}
    fractions = list(fset["fractions"])
    for key, m in (hazards_10m or {}).items():
        fr["rasters"][key] = m
        fr["observed"][key] = np.isfinite(m)
        fractions.append(key)
    not_computed = tuple(fset["not_computed"])

    makers = {"grid": lambda: [(None, None, p) for p in vu.grid_units(layer, fset["transform"])],
              "footprint": lambda: [(None, None, p) for p in vu.footprint_units(layer)],
              "path": lambda: [(None, None, p) for p in vu.path_units(layer)]}
    if boundary_id:
        makers[f"ward:{boundary_id}"] = lambda: [
            (uid, name, p) for uid, name, p, _ in load_boundary_units(layer, boundary_id, boundary_root)]

    out = {}
    for t, make in makers.items():
        rows = make()
        if not rows:
            out[t] = {"status": "unavailable", "reason": f"no {t} units could be formed",
                      "n_units": 0, "units": []}
            continue
        polys = [p for _, _, p in rows]
        agg = vu.aggregate(polys, fr, osm_regime, fractions=fractions, not_computed=not_computed)
        seen = observation_per_unit(polys, fset)
        units = []
        for (uid, name, poly), u, ob in zip(rows, agg["units"], seen):
            u["observation"] = ob
            u.pop("osm_coverage", None)       # AOI-level, stored once per type
            u["unit_id"] = uid if uid is not None else str(u["unit_index"])
            u["unit_name"] = name
            u["geometry"] = _to_geojson(poly, layer.crs)
            units.append(u)
        block = {"status": "available", "n_units": len(units), "units": units,
                 "osm_coverage": osm_regime, "totals": agg["totals"]}
        if t == "path":
            fs = layer.fetch_status("network")
            block["fetch"] = fs
            if fs["status"] != "complete":
                block["status"] = "partial_fetch"
        out[t] = block
    vec = {t: {"status": out[t]["status"], "totals": out[t].get("totals"),
               "unit_area_total_m2": sum(u["area_m2"] for u in out[t]["units"])}
           for t in VECTOR_UNIT_TYPES if out[t]["units"]}
    if vec:
        consistency = vu.consistency_check(vec, layer.aoi.area)
        for t in vec:
            out[t]["consistency"] = consistency
    return out


def observation_per_unit(polys, fset: dict) -> list:
    """Item 35 (C25/C26): per unit, the observed share of its area and the
    count of observed 10 m pixels, on the same denominator as the fractions
    (>= MIN_VALID_OBS clear observations; analysis/observability.py).

        observed_fraction   observed 2 m sub-cells / all sub-cells in the unit
        valid_pixel_count   10 m pixels whose CENTRE is in the unit and that
                            are observed
        pixel_count         10 m pixels whose centre is in the unit

    A unit smaller than a pixel can have pixel_count 0; observed_fraction is
    still defined from its sub-cells."""
    from rasterio.features import rasterize
    from shapely.geometry import mapping
    from vector import units as vu
    from vector.fractions import MIN_VALID_OBS
    observed = np.asarray(fset["valid_obs"]) >= MIN_VALID_OBS
    n = len(polys)
    fine = vu._labels(polys, fset["transform"], fset["shape"])
    inside = fine >= 0
    lab = fine[inside]
    area = np.bincount(lab, minlength=n).astype(float)
    obs = np.bincount(lab, weights=vu._upsample(observed)[inside].astype(float), minlength=n)
    centre = rasterize(((mapping(p), i) for i, p in enumerate(polys)), out_shape=fset["shape"],
                       transform=fset["transform"], fill=-1, dtype="int32")
    cin = centre >= 0
    pix = np.bincount(centre[cin], minlength=n)
    vpix = np.bincount(centre[cin], weights=observed[cin].astype(float), minlength=n)
    return [{"observed_fraction": round(float(obs[i] / area[i]), 4) if area[i] else 0.0,
             "valid_pixel_count": int(vpix[i]), "pixel_count": int(pix[i])} for i in range(n)]


# ── serving ─────────────────────────────────────────────────────────────

def spatial_hazards(result: dict) -> tuple:
    """The flood types whose values were aggregated per unit. Results stored
    before Phase 4 Step B carry only pluvial's (it has no `per_unit` flag)."""
    s = result["outputs"]["susceptibility"]
    return tuple(h for h in HAZARDS if s[h].get("per_unit") or h == "pluvial")


def ward_context(result: dict) -> dict:
    """What materialize() needs from a stored result."""
    o = result["outputs"]
    fr = o["fractions"]
    spatial = spatial_hazards(result)
    return {"model_version": result["model_version"],
            "fractions": {f: {"validation_status": v["validation_status"],
                              "data_sources": v["data_sources"]} for f, v in fr.items()},
            "hazards": {h: {"validation_status": o["susceptibility"][h]["validation_status"],
                            "status": o["susceptibility"][h]["status"],
                            "data_sources": o["susceptibility"][h]["data_sources"],
                            "validated_scope": o["susceptibility"][h].get("validated_scope")}
                        for h in spatial},
            "scalar_hazards": {h: o["susceptibility"][h] for h in HAZARDS if h not in spatial},
            "observability_label": o.get("observability", {}).get(
                "observed_fraction", {}).get("validation_status", "experimental")}


def _value_status(cell: dict) -> tuple:
    """(value, status): a value only where the cell is available and has one."""
    status = cell["status"]
    value = cell["value"] if status == "available" else None
    if status == "available" and value is None:
        status = "insufficient_observation"
    return (round(float(value), 6) if value is not None else None), status


def feature(unit: dict, ctx: dict) -> dict:
    """One stored unit as a GeoJSON feature for drawing. Absent is null, never
    0 (item 36): the status says why."""
    props = {"unit_id": unit.get("unit_id"), "unit_name": unit.get("unit_name"),
             "area_m2": unit["area_m2"]}
    for f in ctx["fractions"]:
        props[f], props[f"{f}_status"] = _value_status(
            unit.get(f) or {"value": None, "status": "not_computed"})
    for h, meta in ctx["hazards"].items():
        # flood_<type>: the unit's mean score where measured, else null with
        # the status (an AOI-level timeout withholds every unit's, item 38).
        if meta["status"] != "available":
            v, st = None, meta["status"]
        else:
            v, st = _value_status(unit.get(hazard_key(h)) or {"value": None,
                                                              "status": "not_computed"})
        props[f"flood_{h}"], props[f"flood_{h}_status"] = v, st
    return {"type": "Feature", "id": unit["unit_index"], "geometry": unit.get("geometry"),
            "properties": props}


def _cell(cell: dict, *, label, sources, mv, basis, **extra) -> dict:
    value, status = _value_status(cell)
    if status == "available":
        return C.output(value, validation_status=label,
                        coverage=C.coverage(cell["coverage"], basis),
                        data_sources=sources, model_version=mv, **extra)
    if cell.get("value") is not None:
        # Below MIN_UNIT_COVERAGE: kept for transparency, never as the value.
        extra["value_below_coverage_threshold"] = round(float(cell["value"]), 6)
    return C.output(None, status=status, validation_status=label,
                    coverage=C.coverage(cell["coverage"], basis),
                    data_sources=sources, model_version=mv, **extra)


def materialize(unit: dict, unit_type: str, ctx: dict) -> dict:
    """One stored unit as contract outputs."""
    mv = ctx["model_version"]
    basis = "share of the unit's area observed for this quantity"
    outputs = {"fractions": {}}
    for f, meta in ctx["fractions"].items():
        cell = unit.get(f) or {"value": None, "status": "not_computed", "coverage": 0.0}
        outputs["fractions"][f] = _cell(cell, label=meta["validation_status"],
                                        sources=meta["data_sources"], mv=mv, basis=basis)
    ob = unit.get("observation")
    if ob is not None:
        src = ["COPERNICUS/S2_SR_HARMONIZED SCL / clear-observation count"]
        lab = ctx.get("observability_label", "experimental")
        cov = C.coverage(ob["observed_fraction"], "share of the unit's area observed")
        outputs["observability"] = {
            "observed_fraction": C.output(ob["observed_fraction"], validation_status=lab,
                                          coverage=cov, data_sources=src, model_version=mv,
                                          unit="share of unit area"),
            "valid_pixel_count": C.output(ob["valid_pixel_count"], validation_status=lab,
                                          coverage=cov, data_sources=src, model_version=mv,
                                          unit="observed 10 m pixels (centre in unit)",
                                          pixel_count=ob["pixel_count"]),
        }
    hz = {}
    for h, meta in ctx["hazards"].items():
        key = hazard_key(h)
        st = meta.get("status", "available")
        # C70: a validated output carries its scope, per unit as for the AOI.
        scope = {"validated_scope": meta["validated_scope"]} if meta.get("validated_scope") else {}
        if st in ("timeout", "failed") or (st != "available" and key in unit):
            # Item 38: the AOI-level module did not finish (timeout / failed)
            # or was withheld; no unit gets a value or tier from it, and every
            # unit says why (since flood round 4 a DEM timeout leaves no map
            # at all to sample).
            hz[h] = C.output(None, status=st, validation_status=meta["validation_status"],
                             coverage=C.coverage(0.0, f"AOI-level {h} did not finish"),
                             data_sources=meta["data_sources"], model_version=mv, tier=None,
                             **scope)
            continue
        if key not in unit:
            continue
        p = _cell(unit[key], label=meta["validation_status"], sources=meta["data_sources"],
                  mv=mv, basis=basis, **scope)
        p["tier"] = classify_pluvial(p["value"])
        p["spatial"] = True
        hz[h] = p
    for h, aoi_out in ctx["scalar_hazards"].items():
        o = {k: v for k, v in aoi_out.items()
             if k in C.OUTPUT_KEYS or k in ("tier", "reason", "tier2_verdict",
                                            "incomplete_inputs", "validated_scope")}
        o["coverage"] = C.coverage(aoi_out["coverage"]["observed_fraction"],
                                   "AOI-wide scalar applied uniformly to every unit; "
                                   "it carries no within-AOI variation")
        o["spatial"] = False
        hz[h] = o
    if hz:
        outputs["susceptibility"] = hz
    out = {"unit_type": unit_type, "unit_index": unit["unit_index"],
           "unit_id": unit.get("unit_id"), "unit_name": unit.get("unit_name"),
           "area_m2": unit["area_m2"], "geometry": unit.get("geometry"),
           "model_version": mv, "outputs": outputs}
    C.check_result(out)
    return out


def change_cells(layer, change: dict | None) -> dict:
    """Item 25's per-cell verdicts as drawable cells, on change's own grid
    (vector.change: 100 m cells from a 10 m-snapped origin, so not item 22's
    grid units). Each cell names its verdict per fraction: increase /
    decrease / no_detectable_change, or insufficient_observation /
    epoch_unreliable where no change could be judged; `delta` is null there."""
    if not change or not change.get("fractions"):
        return {"status": "unavailable", "reason": "the change stage produced no verdicts",
                "fractions": [], "cells": []}
    from vector import fractions as vf, units as vu
    polys = vu.grid_units(layer, vf.grid_for(layer)[0])
    per = change["fractions"]
    if any(len(r["units"]) != len(polys) for r in per.values()):
        return {"status": "unavailable", "reason": "change units do not match the change grid",
                "fractions": [], "cells": []}
    cells = []
    for i, poly in enumerate(polys):
        c = {"unit_index": i, "geometry": _to_geojson(poly, layer.crs)}
        for f, r in per.items():
            u = r["units"][i]
            c[f] = u["status"]
            judged = u["status"] in ("increase", "decrease", "no_detectable_change")
            c[f"{f}_delta"] = round(u["delta"], 6) if judged and u["delta"] is not None else None
        cells.append(c)
    return {"status": "available", "grid_cell_m": vu.GRID_CELL_M, "fractions": list(per),
            "cells": cells}


def change_features(block: dict) -> dict:
    """change_cells() as a GeoJSON FeatureCollection."""
    return {"type": "FeatureCollection", "status": block["status"],
            "fractions": block.get("fractions", []),
            "features": [{"type": "Feature", "id": c["unit_index"], "geometry": c["geometry"],
                          "properties": {k: v for k, v in c.items() if k != "geometry"}}
                         for c in block.get("cells", [])]}
