"""
Connectivity terrain features (no labels): the water level at which each cell first
connects to a seed set (mapped water, or the sea), by a minimax-path flood fill.

    spill_level(elev, seeds) -> for every cell, the lowest water level L such that the
    cell is reachable from a seed through 8-connected cells all <= L
    (L >= the cell's own elevation). Unreachable cells (no finite path) are NaN.

A low depression behind a ridge or levee gets the ridge's level, not its own elevation.
"""
from __future__ import annotations

import heapq

import numpy as np


def spill_level(elev: np.ndarray, seeds: np.ndarray) -> np.ndarray:
    H, W = elev.shape
    out = np.full((H, W), np.inf)
    e = np.where(np.isfinite(elev), elev, np.inf)
    h = []
    for r, c in zip(*np.nonzero(seeds & np.isfinite(elev))):
        out[r, c] = e[r, c]
        h.append((e[r, c], r, c))
    heapq.heapify(h)
    nb = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    while h:
        lv, r, c = heapq.heappop(h)
        if lv > out[r, c]:
            continue
        for dr, dc in nb:
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and np.isfinite(e[rr, cc]):
                nl = max(lv, e[rr, cc])
                if nl < out[rr, cc]:
                    out[rr, cc] = nl
                    heapq.heappush(h, (nl, rr, cc))
    out[~np.isfinite(out)] = np.nan
    return out
