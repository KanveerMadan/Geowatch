"""
POST-HOC, NOT PRE-REGISTERED. Written after ceiling_rare_fractions.py had
run; it carries no verdict and must not be cited as one.

Why: the pre-registered run treats each fraction as one target over all its
sites. Two results made the per-site picture worth seeing:
  * mixed_water_vegetation returned no verdict (control 3 failed: vegetation
    fell to 0.634 with it in the scene) and its sites span 54 deg.
  * solar's sites span 21 deg, and Benban sits 3 deg from its own surround.
This reruns the same realistic scene, same constants, with ONE site endmember
at a time, at noise 0.005 / 0.010 / 0.020.

Usage (from the repo root):
    python experiments/rare_fraction_ceilings/posthoc_per_site.py
"""

import json
import os
import sys

sys.path.insert(0, os.getcwd())

import ceiling_rare_fractions as crf   # noqa: E402

OUT = "experiments/rare_fraction_ceilings/posthoc_per_site_2026-10-28.json"


def main():
    _, groups = crf.load_endmembers()
    rows = []
    print("POST-HOC per-site ceilings (not pre-registered; no verdicts)")
    print(f"{'fraction':<24} {'site':<15} {'noise':>6} {'ridge':>7} "
          f"{'gbt':>7} {'veg':>7}")
    for frac in ("solar", "mixed_water_vegetation"):
        for s in groups[frac]:
            for r in crf.ceiling_for([s["mean"]],
                                     noise_sweep=crf.NOISE_REPORTED):
                rows.append(dict(fraction=frac, site=s["name"],
                                 subtype=s["subtype"], **r))
                print(f"{frac:<24} {s['name']:<15} {r['noise']:>6.3f} "
                      f"{r['ridge'][0]:>7.3f} {r['gbt'][0]:>7.3f} "
                      f"{r['veg_ridge_r2']:>7.3f}")
    with open(OUT, "w") as f:
        json.dump(dict(validation_status="experimental", post_hoc=True,
                       pre_registered=False, rows=rows), f, indent=2)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
