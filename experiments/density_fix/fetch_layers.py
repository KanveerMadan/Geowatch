"""Item 23 fix, step 0: build (and cache) the vector layers for the separation
test's two DEV AOIs, one after the other (one Earth Engine job at a time), and
record the CURRENT metrics so the failed result is reproduced before any change.

Run from the repo root:  python -m experiments.density_fix.fetch_layers
"""
import json
import os
import sys
import time

from vector import density
from vector.aois import MORPHOLOGY_AOIS
from vector.roads import load_road_layer

OUT = os.path.join("experiments", "density_fix", "baseline_metrics.json")
AOIS = ("chandigarh_central", "dharavi")


def main():
    out = {}
    for name in AOIS:
        bbox = MORPHOLOGY_AOIS[name]["bbox"]
        for attempt in range(6):
            try:
                t = time.time()
                layer = load_road_layer(name, bbox)
                break
            except Exception as e:                       # EE quota / Overpass busy: back off
                msg = str(e)
                print(f"{name}: attempt {attempt + 1} failed: {msg[:200]}", flush=True)
                if attempt == 5:
                    raise
                time.sleep(60 * (attempt + 1))
        print(f"{name}: layer in {time.time() - t:.0f} s, {len(layer.footprints)} footprints",
              flush=True)
        out[name] = density.density_metrics(layer)
    out["separation"] = density.evaluate_separation(out["chandigarh_central"], out["dharavi"])
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    print(json.dumps(out["separation"], indent=1, default=str))


if __name__ == "__main__":
    sys.exit(main())
