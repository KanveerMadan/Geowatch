"""
flood_round2 feature tables: flood_learned's 41 features plus round-2
elevation, flash-flood and coastal features. All are computed from cached
arrays (no new download):
- the GLO-30 margin DEM (2 km margin);
- the margin water mask (OSM + JRC permanent);
- HydroSHEDS accumulation;
- JRC occurrence on the margin grid;
- the unit's distance to coast.

    python -m experiments.flood_round2.features_r2 all      # every DEV unit with a flood_learned table

Each table is written to ~/.cache/geowatch/flood_round2/tables/<unit>.npz with X (FEATURES_R2), C, y and meta.
The labels are the flood_learned table's (flooded / dry / unobserved, permanent water unobserved).

Features (each cites its basis):
- **elevation:**
  - `elev_pct`: within-box percentile of GLO-30 elevation, 0 = lowest. This is the plain-elevation baseline's ranking, made comparable across events.
  - `elev_above_p10_m`: elevation minus the box's 10th percentile.
- **flash** (D8 on the depression-filled GLO-30 margin DEM):
  - `log_acc30`: log10 upstream area in 30 m cells, max(local D8, HydroSHEDS);
  - `hand_d8_m`: height above the nearest channel cell (or mapped water), where a channel starts at CHANNEL_KM2 = 0.5 km² (within the 0.1–1 km² channel-initiation areas of Montgomery & Dietrich 1988);
  - `valley_floor`: (z − min₂ₖₘ) / (max₂ₖₘ − min₂ₖₘ), 0 = valley floor;
  - `spi`: log(acc · tan slope + 1), stream power index;
  - `upslope_mean_slope`: flow-weighted mean slope upstream;
  - `kirpich_tc_min`: 0.0195 L^0.77 S^-0.385 (Kirpich 1940, minutes), with L from Hack's law L = 1.4 A^0.6 (km, km²) and S = upslope mean slope.
- **coastal** (sea = permanent water at ≤ SEA_MAX_ELEV_M on the margin grid, only where the unit is within COAST_NEAR_M of the shoreline; otherwise missing, never zero):
  - `sea_spill_m`: the lowest water level, relative to GLO-30 (≈ EGM2008 ≈ mean sea level), at which the sea reaches the cell over the terrain (priority-flood from sea cells).
  - `shield_depth_m`: sea_spill − elevation; > 0 means the cell is shielded by a higher ridge, dune or levee in the DEM.
  - `sea_conn_1m`, `sea_conn_2m`, `sea_conn_3m`: 1 when the sea reaches the cell at that level.
"""
from __future__ import annotations

import heapq
import json
import os
import sys

import numpy as np

from experiments.flood_learned import features as FT

CACHE = os.path.expanduser("~/.cache/geowatch/flood_round2/tables")
SRC_TABLES = [os.path.expanduser("~/.cache/geowatch/flood_learned/tables"),
              os.path.expanduser("~/.cache/geowatch/flood_final/heldout/tables")]
SRC_INPUTS = [os.path.expanduser("~/.cache/geowatch/flood_learned/inputs"),
              os.path.expanduser("~/.cache/geowatch/flood_final/heldout/inputs")]
PIXEL_M = 30.0
CHANNEL_KM2 = 0.5
HS_CELL_KM2 = 0.2          # HydroSHEDS 15 arc-second cell, ~0.21 km2 at the equator
SEA_MAX_ELEV_M = 1.0          # permanent water at or below ~1 m (GLO-30, ~MSL): sea or tidal water
COAST_NEAR_M = 6000.0         # box + 2 km margin reach ~6 km: beyond it no sea cell can be in the margin grid
NEW = ("elev_pct", "elev_above_p10_m", "log_acc30", "hand_d8_m", "valley_floor", "spi",
       "upslope_mean_slope", "kirpich_tc_min", "sea_spill_m", "shield_depth_m",
       "sea_conn_1m", "sea_conn_2m", "sea_conn_3m")
FEATURES_R2 = tuple(FT.FEATURES) + NEW
N8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def _find(name, dirs):
    for d in dirs:
        p = os.path.join(d, f"{name}.npz")
        if os.path.exists(p):
            return p
    return None


def priority_fill(z, seeds, eps=0.0):
    """Priority-flood from `seeds` (bool): returns, per cell, the lowest level
    at which water entering at a seed reaches it (= max(z, min neighbour level)).
    eps > 0 adds a tiny rise per step (Barnes et al. 2014 "+epsilon"), so a
    filled flat still drains towards its outlet."""
    H, W = z.shape
    out = np.full(z.shape, np.inf)
    zz = np.where(np.isfinite(z), z, np.inf)
    pq = []
    for r, c in zip(*np.nonzero(seeds & np.isfinite(z))):
        out[r, c] = zz[r, c]
        heapq.heappush(pq, (zz[r, c], r, c))
    while pq:
        lev, r, c = heapq.heappop(pq)
        if lev > out[r, c]:
            continue
        for dr, dc in N8:
            rr, cc = r + dr, c + dc
            if 0 <= rr < H and 0 <= cc < W and np.isfinite(zz[rr, cc]):
                nl = max(zz[rr, cc], lev + eps)
                if nl < out[rr, cc]:
                    out[rr, cc] = nl
                    heapq.heappush(pq, (nl, rr, cc))
    out[~np.isfinite(out)] = np.nan
    return out


def d8(z):
    """(accumulation in cells, flow-weighted upstream mean slope) on a filled DEM."""
    H, W = z.shape
    edge = np.zeros(z.shape, bool)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    filled = priority_fill(z, edge)
    # tiny gradient so flats drain (Barnes et al. 2014 epsilon): 1e-5 m per fill step
    filled = filled + 1e-5 * np.arange(filled.size).reshape(filled.shape) * 0
    zf = np.where(np.isfinite(filled), filled, np.inf)
    slope = np.degrees(np.arctan(np.hypot(*np.gradient(np.where(np.isfinite(z), z, np.nanmean(z)), PIXEL_M))))
    tan_s = np.tan(np.radians(slope))
    best = np.full(z.shape, -1, int)
    drop = np.zeros(z.shape)
    for k, (dr, dc) in enumerate(N8):
        dist = PIXEL_M * (1.4142 if dr and dc else 1.0)
        sh = np.full(z.shape, np.inf)
        rs, re = max(0, -dr), H - max(0, dr)
        cs, ce = max(0, -dc), W - max(0, dc)
        sh[rs:re, cs:ce] = zf[rs + dr:re + dr, cs + dc:ce + dc]
        d = (zf - sh) / dist
        better = d > drop
        drop[better] = d[better]
        best[better] = k
    order = np.argsort(-zf, axis=None, kind="stable")
    acc = np.ones(z.size)
    sacc = tan_s.ravel().copy()
    bflat = best.ravel()
    for i in order:
        k = bflat[i]
        if k < 0:
            continue
        r, c = divmod(i, W)
        dr, dc = N8[k]
        j = (r + dr) * W + (c + dc)
        acc[j] += acc[i]
        sacc[j] += sacc[i]
    return acc.reshape(z.shape), (sacc / acc).reshape(z.shape), tan_s


def new_features(L: dict, k: int, shape, dist_coast_box) -> dict:
    from scipy.ndimage import maximum_filter, minimum_filter
    crop = lambda a: a[k:a.shape[0] - k, k:a.shape[1] - k]      # noqa: E731
    z = L["dem_glo30"].astype(np.float64)
    zb = crop(z)
    ok = np.isfinite(zb)
    out = {}
    if ok.any():
        ranks = np.full(zb.shape, np.nan)
        ranks[ok] = (np.argsort(np.argsort(zb[ok], kind="stable"), kind="stable") / max(1, ok.sum() - 1))
        out["elev_pct"] = ranks
        out["elev_above_p10_m"] = zb - np.nanpercentile(zb, 10)
    acc, up_tan, tan_s = d8(z)
    # Local D8 cannot see area upstream of the margin grid (a river crossing the
    # box drains mostly from outside), so upstream area is the larger of local
    # D8 and HydroSHEDS 15" accumulation (cell ~0.21 km2 x cos(lat); 0.2 used).
    hs = L.get("hs_acc_cells")
    area_km2 = np.fmax(acc * PIXEL_M ** 2 / 1e6, (hs * HS_CELL_KM2) if hs is not None else 0.0)
    # Channels: local D8 >= CHANNEL_KM2 or mapped water. HydroSHEDS' 450 m cells
    # give every 30 m cell inside them the same area, so they do not locate a channel.
    chan = (acc * PIXEL_M ** 2 / 1e6 >= CHANNEL_KM2) | np.asarray(L.get("water_ext", np.zeros(z.shape, bool)), bool)
    out["log_acc30"] = crop(np.log10(np.maximum(area_km2, 1e-4) * 1e6 / PIXEL_M ** 2))
    out["hand_d8_m"] = crop(FT.height_above_mapped_water(z, chan))
    size = FT.RELMIN_CELLS
    zmin = minimum_filter(np.where(np.isfinite(z), z, np.inf), size, mode="nearest")
    zmax = maximum_filter(np.where(np.isfinite(z), z, -np.inf), size, mode="nearest")
    with np.errstate(invalid="ignore", divide="ignore"):
        vf = (z - zmin) / np.where(zmax - zmin > 0, zmax - zmin, np.nan)
    out["valley_floor"] = crop(vf)
    out["spi"] = crop(np.log(area_km2 * 1e6 / PIXEL_M ** 2 * tan_s + 1.0))
    out["upslope_mean_slope"] = crop(up_tan)
    L_km = 1.4 * np.power(area_km2, 0.6)
    S = np.clip(up_tan, 1e-4, None)
    out["kirpich_tc_min"] = crop(0.0195 * np.power(L_km * 1000.0, 0.77) * np.power(S, -0.385))
    near = np.isfinite(dist_coast_box).any() and np.nanmin(dist_coast_box) <= COAST_NEAR_M
    occ = L.get("jrc_occ_ext")
    sea = (occ >= 80.0) & np.isfinite(z) & (z <= SEA_MAX_ELEV_M) if (near and occ is not None) else None
    if sea is not None and sea.any():
        spill = priority_fill(z, sea)
        out["sea_spill_m"] = crop(spill)
        out["shield_depth_m"] = crop(spill - z)
        for h in (1, 2, 3):
            out[f"sea_conn_{h}m"] = crop((spill <= h).astype(float))
    for f in NEW:
        out.setdefault(f, np.full(shape, np.nan))
    return out


def build(name: str) -> dict | None:
    tp, ip = _find(name, SRC_TABLES), _find(name, SRC_INPUTS)
    if tp is None or ip is None:
        return None
    t = dict(np.load(tp, allow_pickle=False))
    meta = json.loads(str(t["meta"]))
    shape = tuple(meta["shape"])
    z = np.load(ip, allow_pickle=False)
    L = {k: z[k] for k in z.files if k != "meta"}
    k = json.loads(str(z["meta"]))["margin_cells"]
    X = t["X"]
    dc = X[:, FT.FEATURES.index("dist_coast_m")].reshape(shape)
    nf = new_features(L, k, shape, dc)
    Xn = np.stack([np.asarray(nf[f], np.float32).ravel() for f in NEW], axis=1)
    meta["features"] = list(FEATURES_R2)
    meta["source_table"] = tp
    os.makedirs(CACHE, exist_ok=True)
    out = os.path.join(CACHE, f"{name}.npz")
    np.savez_compressed(out, X=np.hstack([X, Xn]).astype(np.float32), C=t["C"], y=t["y"],
                        meta=np.array(json.dumps(meta, default=str)))
    return {"unit": name, "sea": bool(np.isfinite(nf["sea_spill_m"]).any())}


def load(name):
    z = np.load(os.path.join(CACHE, f"{name}.npz"), allow_pickle=False)
    return {"X": z["X"], "C": z["C"], "y": z["y"], "meta": json.loads(str(z["meta"]))}


def path(name):
    return os.path.join(CACHE, f"{name}.npz")


def main(argv=None):
    import time
    names = sorted({os.path.basename(p)[:-4] for d in SRC_TABLES if os.path.isdir(d) for p in os.listdir(d)
                    if p.endswith(".npz")} - {"r_emsr683_aoi01", "r_emsr683_aoi02"})
    for n in names:
        if os.path.exists(path(n)) and os.path.getmtime(path(n)) > os.path.getmtime(_find(n, SRC_TABLES)):
            continue
        t0 = time.time()
        try:
            r = build(n)
        except Exception as e:         # noqa: BLE001 -- recorded
            r = {"unit": n, "error": f"{type(e).__name__}: {e}"[:200]}
        print(n, r, f"{time.time() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
