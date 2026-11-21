"""
P0b-3: terrain sensitivity with documented error structure (replaces c6's
single-range noise, whose amplitude used GEDTM30's std; that std is ensemble
MODEL SPREAD, not measured elevation error, and is no longer used as one).

Error magnitudes (documented):
  FABDEM MAE 1.12 m in built-up areas, 2.88 m in forest; COPDEM30 1.61 m
  urban (Hawker et al. 2022, ERL 17 024016, LiDAR/ICESat references).
  DeltaDTM (coastal, lidar-corrected GLO-30) MAE 0.45 m.
  sigma = MAE * sqrt(pi/2) assumes zero-mean Gaussian errors (an assumption:
  MAE also contains bias). -> 1.40 m (FABDEM urban), 0.56 m (DeltaDTM).
Spatial correlation (documented ranges, partition NOT documented for FABDEM):
  short range ~20-200 m and long range ~1-50 km (Hugonnet et al. 2022, IEEE
  JSTARS 15:6456, multi-range variograms); SRTM near-field ~2 km (Rougier).
  Model: Gaussian short range 100 m + Gaussian long range 2 km; variance
  split 50/50 and 80/20 (short/long) as a sensitivity, single-range 100 m
  kept for comparison with c6.
Systematic biases (bracketing, magnitude informed but not measured):
  constant offset +/-1.0 m against a fixed downstream water level (an
  offset only matters relative to a level boundary); an urban block +/-1.0 m
  (FABDEM's residual building artefacts / regional underestimation);
  a long-wavelength tilt +/-0.5 m across 3 km.

Terrain: the c5 analytic surface at 30 m, east edge a fixed-level boundary
set 0.3 m above the lowest boundary bed, so backwater from the level enters
the domain. huthresh = 0.0002 m (converged in p0b_huthresh A).
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sfincs_io as io  # noqa: E402
from p0_cases import HOLLOWS, dem_at, hollow_depths, hollow_ponded_m3  # noqa: E402

DX = 30.0
HUT = 0.0002
SIG_FAB_URBAN = 1.12 * np.sqrt(np.pi / 2)    # 1.40 m
SIG_DELTADTM = 0.45 * np.sqrt(np.pi / 2)     # 0.56 m
URBAN_BLOCK = (1700.0, 2000.0, 1300.0, 1700.0)   # x0, x1, y0, y1: between the mid and large hollows, on the flow path


def gauss_field(shape, range_m, rng):
    w = rng.standard_normal(shape)
    ky = np.fft.fftfreq(shape[0], d=DX)[:, None]
    kx = np.fft.fftfreq(shape[1], d=DX)[None, :]
    g = np.exp(-2 * (np.pi * range_m / 2) ** 2 * (kx ** 2 + ky ** 2))   # Gaussian, practical range ~range_m
    f = np.real(np.fft.ifft2(np.fft.fft2(w) * g))
    return f / f.std()


def error_field(shape, sigma, split_short, rng):
    if split_short >= 1.0:
        return sigma * gauss_field(shape, 100.0, rng)
    s_short, s_long = sigma * np.sqrt(split_short), sigma * np.sqrt(1 - split_short)
    return s_short * gauss_field(shape, 100.0, rng) + s_long * gauss_field(shape, 2000.0, rng)


def model(d, z, level):
    ny, nx = z.shape
    msk = np.ones(z.shape, int)
    msk[:, -1] = 2
    bnd = [(nx * DX - 15, 15.0), (nx * DX - 15, ny * DX - 15)]
    io.write_model(d, z, msk, DX, 3 * 3600, 3 * 3600,
                   rain=[(0, 60.0), (3600, 60.0), (3601, 0.0), (3 * 3600, 0.0)],
                   bnd=bnd, bzs=[(0, level, level), (3 * 3600, level, level)],
                   zsini=float(z.min()) - 1.0, extra={"huthresh": HUT})
    r = io.run(d)
    hmax = io.read_map(d)["hmax"][-1]
    return np.where(hmax > -1e3, hmax, 0.0), r


def summary(hmax, ref_mask):
    f = hmax > 0.10
    return {"hollow_max_depth_m": hollow_depths(hmax, DX), "hollow_ponded_m3": hollow_ponded_m3(hmax, DX),
            "flooded_km2_0.10": round(float(f.sum() * DX * DX / 1e6), 4),
            "jaccard_vs_ref": round(float((f & ref_mask).sum() / max((f | ref_mask).sum(), 1)), 4),
            "flooded_cells": f}


def main(root, outpath, realisations=10, seed=20261101):
    z0 = dem_at(DX)
    level = float(z0[:, -1].min()) + 0.3
    h0, r0 = model(os.path.join(root, "tr_ref"), z0, level)
    ref = h0 > 0.10
    res = {"settings": {"dx_m": DX, "huthresh_m": HUT, "boundary_level_m": round(level, 3),
                        "sigma_fabdem_urban_m": round(SIG_FAB_URBAN, 3), "sigma_deltadtm_m": round(SIG_DELTADTM, 3),
                        "realisations": realisations, "seed": seed,
                        "gedtm30_std_note": "GEDTM30 std (Hanoi median 1.24 m) is ensemble model spread, "
                                            "not measured error; not used here"},
           "reference": {k: v for k, v in summary(h0, ref).items() if k != "flooded_cells"},
           "random": {}, "systematic": {}}
    rng = np.random.default_rng(seed)
    yy, xx = (np.mgrid[0:z0.shape[0], 0:z0.shape[1]] + 0.5) * DX
    for name, sigma, split in (("fabdem_urban_short100m", SIG_FAB_URBAN, 1.0),
                               ("fabdem_urban_50short_50long2km", SIG_FAB_URBAN, 0.5),
                               ("fabdem_urban_80short_20long2km", SIG_FAB_URBAN, 0.8),
                               ("deltadtm_50short_50long2km", SIG_DELTADTM, 0.5)):
        rows, freq = [], np.zeros(z0.shape)
        for k in range(realisations):
            h, _ = model(os.path.join(root, f"tr_{name}_{k}"), z0 + error_field(z0.shape, sigma, split, rng), level)
            s = summary(h, ref)
            freq += s.pop("flooded_cells")
            rows.append(s)
        freq /= realisations
        res["random"][name] = {
            "sigma_m": round(sigma, 3), "short_range_variance_share": split,
            "hollow_wet_fraction": {h: float(np.mean([r["hollow_max_depth_m"][h] > 0.10 for r in rows])) for h in HOLLOWS},
            "hollow_ponded_m3": {h: {q: float(np.percentile([r["hollow_ponded_m3"][h] for r in rows], p))
                                     for q, p in (("p10", 10), ("median", 50), ("p90", 90))} for h in HOLLOWS},
            "flooded_km2_0.10": {q: float(np.percentile([r["flooded_km2_0.10"] for r in rows], p))
                                 for q, p in (("p10", 10), ("median", 50), ("p90", 90))},
            "jaccard_vs_ref": {q: float(np.percentile([r["jaccard_vs_ref"] for r in rows], p))
                               for q, p in (("p10", 10), ("median", 50), ("p90", 90))},
            "ref_flooded_cells_wet_in_majority": round(float((freq[ref] >= 0.5).mean()), 4),
            "nonref_cells_wet_in_majority_km2": round(float(((freq >= 0.5) & ~ref).sum() * DX * DX / 1e6), 4)}
    block = (xx >= URBAN_BLOCK[0]) & (xx < URBAN_BLOCK[1]) & (yy >= URBAN_BLOCK[2]) & (yy < URBAN_BLOCK[3])
    for name, dz in (("offset_+1.0m", 1.0), ("offset_-1.0m", -1.0),
                     ("urban_block_+1.0m", np.where(block, 1.0, 0.0)), ("urban_block_-1.0m", np.where(block, -1.0, 0.0)),
                     ("tilt_+0.5m_west_up", 0.5 * (1 - xx / 3000.0)), ("tilt_-0.5m_west_down", -0.5 * (1 - xx / 3000.0))):
        h, _ = model(os.path.join(root, f"tr_{name}"), z0 + dz, level)
        s = summary(h, ref)
        s.pop("flooded_cells")
        s["boundary_zone_flooded_km2_0.10"] = round(float(((h > 0.10) & (xx > 2400)).sum() * DX * DX / 1e6), 4)
        res["systematic"][name] = s
    res["reference"]["boundary_zone_flooded_km2_0.10"] = round(float((ref & (xx > 2400)).sum() * DX * DX / 1e6), 4)
    io.save_json(outpath, res)
    print("ref", res["reference"])
    for k, v in res["random"].items():
        print(k, {kk: v[kk] for kk in ("hollow_wet_fraction", "flooded_km2_0.10", "jaccard_vs_ref",
                                        "ref_flooded_cells_wet_in_majority", "nonref_cells_wet_in_majority_km2")})
        print("   ponded", v["hollow_ponded_m3"])
    for k, v in res["systematic"].items():
        print(k, v)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
