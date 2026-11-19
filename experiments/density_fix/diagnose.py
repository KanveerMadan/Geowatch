"""Item 23 fix, step 1: how Open Buildings polygons sit against each other in
the two DEV AOIs. Groups polygons whose boundaries are within d metres
(single-linkage), for several d, and reports group counts and sizes.
Offline: reads the cached layers.

Run from the repo root:  python -m experiments.density_fix.diagnose
"""
import json

import numpy as np
from shapely.strtree import STRtree

from vector.aois import MORPHOLOGY_AOIS
from vector.roads import load_road_layer


def groups(polys, d):
    tree = STRtree(polys)
    parent = list(range(len(polys)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    a, b = tree.query(polys, predicate="dwithin", distance=d)
    for i, j in zip(a, b):
        if i < j:
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj
    roots = np.array([find(i) for i in range(len(polys))])
    _, inv, counts = np.unique(roots, return_inverse=True, return_counts=True)
    area = np.bincount(inv, weights=[p.area for p in polys])
    return counts, area


out = {}
for name in ("chandigarh_central", "dharavi"):
    layer = load_road_layer(name, MORPHOLOGY_AOIS[name]["bbox"])
    fps = [p for p in layer.footprints if p.representative_point().within(layer.aoi)]
    row = {"n": len(fps), "median_m2": float(np.median([p.area for p in fps]))}
    for d in (0.0, 0.25, 0.5, 1.0, 2.0):
        counts, area = groups(fps, d)
        row[f"d={d}"] = {"groups": int(len(counts)), "share_in_multi": float((counts[counts > 1].sum()) / len(fps)),
                         "median_group_m2": float(np.median(area)), "p90_group_m2": float(np.percentile(area, 90)),
                         "max_group_m2": float(area.max()), "largest_group_n": int(counts.max())}
    out[name] = row
print(json.dumps(out, indent=1))
json.dump(out, open("experiments/density_fix/diagnosis.json", "w"), indent=1)
