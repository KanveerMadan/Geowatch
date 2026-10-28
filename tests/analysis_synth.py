"""Offline stand-ins for the analysis pipeline's external fetches (Earth
Engine, Overpass), on the vector-track synthetic layer. Not a test module."""
import time

import numpy as np

from analysis.fractions import StandInFractions
from tests.vector_synth import BBOX, _fix_ns, _grid_ways, _layer, _rows_of_huts

WINDOW = {"start": "2026-01-01", "end": "2026-03-31", "mode": "manual"}
COMMIT = {"commit": "0" * 40, "dirty": False, "diff_sha256": None}


def synth_layer():
    ws = _grid_ways()
    ws[1] = _fix_ns(ws[1])
    return _layer(ws, footprints=_rows_of_huts())


class SynthProducer(StandInFractions):
    """The stand-in producer with a synthetic composite: vegetation on the
    left third, water on a strip, and an unobserved (cloud) corner."""
    def __init__(self, unobserved_all=False, **kw):
        super().__init__(**kw)
        self.unobserved_all = unobserved_all

    def fetch_composite(self, layer, transform, shape, window):
        H, W = shape
        ndvi = np.full(shape, 0.1, dtype=np.float32)
        ndvi[:, : W // 3] = 0.6
        mndwi = np.full(shape, -0.3, dtype=np.float32)
        mndwi[H // 2: H // 2 + 3, :] = 0.4
        obs = np.full(shape, 10, dtype=np.int32)
        obs[: H // 5, : W // 5] = 0
        if self.unobserved_all:
            obs[:] = 0
        return {"ndvi": ndvi, "mndwi": mndwi, "valid_obs": obs, "window": window,
                "source_image_count": 12,
                "observation_quality": {"status": "available", "valid_observation_pct": 90.0}}


def context_fns(overrides=None):
    fns = {
        "hand": lambda: {"status": "available", "mean_hnd_m": 3.0, "min_hnd_m": 0.0,
                         "max_hnd_m": 9.0, "river_connectivity": True,
                         "max_upstream_area_km2": 20.0, "buffer_km": 5},
        "fabdem": lambda: {"status": "available", "mean_elevation_m": 8.0},
        "slope": lambda: {"status": "available", "mean_slope_deg": 2.0},
        "rainfall": lambda: {"status": "available", "mean_annual_mm": 2200.0},
        "coastline": lambda: {"status": "available", "distance_km": 1.0,
                              "coastal_connectivity": True, "search_radius_km": 50},
        "relative_elevation": lambda: {"status": "experimental", "score": 0.5},
    }
    fns.update(overrides or {})
    return fns


def sleeper(seconds):
    def f():
        time.sleep(seconds)
        return {"status": "available"}
    return f


def fake_dem(layer, transform, shape):
    H, W = shape
    y, x = np.mgrid[0:H, 0:W]
    return (10.0 + 0.05 * x + 0.03 * y).astype(np.float64)


def fake_waterways(name, bbox):
    w, s, e, n = bbox
    return {"ways": [{"type": "way", "id": 9,
                      "geometry": [{"lon": w, "lat": (s + n) / 2}, {"lon": e, "lat": (s + n) / 2}]}],
            "unavailable": []}


def fake_change(layer, epochs):
    from vector import change, fractions, units
    tr, shape = fractions.grid_for(layer)
    n = len(units.grid_units(layer, tr))
    rng = np.random.default_rng(0)
    out = {"fractions": {}}
    for f in ("built", "vegetation", "water"):
        if f == "built" and not epochs.get("built"):
            continue
        va, vb = rng.random(n), rng.random(n)
        r = change.detect(f, va, vb, np.ones(n), np.ones(n), 0.05)
        r["validation_status"] = "experimental" if f == "built" else "placeholder"
        out["fractions"][f] = r
    return out


def fake_cause_counts(layer, transform, shape, window, cct):
    """12 scenes everywhere; 2 cloudy everywhere, 1 shadowed on the top
    half, none snowy."""
    H, W = shape
    sh = np.zeros(shape)
    sh[: H // 2] = 1
    return {"n_scene": np.full(shape, 12.0), "cloud_nodata": np.full(shape, 2.0),
            "fully_shadowed": sh, "transient_snow": np.zeros(shape)}


def deps(**overrides):
    d = {"init_ee": lambda: None, "load_layer": lambda name, bbox: synth_layer(),
         "context_fns": context_fns(), "fetch_dem": fake_dem,
         "fetch_waterways": fake_waterways, "run_change": fake_change,
         "fetch_cause_counts": fake_cause_counts}
    d.update(overrides)
    return d


def run(producer=None, **kw):
    from analysis.run import run_analysis
    return run_analysis(BBOX, WINDOW, name="synth", producer=producer or SynthProducer(),
                        deps=kw.pop("deps", None) or deps(), commit=COMMIT, **kw)
