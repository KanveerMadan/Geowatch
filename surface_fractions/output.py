"""
Item 21 Phase A — output schema and writer.

Two files per run:
  result.json    AOI-level record: fractions, observability, estimate
                 quality, flags, provenance, statuses
  fractions.tif  per-pixel float32 bands on the native Sentinel-2 grid

Field-naming discipline (Decision 14): the eight land-cover fractions live
under "fractions" and nowhere else. Observability, estimate quality, flags
and context are structurally separate, so a consumer summing "fractions"
gets ~1 on the known-pixel denominator and never mistakes a coverage field
for a ninth class.

The writer refuses to write a fraction without a provenance, and stamps the
validation-first mandate and the placeholder banner at the top of the file.
"""

from __future__ import annotations

import json
import os

import numpy as np

from surface_fractions.bookkeeping import EIGHT

# /2 (2026-09-25): estimate_quality.built_disagreement.iou_10m renamed
# weighted_jaccard.
SCHEMA = "geowatch.surface_fractions.phase_a/2"
CLAIM_STATUS = ("proposed research design, not an established claim -- Part 4 "
                "validation-first mandate (05_BUILD_MANUAL.md, 2026-09-24)")


class OutputContractError(ValueError):
    pass


def check_contract(result: dict) -> None:
    fr = result["fractions"]
    if set(fr) != set(EIGHT):
        raise OutputContractError(f"fractions must be exactly {EIGHT}, got {sorted(fr)}")
    for name, rec in {**fr, **result["derived"]}.items():
        if not rec.get("provenance"):
            raise OutputContractError(f"{name} has no provenance")
        if rec["placeholder_tainted"] and not result["banner"]["contains_placeholder"]:
            raise OutputContractError(f"{name} is placeholder-tainted but the banner is off")
        if rec["placeholder_tainted"] and not rec["provenance"].startswith("placeholder"):
            raise OutputContractError(
                f"{name} is placeholder-tainted but its provenance "
                f"{rec['provenance']!r} does not say so")
    for group in ("observability", "estimate_quality", "flags", "context"):
        clash = set(result[group]) & set(EIGHT)
        if clash:
            raise OutputContractError(f"{group} reuses fraction names {clash}")


def _jsonable(o):
    if isinstance(o, dict):
        return {str(k): _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    if isinstance(o, np.ndarray):
        raise OutputContractError("per-pixel arrays belong in the raster, not result.json")
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o


def write_result(result: dict, run_dir: str) -> str:
    check_contract(result)
    path = os.path.join(run_dir, "result.json")
    with open(path, "w") as fh:
        json.dump(_jsonable(result), fh, indent=2)
    return path


def write_raster(layers: dict, grid, run_dir: str, name: str = "fractions.tif") -> tuple:
    """Write {band name: 2-D array | None} as float32; None layers are
    skipped and listed, never written as zeros."""
    import rasterio
    present = [(k, v) for k, v in layers.items() if v is not None]
    skipped = [k for k, v in layers.items() if v is None]
    path = os.path.join(run_dir, name)
    with rasterio.open(path, "w", driver="GTiff", width=grid.width, height=grid.height,
                       count=len(present), dtype="float32", crs=grid.crs,
                       transform=grid.affine(), nodata=np.nan, compress="deflate") as dst:
        for i, (k, v) in enumerate(present, start=1):
            dst.write(np.asarray(v, dtype=np.float32), i)
        dst.descriptions = tuple(k for k, _ in present)
    return path, [k for k, _ in present], skipped
