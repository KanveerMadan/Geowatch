"""
M6–M8 v2 step 3: connected water spreading on a terrain grid (ARCHITECTURE_V2 "How a change in
forcing changes the map", items 2-3). Pure numpy/heapq; synthetic tests in test_routing.py.

- level_from_sources: L_i = max { W_s : a path from source cell s to i stays at or below W_s }, i.e.
  the highest source water surface that can spill into the cell (B(i,s) <= W_s, with B the minimax
  spill elevation). Barriers (levee crests) raise the terrain they sit on; a breach opens them.
- connected_depth: max(0, L_i - z_i). A constant single-reach level reproduces the HAND ranking;
  spatial skill can only come from changing levels along the network, closed paths and finite storage.
- volume_limited: for one source with a finite release volume V, the level W* <= W_s such that the
  connected stored volume equals V (never every connected hollow at once).
"""
from __future__ import annotations

import heapq

import numpy as np

N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def level_from_sources(z, sources, levels, barrier=None, breach=None):
    """z: terrain (NaN = no data, impassable). sources: list of (row, col) arrays per source group;
    levels: water surface per group (terrain datum). barrier: extra crest height (m) per cell or None;
    breach: boolean mask of barrier cells that are open. Returns the reachable level per cell (NaN if none)."""
    zz = np.where(np.isfinite(z), z, np.inf).astype(np.float64)
    if barrier is not None:
        b = np.nan_to_num(barrier, nan=0.0)
        if breach is not None:
            b = np.where(breach, 0.0, b)
        zz = zz + b
    H, W = zz.shape
    L = np.full((H, W), -np.inf)
    order = sorted(range(len(sources)), key=lambda k: -levels[k])
    for k in order:
        lev = levels[k]
        rr, cc = sources[k]
        stack = [(r, c) for r, c in zip(np.atleast_1d(rr), np.atleast_1d(cc)) if zz[r, c] <= lev and L[r, c] < lev]
        for r, c in stack:
            L[r, c] = lev
        while stack:
            r, c = stack.pop()
            for dr, dc in N8:
                a, b2 = r + dr, c + dc
                if 0 <= a < H and 0 <= b2 < W and L[a, b2] < lev and zz[a, b2] <= lev:
                    L[a, b2] = lev
                    stack.append((a, b2))
    return np.where(np.isfinite(L), L, np.nan)


def minimax_spill(z, sources):
    """B_i: the lowest possible maximum terrain elevation along any path from the sources to i."""
    zz = np.where(np.isfinite(z), z, np.inf)
    H, W = zz.shape
    B = np.full((H, W), np.inf)
    h = []
    for r, c in zip(*sources):
        B[r, c] = zz[r, c]
        heapq.heappush(h, (zz[r, c], r, c))
    while h:
        v, r, c = heapq.heappop(h)
        if v > B[r, c]:
            continue
        for dr, dc in N8:
            a, b = r + dr, c + dc
            if 0 <= a < H and 0 <= b < W:
                nv = max(v, zz[a, b])
                if nv < B[a, b]:
                    B[a, b] = nv
                    heapq.heappush(h, (nv, a, b))
    return np.where(np.isfinite(B), B, np.nan)


def connected_depth(z, sources, levels, **kw):
    L = level_from_sources(z, sources, levels, **kw)
    return np.where(np.isfinite(L), np.maximum(L - z, 0.0), 0.0)


def volume_limited(z, source, level_max, volume_m3, cell_area_m2, **kw):
    """(level, depth): the level <= level_max whose connected stored volume equals volume_m3."""
    rr, cc = source
    lo = float(np.nanmin(z[rr, cc]))
    if not np.isfinite(lo) or level_max <= lo or volume_m3 <= 0:
        return lo, np.zeros_like(z, dtype=float)

    def vol(lv):
        d = connected_depth(z, [source], [lv], **kw)
        return float(d.sum() * cell_area_m2), d
    v_hi, d_hi = vol(level_max)
    if v_hi <= volume_m3:
        return level_max, d_hi
    a, b = lo, level_max
    for _ in range(40):
        m = (a + b) / 2
        if vol(m)[0] < volume_m3:
            a = m
        else:
            b = m
    return a, vol(a)[1]


def physics_score(z, seed_groups, levels):
    """Per cell: max over source groups of (W_g - B_g,i), with B the minimax spill elevation from the
    group's cells. On freely connected ground B_g,i = z_i, so the score is the water depth; behind a
    ridge or levee it is the (negative) rise still needed to reach the cell. One continuous ranking,
    no ties at zero. Groups bin the channel cells by level (a few bins keep it tractable)."""
    best = np.full(z.shape, -np.inf)
    for seeds, w in zip(seed_groups, levels):
        if len(seeds[0]) == 0:
            continue
        B = minimax_spill(z, seeds)
        best = np.fmax(best, np.where(np.isfinite(B), w - B, -np.inf))
    return np.where(np.isfinite(best), best, np.nan)


def channel_groups(z, channel, stage, nbins=8):
    """Bin channel cells by water-surface elevation (z + stage) into nbins groups."""
    rr, cc = np.nonzero(channel & np.isfinite(z) & np.isfinite(stage))
    if len(rr) == 0:
        return [], []
    w = z[rr, cc] + stage[rr, cc]
    qs = np.unique(np.quantile(w, np.linspace(0, 1, nbins + 1)))
    groups, levels = [], []
    for a, b in zip(qs[:-1], qs[1:]):
        m = (w >= a) & ((w < b) | (b == qs[-1]))
        if m.any():
            groups.append((rr[m], cc[m]))
            levels.append(float(np.mean(w[m])))
    return groups, levels
