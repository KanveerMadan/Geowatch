"""
Item 23 — density metrics, from the vector layer alone. NO spectral inputs.

Every metric is a {value, status} block:
  * road length per area (all / arterial / narrow / broad, kept separate)
  * footprint density and built-area share
  * footprint size distribution (m^2)
  * spacing: nearest-neighbour distance between footprint centroids (m)
  * orthogonality: Boeing's orientation order phi (Boeing 2019, "Urban
    spatial order: street network orientation, configuration, and entropy",
    Applied Network Science 4:67). phi = 1 - ((H - H_g) / (H_max - H_g))^2,
    with H the Shannon entropy of length-weighted street bearings in 36 bins
    of 10 degrees, H_max = ln 36 and H_g = ln 4. 1 is a perfect grid; 0 is
    uniformly disordered.
  * impervious_total: status "not_computed". It needs item 21's regression,
    which is not built.

Low-coverage policy (item 20 sets the thresholds): orthogonality is a
network-topology metric and is SUPPRESSED when coverage.score_layer says so.
Footprint metrics stay meaningful at low coverage and are computed with the
coverage block's confidence flag attached.
"""
from __future__ import annotations

import math

import numpy as np

from vector import coverage

ORIENTATION_BINS = 36
_H_MAX = math.log(ORIENTATION_BINS)
_H_GRID = math.log(4)


def _block(value, status="available", **extra):
    return {"value": value, "status": status, **extra}


def orientation_order(G) -> float | None:
    """Boeing's phi from the layer graph's edges, length-weighted. Bearings
    are axial (a street has no direction), so each edge counts at theta and
    at theta + 180. Returns None for an empty graph."""
    weights = np.zeros(ORIENTATION_BINS)
    for a, b, d in G.edges(data=True):
        (x0, y0), (x1, y1) = G.nodes[a]["xy"], G.nodes[b]["xy"]
        L = d["length_m"]
        if L <= 0:
            continue
        theta = math.degrees(math.atan2(x1 - x0, y1 - y0)) % 360.0   # compass bearing
        for t in (theta, (theta + 180.0) % 360.0):
            # Bins centred on 0, 10, 20 ... so N-S and E-W fall mid-bin.
            weights[int(((t + 5.0) % 360.0) // 10.0)] += L
    total = weights.sum()
    if total <= 0:
        return None
    p = weights[weights > 0] / total
    H = float(-(p * np.log(p)).sum())
    return 1.0 - ((H - _H_GRID) / (_H_MAX - _H_GRID)) ** 2


def _quantiles(values) -> dict:
    v = np.asarray(values, dtype=float)
    q = np.percentile(v, [10, 25, 50, 75, 90])
    return {"n": int(v.size), "p10": float(q[0]), "p25": float(q[1]),
            "median": float(q[2]), "p75": float(q[3]), "p90": float(q[4]),
            "mean": float(v.mean())}


def density_metrics(layer, reference=None, region=None) -> dict:
    """All item 23 metrics for the AOI (or `region`), plus the item 20
    coverage block they were computed under."""
    from scipy.spatial import cKDTree

    region_geom = layer.aoi if region is None else region
    area_km2 = region_geom.area / 1e6
    cov = coverage.score_layer(layer, reference, region=region)

    L = layer.lengths_km(region)
    def _road(k):
        fs = layer.fetch_status(k)
        return _block(L[k] / area_km2,
                      "available" if fs["status"] == "complete" else "partial_fetch",
                      unit="km/km^2", fetch=fs)
    road = {k: _road(k) for k in ("all", "arterial", "narrow_pedestrian", "broad_pedestrian")}

    fps = [p for p in layer.footprints if p.representative_point().within(region_geom)]
    conf = cov["footprint_metrics_confidence"]
    if fps:
        areas = [p.area for p in fps]
        built_m2 = sum(p.intersection(region_geom).area for p in fps)
        fp_density = _block(len(fps) / area_km2, unit="footprints/km^2", confidence=conf)
        built_share = _block(built_m2 / region_geom.area, unit="share of area", confidence=conf)
        size = _block(_quantiles(areas), unit="m^2", confidence=conf)
        if len(fps) >= 2:
            pts = np.array([(c.x, c.y) for c in (p.centroid for p in fps)])
            dist, _ = cKDTree(pts).query(pts, k=2)
            spacing = _block(_quantiles(dist[:, 1]), unit="m, centroid nearest neighbour",
                             confidence=conf)
        else:
            spacing = _block(None, "insufficient_footprints")
    else:
        none = dict(status="no_footprints", confidence=conf)
        fp_density = _block(0.0, unit="footprints/km^2", **none)
        built_share = _block(0.0, unit="share of area", **none)
        size = _block(None, **none)
        spacing = _block(None, **none)

    if cov["topology_metrics_suppressed"]:
        ortho = _block(None, "suppressed_low_coverage",
                       reason=f"coverage_regime_flag={cov['coverage_regime_flag']}")
    else:
        G = layer.graph()
        if region is not None:
            from shapely.geometry import LineString
            G = G.edge_subgraph([(a, b) for a, b in G.edges
                                 if LineString([G.nodes[a]["xy"], G.nodes[b]["xy"]])
                                 .intersects(region_geom)])
        phi = orientation_order(G)
        fs = layer.fetch_status("network")
        ortho = (_block(phi, "available" if fs["status"] == "complete" else "partial_fetch",
                        method="boeing_2019_orientation_order", fetch=fs)
                 if phi is not None else _block(None, "no_network"))

    return layer.stamp({
        "road_length_per_area": road,
        "footprint_density": fp_density,
        "built_area_share": built_share,
        "footprint_size_m2": size,
        "footprint_spacing_m": spacing,
        "orthogonality": ortho,
        "impervious_total": _block(None, "not_computed",
                                   reason="requires item 21's spectral regression, not built"),
        "footprint_source": layer.footprint_source,
        "coverage": cov,
        "spectral_inputs": [],
    })


# ── Pre-registered separation test (fixed 2026-10-27, before either AOI's
# metrics were computed). Known-formal vs known-informal, same footprint
# source (Open Buildings v3) so the source cannot be what separates them. ──
SEPARATION_TEST = {
    "formal": "chandigarh_central",
    "informal": "dharavi",
    "predictions": [
        # (name, metric path, direction, threshold)
        ("larger formal footprints", ("footprint_size_m2", "median"), "formal_over_informal_ratio", 2.0),
        ("denser informal footprints", ("footprint_density",), "informal_over_formal_ratio", 2.0),
        ("wider formal spacing", ("footprint_spacing_m", "median"), "formal_over_informal_ratio", 1.5),
        ("more orthogonal formal network", ("orthogonality",), "formal_minus_informal", 0.10),
    ],
    "pass_rule": "at least 3 of 4 predictions hold AND none is reversed in direction",
    "min_holding": 3,
}


def _get(metrics, path):
    block = metrics[path[0]]
    if block["status"] != "available" or block["value"] is None:
        return None
    v = block["value"]
    return v[path[1]] if len(path) > 1 else v


def evaluate_separation(formal: dict, informal: dict, test=SEPARATION_TEST) -> dict:
    rows, holding, reversed_ = [], 0, 0
    for name, path, kind, thr in test["predictions"]:
        f, i = _get(formal, path), _get(informal, path)
        if f is None or i is None:
            rows.append({"prediction": name, "formal": f, "informal": i,
                         "outcome": "not_tested", "threshold": thr, "kind": kind})
            continue
        if kind == "formal_over_informal_ratio":
            stat, wrong_dir = (f / i if i else math.inf), f < i
        elif kind == "informal_over_formal_ratio":
            stat, wrong_dir = (i / f if f else math.inf), i < f
        else:
            stat, wrong_dir = f - i, f < i
        holds = stat >= thr
        holding += holds
        reversed_ += wrong_dir
        rows.append({"prediction": name, "formal": f, "informal": i, "statistic": stat,
                     "threshold": thr, "kind": kind,
                     "outcome": "holds" if holds else ("reversed" if wrong_dir else "short_of_threshold")})
    passed = holding >= test["min_holding"] and reversed_ == 0
    return {"rows": rows, "holding": holding, "reversed": reversed_,
            "pass_rule": test["pass_rule"], "result": "PASS" if passed else "FAIL"}
