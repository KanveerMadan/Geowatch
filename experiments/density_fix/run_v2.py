"""Item 23 fix, step 2: score the pre-registered tests on the DEV AOIs.
Run only after PREREGISTRATION_V2.md is committed and pushed. Offline except
for Open Buildings' count check (cached layers).

    python -m experiments.density_fix.run_v2

Writes result_v2.json with: the v1 test on the unchanged metrics (must
reproduce the 2026-10-28 FAIL), the v1 predictions with built masses in
place of footprints (side analysis S1), and the v2 test.
"""
import hashlib
import json
from datetime import datetime, timezone

from vector import density
from vector.aois import MORPHOLOGY_AOIS
from vector.roads import load_road_layer

OUT = "experiments/density_fix/result_v2.json"


def _mass_as_footprints(m):
    """S1: v1's predictions read from masses instead of polygons."""
    v = m["built_mass"]["value"]
    return {
        "footprint_size_m2": {"status": "available", "value": {"median": v["median_mass_m2"]}},
        "footprint_density": {"status": "available", "value": v["n_masses"] / m["_area_km2"]},
        "footprint_spacing_m": {"status": "available", "value": {"median": v["median_gap_m"]}},
        "orthogonality": m["orthogonality"],
    }


def main():
    sha = hashlib.sha256(open(density.__file__, "rb").read()).hexdigest()
    metrics = {}
    for name in ("chandigarh_central", "dharavi"):
        layer = load_road_layer(name, MORPHOLOGY_AOIS[name]["bbox"])
        m = density.density_metrics(layer)
        m["_area_km2"] = layer.aoi.area / 1e6
        metrics[name] = m
    f, i = metrics["chandigarh_central"], metrics["dharavi"]
    out = {
        "run_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "density_py_sha256": sha,
        "v1": density.evaluate_separation(f, i, density.SEPARATION_TEST),
        "s1_v1_on_masses": density.evaluate_separation(_mass_as_footprints(f), _mass_as_footprints(i),
                                                       density.SEPARATION_TEST),
        "v2": density.evaluate_separation(f, i, density.SEPARATION_TEST_V2),
        "metrics": {k: {kk: vv for kk, vv in v.items() if kk in (
            "footprint_density", "built_area_share", "footprint_size_m2", "footprint_spacing_m",
            "built_mass", "orthogonality", "footprint_source", "_area_km2")} for k, v in metrics.items()},
    }
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    for k in ("v1", "s1_v1_on_masses", "v2"):
        print(k, out[k]["result"], out[k]["holding"], "hold,", out[k]["reversed"], "reversed")
        for r in out[k]["rows"]:
            print("   ", r["prediction"], "|", r.get("formal"), r.get("informal"), r.get("statistic"), r["outcome"])


if __name__ == "__main__":
    main()
