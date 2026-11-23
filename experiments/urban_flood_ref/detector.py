"""Four-state reference candidates from matched Sentinel-1 acquisitions on a metric grid.

Arrays must already be co-registered and preprocessed on the same grid. Archive
nodata as NaN; validate scene identities, relative orbit, pass, platform and date
ordering before calling. See DETECTOR.md for signal definitions and limitations.
"""
from enum import IntEnum, IntFlag
import warnings

import numpy as np


class State(IntEnum):
    UNOBSERVED = 0
    DRY = 1
    FLOODED = 2
    AMBIGUOUS = 3


class Method(IntFlag):
    DARKENING = 1
    URBAN_BRIGHTENING = 2
    COHERENCE_DROP = 4
    STABLE_OPEN_LAND = 8
    MEASURED_DRY = 16
    NEAR_DARKENING = 32


# Operating choices for the development study. Values in dB compare co-registered
# full-resolution inputs from the same track. They are not pooled probabilities.
MIN_PRE_DATES = 3
MIN_BUILT_FRACTION = 0.10
MAX_SLOPE_DEG = 10.0
MIN_URBAN_EXCESS_DB = 3.0
MIN_ROBUST_DEPARTURE = 2.5
MAX_ANCHOR_DISTANCE_M = 110.0


def _array(arr):
    return np.ma.asarray(arr, dtype=np.float32).filled(np.nan)


def _as_grid(arr, shape):
    return np.broadcast_to(_array(arr), shape)


def _lagged_view(mask, dy, dx):
    """Align one neighbor offset to the output grid, padding outside as False."""
    ny, nx = mask.shape
    out = np.zeros_like(mask)
    if abs(dy) < ny and abs(dx) < nx:
        out[max(0, -dy):min(ny, ny-dy), max(0, -dx):min(nx, nx-dx)] = (
            mask[max(0, dy):min(ny, ny+dy), max(0, dx):min(nx, nx+dx)]
        )
    return out


def _local_group(mask):
    neighbors = np.zeros(mask.shape, dtype=np.uint8)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            neighbors += _lagged_view(mask, dy, dx)
    return mask & (neighbors >= 3)


def _nearby(mask, pixel_size_m):
    """Euclidean dilation in metres using only NumPy; no edge wraparound."""
    radius = int(np.floor(MAX_ANCHOR_DISTANCE_M / pixel_size_m))
    # For each row offset, use cumulative row sums for the horizontal interval.
    extended = np.zeros_like(mask)
    for dy in range(-min(radius, mask.shape[0]-1), min(radius, mask.shape[0]-1)+1):
        width = int(np.floor(np.sqrt(max(0., (MAX_ANCHOR_DISTANCE_M / pixel_size_m)**2 - dy**2))))
        row = _lagged_view(mask, dy, 0)
        prefix = np.pad(np.cumsum(row, axis=1, dtype=np.int32), ((0, 0), (1, 0)))
        x = np.arange(mask.shape[1])
        extended |= prefix[:, np.minimum(x+width+1, mask.shape[1])] > prefix[:, np.maximum(x-width, 0)]
    return extended


def _support(margin):
    # A ratio of one just meets all conditions; capped numerical support is
    # deliberately uncalibrated. Margin is measured in operating thresholds.
    margin = np.clip(margin, 0., 100.)
    return (margin / (1.+margin)).astype(np.float32)


def detect_summary(pre_vv_median, pre_vh_median, pre_vv_mad, pre_vh_mad,
                   pre_count, post_vv, post_vh, *, built_fraction, slope_deg,
                   occurrence_pct, terrain_visible=None, open_land=None, dry_evidence=None,
                   coherence_pre=None, coherence_event=None, pixel_size_m=10.0):
    """Classify one SAR acquisition using paired pre-event medians and raw MADs.

    built_fraction is 0..1 and occurrence_pct 0..100. terrain_visible and
    open_land and dry_evidence use 1 for explicit positive evidence and 0 or NaN otherwise.
    open_land must come from an independent pre-event map of open terrain.
    Unavailable dry/coherence never supplies wet, dry or independent validation.
    """
    vv = _array(post_vv)
    vh = _array(post_vh)
    if vv.shape != vh.shape or vv.ndim != 2 or not all(vv.shape):
        raise ValueError("post VV and VH must be non-empty co-registered 2D arrays")
    if not np.isfinite(pixel_size_m) or pixel_size_m <= 0:
        raise ValueError("pixel_size_m must be a positive metric grid spacing")
    if (coherence_pre is None) != (coherence_event is None):
        raise ValueError("supply both matched coherence images or neither")

    bvv, bvh, mvv, mvh, count, built, slope, occ = (
        _as_grid(x, vv.shape) for x in (pre_vv_median, pre_vh_median, pre_vv_mad,
        pre_vh_mad, pre_count, built_fraction, slope_deg, occurrence_pct)
    )
    valid = (np.isfinite(vv) & np.isfinite(vh) & np.isfinite(bvv) & np.isfinite(bvh)
             & np.isfinite(mvv) & (mvv >= 0) & np.isfinite(mvh) & (mvh >= 0)
             & np.isfinite(count) & (count >= MIN_PRE_DATES) & (built >= 0) & (built <= 1)
             & (slope >= 0) & (slope <= MAX_SLOPE_DEG) & (occ >= 0) & (occ < 80))
    if terrain_visible is not None:
        valid &= _as_grid(terrain_visible, vv.shape) == 1
    urban = (built >= MIN_BUILT_FRACTION) & (built <= 1)
    dvv, dvh = vv - bvv, vh - bvh
    svv, svh = 1.4826 * mvv, 1.4826 * mvh
    vv_gate = np.maximum(3., MIN_ROBUST_DEPARTURE*svv)
    vh_gate = np.maximum(1.5, MIN_ROBUST_DEPARTURE*svh)

    dark_margin = np.minimum(-dvv/vv_gate, -dvh/vh_gate)
    dark_pixel = valid & (dark_margin >= 1.) & (vv <= -16.) & (vh <= -22.) & ((bvv > -16.) | (bvh > -22.))
    dark = _local_group(dark_pixel)

    # A co-polar rise exceeding cross-polar change is compatible with
    # water-wall scattering. Temporal variability suppresses noisy urban returns.
    bright_margin = np.minimum(dvv / vv_gate, (dvv-dvh) / MIN_URBAN_EXCESS_DB)
    bright_pixel = valid & urban & (bright_margin >= 1.)
    bright = _local_group(bright_pixel)

    coherent = np.zeros(vv.shape, dtype=bool)
    coherence_margin = np.zeros(vv.shape, dtype=np.float32)
    if coherence_pre is not None:
        pre, event = (_as_grid(x, vv.shape) for x in (coherence_pre, coherence_event))
        coherence_margin = (pre-event)/.25
        coherent = _local_group(valid & urban & (pre >= .65) & (pre <= 1.)
                                & (event >= 0.) & (event <= 1.) & (coherence_margin >= 1.))

    neighbor = _nearby(dark, pixel_size_m)
    confirmed_bright = bright & (neighbor | coherent)
    confirmed_coherence = coherent & (bright | neighbor)
    new_flood = dark | confirmed_bright | confirmed_coherence

    # Stable high radar returns can be roofs or canopy above floodwater.
    # The open-land dry proxy is conservative and still needs its own validation.
    stable = valid & (np.abs(dvv) < 1.5) & (np.abs(dvh) < 1.5) & (svv <= 1.5) & (svh <= 1.5)
    open_mask = np.zeros(vv.shape, dtype=bool) if open_land is None else _as_grid(open_land, vv.shape) == 1
    open_dry = stable & ~urban & open_mask & (occ == 0) & (vv > -12.) & (vh > -18.) & ~neighbor
    direct = np.zeros(vv.shape, dtype=bool) if dry_evidence is None else _as_grid(dry_evidence, vv.shape) == 1
    agreed_dry = direct & stable & ~neighbor & ~coherent
    dry = open_dry | agreed_dry
    # A timed independent dry observation conflicting with apparent SAR water
    # forces abstention; it cannot be used as the evaluation reference afterward.
    conflict = direct & (new_flood | dark_pixel | bright_pixel | coherent)
    state = np.full(vv.shape, State.UNOBSERVED, dtype=np.uint8)
    state[valid] = State.AMBIGUOUS
    state[dry & ~conflict] = State.DRY
    baseline = state.copy()
    baseline[dark & ~conflict] = State.FLOODED
    state[new_flood & ~conflict] = State.FLOODED

    method = np.zeros(vv.shape, dtype=np.uint8)
    for flag, mask in ((Method.DARKENING, dark_pixel), (Method.URBAN_BRIGHTENING, bright_pixel),
                       (Method.COHERENCE_DROP, coherent), (Method.STABLE_OPEN_LAND, open_dry),
                       (Method.MEASURED_DRY, valid & direct),
                       (Method.NEAR_DARKENING, neighbor & (bright | coherent))):
        method[mask] |= int(flag)

    confidence = np.where(valid, 0., np.nan).astype(np.float32)
    quiet_margin = np.minimum(1.5 / np.maximum(np.maximum(np.abs(dvv), np.abs(dvh)), .01),
                              1.5 / np.maximum(np.maximum(svv, svh), .01))
    confidence[dry & ~conflict] = _support(quiet_margin[dry & ~conflict])
    wet_margin = np.maximum.reduce((np.where(dark, dark_margin, 0),
                                    np.where(confirmed_bright, bright_margin, 0),
                                    np.where(confirmed_coherence, coherence_margin, 0)))
    confidence[new_flood & ~conflict] = _support(wet_margin[new_flood & ~conflict])
    return {"state":state, "confidence":confidence, "method":method, "baseline_state":baseline, "urban":urban}


def detect(pre_vv, pre_vh, post_vv, post_vh, **context):
    """Summarize [date,y,x] matched stacks. Both channels must exist on each pre date."""
    vv, vh = _array(pre_vv), _array(pre_vh)
    if vv.ndim != 3 or vv.shape != vh.shape or vv.shape[0] == 0 or vv.shape[1:] != np.shape(post_vv):
        raise ValueError("pre VV/VH stacks must be paired [date,y,x] at post resolution")
    paired = np.isfinite(vv) & np.isfinite(vh)
    vv, vh = np.where(paired, vv, np.nan), np.where(paired, vh, np.nan)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="All-NaN slice encountered", category=RuntimeWarning)
        bvv, bvh = np.nanmedian(vv, axis=0), np.nanmedian(vh, axis=0)
        mvv = np.nanmedian(np.abs(vv-bvv), axis=0)
        mvh = np.nanmedian(np.abs(vh-bvh), axis=0)
    return detect_summary(bvv, bvh, mvv, mvh, paired.sum(axis=0), post_vv, post_vh, **context)
