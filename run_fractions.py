"""
Item 21 Phase A — run the surface-fraction pipeline for one AOI.

    python run_fractions.py --aoi dharavi

Parts 1-5 (and 6, context layers) of 05_BUILD_MANUAL.md item 21, "Phase A".
No model is trained. Vegetation, water and the impervious share are
PLACEHOLDERS; every output that touches them is marked.
"""

from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone

import numpy as np

from surface_fractions import bookkeeping, built, detectors, occlusion, output
from surface_fractions.config import load_config
from surface_fractions.inputs import assemble_inputs
from surface_fractions.regressors import placeholder_regressors


def run(aoi_name: str, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    started = datetime.now(timezone.utc).isoformat()

    # Part 1
    bundle = assemble_inputs(aoi_name, cfg)
    run_dir = os.path.dirname(bundle.stack_path)
    grid, aoi = bundle.grid, bundle.aoi
    smoke = bool(aoi.get("smoke_test", False))

    # Part 2 inputs + part 3 datasets, same grid.
    obs, obs_prov = occlusion.export_observations(aoi, cfg, grid, run_dir)
    ds, ds_prov = detectors.export_datasets(cfg, grid, run_dir)
    bands = {**bundle.bands, **obs, **ds}
    counts = {k: np.nan_to_num(obs[k]).astype(np.int64) for k in occlusion.COUNT_BANDS}

    # snow_ice first: occlusion needs it to split permanent from transient
    # snow. It runs on every pixel with any valid-or-snow observation.
    pre_known = (counts["n_valid"] + counts["n_snow"]) > 0
    snow = detectors.run_detector("snow_ice", cfg, bands, pre_known)
    snow_mask = None if snow["fraction"] is None else np.nan_to_num(snow["fraction"]) > 0

    # Part 2
    occ = occlusion.resolve_occlusion(
        counts, snow_mask,
        firms_complete=obs_prov["fire"]["scenes_without_firms_image"] == 0)
    known = occ["known"]
    features = {**bands, **{f"obs_{k}": v for k, v in
                            occlusion.observable_composite(bands, occ).items()}}

    # Part 3, on the final known mask
    dets = {"snow_ice": snow}
    if snow["fraction"] is not None:
        snow["fraction"] = np.where(known, snow["fraction"], np.nan).astype(np.float32)
    for name in ("solar", "mixed_water_vegetation"):
        dets[name] = detectors.run_detector(name, cfg, features, known)
    legend = cfg["detectors"]["mixed_water_vegetation"]["sub_typing"]["glwd_legend"]
    mwv_sub = detectors.sub_type(dets["mixed_water_vegetation"]["fraction"],
                                 bands["gmw_cov"], bands["glwd_class"], legend)

    # Part 4
    b = built.compute_built(bundle.bands, bundle.status, bundle.provenance["open_buildings"])

    # Part 5
    regs = {t: r.predict(features, known) for t, r in placeholder_regressors(cfg).items()}
    fr = bookkeeping.compute_fractions(
        known, b["built"], regs, dets, smoke_test=smoke,
        detector_placeholder_value=cfg["placeholders"]["detector_smoke_test_value"])

    derived_names = ("impervious_total", "hard_surface_remainder", "paved_unclamped")
    result = {
        "schema": output.SCHEMA,
        "banner": {"claim_status": output.CLAIM_STATUS,
                   "contains_placeholder": fr["contains_placeholder"],
                   "smoke_test": smoke,
                   "trained_models": None},
        "run": {"aoi": aoi, "started_utc": started,
                "finished_utc": datetime.now(timezone.utc).isoformat(),
                "run_dir": run_dir},
        "grid": grid.to_dict(),
        "fractions": {n: fr["fractions"][n] for n in bookkeeping.EIGHT},
        "derived": {n: fr["fractions"][n] for n in derived_names},
        "sum_check": fr["sum_check"],
        "substitutions": fr["substitutions"],
        "precedence": fr["precedence"],
        "observability": occ["fields"],
        "estimate_quality": {
            **{f"prediction_interval_{t}": p.prediction_interval for t, p in regs.items()},
            "paved_derivation_uncertainty": {
                "status": "not_computed",
                "reason": "needs prediction intervals on impervious_total; "
                          "placeholder regressors have none"},
            "built_disagreement": b["disagreement"],
        },
        "flags": fr["flags"],
        "detectors": {n: {k: v for k, v in d.items() if k != "fraction"}
                      for n, d in dets.items()},
        "mixed_water_vegetation_sub_type": {k: v for k, v in mwv_sub.items() if k != "labels"},
        "dataset_context": detectors.dataset_context(bands, legend),
        "sources": {"status": bundle.status, "errors": bundle.errors,
                    "provenance": {**bundle.provenance, "observations": obs_prov,
                                   "datasets": ds_prov, "built": b["provenance"]}},
    }

    layers = {n: fr["per_pixel"][n] for n in bookkeeping.EIGHT}
    layers.update({n: fr["per_pixel"][n] for n in derived_names + ("sum_excess",)})
    layers["known"] = known.astype(np.float32)
    layers.update({f"occluded_{k}": v.astype(np.float32) for k, v in occ["pixels"].items()})
    layers.update({f"flag_{k}": v.astype(np.float32) for k, v in fr["flag_arrays"].items()})
    layers["built_secondary_abs_diff"] = b["built_secondary_abs_diff"]
    raster, written, skipped = output.write_raster(layers, grid, run_dir)
    result["rasters"] = {"fractions": raster, "bands": written,
                         "not_written_not_computed": skipped,
                         "inputs": bundle.stack_path}
    result["result_path"] = output.write_result(result, run_dir)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aoi", required=True)
    args = ap.parse_args()
    r = run(args.aoi)
    print(f"\nresult:  {r['result_path']}\nraster:  {r['rasters']['fractions']}")
    print(f"placeholder outputs: {r['banner']['contains_placeholder']}")


if __name__ == "__main__":
    main()
