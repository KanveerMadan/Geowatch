"""
Item 21 Phase A, part 4 — `built` from footprints, and the two-source
disagreement signal.

`built` is Open Buildings v3 (confidence >= 0.7) covered fraction per 10 m
cell, and nothing else (Phase A ruling, 2026-09-25). It is taken from vector
footprints, not estimated from spectra (Decision 11, item 21 re-scope).

Microsoft Global ML Building Footprints is used ONLY for the disagreement
signal. Three measures are emitted and none is named the confidence score:
that name waits until the hand-digitised check at Makoko / Kibera / Rocinha
ties a disagreement level to a measured error (item 21, "`built`
validation").

  coverage totals   mean covered fraction per source over the AOI
  fraction MAE      mean |ob - ms| per pixel
  10 m IoU          sum(min(ob, ms)) / sum(max(ob, ms)) over pixels -- the
                    area-weighted (Ruzicka) IoU of the two coverage rasters.
                    Threshold-free: no binarisation cut is needed.
"""

from __future__ import annotations

import numpy as np

BUILT_METHOD = "polygon coverage on the native Sentinel-2 10 m grid"


def disagreement(ob: np.ndarray, ms: np.ndarray | None, ms_status: str) -> dict:
    """AOI-level disagreement between the two footprint sources."""
    if ms is None or ms_status != "available" or not np.isfinite(ms).any():
        return {"status": "unavailable",
                "reason": f"second footprint source status: {ms_status}"}
    both = np.isfinite(ob) & np.isfinite(ms)
    a, b = ob[both].astype(np.float64), ms[both].astype(np.float64)
    denom = float(np.maximum(a, b).sum())
    return {
        "status": "computed",
        "is_confidence_score": False,
        "note": "diagnostic only; calibration against hand-digitised "
                "buildings (item 21) decides which measure becomes built "
                "confidence",
        "sources": {"primary": "open_buildings_v3",
                    "secondary": "microsoft_global_ml_building_footprints"},
        "pixels_compared": int(both.sum()),
        "coverage_total_primary": float(a.mean()) if a.size else None,
        "coverage_total_secondary": float(b.mean()) if b.size else None,
        "fraction_mae": float(np.abs(a - b).mean()) if a.size else None,
        "iou_10m": float(np.minimum(a, b).sum()) / denom if denom > 0 else None,
    }


def compute_built(bands: dict, status: dict, ob_provenance: dict) -> dict:
    """-> {"built": array, "built_secondary_abs_diff": array | None,
           "provenance": ..., "disagreement": ...}"""
    ob = bands["ob_cov"].astype(np.float32)
    ms = bands.get("ms_cov")
    ms_status = status.get("microsoft_buildings", "unavailable")
    diff = (np.abs(ob - ms).astype(np.float32)
            if ms is not None and ms_status == "available" else None)
    return {
        "built": ob,
        "built_secondary_abs_diff": diff,
        # Asset and confidence cut come from what part 1 actually used, not
        # from a second copy here that could drift from the config.
        "provenance": {"source": "footprints", "measured_spectrally": False,
                       "method": BUILT_METHOD, **ob_provenance},
        "disagreement": disagreement(ob, ms, ms_status),
    }
