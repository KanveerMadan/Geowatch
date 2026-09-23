"""
Arm D probe: same 3 cities / 1 seed / 1600 steps as fix_probe.py.

Arms A and C are read from the existing cache (identical seed, patch order and
batch order, so they are paired with D fold-for-fold).

VAL IS HELD FIXED ACROSS ALL ARMS. Arm D only re-cuts patches in the TRAINING
cities; the held-out city's patches keep the baseline geometry and the baseline
/ corrected masks, so every arm is scored against the same images and the same
targets and the only thing that varies is the training data.
"""

import sys as _sys, pathlib as _pl
_HERE = _pl.Path(__file__).resolve().parent
_ROOT = _HERE.parents[2]
_sys.path.insert(0, str(_ROOT))
_sys.path.insert(0, str(_HERE))
RESULTS = _ROOT / "experiments" / "band_reflectance" / "results" / "c43"
RESULTS.mkdir(parents=True, exist_ok=True)
import sys, json, time, argparse
from pathlib import Path
import numpy as np
from experiments.band_reflectance.arm_inputs import build_arm_images
from experiments.band_reflectance.fidelity_run import pick_device
from fix_build import build_variants
from fix_build_d import build_arm_d
from fix_probe import run_fold, MODE

ap = argparse.ArgumentParser()
ap.add_argument("--cities", default="capetown,dhaka,guatemala")
ap.add_argument("--seed", type=int, default=1337)
ap.add_argument("--steps", type=int, default=1600)
args = ap.parse_args()
cities = args.cities.split(",")

device = pick_device()
base, pD, mD, changed = build_arm_d()
_, mB, mC, stat, *_ = build_variants()
mA = [p["mask"] for p in base]
imgA = build_arm_images(base, MODE)      # baseline geometry (arms A, B, C)
imgD = build_arm_images(pD, MODE)        # native-cut geometry for the 63
yard = {"orig": mA, "corrected": mC}
print(f"device {device} | {len(base)} patches | seed {args.seed} | steps {args.steps}")
print(f"arm D re-cuts {len(changed)} patches to native 64x64\n", flush=True)

out_path = RESULTS / "fix_probe_raw.json"
results = json.loads(out_path.read_text()) if out_path.exists() else []
done = {(r["arm"], r["city"]) for r in results}
for city in cities:
    if ("D_human_native", city) in done:
        print(f"  {city:<11}D_human_native cached", flush=True); continue
    # train cities get D geometry+masks; the held-out city stays on baseline geometry
    imgs = [imgD[i] if base[i]["city"] != city else imgA[i] for i in range(len(base))]
    msks = [mD[i] if base[i]["city"] != city else mC[i] for i in range(len(base))]
    n_recut = sum(1 for i in changed if base[i]["city"] != city)
    t0 = time.time()
    r = run_fold(imgs, base, msks, yard, city, device, args.seed, args.steps)
    r.update({"arm": "D_human_native", "seed": args.seed, "n_recut_in_train": n_recut})
    results.append(r); out_path.write_text(json.dumps(results, indent=2))
    print(f"  {city:<11}D_human_native ep={r['epochs']:>3} recut_in_train={n_recut:>3} "
          f"mIoU[orig]={r['miou_last5[orig]']:.4f} mIoU[corr]={r['miou_last5[corrected]']:.4f} "
          f"loss={r['final_train_loss']:.4f}  {time.time()-t0:.0f}s", flush=True)
