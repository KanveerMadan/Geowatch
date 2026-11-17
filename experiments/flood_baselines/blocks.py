"""
Spatial correlation range and the spatially blocked bootstrap (pure).

Why blocked: neighbouring 30 m cells are not independent. A per-pixel
bootstrap treats ~15 000 correlated cells as independent draws and gives
intervals that are far too narrow. Resampling whole square blocks, each at
least as wide as the correlation range, keeps the dependence inside a block
(Kunsch 1989; Lahiri 2003; for spatial CV, Roberts et al. 2017, Ecography 40:913).

Block size is measured, not assumed: `correlation_range` estimates, per event,
the distance at which the correlogram of the reference flood indicator falls
to 0.05. That is the "practical range" convention of an exponential
correlogram (correlation exp(-3h/a) = 0.05 at h = a; Journel & Huijbregts
1978), the standard definition of the distance beyond which correlation is
negligible. The block side is then chosen from the measured ranges (REPORT.md).
"""
from __future__ import annotations

import numpy as np

from experiments.flood_validation.harness import auc

PRACTICAL_RANGE_CORR = 0.05      # exponential-model practical range (see module doc)


def correlogram(indicator: np.ndarray, valid: np.ndarray, max_lag: int) -> np.ndarray:
    """Pearson correlation of a 2-D field with itself shifted by 1..max_lag
    cells, along rows and columns pooled, over pairs where both cells are
    valid. Index k holds lag k (index 0 = 1.0)."""
    x = np.asarray(indicator, dtype=np.float64)
    v = np.asarray(valid, bool) & np.isfinite(x)
    out = np.full(max_lag + 1, np.nan)
    out[0] = 1.0
    for k in range(1, max_lag + 1):
        a, b = [], []
        if x.shape[1] > k:
            m = v[:, :-k] & v[:, k:]
            a.append(x[:, :-k][m]); b.append(x[:, k:][m])
        if x.shape[0] > k:
            m = v[:-k, :] & v[k:, :]
            a.append(x[:-k, :][m]); b.append(x[k:, :][m])
        a, b = np.concatenate(a) if a else np.array([]), np.concatenate(b) if b else np.array([])
        if a.size > 2 and a.std() > 0 and b.std() > 0:
            out[k] = float(np.corrcoef(a, b)[0, 1])
    return out


def correlation_range(indicator, valid, max_lag: int, corr: float = PRACTICAL_RANGE_CORR):
    """First lag (cells) at which the correlogram drops to `corr`, or None if
    it never does within max_lag (range longer than measurable in the box)."""
    r = correlogram(indicator, valid, max_lag)
    below = np.nonzero(np.isfinite(r[1:]) & (r[1:] <= corr))[0]
    return None if below.size == 0 else int(below[0] + 1), r


def tile_ids(shape, block: int) -> np.ndarray:
    """Integer tile id per cell for a block x block tiling anchored at (0, 0)."""
    H, W = shape
    rows = np.arange(H) // block
    cols = np.arange(W) // block
    ncols = (W + block - 1) // block
    return rows[:, None] * ncols + cols[None, :]


def _auc_cells(s, f):
    f = f.astype(bool)
    if f.all() or not f.any():
        return np.nan
    return auc(s, f.astype(int), (~f).astype(int))


def paired_block_bootstrap(scores: dict, flooded: np.ndarray, ok: np.ndarray, block: int,
                           reps: int, seed: int) -> dict:
    """Resample block x block tiles with replacement (as many tiles as hold
    an evaluation cell) and recompute every score's AUC on the SAME resample,
    so differences between scores are paired.

    scores: {name: 2-D array}; ok: the common evaluation cells (2-D bool).
    Returns {"point": {name: auc}, "reps": {name: array(reps)}, "tiles": n}.
    A replicate with no flooded or no dry cell gives NaN for every score."""
    flooded = np.asarray(flooded, bool)
    ok = np.asarray(ok, bool)
    tid = tile_ids(flooded.shape, block)[ok]
    f_all = flooded[ok]
    s_all = {k: np.asarray(v, np.float64)[ok] for k, v in scores.items()}
    uniq, inv = np.unique(tid, return_inverse=True)
    order = np.argsort(inv, kind="stable")
    bounds = np.concatenate([[0], np.cumsum(np.bincount(inv))])
    members = [order[bounds[i]:bounds[i + 1]] for i in range(len(uniq))]
    point = {k: _auc_cells(s, f_all) for k, s in s_all.items()}
    rng = np.random.default_rng(seed)
    out = {k: np.full(reps, np.nan) for k in s_all}
    n = len(members)
    for r in range(reps):
        pick = rng.integers(0, n, n)
        idx = np.concatenate([members[i] for i in pick])
        f = f_all[idx]
        if f.all() or not f.any():
            continue
        for k, s in s_all.items():
            out[k][r] = auc(s[idx], f.astype(int), (~f).astype(int))
    return {"point": point, "reps": out, "tiles": n}


def ci(samples, level: float = 0.95):
    """Percentile interval of the finite samples, or (None, None)."""
    s = np.asarray(samples, np.float64)
    s = s[np.isfinite(s)]
    if s.size == 0:
        return None, None
    a = (1 - level) / 2
    return float(np.quantile(s, a)), float(np.quantile(s, 1 - a))


def cluster_mean_bootstrap(per_event_reps: dict, cluster_of: dict, reps: int, seed: int):
    """Two-stage bootstrap of the mean over events: resample registry
    clusters with replacement (events in one cluster are dependent), then
    for every event in a drawn cluster take one random draw from its own
    blocked-bootstrap replicates. Returns an array of `reps` means.

    per_event_reps: {event: array of within-event replicates (NaN allowed)}."""
    rng = np.random.default_rng(seed)
    ev = [e for e, r in per_event_reps.items() if np.isfinite(r).any()]
    if not ev:
        return np.full(reps, np.nan)
    finite = {e: np.asarray(per_event_reps[e])[np.isfinite(per_event_reps[e])] for e in ev}
    by_cluster = {}
    for e in ev:
        by_cluster.setdefault(cluster_of[e], []).append(e)
    cl = list(by_cluster)
    out = np.empty(reps)
    for r in range(reps):
        drawn = [cl[i] for i in rng.integers(0, len(cl), len(cl))]
        vals = [finite[e][rng.integers(0, finite[e].size)] for c in drawn for e in by_cluster[c]]
        out[r] = float(np.mean(vals))
    return out
