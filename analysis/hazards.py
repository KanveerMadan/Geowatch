"""
Flood susceptibility for the analysis pipeline (item 26's modules, consumed
as they are: susceptibility/ is not edited here).

Each module's output becomes one contract output. Its label is the worst of
the module's own label, its pinned Tier 2 verdict, and its inputs' labels
(analysis.contract.hazard_label). Pluvial, flash flood and waterlogging run
flood round 4's new methods (bluespot fill-and-spill; persistence, clay,
relief and backwater; stream power on valley floors), all per-pixel on the
hydrology grid; rounds 1-3's verdicts were on the retired methods and do not
carry over. Coastal is `failed` (round 2). Fluvial reads `validated`,
with its scope note, only while it runs exactly the configuration round 2
validated (C70, analysis.contract.VALIDATED_CONFIGS); otherwise its
experimental raster inputs cap it.
"""
from __future__ import annotations

import numpy as np

from analysis import contract as C
from analysis.stages import STAGE_TIMEOUT_S, run_stage, summary

HAZARDS = ("pluvial", "fluvial", "coastal", "flash_flood", "waterlogging")

CONTEXT_SOURCES = {
    "hand": "MERIT/Hydro/v1_0_1 (hnd, upa)",
    "fabdem": "projects/sat-io/open-datasets/FABDEM",
    "slope": "COPERNICUS/DEM/GLO30 slope",
    "rainfall": "UCSB-CHG/CHIRPS/DAILY climatology",
    "coastline": "projects/sat-io/open-datasets/shoreline",
    "relative_elevation": "COPERNICUS/DEM/GLO30_2024_1 (AOI-relative proxy, NOT HAND)",
    "hydro_rasters": ("per-pixel MERIT/Hydro/v1_0_1 (hnd, upa), FABDEM slope, "
                      "CHIRPS and IMERG V07 (susceptibility/hydro_rasters.py)"),
}

# Which context layers each module reads. Fluvial, flash flood and
# waterlogging are per-pixel since item 26 Phase 1a: their input is the
# hydro_rasters stage (fluvial still reads `hand` for its connectivity caveat
# only, so a missing `hand` does not withhold its score). Since flood round 4
# pluvial reads it too (its design storm), with the DEM and the stand-in
# surfaces.
MODULE_CONTEXT = {
    "pluvial": ("hydro_rasters",),
    "fluvial": ("hydro_rasters",),
    "coastal": ("coastline", "fabdem"),
    "flash_flood": ("hydro_rasters",),
    "waterlogging": ("hydro_rasters",),
}


def _context_fns(bbox):
    w, s, e, n = bbox
    from ingestion import coastal, hydrology, osm_dem, rainfall

    def rain():
        import ee
        return rainfall.get_rainfall_climatology(ee.Geometry.Rectangle([w, s, e, n]))

    return {
        "hand": lambda: hydrology.get_merit_hand_context(w, s, e, n),
        "fabdem": lambda: hydrology.get_fabdem_elevation_stats(w, s, e, n),
        "slope": lambda: hydrology.get_slope_stats(w, s, e, n),
        "rainfall": rain,
        "coastline": lambda: coastal.get_coastline_context(w, s, e, n),
        "relative_elevation": lambda: osm_dem.compute_relative_elevation_proxy(w, s, e, n),
    }


def context_from_outcome(outcome: dict) -> dict:
    """A context dict for the modules. A stage that did not finish becomes a
    dict whose status says so ("timeout" / "failed"), never "available"."""
    if outcome["status"] == "ok":
        v = outcome["value"]
        return v if isinstance(v, dict) else {"status": "unavailable", "error": "no dict"}
    return {"status": outcome["status"], "error": outcome.get("error"),
            "exception_class": outcome.get("exception_class")}


def fetch_context(bbox, *, fns=None) -> tuple:
    """({name: context dict}, {name: stage summary})."""
    fns = fns or _context_fns(bbox)
    ctx, stages = {}, {}
    for name, fn in fns.items():
        o = run_stage(f"context:{name}", fn, timeout_s=STAGE_TIMEOUT_S["context"])
        ctx[name] = context_from_outcome(o)
        stages[f"context:{name}"] = summary(o)
    return ctx, stages


def applicability_for(ctx: dict, impervious: dict | None) -> dict:
    """Applicability without a land-cover model. compute_applicability()'s
    model-trust verdict is the retired classifier's; it is replaced by
    "not_used" (build_flag treats every mechanism as independent of it,
    which since item 26 they all are). The two pct arguments only feed that
    replaced verdict."""
    from perception.applicability import compute_applicability, finalize_applicability
    from susceptibility.inputs import mean_pct
    app = compute_applicability(unknown_pct=0.0, ambiguous_pct=0.0,
                                hand_context=ctx.get("hand"),
                                coastal_context=ctx.get("coastline"),
                                slope_context=ctx.get("slope"))
    app["urban_landcover_model"] = {
        "status": "not_used",
        "reason": "No 7-class land-cover model runs in this pipeline (08_STATE.md §RETIRED)."}
    return finalize_applicability(app, {"impervious_fraction_pct": mean_pct(impervious)})


def run_modules(ctx: dict, surfaces: dict, waterway_dist, app: dict, rasters: dict = None) -> dict:
    """Run the five modules. `surfaces`: dem, impervious, conduits (declared
    surfaces); any may be absent. `rasters`: susceptibility.hydro_rasters
    output on the same grid, or None. `waterway_dist` is no longer read by
    any module (round 4's pluvial routes on the DEM); it is kept for the
    caller's data-source record."""
    from susceptibility.coastal import compute_coastal_susceptibility
    from susceptibility.flash_flood import compute_flash_flood_susceptibility
    from susceptibility.fluvial import compute_fluvial_susceptibility
    from susceptibility.pluvial import compute_pluvial_susceptibility
    from susceptibility.waterlogging import compute_waterlogging_susceptibility
    return {
        "pluvial": compute_pluvial_susceptibility(
            dem=surfaces.get("dem"), impervious=surfaces.get("impervious"),
            conduits=surfaces.get("conduits"), rasters=rasters, applicability=app),
        "fluvial": compute_fluvial_susceptibility(rasters, ctx.get("hand"), applicability=app),
        "coastal": compute_coastal_susceptibility(ctx["coastline"], ctx["fabdem"],
                                                  applicability=app),
        "flash_flood": compute_flash_flood_susceptibility(rasters, applicability=app),
        "waterlogging": compute_waterlogging_susceptibility(rasters, applicability=app),
    }


def _input_labels(mod: dict) -> list:
    return [i["validation_status"] for i in (mod.get("inputs") or {}).values()
            if isinstance(i, dict) and i.get("validation_status") in C.VALIDATION_PRECEDENCE]


def _sources(name: str, mod: dict, has_waterways: bool) -> list:
    out = [f"{i['source']} ({k})" for k, i in (mod.get("inputs") or {}).items()
           if isinstance(i, dict) and i.get("source")]
    out += [CONTEXT_SOURCES[c] for c in MODULE_CONTEXT[name]]
    return out


# Item 38 (C27): an input that did not finish decides the output's status.
# A timeout outranks a failure: retrying can fix it, and saying so matters.
INCOMPLETE = ("timeout", "failed")


def incomplete_inputs(name: str, ctx: dict, stage_status: dict | None = None) -> dict:
    """{input: {"status", "error"}} for every input of module `name` whose
    stage timed out or failed. Pluvial's DEM is a stage too."""
    out = {}
    for c in MODULE_CONTEXT[name]:
        st = (ctx.get(c) or {}).get("status")
        if st in INCOMPLETE:
            out[c] = {"status": st, "error": ctx[c].get("error")}
    if name == "pluvial":
        for k, v in (stage_status or {}).items():
            if k == "dem" and v.get("status") in INCOMPLETE:
                out[k] = {"status": v["status"], "error": v.get("error")}
    return out


def hazard_outputs(modules: dict, mv: dict, verdicts: dict, *, has_waterways: bool,
                   ctx: dict | None = None, stage_status: dict | None = None) -> dict:
    """Each module as a contract output.

    Item 38 (C27): a module whose input timed out (or failed) is reported
    with that status and NO tier, even when it could score the inputs that
    did arrive. A tier from a partial input set is what made two runs of the
    same wards disagree; a status says why they differ."""
    out = {}
    for name in HAZARDS:
        mod = modules[name]
        score = mod.get("aoi_mean_score")
        bad = incomplete_inputs(name, ctx or {}, stage_status)
        # C70: exactly the validated configuration keeps `validated`, scoped.
        scope = None if bad else C.validated_scope(name, mod, verdicts.get(name))
        label = C.hazard_label(mod.get("validation_status", "experimental"),
                               verdicts.get(name), *_input_labels(mod), scope=scope)
        if bad:
            status = "timeout" if any(v["status"] == "timeout" for v in bad.values()) else "failed"
            out[name] = C.absent(
                status, reason=f"input(s) did not finish: {sorted(bad)}",
                validation_status=label,
                data_sources=_sources(name, mod, has_waterways), model_version=mv,
                incomplete_inputs=bad, tier=None, module_status=mod.get("status"),
                score_from_partial_inputs_withheld=score is not None,
                tier2_verdict=verdicts.get(name), spatial=False)
            continue
        extra = {"module_status": mod.get("status"),
                 "validated_scope": scope,
                 "tier": mod.get("aoi_mean_class") if score is not None else None,
                 "tier_scale": "very_low < low < moderate < high < very_high",
                 "tier2_verdict": verdicts.get(name),
                 "spatial": bool(mod.get("susceptibility_map") is not None),
                 "components_used": mod.get("components_used", []),
                 "components_excluded": mod.get("components_excluded", []),
                 "applicability": mod.get("applicability"),
                 "limitations": mod.get("limitations", []),
                 "method": mod.get("method")}
        if score is None:
            status = {"not_applicable": "not_applicable"}.get(mod.get("status"),
                                                               "insufficient_evidence")
            out[name] = C.absent(status, reason=mod.get("reason") or "no input produced a score",
                                 validation_status=label,
                                 data_sources=_sources(name, mod, has_waterways),
                                 model_version=mv, **extra)
            continue
        smap = mod.get("susceptibility_map")
        if smap is not None:
            cov = C.coverage(float(np.isfinite(smap).mean()) if smap.size else 0.0,
                             "share of hydrology-grid cells with a finite score")
        else:
            cov = C.coverage(1.0, "AOI-wide scalar: one statistic over the AOI's bounding box")
        out[name] = C.output(round(float(score), 4), validation_status=label, coverage=cov,
                             data_sources=_sources(name, mod, has_waterways),
                             model_version=mv, **extra)
    out.update(unbuilt_outputs(mv))
    return out


def unbuilt_outputs(mv: dict) -> dict:
    """The flood types no module computes (docs/flood_taxonomy.md): each is an
    output with no value, so every type in the taxonomy has a label."""
    ids = {t["module"]: i for i, t in C.FLOOD_TAXONOMY.items()}
    return {m: C.absent(status, reason=reason, validation_status=label,
                        data_sources=["none: not computed (docs/flood_taxonomy.md)"],
                        model_version=mv, flood_type=ids[m], tier=None, spatial=False)
            for m, (status, label, reason) in C.UNBUILT_FLOOD_TYPES.items()}
