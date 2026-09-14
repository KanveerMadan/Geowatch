"""
Is the equal-step budget large enough for the 100% point?

The learning-curve run holds optimizer steps equal at 1,600 so the curve is not
partly a measure of gradient steps. But 1,600 steps is ~19.5 epochs at 100%,
and in the fixed-budget arm runs on the same full data arm A peaked at epoch 37
and arm B at epoch 24 — both past 19.5. If the 100% point stops before its own
peak, that depresses the top of the curve and FLATTENS it, while the 25% point
is separately depressed by overfitting (~80 passes over 353 patches). Two
endpoints pushed down by different mechanisms leave the slope biased in an
unknown direction, which is the one outcome a go/no-go gate cannot tolerate.

This probe answers that without disturbing the main run: one Accra fold per
(fraction, budget), recording the FULL val and train-loss trajectory, so the
value at step 1,600 can be read off the same run that continues to 3,200.

Reference points from the 3-seed fixed-budget arm runs, same fold, same data,
40 epochs = 3,200 steps:

    arm A (rgb_stretch)  plateau 0.3503 +/- 0.0305   best 0.3808 +/- 0.0137
    arm B (rgb_abs)      plateau 0.3642 +/- 0.0368   best 0.4122 +/- 0.0227

If 100% at 1,600 steps lands meaningfully below arm A's numbers, the budget is
too small and the curve's top is a protocol artefact.

Usage:
    python experiments/band_reflectance/budget_probe.py --fractions 1.0 --steps 3200
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import experiments.band_reflectance.learning_curve as lc  # noqa: E402
from experiments.band_reflectance.arm_inputs import build_arm_images  # noqa: E402
from experiments.band_reflectance.fidelity_run import pick_device, set_determinism  # noqa: E402
from experiments.band_reflectance.production_patches_v2 import build_all_patches  # noqa: E402

OUT = Path(__file__).resolve().parent / "results" / "learning_curve" / "budget_probe.json"
ARM_A_REF = {"plateau": 0.3503, "plateau_sd": 0.0305, "best": 0.3808, "best_sd": 0.0137,
             "steps": 3200, "note": "3-seed fixed-budget arm A, accra, 40 epochs"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fractions", default="1.0")
    ap.add_argument("--steps", type=int, default=3200)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--city", default="accra")
    args = ap.parse_args()

    device = pick_device()
    set_determinism(args.seed)
    patches = build_all_patches(verbose=False)
    images = build_arm_images(patches, lc.MODE)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    out = json.loads(OUT.read_text()) if OUT.exists() else {}

    for frac in [float(x) for x in args.fractions.split(",")]:
        key = f"frac{frac}_steps{args.steps}_seed{args.seed}_{args.city}"
        if key in out:
            print(f"  {key} cached")
            continue
        rng = np.random.default_rng(args.seed)
        keep = lc.stratified_subsample(patches, frac, rng)
        lc.TARGET_STEPS = args.steps
        t0 = time.time()
        r = lc.run_fold_verbose(images, patches, keep, args.city, device, args.seed)
        r.update({"fraction": frac, "target_steps": args.steps, "seed": args.seed})
        out[key] = r
        OUT.write_text(json.dumps(out, indent=2))

        curve, loss = r["val_curve"], r["loss_curve"]
        nb = r["n_batches"]
        at1600 = min(len(curve), max(1, round(1600 / nb))) - 1
        print(f"\n  frac {frac} @ {args.steps} steps  (n_train {r['n_train']}, "
              f"{nb} batches/ep, {r['epochs']} epochs, {time.time() - t0:.0f}s)")
        print(f"    val at step 1600 (epoch {at1600 + 1:>3}): {curve[at1600]:.4f}   "
              f"train loss {loss[at1600]:.4f}")
        print(f"    val at end      (epoch {len(curve):>3}): {curve[-1]:.4f}   "
              f"train loss {loss[-1]:.4f}")
        print(f"    best over run   (epoch {int(np.argmax(curve)) + 1:>3}): {max(curve):.4f}"
              f"   [SELECTED ON TEST]")
        tail = curve[-5:]
        print(f"    last-5 mean: {np.mean(tail):.4f}")
        half = len(loss) // 2
        print(f"    train-loss slope, 2nd half: "
              f"{(loss[half] - loss[-1]) / max(1, len(loss) - half):.5f}/epoch "
              f"(loss {loss[half]:.4f} -> {loss[-1]:.4f})")
        if frac == 1.0:
            print(f"    arm A reference @3200 steps: plateau {ARM_A_REF['plateau']:.4f} "
                  f"+/-{ARM_A_REF['plateau_sd']:.4f}, best {ARM_A_REF['best']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
