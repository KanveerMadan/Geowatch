"""
The end-to-end analysis run. No 7-class classifier anywhere:

    AOI -> vector layer (item 19) -> OSM coverage (item 20)
        -> fractions (a swappable producer; analysis/fractions.py)
        -> flood susceptibility (item 26's five modules)
        -> change (item 25) -> aggregation (item 22, plus wards)
        -> result (analysis/contract.py)

Every Earth Engine or Overpass call runs in a stage with an explicit
timeout (analysis/stages.py). A stage that times out or fails is recorded
in `stages` and every output that depended on it says so; the run goes on.

`deps` replaces the external fetches, so the whole chain runs offline in
tests on a synthetic layer.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone

import numpy as np

from analysis import contract as C
from analysis import hazards as H
from analysis.stages import STAGE_TIMEOUT_S, run_stage, summary

SCHEMA = "geowatch.analysis/1"
PIPELINE = "fraction_vector"

# Fixed 2026-10-28, before any real-data run of this pipeline.
DEFAULT_WINDOW_DAYS = 90           # when no dates are given: the 90 days ending yesterday
CHANGE_BASELINE_YEARS_BACK = 5     # change compares the window with the same window 5 years earlier
OB_TEMPORAL_YEARS = (2016, 2023)   # Open Buildings 2.5D Temporal's years (vector/change.py)


# ── windows ─────────────────────────────────────────────────────────────

def resolve_window(start: str | None, end: str | None, today: date | None = None) -> dict:
    """Explicit dates are kept; missing ones become the DEFAULT_WINDOW_DAYS
    ending yesterday. Resolved BEFORE caching, so the cache key is a date."""
    if bool(start) != bool(end):
        raise ValueError("give both start and end dates, or neither")
    if start:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        if s >= e:
            raise ValueError("start must be before end")
        return {"start": s.isoformat(), "end": e.isoformat(), "mode": "manual"}
    today = today or date.today()
    e = today - timedelta(days=1)
    return {"start": (e - timedelta(days=DEFAULT_WINDOW_DAYS)).isoformat(),
            "end": e.isoformat(), "mode": "latest_auto"}


def _years_back(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year - n)
    except ValueError:                        # 29 February
        return d.replace(year=d.year - n, day=28)


def change_epochs(window: dict) -> dict:
    """vector.change EPOCHS for this window: S2 epochs are the window and the
    same calendar window CHANGE_BASELINE_YEARS_BACK earlier; built epochs are
    those years clamped to Open Buildings Temporal's, or None if they collapse."""
    s, e = date.fromisoformat(window["start"]), date.fromisoformat(window["end"])
    bs, be = _years_back(s, CHANGE_BASELINE_YEARS_BACK), _years_back(e, CHANGE_BASELINE_YEARS_BACK)
    lo, hi = OB_TEMPORAL_YEARS
    ya, yb = min(max(bs.year, lo), hi), min(max(e.year, lo), hi)
    built = (ya, yb) if ya < yb else None
    return {"s2": ((bs.isoformat(), be.isoformat()), (s.isoformat(), e.isoformat())),
            "built": built, "built_noise": (yb - 1, yb) if built else None}


# ── default external dependencies ───────────────────────────────────────

def _default_deps():
    def init_ee():
        from ingestion.gee_client import initialize_gee
        initialize_gee()

    def load_layer(name, bbox):
        from vector.roads import load_road_layer
        return load_road_layer(name, bbox)

    def fetch_dem(layer, transform, shape):
        from susceptibility.terrain import fetch_dem as f
        return f(layer, transform, shape)

    def fetch_waterways(name, bbox):
        from analysis.waterways import fetch_waterways as f
        return f(name, bbox)

    def run_change(layer, epochs):
        from vector.change import run_change as f
        return f(layer, epochs)

    return {"init_ee": init_ee, "load_layer": load_layer, "context_fns": None,
            "fetch_dem": fetch_dem, "fetch_waterways": fetch_waterways,
            "run_change": run_change}


# ── output builders ─────────────────────────────────────────────────────

def _aoi_fraction_outputs(layer, fset: dict, mv: dict) -> dict:
    """AOI-level value per fraction: one-unit aggregation over the AOI."""
    from vector.units import aggregate
    agg = aggregate([layer.aoi], fset, {}, fractions=fset["fractions"],
                    not_computed=tuple(fset["not_computed"]))["units"][0]
    out = {}
    for f in fset["fractions"]:
        cell = agg[f]
        cov = C.coverage(cell["coverage"], "share of the AOI's area observed for this fraction")
        extra = {"method": fset["method"].get(f), "producer": fset["producer"].get(f),
                 "unit": "area fraction in [0, 1]"}
        if cell["value"] is None or cell["status"] != "available":
            out[f] = C.output(None, status="insufficient_observation",
                              validation_status=fset["labels"][f], coverage=cov,
                              data_sources=fset["sources"][f], model_version=mv, **extra)
        else:
            out[f] = C.output(round(float(cell["value"]), 6), validation_status=fset["labels"][f],
                              coverage=cov, data_sources=fset["sources"][f], model_version=mv,
                              **extra)
    for f, why in fset["not_computed"].items():
        out[f] = C.absent("not_computed", reason=why, validation_status=fset["labels"][f],
                          data_sources=fset["sources"][f], model_version=mv)
    return out


def _coverage_output(cov: dict, mv: dict) -> dict:
    return C.output(cov["osm_density_percentile"], validation_status=cov["validation_status"],
                    coverage=C.coverage(1.0, "AOI-level score over every retrieved OSM clause",
                                        fetch=cov["road_length_fetch"]["all"]),
                    data_sources=["OpenStreetMap highway=* (Overpass)",
                                  f"footprints: {cov['footprint_source']}"],
                    model_version=mv, unit="percentile of narrow pedestrian density",
                    coverage_regime_flag=cov["coverage_regime_flag"],
                    regime_reasons=cov["regime_reasons"],
                    topology_metrics_suppressed=cov["topology_metrics_suppressed"],
                    footprint_metrics_confidence=cov["footprint_metrics_confidence"],
                    narrow_pedestrian_km_per_km2=cov["narrow_pedestrian_km_per_km2"],
                    measure=cov["measure"], source_layer_id=cov["source_layer_id"])


def _change_outputs(ch: dict | None, stage: dict, epochs: dict, fset: dict, mv: dict) -> dict:
    out = {}
    sources = {"built": ["GOOGLE/Research/open-buildings-temporal/v1 building_presence"],
               "vegetation": fset["sources"].get("vegetation", ["none"]),
               "water": fset["sources"].get("water", ["none"])}
    for f in ("built", "vegetation", "water"):
        label = fset["labels"].get(f, "placeholder")
        r = (ch or {}).get("fractions", {}).get(f)
        if r is None:
            if stage["status"] != "ok":
                status, why = stage["status"], f"change stage {stage['status']}: {stage.get('error')}"
            else:
                status, why = "not_computed", "no Open Buildings Temporal epoch pair for this window"
            out[f] = C.absent(status, reason=why, validation_status=label,
                              data_sources=sources[f], model_version=mv)
            continue
        counts = r["counts"]
        n = sum(counts.values())
        judged = counts["increase"] + counts["decrease"] + counts["no_detectable_change"]
        out[f] = C.output(
            {k: counts[k] for k in ("increase", "decrease", "no_detectable_change")},
            validation_status=C.worst(label, r.get("validation_status", label)),
            coverage=C.coverage(judged / n if n else 0.0,
                                "share of change-grid units observed well enough in both epochs"),
            data_sources=sources[f], model_version=mv,
            unit="count of 100 m grid units", counts_all=counts, noise=r["noise"], k=r["k"],
            threshold=r["threshold"], noise_basis=r.get("noise_basis"), method=r.get("method"),
            epochs=r.get("epochs"))
    for f, why in fset["not_computed"].items():
        out[f] = C.absent("not_computed", reason=why, validation_status="placeholder",
                          data_sources=["none: not computed"], model_version=mv)
    return out


def _aggregation_outputs(unit_sets: dict, mv: dict, fset: dict) -> dict:
    out = {}
    for t, b in unit_sets.items():
        extra = {"unit_type": t, "consistency": (b.get("consistency") or {}).get("result"),
                 "fetch": b.get("fetch")}
        label = "experimental"
        sources = ["item 19 vector layer"] + ([f"boundary layer {t.split(':', 1)[1]}"]
                                             if t.startswith("ward:") else [])
        key = t.replace(":", "__")     # ward:<id> -> ward__<id>
        if not b["units"]:
            out[key] = C.absent("unavailable", reason=b.get("reason", "no units"),
                              validation_status=label, data_sources=sources, model_version=mv,
                              **extra)
            continue
        covs = [u["vegetation"]["coverage"] if "vegetation" in u else 0.0 for u in b["units"]]
        out[key] = C.output(
            b["n_units"], validation_status=label,
            coverage=C.coverage(float(np.mean(covs)), "mean per-unit observed share (vegetation)"),
            data_sources=sources, model_version=mv, unit="number of units", **extra)
    return out


# ── the run ─────────────────────────────────────────────────────────────

def run_analysis(bbox, window: dict, *, name: str, producer=None, boundary_id: str | None = None,
                 verdicts: dict | None = None, deps: dict | None = None,
                 commit: dict | None = None) -> tuple:
    """Run the whole chain. Returns (result, unit_sets)."""
    from rasterio.transform import Affine
    from analysis.fractions import StandInFractions
    from analysis.waterways import distance_map
    from configs.pluvial_constants import HYDROLOGY_PIXEL_M
    from vector.coverage import score_layer
    from vector.fractions import PIXEL_M, grid_for
    from susceptibility.inputs import road_conduits
    from susceptibility.terrain import terrain_surfaces

    t0 = time.time()
    producer = producer or StandInFractions()
    deps = {**_default_deps(), **(deps or {})}
    verdicts = C.flood_verdicts() if verdicts is None else verdicts
    art = producer.artifact()
    mv = C.model_version({"fraction_producer": art["sha256"],
                          "flood_validation_result": C.FLOOD_VALIDATION_SHA256}, commit=commit)
    stages = {}

    def stage(key, fn, *a, timeout_key=None):
        o = run_stage(key, fn, *a, timeout_s=STAGE_TIMEOUT_S[timeout_key or key])
        stages[key] = summary(o)
        return o

    stage("ee_init", deps["init_ee"], timeout_key="context")

    # 1. item 19: the vector layer. Everything downstream reads it.
    lo = stage("road_layer", deps["load_layer"], name, tuple(bbox))
    if lo["status"] != "ok":
        raise RuntimeError(f"road layer {lo['status']}: {lo.get('error')}")
    layer = lo["value"]

    # 2. item 20: coverage, derived from the layer as built.
    cov = score_layer(layer)

    # 3. fractions on a 10 m grid nested in the 30 m hydrology grid.
    k = int(round(HYDROLOGY_PIXEL_M / PIXEL_M))
    ht, (H_, W_) = grid_for(layer, HYDROLOGY_PIXEL_M)
    ft, fshape = ht * Affine.scale(1.0 / k), (H_ * k, W_ * k)
    fo = stage("s2_composite", producer.produce, layer, ft, fshape, window)
    if fo["status"] != "ok":
        raise RuntimeError(f"fraction producer {fo['status']}: {fo.get('error')}")
    fset = fo["value"]

    # 4. flood surfaces and context.
    surfaces = dict(producer.hydrology_inputs(layer, fset, ht, (H_, W_), k))
    surfaces["conduits"] = road_conduits(layer, ht, (H_, W_))
    do = stage("dem", deps["fetch_dem"], layer, ht, (H_, W_))
    if do["status"] == "ok":
        surfaces["terrain"] = terrain_surfaces(do["value"], HYDROLOGY_PIXEL_M)
    wo = stage("waterways", deps["fetch_waterways"], name, tuple(bbox))
    waterway = None
    if wo["status"] == "ok":
        waterway = distance_map(wo["value"]["ways"], layer.crs, ht, (H_, W_))
        stages["waterways"]["unavailable_clauses"] = wo["value"]["unavailable"]
    ctx, cstages = H.fetch_context(tuple(bbox), fns=deps["context_fns"])
    stages.update(cstages)
    app = H.applicability_for(ctx, surfaces.get("impervious"))
    modules = H.run_modules(ctx, surfaces, waterway, app)
    hz = H.hazard_outputs(modules, mv, verdicts, has_waterways=waterway is not None)

    # 5. item 25: change.
    epochs = change_epochs(window)
    co = stage("change", deps["run_change"], layer, epochs)
    change = co["value"] if co["status"] == "ok" else None

    # 6. item 22: aggregation units and wards.
    from analysis.wards import build_unit_sets
    pmap = modules["pluvial"].get("susceptibility_map")
    pluvial_10m = np.repeat(np.repeat(pmap, k, axis=0), k, axis=1) if pmap is not None else None
    osm_regime = {"regime": cov["coverage_regime_flag"], "basis": "aoi",
                  "osm_density_percentile": cov["osm_density_percentile"]}
    unit_sets = build_unit_sets(layer, fset, osm_regime, pluvial_10m, boundary_id)

    outputs = {
        "fractions": _aoi_fraction_outputs(layer, fset, mv),
        "osm_coverage": _coverage_output(cov, mv),
        "susceptibility": hz,
        "change": _change_outputs(change, stages["change"], epochs, fset, mv),
        "aggregation": _aggregation_outputs(unit_sets, mv, fset),
    }
    result = {
        "schema": SCHEMA, "pipeline": PIPELINE, "seven_class_classifier": False,
        "request": {"aoi_label": name, "bbox": list(bbox), "window": window,
                    "boundary_layer_id": boundary_id},
        "model_version": mv, "fraction_producer": art,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_layer_id": layer.layer_id, "footprint_source": layer.footprint_source,
        "imagery": {"window": fset.get("window"), "source_image_count": fset.get("source_image_count"),
                    "observation_quality": fset.get("observation_quality")},
        "change_epochs": epochs, "stages": stages, "outputs": outputs,
        "wards": {t: {"status": b["status"], "n_units": b["n_units"]} for t, b in unit_sets.items()},
    }
    C.check_result(result)
    result["validation_summary"] = C.label_summary(result)
    result["runtime_s"] = round(time.time() - t0, 1)
    return result, unit_sets
