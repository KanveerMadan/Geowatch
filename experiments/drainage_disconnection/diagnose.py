"""
Item 26 Phase 1a, task 4: why drainage_disconnection saturates on flat ground
(0.914 on Dharavi in the item 26 smoke run). DEM only -- no flood reference.

Question: is it a bug, or what the method does on a flat, noisy 30 m DEM?
Measures, on Dharavi's FABDEM on a 30 m UTM grid:
  * the disconnected share as built (susceptibility/terrain.py);
  * how many terminal pits are exact flats (an equal-height neighbour) and
    how many are strict single-cell pits, and how deep the pits are;
  * the share left if every flat that touches an outlet (the grid edge, or a
    connected cell) drained through it -- i.e. how much of the saturation a
    flat-resolution fix could remove.

    python -m experiments.drainage_disconnection.diagnose
"""
import json
import os
from types import SimpleNamespace

import numpy as np

from susceptibility.hydro_rasters import utm_grid
from susceptibility.terrain import d8_receivers, drains_to_edge, fetch_dem, flow_accumulation

BBOX = (72.836, 19.037, 72.862, 19.060)       # vector/aois.py dharavi
HERE = os.path.dirname(os.path.abspath(__file__))
OFFS = [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1) if a or b]


def flat_components(dem):
    """Label of each cell's 8-connected equal-elevation component."""
    H, W = dem.shape
    parent = np.arange(dem.size)

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for i in range(H):
        for j in range(W):
            for di, dj in ((0, 1), (1, -1), (1, 0), (1, 1)):
                a, b = i + di, j + dj
                if 0 <= a < H and 0 <= b < W and dem[i, j] == dem[a, b]:
                    ra, rb = find(i * W + j), find(a * W + b)
                    if ra != rb:
                        parent[ra] = rb
    return np.array([find(k) for k in range(dem.size)])


def resolve_flats(dem, recv, out):
    """`out` after letting every flat that holds a connected cell drain."""
    roots = flat_components(dem)
    out, order = out.copy(), np.argsort(dem.ravel())
    while True:
        before = out.sum()
        good = np.zeros(dem.size, bool)
        good[np.unique(roots[out])] = True
        out |= good[roots]
        for k in order:
            if not out[k] and recv[k] >= 0:
                out[k] = out[recv[k]]
        if out.sum() == before:
            return out, roots


def main():
    from ingestion.gee_client import initialize_gee
    initialize_gee()
    transform, shape, crs = utm_grid(BBOX)
    from pyproj import CRS
    dem = fetch_dem(SimpleNamespace(bbox=BBOX, crs=CRS.from_string(crs)), transform, shape)
    H, W = dem.shape
    recv = d8_receivers(dem, 30.0)
    out = drains_to_edge(dem, recv).ravel()
    pits = recv == -1
    pad = np.pad(dem, 1, constant_values=np.nan)
    nb = np.stack([pad[1 + a:1 + a + H, 1 + b:1 + b + W] for a, b in OFFS])
    flat = (nb == dem).any(axis=0).ravel()
    with np.errstate(invalid="ignore"):
        depth = (np.nanmin(nb, axis=0) - dem).ravel()
    resolved, roots = resolve_flats(dem, recv, out)
    zero = dem.ravel() == 0
    edge = np.zeros((H, W), bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    acc = flow_accumulation(dem, recv).ravel()
    result = {
        "bbox": BBOX, "grid": {"crs": crs, "shape": list(shape)},
        "dem_m": {"min": float(np.nanmin(dem)), "max": float(np.nanmax(dem)),
                  "nodata_cells": int(np.isnan(dem).sum()), "cells_exactly_0": int(zero.sum()),
                  "zero_plateau_touches_edge": bool((zero.reshape(H, W) & edge).any())},
        "disconnected_share_as_built": round(float(1 - out.mean()), 3),
        "terminal_pits": int(pits.sum()),
        "pits_on_exact_flats": int((pits & flat).sum()),
        "strict_single_cell_pits": int((pits & ~flat).sum()),
        "strict_pit_depth_m_quantiles_10_50_90": [round(float(q), 4) for q in
                                                  np.quantile(depth[pits & ~flat], [.1, .5, .9])],
        "pit_catchment_cells_median": float(np.median(acc[pits] + 1)),
        "disconnected_share_if_flats_drain": round(float(1 - resolved.mean()), 3),
    }
    print(json.dumps(result, indent=1))
    with open(os.path.join(HERE, "result_2026-10-28.json"), "w") as f:
        json.dump(result, f, indent=1)


if __name__ == "__main__":
    main()
