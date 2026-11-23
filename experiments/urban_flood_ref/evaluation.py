"""Conditional agreement at 30 m, with preserved missingness and paired spatial blocks."""
from pathlib import Path

import numpy as np
import rasterio

from .package import AMBIGUOUS, DRY, UNOBSERVED, WET, check_grid

BLOCK_CELLS = 33  # 990 m, approximately one kilometre on the model lattice
BOOTSTRAP_DRAWS = 2000
STATE_CODES = [UNOBSERVED, DRY, WET, AMBIGUOUS]
REF_CODES = [0, 1, 255]  # observed dry, observed wet, unknown


def _ratio(x, y):
    return float(x/y) if y else None


def _interval(numer, denom, rng):
    occupied = denom > 0
    n = int(occupied.sum())
    if n < 2:
        return None, None, n
    numer, denom = numer[occupied], denom[occupied]
    boot = []
    for _ in range(0, BOOTSTRAP_DRAWS, 50):
        ix = rng.integers(n, size=(50, n))
        boot.extend(numer[ix].sum(axis=1)/denom[ix].sum(axis=1))
    lo, hi = np.quantile(boot, [0.025, 0.975])
    return float(lo), float(hi), n


def _check_state(a):
    if a.ndim != 2 or not np.isin(a, STATE_CODES).all():
        raise ValueError("Invalid four-state raster")


def score_arrays(state, base, urban, truth=None, *, block_cells=BLOCK_CELLS, seed=20261123):
    """One independent reference at a time. Without reference, accuracy stays undefined."""
    state, base, urban = map(np.asarray, (state, base, urban))
    for a in (state, base):
        _check_state(a)
    if truth is None:
        truth = np.full(state.shape, 255, dtype=np.uint8)
    truth = np.asarray(truth)
    if (not all(a.shape == state.shape for a in (base, urban, truth))
            or not np.isin(urban,[0,1]).all() or not np.isin(truth, REF_CODES).all()):
        raise ValueError("Input shape, urban mask or independent classification is invalid")
    if not isinstance(block_cells,int) or block_cells < 1:
        raise ValueError("Block size must be a positive integer number of cells")
    yy, xx = np.indices(state.shape)
    width_blocks = (state.shape[1]+block_cells-1)//block_cells
    block = yy//block_cells*width_blocks + xx//block_cells
    nblocks = int(block.max())+1
    def counts(mask):
        return np.bincount(block[mask],minlength=nblocks)
    rows = []
    for where, footprint in (("all", np.ones(state.shape,bool)),("urban",urban.astype(bool))):
        pos, neg = footprint & (truth == 1), footprint & (truth == 0)
        known = pos | neg
        add = footprint & (state == WET) & (base != WET)
        dropped = footprint & (base == WET) & (state != WET)
        common = {
            "stratum":where, "total":int(footprint.sum()),"ref_wet":int(pos.sum()),
            "ref_dry":int(neg.sum()),"ref_unknown":int((footprint & ~known).sum()),
            "new_wet":int(add.sum()),"new_ref_wet":int((add & pos).sum()),
            "new_ref_dry":int((add & neg).sum()),"new_ref_unknown":int((add & ~known).sum()),
            "new_over_baseline_dry":int((add & (base==DRY)).sum()),
            "lost_baseline_wet":int(dropped.sum()),
        }
        for label, m in (("urban_detector",state), ("intensity_only",base)):
            wet = m == WET
            dry = m == DRY
            classified = wet | dry
            hits = pos & wet
            alarms = neg & wet
            row = {**common,"detector":label,"observed":int((footprint & (m!=UNOBSERVED)).sum()),
                   "classified":int((footprint & classified).sum()),"wet":int((footprint & wet).sum()),
                   "dry":int((footprint & dry).sum()),"ambiguous":int((footprint & (m==AMBIGUOUS)).sum()),
                   "unobserved":int((footprint & (m==UNOBSERVED)).sum()),
                   "tp":int(hits.sum()),"fp":int(alarms.sum()),"tn":int((neg & dry).sum()),
                   "fn_classified":int((pos & dry).sum()),"ref_wet_abstained":int((pos & ~classified).sum()),
                   "ref_dry_abstained":int((neg & ~classified).sum())}
            measures = {
                "wet_recall": (hits,pos), # counts abstentions as misses of known flooded cells
                "dry_false_alarm": (alarms,neg), # alongside classified-only and abstention
                "classified_wet_recall": (hits,pos & classified),
                "classified_dry_false_alarm": (alarms,neg & classified),
                "agreement_if_classified": (hits | (neg & dry),known & classified),
                "coverage": (footprint & classified,footprint),
                "wet_share_observed": (wet & footprint,footprint & (m != UNOBSERVED)),
                "paired_recall_delta": (None,pos),
            }
            for name,(num,den) in measures.items():
                nb = counts(num) if num is not None else counts(pos & (state == WET)) - counts(pos & (base == WET))
                db = counts(den)
                row[name] = _ratio(nb.sum(), db.sum())
                # Common RNG for the two methods yields matched block draws.
                lo, hi, n = _interval(nb, db, np.random.default_rng(seed))
                row[name+"_lo"],row[name+"_hi"],row[name+"_blocks"] = lo,hi,n
            rows.append(row)
    return rows


def reference_array(path, grid):
    with rasterio.open(path) as src:
        crs, t, shape = check_grid(grid)
        if src.crs != crs or src.transform != t or src.shape != shape:
            raise ValueError(f"Independent reference does not match the model grid: {Path(path).name}")
        if src.count != 1 or src.nodata != 255:
            raise ValueError("Reference must declare a single band with nodata=255")
        a = src.read(1)
        if not np.isin(a,REF_CODES).all():
            raise ValueError("Independent reference must encode wet=1, dry=0, unknown=255")
        return a


def event_arrays(path):
    with rasterio.open(path) as src:
        grid = {"crs":src.crs.to_string(),"shape":list(src.shape),"transform":list(src.transform)[:6]}
        check_grid(grid)
        bands = {name:idx for idx,name in enumerate(src.descriptions,1)}
        state,base,urban = (src.read(bands[k]) for k in ("state","baseline_state","urban"))
        return state,base,urban,grid
