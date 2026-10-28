"""
Flood susceptibility for the analysis pipeline (item 26's modules, consumed
as they are: susceptibility/ is not edited here).

Each module's output becomes one contract output. Its label is the worst of
the module's own label, its pinned Tier 2 verdict, and its inputs' labels
(analysis.contract.hazard_label), so pluvial and waterlogging are `failed`.
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
}

# Which context layers each scalar module reads.
MODULE_CONTEXT = {
    "pluvial": ("rainfall", "relative_elevation"),
    "fluvial": ("hand",),
    "coastal": ("coastline", "fabdem"),
    "flash_flood": ("slope", "hand", "rainfall"),
    "waterlogging": ("hand", "rainfall"),
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


def run_modules(ctx: dict, surfaces: dict, waterway_dist, app: dict) -> dict:
    """Run the five modules. `surfaces`: impervious, infiltration, conduits
    (declared surfaces) and terrain ({name: surface}); any may be absent."""
    from susceptibility.coastal import compute_coastal_susceptibility
    from susceptibility.flash_flood import compute_flash_flood_susceptibility
    from susceptibility.fluvial import compute_fluvial_susceptibility
    from susceptibility.pluvial import compute_pluvial_susceptibility
    from susceptibility.waterlogging import compute_waterlogging_susceptibility
    return {
        "pluvial": compute_pluvial_susceptibility(
            impervious=surfaces.get("impervious"), infiltration=surfaces.get("infiltration"),
            conduits=surfaces.get("conduits"), terrain=surfaces.get("terrain"),
            waterway_dist_map=waterway_dist,
            relative_elevation_score=ctx["relative_elevation"].get("score"),
            rainfall_mean_annual_mm=ctx["rainfall"].get("mean_annual_mm"),
            applicability=app),
        "fluvial": compute_fluvial_susceptibility(ctx["hand"], applicability=app),
        "coastal": compute_coastal_susceptibility(ctx["coastline"], ctx["fabdem"],
                                                  applicability=app),
        "flash_flood": compute_flash_flood_susceptibility(ctx["slope"], ctx["hand"],
                                                          ctx["rainfall"], applicability=app),
        "waterlogging": compute_waterlogging_susceptibility(ctx["hand"], surfaces.get("impervious"),
                                                            ctx["rainfall"], applicability=app),
    }


def _input_labels(mod: dict) -> list:
    return [i["validation_status"] for i in (mod.get("inputs") or {}).values()
            if isinstance(i, dict) and i.get("validation_status") in C.VALIDATION_PRECEDENCE]


def _sources(name: str, mod: dict, has_waterways: bool) -> list:
    out = [f"{i['source']} ({k})" for k, i in (mod.get("inputs") or {}).items()
           if isinstance(i, dict) and i.get("source")]
    out += [CONTEXT_SOURCES[c] for c in MODULE_CONTEXT[name]]
    if name == "pluvial" and has_waterways:
        out.append("OpenStreetMap waterway=* / natural=water (Overpass)")
    return out


# Item 38 (C27): an input that did not finish decides the output's status.
# A timeout outranks a failure: retrying can fix it, and saying so matters.
INCOMPLETE = ("timeout", "failed")


def incomplete_inputs(name: str, ctx: dict, stage_status: dict | None = None) -> dict:
    """{input: {"status", "error"}} for every input of module `name` whose
    stage timed out or failed. Pluvial's spatial inputs are stages too."""
    out = {}
    for c in MODULE_CONTEXT[name]:
        st = (ctx.get(c) or {}).get("status")
        if st in INCOMPLETE:
            out[c] = {"status": st, "error": ctx[c].get("error")}
    if name == "pluvial":
        for k, v in (stage_status or {}).items():
            if k in ("s2_composite", "dem", "waterways") and v.get("status") in INCOMPLETE:
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
        if bad:
            status = "timeout" if any(v["status"] == "timeout" for v in bad.values()) else "failed"
            out[name] = C.absent(
                status, reason=f"input(s) did not finish: {sorted(bad)}",
                validation_status=C.hazard_label(mod.get("validation_status", "experimental"),
                                                 verdicts.get(name), *_input_labels(mod)),
                data_sources=_sources(name, mod, has_waterways), model_version=mv,
                incomplete_inputs=bad, tier=None, module_status=mod.get("status"),
                score_from_partial_inputs_withheld=score is not None,
                tier2_verdict=verdicts.get(name), spatial=False)
            continue
        label = C.hazard_label(mod.get("validation_status", "experimental"),
                               verdicts.get(name), *_input_labels(mod))
        extra = {"module_status": mod.get("status"),
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
    return out
