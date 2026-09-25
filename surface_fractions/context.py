"""
Item 21 Phase A, part 6 — flags and context layers (Decision 11).

Not fractions, not observability. They touch neither the denominator nor any
fraction (Decision 14, 2026-09-24 extension). Per-pixel; one AOI can carry
many at once.

  OSM sub-type flags  vegetation: sports field / golf / park / farmland
                      bare: sand / rock / landfill / quarry / dirt track /
                            unpaved parking (salt flat, dry lakebed: no OSM
                            producer)
                      other: pier / quay (context only; the docks -> built
                             rule is struck, 2026-09-25)
  synthetic turf      secondary check on sports fields: criterion UNSET
  bare plausibility   "geographic plausibility": criterion UNSET
  volcano             Smithsonian GVP match; Copernicus DEM shape as
                      secondary confirmation (descriptive only, no pass/fail)
  terrain             flat / hilly / mountainous: cut-offs UNSET; the slope
                      and elevation distributions are reported regardless
"""

from __future__ import annotations

import json
import os

import numpy as np

from surface_fractions.config import REPO_ROOT


def _unset(spec: dict) -> list:
    return sorted(k for k, t in spec.items()
                  if isinstance(t, dict) and (t.get("status") == "UNSET" or t.get("value") is None))


# ── OSM sub-type flags ──────────────────────────────────────────────────────

def osm_flag(layer: dict) -> np.ndarray | None:
    """0/1 per pixel: any area coverage or any line touch. None when the
    layer has no producer or was unavailable (never zeros)."""
    if layer["status"] != "available":
        return None
    parts = []
    if layer.get("area_fraction") is not None:
        parts.append(layer["area_fraction"] > 0)
    if layer.get("line_touch") is not None:
        parts.append(layer["line_touch"] > 0)
    return np.logical_or.reduce(parts) if parts else None


def osm_flags(osm: dict, cfg: dict, known: np.ndarray) -> dict:
    groups = cfg["context"]["osm_flags"]
    arrays, summary = {}, {}
    n_known = int(known.sum())
    for group, names in groups.items():
        summary[group] = {}
        for name in names:
            layer = osm[name]
            flag = osm_flag(layer)
            if flag is None:
                summary[group][name] = {"status": layer["status"],
                                        **({"error": layer["error"]} if layer.get("error") else {})}
                continue
            arrays[f"osm_{name}"] = flag
            area = layer.get("area_fraction")
            summary[group][name] = {
                "status": "computed",
                "pixel_share_of_known": float(flag[known].sum()) / n_known if n_known else None,
                "covered_area_share": (float(np.mean(area[known])) if area is not None and n_known
                                       else None),
                "n_features": layer["n_features"],
            }
    return {"arrays": arrays, "summary": summary}


# ── volcano ─────────────────────────────────────────────────────────────────

def load_gvp(path: str) -> list:
    """GVP points from a local export: GeoJSON FeatureCollection, or CSV with
    Volcano_Number, Volcano_Name, Latitude, Longitude."""
    if path.endswith(".csv"):
        import csv
        with open(path, newline="") as fh:
            return [{"number": r["Volcano_Number"], "name": r["Volcano_Name"],
                     "lon": float(r["Longitude"]), "lat": float(r["Latitude"])}
                    for r in csv.DictReader(fh)]
    with open(path) as fh:
        fc = json.load(fh)
    out = []
    for f in fc["features"]:
        p = f.get("properties", {})
        lon, lat = f["geometry"]["coordinates"][:2]
        out.append({"number": p.get("Volcano_Number"), "name": p.get("Volcano_Name"),
                    "lon": float(lon), "lat": float(lat)})
    return out


def volcano(cfg: dict, bbox: dict, dem: np.ndarray, slope: np.ndarray) -> dict:
    spec = cfg["context"]["volcano"]
    path = spec["gvp_path"]
    path = path if os.path.isabs(path) else os.path.join(REPO_ROOT, path)
    per_pixel = {"status": "not_computed",
                 "reason": "match_radius_m is UNSET: a GVP point has no extent "
                           "without one"}
    if not os.path.exists(path):
        return {"status": "unavailable",
                "reason": f"GVP source file not present at {spec['gvp_path']} "
                          "(GVP refuses programmatic access; supply the official "
                          "export by hand)",
                "per_pixel": per_pixel}
    pts = load_gvp(path)
    inside = [p for p in pts
              if bbox["west"] <= p["lon"] <= bbox["east"]
              and bbox["south"] <= p["lat"] <= bbox["north"]]
    finite = np.isfinite(dem)
    return {
        "status": "computed",
        "source": {"dataset": "Smithsonian GVP Volcanoes of the World (Holocene)",
                   "path": spec["gvp_path"], "records": len(pts)},
        "match_rule": "GVP point inside the AOI bounding box; no confidence flag "
                      "on a database match (Decision 11)",
        "matches": inside,
        # Secondary confirmation is DESCRIPTIVE: no shape test is defined.
        "dem_shape_description": ({
            "elevation_m": {"min": float(np.nanmin(dem)), "max": float(np.nanmax(dem)),
                            "relief": float(np.nanmax(dem) - np.nanmin(dem))},
            "slope_deg": {"p50": float(np.nanpercentile(slope, 50)),
                          "p90": float(np.nanpercentile(slope, 90)),
                          "max": float(np.nanmax(slope))},
        } if inside and finite.any() else None),
        "per_pixel": per_pixel,
    }


# ── terrain ─────────────────────────────────────────────────────────────────

def terrain(cfg: dict, dem: np.ndarray, slope: np.ndarray) -> dict:
    spec = cfg["context"]["terrain"]
    missing = _unset(spec)
    q = [5, 25, 50, 75, 95]
    distribution = {
        "elevation_m": dict(zip([f"p{x}" for x in q],
                                np.nanpercentile(dem, q).round(2).tolist())),
        "slope_deg": dict(zip([f"p{x}" for x in q],
                              np.nanpercentile(slope, q).round(2).tolist())),
        "source": "Copernicus GLO-30 (slope at 30 m in the grid CRS)",
    }
    if missing:
        return {"status": "not_computed", "reason": f"UNSET cut-offs: {missing}",
                "class_distribution": None, "descriptive_distribution": distribution}
    raise NotImplementedError("terrain cut-offs are set but classification is not "
                              "implemented; implement the cited scheme first")


def check_config(cfg: dict) -> None:
    """Refuse a context criterion that is set but has no implementation."""
    c = cfg["context"]
    for name, spec in (("synthetic_turf_check", c["synthetic_turf_check"]),
                       ("bare_geographic_plausibility", c["bare_geographic_plausibility"]),
                       ("volcano.match_radius_m", {"r": c["volcano"]["match_radius_m"]})):
        if not _unset(spec):
            raise NotImplementedError(f"context {name} is set but not implemented")


def context_layers(osm: dict, cfg: dict, known: np.ndarray, bbox: dict,
                   dem: np.ndarray, slope: np.ndarray) -> dict:
    check_config(cfg)
    flags = osm_flags(osm, cfg, known)
    turf_missing = _unset(cfg["context"]["synthetic_turf_check"])
    plaus_missing = _unset(cfg["context"]["bare_geographic_plausibility"])
    return {
        "arrays": flags["arrays"],
        "summary": {
            "osm_flags": flags["summary"],
            "synthetic_turf_check": {"status": "not_computed",
                                     "reason": f"UNSET: {turf_missing}"},
            "bare_geographic_plausibility": {"status": "not_computed",
                                             "reason": f"UNSET: {plaus_missing}"},
            "volcano": volcano(cfg, bbox, dem, slope),
            "terrain": terrain(cfg, dem, slope),
            "note": "context layers touch neither the denominator nor any fraction",
        },
    }
