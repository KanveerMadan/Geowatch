"""
Item 37 (C22): no-data has its own render state, never a value on the
susceptibility scale.

The legacy preview (susceptibility/pluvial.save_pluvial_susceptibility_output)
renders NaN black, the same as score 0 -- and in the 7-class map no-data
scored like standing_water. Here a map is rendered as RGBA:

    observed cell     its tier's colour, alpha 255
    no-data cell      alpha 0 (transparent), RGB 0 -- not a colour on the scale

The no-data mask is the map's own NaN cells, which come from the
observation mask set at ingestion (fewer than MIN_VALID_OBS clear Sentinel-2
observations -> NaN vegetation -> NaN infiltration -> NaN pluvial). The legend
names the no-data state separately from the five tiers.
"""
from __future__ import annotations

import io

import numpy as np

# One colour per tier, very_low -> very_high. Fixed 2026-10-28.
TIER_COLOURS = {
    "very_low": (26, 152, 80), "low": (145, 207, 96), "moderate": (254, 224, 139),
    "high": (252, 141, 89), "very_high": (215, 48, 39),
}
NODATA_RENDER = {"rgba": (0, 0, 0, 0), "label": "no data (not observed)",
                 "meaning": "transparent: not a value on the susceptibility scale"}


def legend() -> dict:
    from configs.pluvial_constants import SUSCEPTIBILITY_CLASS_BREAKS
    return {"tiers": [{"tier": t, "range": list(SUSCEPTIBILITY_CLASS_BREAKS[t]),
                       "rgba": [*TIER_COLOURS[t], 255]} for t in TIER_COLOURS],
            "nodata": {**NODATA_RENDER, "rgba": list(NODATA_RENDER["rgba"])}}


def render_rgba(score: np.ndarray) -> np.ndarray:
    """(H, W) scores in [0, 1] with NaN = no data -> (H, W, 4) uint8."""
    from configs.pluvial_constants import SUSCEPTIBILITY_CLASS_BREAKS
    s = np.asarray(score, dtype=np.float64)
    out = np.zeros((*s.shape, 4), dtype=np.uint8)
    finite = np.isfinite(s)
    for tier, (lo, hi) in SUSCEPTIBILITY_CLASS_BREAKS.items():
        m = finite & (s >= lo) & (s < hi)
        out[m, :3] = TIER_COLOURS[tier]
        out[m, 3] = 255
    top = finite & (s >= max(hi for _, hi in SUSCEPTIBILITY_CLASS_BREAKS.values()))
    out[top, :3], out[top, 3] = TIER_COLOURS["very_high"], 255
    return out


def png_bytes(rgba: np.ndarray) -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG")
    return buf.getvalue()


def map_record(name: str, score: np.ndarray, transform, crs: str) -> tuple:
    """(metadata for the result, PNG bytes for the store)."""
    finite = np.isfinite(score)
    meta = {"name": name, "format": "png_rgba", "crs": crs,
            "transform": [float(v) for v in list(transform)[:6]],
            "shape": list(score.shape), "nodata_cells": int((~finite).sum()),
            "cells": int(score.size), "nodata_render": "alpha 0 (transparent)",
            "legend": legend()}
    return meta, png_bytes(render_rgba(score))
