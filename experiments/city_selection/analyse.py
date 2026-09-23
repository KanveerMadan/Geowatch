"""
Join the five tests, build the morphological distance matrix, print the table.

DISTANCE IS MEASURED TWO WAYS, because they answer different questions.

  d_centroid  distance from the centroid of the existing 11 in descriptor
              space. "How unlike our training set in general?"
  d_nearest   distance to the SINGLE closest existing city. "Do we already
              have one of these?"

A candidate can sit far from the centroid while being a near-twin of one
existing city (the centroid is an average of eleven quite different places and
is not itself a real city). Ranking on d_centroid alone would happily add a
duplicate. `d_nearest` is the one that catches redundancy, so both are
reported and the recommendation weighs `d_nearest`.

Descriptors are z-scored across all 39 sites so each contributes comparably.
Two are log1p-transformed first -- population density and median footprint
area -- because both are strongly right-skewed and would otherwise let a
couple of extreme cities dominate the Euclidean distance.

Slope enters as BOTH mean and standard deviation. A uniformly tilted plain and
a ravine-cut hillside can share a mean slope; the spread is what separates
them, and hillside fabric is the specific gap in the existing 11.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.city_selection.aois import all_sites  # noqa: E402

CACHE = Path(__file__).resolve().parent / "cache"

DESCRIPTORS = [
    ("ob_built_fraction", False, "built frac"),
    ("ob_median_m2", True, "med fp m2"),
    ("ob_iqr_m2", True, "fp IQR"),
    ("road_km_per_km2", False, "road km/km2"),
    ("intersections_per_km2", False, "int/km2"),
    ("slope_mean_deg", False, "slope mean"),
    ("slope_std_deg", False, "slope sd"),
    ("ghsl_built_frac", False, "ghsl built"),
    ("ghsl_pop_per_km2", True, "pop/km2"),
]


def load():
    c1 = json.loads((CACHE / "test1_cloud.json").read_text())
    c2 = json.loads((CACHE / "test2_osm.json").read_text())
    c345 = json.loads((CACHE / "test345.json").read_text())
    sites = all_sites()
    rows = {}
    for name, meta in sites.items():
        r = dict(meta)
        r.update({k: v for k, v in c1.get(name, {}).items() if k != "scenes"})
        r.update(c2.get(name, {}))
        r.update(c345.get(name, {}))
        rows[name] = r
    return rows


def distances(rows):
    names = list(rows)
    X = np.zeros((len(names), len(DESCRIPTORS)), dtype=float)
    for i, n in enumerate(names):
        for j, (key, logt, _) in enumerate(DESCRIPTORS):
            v = rows[n].get(key)
            v = 0.0 if v is None else float(v)
            X[i, j] = np.log1p(max(v, 0.0)) if logt else v
    mu, sd = X.mean(axis=0), X.std(axis=0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd

    ex_idx = [i for i, n in enumerate(names) if rows[n]["group"] == "existing"]
    centroid = Z[ex_idx].mean(axis=0)

    out = {}
    for i, n in enumerate(names):
        d_cent = float(np.linalg.norm(Z[i] - centroid))
        dists = {names[k]: float(np.linalg.norm(Z[i] - Z[k]))
                 for k in ex_idx if names[k] != n}
        nearest = min(dists, key=dists.get)
        out[n] = {"d_centroid": d_cent, "d_nearest": dists[nearest],
                  "nearest_city": nearest, "z": Z[i].tolist()}
    return out, names


def main() -> int:
    rows = load()
    dist, names = distances(rows)
    for n in names:
        rows[n].update(dist[n])

    cand = [n for n in names if rows[n]["group"] == "candidate"]
    exist = [n for n in names if rows[n]["group"] == "existing"]

    def gate_ob(n):
        return rows[n]["ob_n_buildings"] > 0

    def gate_cloud(n):
        return rows[n]["passes_gate"]

    print("=" * 172)
    print("CANDIDATE TABLE — all 28 candidates + the existing 11 as baseline")
    print("25 km2 AOI per site; cloud over 2023-09-01..2026-09-01; "
          "OSM via Overpass; footprints Open Buildings v3")
    print("=" * 172)
    hdr = (f"{'site':<16}{'tier':>5}{'region':>10}"
           f"{'clr<10':>7}{'best3mo':>9}{'n':>4}"
           f"{'roadkm':>8}{'/km2':>6}{'maj/km2':>8}{'int/km2':>8}{'watr':>5}"
           f"{'OBn':>8}{'built%':>7}{'medm2':>7}"
           f"{'slope':>6}{'slpsd':>6}"
           f"{'WCbare%':>8}{'scrn%':>7}"
           f"{'dCent':>7}{'dNear':>7}{'nearest':>11}")
    print(hdr)
    print("-" * len(hdr))

    def line(n):
        r = rows[n]
        bw = r.get("best_window_months") or []
        return (f"{n:<16}{r['tier']:>5}{r['region']:>10}"
                f"{r.get('aoi_cloud_lt10', 0):>7}"
                f"{'-'.join(str(m) for m in bw):>9}{r.get('best_window_n_lt10', 0):>4}"
                f"{r.get('road_km', 0):>8.0f}{r.get('road_km_per_km2', 0):>6.1f}"
                f"{r.get('major_km_per_km2', 0):>8.2f}"
                f"{r.get('intersections_per_km2', 0):>8.1f}"
                f"{r.get('waterway_features', 0):>5}"
                f"{r.get('ob_n_buildings', 0):>8}"
                f"{(r.get('ob_built_fraction') or 0) * 100:>7.1f}"
                f"{r.get('ob_median_m2', 0):>7.1f}"
                f"{(r.get('slope_mean_deg') or 0):>6.2f}"
                f"{(r.get('slope_std_deg') or 0):>6.2f}"
                f"{(r.get('wc_bare_frac') or 0) * 100:>8.2f}"
                f"{(r.get('bare_screen_frac') or 0) * 100:>7.1f}"
                f"{r['d_centroid']:>7.2f}{r['d_nearest']:>7.2f}"
                f"{r['nearest_city'][:10]:>11}")

    for n in sorted(cand, key=lambda x: -rows[x]["d_nearest"]):
        flag = "" if (gate_ob(n) and gate_cloud(n)) else "   <-- GATE FAIL"
        print(line(n) + flag)
    print("-" * len(hdr))
    for n in sorted(exist, key=lambda x: -rows[x]["d_nearest"]):
        print(line(n))
    print("=" * 172)

    print("\nHARD GATES")
    cf = [n for n in cand if not gate_cloud(n)]
    of = [n for n in cand if not gate_ob(n)]
    print(f"  cloud (>=4 clear dates in best season): "
          f"{'ALL PASS' if not cf else 'FAIL: ' + ', '.join(cf)}")
    print(f"  Open Buildings footprints present:     "
          f"{'ALL PASS' if not of else 'FAIL: ' + ', '.join(of)}")

    print("\nEXISTING-11 BASELINE (the reference the brief asks for)")
    for key, label in (("road_km_per_km2", "road km/km2"),
                       ("major_km_per_km2", "major km/km2"),
                       ("intersections_per_km2", "intersections/km2"),
                       ("ob_built_fraction", "OB built fraction"),
                       ("slope_mean_deg", "slope mean deg"),
                       ("wc_bare_frac", "WorldCover bare frac"),
                       ("bare_screen_frac", "dry-season bare screen")):
        v = np.array([rows[n].get(key) or 0 for n in exist], dtype=float)
        c = np.array([rows[n].get(key) or 0 for n in cand], dtype=float)
        print(f"  {label:<24} existing min/med/max "
              f"{v.min():>8.3f}/{np.median(v):>8.3f}/{v.max():>8.3f}   "
              f"candidates median {np.median(c):>8.3f}")

    print("\nHILLSIDE CHECK — existing 11 slope means")
    for n in sorted(exist, key=lambda x: -(rows[x]["slope_mean_deg"] or 0)):
        print(f"  {n:<14}{rows[n]['slope_mean_deg']:>6.2f} deg  "
              f"(sd {rows[n]['slope_std_deg']:>5.2f})")
    print("  candidates above the existing maximum:")
    mx = max(rows[n]["slope_mean_deg"] for n in exist)
    for n in sorted(cand, key=lambda x: -(rows[x]["slope_mean_deg"] or 0)):
        if (rows[n]["slope_mean_deg"] or 0) > mx:
            print(f"    {n:<16}{rows[n]['slope_mean_deg']:>6.2f} deg  "
                  f"(sd {rows[n]['slope_std_deg']:>5.2f})  tier {rows[n]['tier']}")

    out = CACHE / "joined.json"
    out.write_text(json.dumps(rows, indent=2, default=str))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
