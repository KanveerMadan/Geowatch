"""
Ward-level aggregation (item 22's units, plus administrative wards).

Unit types:
    grid, footprint, path   item 22's three partitions of the AOI
    ward:<boundary_id>      an ingested boundary layer (boundaries/ingestion.py),
                            each ward clipped to the AOI

Per unit, every producer fraction and pluvial susceptibility are aggregated
by vector.units.aggregate (area-weighted over the unit's observed part).

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
SCALAR_HAZARDS = ("fluvial", "coastal", "flash_flood", "waterlogging")


def classify_pluvial(score):
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


def build_unit_sets(layer, fset: dict, osm_regime: dict, pluvial_10m=None,
                    boundary_id: str | None = None, boundary_root: str = BOUNDARY_ROOT) -> dict:
    """{unit_type: {"status", "n_units", "units": [compact unit], ...}}"""
    from vector import units as vu
    fr = {"rasters": dict(fset["rasters"]), "observed": dict(fset["observed"]),
          "transform": fset["transform"], "shape": fset["shape"]}
    fractions = list(fset["fractions"])
    if pluvial_10m is not None:
        fr["rasters"][PLUVIAL] = pluvial_10m
        fr["observed"][PLUVIAL] = np.isfinite(pluvial_10m)
        fractions.append(PLUVIAL)
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

def ward_context(result: dict) -> dict:
    """What materialize() needs from a stored result."""
    o = result["outputs"]
    fr = o["fractions"]
    return {"model_version": result["model_version"],
            "fractions": {f: {"validation_status": v["validation_status"],
                              "data_sources": v["data_sources"]} for f, v in fr.items()},
            "pluvial": {"validation_status": o["susceptibility"]["pluvial"]["validation_status"],
                        "status": o["susceptibility"]["pluvial"]["status"],
                        "data_sources": o["susceptibility"]["pluvial"]["data_sources"]},
            "scalar_hazards": {h: o["susceptibility"][h] for h in SCALAR_HAZARDS},
            "observability_label": o.get("observability", {}).get(
                "observed_fraction", {}).get("validation_status", "experimental")}


def _cell(cell: dict, *, label, sources, mv, basis, **extra) -> dict:
    status = cell["status"]
    value = cell["value"] if status == "available" else None
    if status == "available" and value is None:
        status = "insufficient_observation"
    if value is not None:
        value = round(float(value), 6)
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
    if ctx["pluvial"].get("status") in ("timeout", "failed"):
        # Item 38: the AOI-level pluvial did not finish (timeout / failed);
        # no unit gets a value or tier from it, and every unit says why (since
        # flood round 4 a DEM timeout leaves no map at all to sample).
        hz["pluvial"] = C.output(None, status=ctx["pluvial"]["status"],
                                 validation_status=ctx["pluvial"]["validation_status"],
                                 coverage=C.coverage(0.0, "AOI-level pluvial did not finish"),
                                 data_sources=ctx["pluvial"]["data_sources"], model_version=mv,
                                 tier=None)
    elif PLUVIAL in unit:
        p = _cell(unit[PLUVIAL], label=ctx["pluvial"]["validation_status"],
                  sources=ctx["pluvial"]["data_sources"], mv=mv, basis=basis)
        p["tier"] = classify_pluvial(p["value"])
        hz["pluvial"] = p
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
