"""
Label polygons -> per-class 10 m fractions (LABELLING_GUIDE.md §2, §5, §9.5).

Fractions come from polygon AREA on the exact Sentinel-2 grid, using the
same rasteriser as the pipeline (surface_fractions.grid.polygon_coverage),
so a label fraction and a predicted fraction are computed identically. A
labeller never types a percentage.

Per 10 m cell:
  excluded_share   = unsure + shadow_full area share
  <class>          = class area / (1 - excluded_share)   for the 8 scored labels
  partial_shadow   = share of the cell under polygons flagged shadow_partial
  scored           = False if excluded_share == 1; otherwise decided by the
                     §9.5 max-excluded-share number, which is UNSET -> None

Every sub-cell of the tile must be covered exactly once (§3: every pixel in a
chosen tile is labelled). A gap or an overlap is a QC error, found on the
1 m sub-cell raster -- the method itself, not a tolerance.
"""

from __future__ import annotations

import numpy as np
from rasterio.features import rasterize
from rasterio.transform import Affine
from shapely.geometry import shape

from surface_fractions.grid import SUBPIXEL_M, Grid, polygon_coverage


class LabelQCError(ValueError):
    pass


def parse_features(features: list, cfg: dict) -> list:
    """GeoJSON features (already in the tile CRS) -> [(label, partial, geom)]."""
    lab = cfg["labels"]
    allowed = set(lab["scored"]) | set(lab["excluded"])
    flag = lab["partial_shadow_property"]
    out = []
    for i, f in enumerate(features):
        p = f.get("properties", {})
        label = p.get("label")
        if label == "shadow_partial":
            raise LabelQCError(f"feature {i}: shadow_partial is not a label; label the "
                               f"underlying surface and set {flag}: true (guide §1)")
        if label not in allowed:
            raise LabelQCError(f"feature {i}: unknown label {label!r}")
        partial = bool(p.get(flag, False))
        if partial and label in lab["excluded"]:
            raise LabelQCError(f"feature {i}: {label} cannot carry {flag}")
        out.append((label, partial, shape(f["geometry"])))
    return out


def subcell_label_map(polys: list, grid: Grid, cfg: dict, subcell_m: float = SUBPIXEL_M):
    """-> (int map at sub-cell resolution, label list, overlap count).
    Map value = index into label list + 1; 0 = unlabelled."""
    labels = cfg["labels"]["scored"] + cfg["labels"]["excluded"]
    k = int(round(grid.res / subcell_m))
    t = grid.transform
    fine = Affine(t[0] / k, 0.0, t[2], 0.0, t[4] / k, t[5])
    shape_ = (grid.height * k, grid.width * k)
    count = np.zeros(shape_, dtype=np.int32)
    idx = np.zeros(shape_, dtype=np.int32)
    for label, _, geom in polys:
        burn = rasterize([(geom, 1)], out_shape=shape_, transform=fine, fill=0, dtype="uint8")
        count += burn
        idx[burn > 0] = labels.index(label) + 1
    return idx, labels, count


def tile_fractions(features: list, grid: Grid, cfg: dict,
                   max_excluded_share: float | None = None) -> dict:
    """-> {"fractions": {label: HxW}, "excluded_share", "partial_shadow",
           "scored", "pct_unsure", "pct_shadow_full"}."""
    polys = parse_features(features, cfg)
    _, _, count = subcell_label_map(polys, grid, cfg)
    gaps, overlaps = int((count == 0).sum()), int((count > 1).sum())
    if gaps or overlaps:
        raise LabelQCError(f"tile not covered exactly once: {gaps} unlabelled and "
                           f"{overlaps} doubly-labelled 1 m sub-cells (guide §3)")

    area = {}
    for label in cfg["labels"]["scored"] + cfg["labels"]["excluded"]:
        area[label] = polygon_coverage([g for l, _, g in polys if l == label], grid)
    partial = polygon_coverage([g for _, pflag, g in polys if pflag], grid)

    excluded = sum(area[l] for l in cfg["labels"]["excluded"])
    denom = 1.0 - excluded
    with np.errstate(divide="ignore", invalid="ignore"):
        fr = {l: np.where(denom > 0, area[l] / denom, np.nan)
              for l in cfg["labels"]["scored"]}

    if max_excluded_share is None:
        scored = np.where(denom > 0, None, False).astype(object)
    else:
        scored = (excluded <= max_excluded_share) & (denom > 0)
    return {
        "fractions": fr,
        "excluded_share": excluded,
        "partial_shadow": partial,
        "scored": scored,
        "scored_rule": ("max_excluded_share UNSET (guide §9.5): scored is None "
                        "except fully excluded cells" if max_excluded_share is None
                        else f"excluded_share <= {max_excluded_share}"),
        "pct_unsure": float(area["unsure"].mean() * 100),
        "pct_shadow_full": float(area["shadow_full"].mean() * 100),
    }
