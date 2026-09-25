"""
Item 21 Phase A, part 5 — fraction bookkeeping. Pure numpy.

The eight fractions (Decision 11, amended 2026-09-24), per known pixel:

    non_hard          = vegetation + water + snow_ice + solar
                        + mixed_water_vegetation
    remainder         = 1 - non_hard                 (hard-surface remainder)
    impervious_total  = impervious_share * remainder (regressor; share of the
                                                      remainder, Phase A ruling)
    bare              = remainder - impervious_total (residual)
    built             = footprints (part 4)
    paved_unclamped   = impervious_total - built     (derived, never measured)
    paved             = max(paved_unclamped, 0)      (clamped, FLAGGED)
    sum_excess        = paved - paved_unclamped
    => the eight sum to exactly 1 + sum_excess on every known pixel.

Rules, all from 05_BUILD_MANUAL.md item 21 "Phase A — build rulings":
  - Known-pixel denominator only (Decision 14). Occluded pixels are NaN in
    every fraction; they never enter a mean.
  - Fully shadowed pixels left the denominator in part 2 and shadow appears
    nowhere here (shadow rule, locked 2026-09-24).
  - Detectors override the vegetation and water regressors on a detected
    pixel (Phase A simplification). A mixed_water_vegetation pixel is not
    also vegetation or water.
  - Over-subscription (non_hard > 1; built > remainder; two detectors on one
    pixel) is FLAGGED, never rescaled.
  - A not_computed detector makes the remainder not_computed, except in an
    AOI marked smoke_test, where a placeholder stands in and is marked.
  - solar is subtracted from the remainder but NOT added to
    impervious_total (inclusion DEFERRED, Decision 11).
  - solar is ground-mounted only: where it meets an Open Buildings footprint,
    built wins, i.e. solar <= 1 - built on the pixel, flagged (ruling
    2026-09-25, second round).
  - An "excluded" detector (known zero from a dataset) is a real zero and
    does not block the remainder.
  - Blocking is PER PIXEL (R2 amendment, 2026-09-25): an input that is not
    computed on a pixel (NaN on a known pixel, or None for the whole AOI)
    blocks the remainder -- and everything derived from it -- on that pixel
    only. blocked_pixel_share is reported, with each input's share.
  - Dataset producers (R2: GMW mangrove, provenance "dataset:...") are
    continuous and do NOT override vegetation / water; only a spectral
    detection (provenance "detector") does. Overlap is flagged as
    over-subscription, never rescaled.
"""

from __future__ import annotations

import numpy as np

from surface_fractions.regressors import PLACEHOLDER

EIGHT = ("built", "paved", "vegetation", "water", "bare",
         "snow_ice", "solar", "mixed_water_vegetation")
DETECTOR_FRACTIONS = ("snow_ice", "solar", "mixed_water_vegetation")
NON_HARD = ("vegetation", "water") + DETECTOR_FRACTIONS
SUM_TOLERANCE = 1e-5          # float32 arithmetic, not a modelling choice

# Which base inputs each derived quantity depends on, for taint tracking.
DEPENDS = {
    "hard_surface_remainder": NON_HARD,
    "impervious_total": ("hard_surface_remainder", "impervious_share"),
    "bare": ("hard_surface_remainder", "impervious_total"),
    "paved_unclamped": ("impervious_total", "built"),
    "paved": ("paved_unclamped",),
}
DERIVED_PROVENANCE = {
    "hard_surface_remainder": "derived",
    "impervious_total": "regression",
    "bare": "residual",
    "paved_unclamped": "derived",
    "paved": "derived",
}


def _mean(a, known):
    if a is None or not known.any():
        return None
    return float(np.nanmean(np.where(known, a, np.nan)))


def _share(flag, known):
    return float(flag[known].mean()) if known.any() else None


def compute_fractions(known: np.ndarray, built: np.ndarray, regs: dict,
                      detectors: dict, smoke_test: bool,
                      detector_placeholder_value: float) -> dict:
    known = np.asarray(known, dtype=bool)
    nan = lambda: np.full(known.shape, np.nan, dtype=np.float32)
    mask = lambda a: np.where(known, a, np.nan).astype(np.float32)

    base = {}        # name -> array | None
    prov = {}        # name -> provenance string
    substitutions = []

    # Detectors (part 3); smoke-test substitution only.
    for name in DETECTOR_FRACTIONS:
        d = detectors[name]
        frac = None if d.get("fraction") is None else mask(d["fraction"])
        if d["status"] in ("computed", "partial"):
            base[name] = frac
            prov[name] = d.get("provenance", "detector")
        elif d["status"] == "excluded":
            base[name], prov[name] = frac, d["provenance"]
        else:
            base[name], prov[name] = None, "not_computed"
        gap = known if base[name] is None else known & ~np.isfinite(base[name])
        if smoke_test and gap.any():
            # A computed part (R2: GMW mangrove) is kept; the placeholder
            # stands in only where the input is missing, and taints the sum.
            partial = d.get("mangrove_fraction")
            fill = (0.0 if partial is None else np.nan_to_num(partial)) + detector_placeholder_value
            cur = np.zeros(known.shape, np.float32) if base[name] is None else base[name]
            base[name] = mask(np.where(gap, fill, cur))
            prov[name] = PLACEHOLDER
            substitutions.append({"fraction": name, "value": detector_placeholder_value,
                                  "pixels_filled": int(gap.sum()),
                                  "kept_computed_part": partial is not None,
                                  "reason": f"detector {d['status']}; smoke test only"})

    # Precedence: any detection on the pixel zeroes vegetation and water.
    detected = np.zeros(known.shape, dtype=bool)
    for name in DETECTOR_FRACTIONS:
        if base[name] is not None and prov[name] == "detector":
            detected |= np.nan_to_num(base[name]) > 0
    for name in ("vegetation", "water"):
        p = regs[name]
        base[name] = mask(np.where(detected, 0.0, p.value))
        prov[name] = p.provenance
    base["impervious_share"] = mask(regs["impervious_share"].value)
    prov["impervious_share"] = regs["impervious_share"].provenance
    base["built"] = mask(built)
    prov["built"] = "footprints"

    flags = {}
    # Rooftop panels are built: solar yields any area a footprint covers.
    if base["solar"] is not None:
        cap = np.maximum(1.0 - base["built"], 0.0)
        yielded = known & (base["solar"] > cap + SUM_TOLERANCE)
        base["solar"] = mask(np.minimum(base["solar"], cap))
        flags["solar_yielded_to_built"] = yielded
    # Per-pixel availability of every non-hard input.
    input_ok = {n: (np.zeros(known.shape, bool) if base[n] is None
                    else known & np.isfinite(base[n])) for n in NON_HARD}
    avail = known.copy()
    for ok in input_ok.values():
        avail &= ok
    blocked = known & ~avail
    missing = [n for n in NON_HARD if (known & ~input_ok[n]).any()]
    n_known = int(known.sum())
    remainder_block = {
        "blocked_pixel_share": float(blocked.sum()) / n_known if n_known else None,
        "blocked_pixels": int(blocked.sum()),
        "blocked_by": {n: float((known & ~input_ok[n]).sum()) / n_known
                       for n in NON_HARD if (known & ~input_ok[n]).any()} if n_known else {},
    }
    on = lambda a: np.where(avail, a, np.nan).astype(np.float32)
    if not avail.any():
        remainder = imp = bare = paved_u = paved = excess = None
    else:
        non_hard = sum(np.nan_to_num(base[n]) for n in NON_HARD)
        remainder = on(1.0 - non_hard)
        imp = on(base["impervious_share"] * remainder)
        bare = on(remainder - imp)
        paved_u = on(imp - base["built"])
        paved = on(np.maximum(paved_u, 0.0))
        excess = on(paved - paved_u)
        flags["nonhard_oversubscribed"] = avail & (non_hard > 1.0 + SUM_TOLERANCE)
        flags["built_exceeds_remainder"] = avail & (base["built"] > remainder + SUM_TOLERANCE)
        flags["paved_negative"] = avail & (paved_u < -SUM_TOLERANCE)
    det_sum = sum(np.nan_to_num(base[n]) for n in DETECTOR_FRACTIONS if base[n] is not None)
    flags["detector_overlap"] = known & (np.asarray(det_sum) > 1.0 + SUM_TOLERANCE)

    derived = {"hard_surface_remainder": remainder, "impervious_total": imp,
               "bare": bare, "paved_unclamped": paved_u, "paved": paved}
    arrays = {**base, **derived, "sum_excess": excess}
    for k, v in derived.items():
        prov[k] = DERIVED_PROVENANCE[k] if v is not None else "not_computed"

    def placeholder_inputs(name, seen=None):
        seen = set() if seen is None else seen
        if name in DEPENDS:
            for dep in DEPENDS[name]:
                placeholder_inputs(dep, seen)
        elif prov.get(name) == PLACEHOLDER:
            seen.add(name)
        return seen

    def record(name):
        a = arrays[name]
        ph = sorted(placeholder_inputs(name))
        provenance = prov[name]
        # A quantity computed from any placeholder says so in its provenance
        # itself, not only in placeholder_inputs: the field alone must never
        # read as a real regression / residual / derivation.
        if ph and a is not None and provenance != PLACEHOLDER:
            provenance = f"{PLACEHOLDER}:{provenance}"
        share = (float((known & np.isfinite(a)).sum()) / n_known
                 if a is not None and n_known else 0.0)
        status = ("not_computed" if a is None or share == 0
                  else "computed" if share == 1.0 else "partial")
        return {"status": status,
                "provenance": provenance,
                "placeholder_inputs": ph,
                "placeholder_tainted": bool(ph),
                "computed_share_of_known": share,
                "aoi_mean_known_pixels": _mean(a, known)}

    records = {n: record(n) for n in EIGHT}
    for n in ("impervious_total", "hard_surface_remainder", "paved_unclamped"):
        records[n] = record(n)
    records["paved"]["clamped"] = "negative paved_unclamped clamped to 0 and flagged"
    records["paved"]["measured"] = False
    if missing:
        for n in ("hard_surface_remainder", "impervious_total", "bare", "paved",
                  "paved_unclamped"):
            records[n]["reason"] = (f"not_computed inputs: {missing}" if not avail.any()
                                    else f"blocked on {remainder_block['blocked_pixel_share']:.4f} "
                                         f"of known pixels by inputs: {missing}")

    sum_check = None
    if avail.any():
        total = sum(np.nan_to_num(arrays[n]) for n in EIGHT)
        dev = np.where(avail, np.abs(total - (1.0 + np.nan_to_num(excess))), 0.0)
        sum_check = {"max_abs_deviation_from_1_plus_excess": float(dev.max()),
                     "aoi_mean_sum_excess": _mean(excess, avail),
                     "over": "pixels with a computed remainder"}
        if sum_check["max_abs_deviation_from_1_plus_excess"] > SUM_TOLERANCE:
            raise AssertionError(f"fraction bookkeeping broken: {sum_check}")

    return {
        "per_pixel": arrays,
        "fractions": records,
        "flags": {k: {"pixel_share_of_known": _share(v, known), "pixels": int(v.sum())}
                  for k, v in flags.items()},
        "flag_arrays": flags,
        "remainder": remainder_block,
        "remainder_computed": avail,
        "substitutions": substitutions,
        "sum_check": sum_check,
        "precedence": {"detectors_override_vegetation_water": True,
                       "detected_pixels": int((detected & known).sum()),
                       "note": "Phase A simplification (ruled 2026-09-25); revisit "
                               "after each detector's validation case"},
        "contains_placeholder": any(r["placeholder_tainted"] for r in records.values()),
    }
