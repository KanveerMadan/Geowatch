"""
Bluespots with fill-and-spill (flood round 4, M2 pluvial). Pure numpy; the
method is fixed in experiments/flood_validation/PREREGISTRATION_ROUND4.md.

    1. Priority-flood (Barnes et al. 2014) from the grid edge and from cells
       next to no-data: every cell gets its filled level F and a receiver,
       the cell it was flooded from. Following receivers, every cell drains
       to an outlet, through depressions and across flats (ties pop in
       arrival order, so a flat drains toward where it was entered).
    2. Bluespots: 8-connected components of F - z > 0 whose deepest cell is
       at least `min_depth_m`. Storage V = sum(F - z) * cell area.
    3. A bluespot's local catchment is every cell whose route reaches it
       before any other bluespot; its downstream bluespot is the first one on
       the route out of its pour point (or none: the water leaves the grid).
    4. Fill and spill, upstream first: inflow = local runoff + the spill of
       every bluespot upstream; stored = min(inflow, V); the rest spills on.
       Each bluespot's water level holds exactly `stored`, filled from its
       lowest cell up; ponding depth = level - z.
    5. runoff_path: runoff-weighted upstream cells along the routing.

The grid edge stands in for an outlet: water leaving it is gone. Nested
depressions are merged into the one hollow that fills to the spill level.
"""
from __future__ import annotations

import heapq
import itertools

import numpy as np

_OFFSETS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def priority_flood(z: np.ndarray):
    """(F, receiver, order). F: filled level (NaN off the domain); receiver:
    flat index of the cell each cell was flooded from, -1 at an outlet;
    order: flat indices in the order they were flooded (outlets first, every
    receiver before its donors)."""
    z = np.asarray(z, dtype=np.float64)
    H, W = z.shape
    zf = z.ravel()
    ok = np.isfinite(z)
    pad = np.pad(ok, 1, constant_values=False)
    border = np.zeros_like(ok)
    for dr, dc in _OFFSETS:
        border |= ~pad[1 + dr:1 + dr + H, 1 + dc:1 + dc + W]
    F = np.full(zf.size, np.nan)
    recv = np.full(zf.size, -1, dtype=np.int64)
    seen = ~ok.ravel()
    tie = itertools.count()
    heap = []
    for i in np.flatnonzero((ok & border).ravel()):
        seen[i] = True
        F[i] = zf[i]
        heap.append((zf[i], next(tie), int(i)))
    heapq.heapify(heap)
    order = []
    while heap:
        f, _, c = heapq.heappop(heap)
        order.append(c)
        r, q = divmod(c, W)
        for dr, dc in _OFFSETS:
            rr, qq = r + dr, q + dc
            if 0 <= rr < H and 0 <= qq < W:
                n = rr * W + qq
                if not seen[n]:
                    seen[n] = True
                    F[n] = max(zf[n], f)
                    recv[n] = c
                    heapq.heappush(heap, (F[n], next(tie), n))
    return F.reshape(H, W), recv, np.asarray(order, dtype=np.int64)


def bluespots(z: np.ndarray, F: np.ndarray, min_depth_m: float) -> np.ndarray:
    """Bluespot id per cell (0..n-1), -1 elsewhere."""
    from scipy.ndimage import label, maximum
    with np.errstate(invalid="ignore"):
        d = np.where(np.isfinite(z), F - z, 0.0)
    lab, n = label(d > 1e-9, structure=np.ones((3, 3), dtype=bool))
    if n == 0:
        return np.full(z.shape, -1, dtype=np.int64)
    deep = np.asarray(maximum(d, lab, index=np.arange(1, n + 1))) >= min_depth_m
    keep = np.zeros(n + 1, dtype=np.int64) - 1
    keep[1:][deep] = np.arange(int(deep.sum()))
    return keep[lab]


def route_labels(bs_flat: np.ndarray, recv: np.ndarray, order: np.ndarray) -> np.ndarray:
    """The first bluespot on each cell's route (itself included), -1 if the
    route leaves the grid first."""
    down = np.full(bs_flat.size, -1, dtype=np.int64)
    for c in order:
        b = bs_flat[c]
        down[c] = b if b >= 0 else (down[recv[c]] if recv[c] >= 0 else -1)
    return down


def downstream_bluespot(bs_flat, recv, order, down, n: int) -> np.ndarray:
    """For each bluespot, the bluespot its spill reaches next (-1: none). Its
    first-flooded cell was entered from its pour point."""
    nxt = np.full(n, -1, dtype=np.int64)
    done = np.zeros(n, dtype=bool)
    for c in order:
        b = bs_flat[c]
        if b >= 0 and not done[b]:
            done[b] = True
            nxt[b] = down[recv[c]] if recv[c] >= 0 else -1
    return nxt


def upstream_first(nxt: np.ndarray) -> list:
    """Bluespot ids ordered so every bluespot comes after all that spill into it."""
    n = nxt.size
    indeg = np.zeros(n, dtype=np.int64)
    for b in nxt:
        if b >= 0:
            indeg[b] += 1
    queue = [b for b in range(n) if indeg[b] == 0]
    out = []
    while queue:
        b = queue.pop()
        out.append(b)
        t = nxt[b]
        if t >= 0:
            indeg[t] -= 1
            if indeg[t] == 0:
                queue.append(t)
    return out


def water_level(z_cells: np.ndarray, spill_level: float, stored_m3: float,
                cell_m2: float) -> float:
    """The level that holds `stored_m3` over these cells, filling from the
    lowest up; the spill level when full."""
    if stored_m3 <= 0:
        return -np.inf
    zs = np.sort(z_cells)
    k = np.arange(1, zs.size + 1)
    # volume when the level reaches zs[j]: cells 0..j-1 under water
    vol_at = (k[:-1] * zs[1:] - np.cumsum(zs)[:-1]) * cell_m2
    full = (zs.size * spill_level - zs.sum()) * cell_m2
    if stored_m3 >= full:
        return float(spill_level)
    j = int(np.searchsorted(vol_at, stored_m3, side="right")) + 1   # cells under water
    return float((stored_m3 / cell_m2 + zs[:j].sum()) / j)


def fill_and_spill(z: np.ndarray, runoff_c: np.ndarray, design_mm: float, pixel_m: float,
                   min_depth_m: float) -> dict:
    """Ponding depth, fill ratio and runoff-path accumulation on z's grid.

    runoff_c: runoff coefficient per cell (0-1); design_mm: storm depth."""
    z = np.asarray(z, dtype=np.float64)
    C = np.where(np.isfinite(z), np.nan_to_num(np.asarray(runoff_c, dtype=np.float64)), 0.0)
    cell_m2 = pixel_m * pixel_m
    F, recv, order = priority_flood(z)
    bs = bluespots(z, F, min_depth_m)
    bsf = bs.ravel()
    n = int(bsf.max()) + 1 if bsf.size and bsf.max() >= 0 else 0
    down = route_labels(bsf, recv, order)
    zf, Ff = z.ravel(), F.ravel()

    depth = np.zeros(z.size)
    fill = np.zeros(z.size)
    storage = np.zeros(n)
    inflow = np.zeros(n)
    stored = np.zeros(n)
    spill = np.zeros(n)
    if n:
        inb = bsf >= 0
        storage = np.bincount(bsf[inb], weights=(Ff - zf)[inb] * cell_m2, minlength=n)
        has = down >= 0
        local = np.bincount(down[has], weights=C.ravel()[has] * design_mm / 1000.0 * cell_m2,
                            minlength=n)
        nxt = downstream_bluespot(bsf, recv, order, down, n)
        inflow = local.copy()
        for b in upstream_first(nxt):
            stored[b] = min(inflow[b], storage[b])
            spill[b] = inflow[b] - stored[b]
            if nxt[b] >= 0:
                inflow[nxt[b]] += spill[b]
        cells = [[] for _ in range(n)]
        for i in np.flatnonzero(inb):
            cells[bsf[i]].append(i)
        for b in range(n):
            idx = np.asarray(cells[b])
            lvl = water_level(zf[idx], Ff[idx[0]], stored[b], cell_m2)
            depth[idx] = np.maximum(0.0, lvl - zf[idx])
            fill[idx] = stored[b] / storage[b] if storage[b] > 0 else 0.0

    acc = C.ravel().copy()
    for c in order[::-1]:
        if recv[c] >= 0:
            acc[recv[c]] += acc[c]
    upstream = acc - C.ravel()
    nan = ~np.isfinite(zf)
    for a in (depth, fill, upstream):
        a[nan] = np.nan
    H, W = z.shape
    return {"ponding_depth_m": depth.reshape(H, W), "fill_ratio": fill.reshape(H, W),
            "upstream_runoff_cells": upstream.reshape(H, W), "bluespot_id": bs,
            "n_bluespots": n, "storage_m3": storage, "inflow_m3": inflow,
            "stored_m3": stored, "spill_m3": spill, "domain_cells": int(np.isfinite(z).sum())}
