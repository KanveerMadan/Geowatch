"""
The learning-curve gate: does more of this data help?

Trains on 25 / 50 / 75 / 100% of the existing patch set, full LOCO at each
fraction, 3 seeds per point, and plots LOCO mIoU against patch count.

This decides whether the annotation campaign is worth doing. It is built to be
able to say STOP, so every design choice below leans against flattering the
expensive answer.

────────────────────────────────────────────────────────────────────────────
ONE DELIBERATE DEVIATION FROM THE BRIEF: EQUAL STEPS, NOT EQUAL EPOCHS
────────────────────────────────────────────────────────────────────────────
The brief specifies a fixed epoch budget. That removes the early-stopping free
variable, which is right, but at varying dataset size it introduces a worse
one. At batch 16 with drop_last, a LOCO fold holds ~10/11 of the patches:

    fraction   train patches   batches/epoch   x40 epochs = steps
      25%           321             20                      800
      50%           642             40                     1600
      75%           964             60                     2400
     100%          1285             80                     3200

So a fixed 40 epochs gives the 100% point FOUR TIMES the optimization of the
25% point. Any rise in the curve would then be partly "more gradient steps",
not "more data" — and the bias runs toward steepness, which is the
annotate-more conclusion. A gate that exists to be able to say stop must not
be built with its thumb on that side of the scale.

So every point here gets the SAME NUMBER OF OPTIMIZER STEPS (`TARGET_STEPS`),
with the epoch count per fold derived from its own batch count and the cosine
schedule's T_max matched to it. The only thing varying across the curve is how
much UNIQUE data those identical steps see.

The cost is the mirror-image artefact: at 25% the model makes ~4x more passes
over its smaller set, so it overfits harder. That is visible rather than
hidden — final-epoch, last-5-average and best-epoch are all reported, and
final-epoch is the one that suffers most from it. Train loss per point is
recorded so convergence can be compared rather than assumed.

────────────────────────────────────────────────────────────────────────────
STRATIFIED SUBSAMPLING, BY CITY AND CLASS
────────────────────────────────────────────────────────────────────────────
A plain random 25% draw can delete a thin class from a city outright, and the
curve then measures class ABSENCE rather than data volume. The classes this
bites on, measured on the rebuilt set:

    sparse_informal_roofing   30 patches, present in  5 of 11 cities
    vegetation_clearing       70 patches, present in  8 of 11 cities

Sampling is therefore per (city, class) cell, and any cell that has at least
one patch keeps at least one. That makes the realised fraction slightly higher
than nominal at 25%, which is reported rather than glossed: the x-axis is the
ACTUAL patch count, not the nominal percentage.

────────────────────────────────────────────────────────────────────────────
SELECTION RULES
────────────────────────────────────────────────────────────────────────────
Fixed budget, no early stopping. Three statistics, reported separately:

  final        last epoch. No selection. Primary.
  last5        mean over the final 5 epochs. No selection, less noise.
  best_ON_TEST best epoch by held-out mIoU. In LOCO the held-out city is both
               validation and test, so this is SELECTED ON TEST and
               optimistically biased. Named that way everywhere it appears,
               and reported only because it is the rule 0.313 used.

7-class taxonomy throughout, per the brief — merging classes would change the
task and break comparability with everything measured so far.

Usage:
    python experiments/band_reflectance/learning_curve.py [--fractions 0.25,0.5,0.75,1.0]
                                                          [--seeds 1337,7,2024]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
import torch.optim as optim
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.data import DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiments.band_reflectance.arm_inputs import build_arm_images  # noqa: E402
from experiments.band_reflectance.fidelity_run import (  # noqa: E402
    CombinedLoss, compute_per_class_iou, freeze_bn_stats, pick_device, set_determinism,
)
from experiments.band_reflectance.production_patches_v2 import (  # noqa: E402
    CATEGORIES, IGNORE_INDEX, NUM_CLASSES, LOCO_CLEAN_CITIES, build_all_patches,
)
from experiments.band_reflectance.run_comparison import ArmDataset, ArmSeg  # noqa: E402

TARGET_STEPS = 1600         # identical optimizer steps at every point
BATCH = 16
TAIL = 5
MODE, IN_CHANS = "rgb_stretch", 3      # production configuration
OUTDIR = Path(__file__).resolve().parent / "results" / "learning_curve"


def stratified_subsample(patches, fraction, rng):
    """
    Keep `fraction` of patches, sampled within each (city, class) cell, with
    every non-empty cell keeping at least one patch.
    """
    if fraction >= 1.0:
        return list(range(len(patches)))
    cells = defaultdict(list)
    for i, p in enumerate(patches):
        cells[(p["city"], p["label"])].append(i)
    keep = []
    for _, idx in sorted(cells.items()):
        k = max(1, int(round(len(idx) * fraction)))
        keep.extend(rng.choice(idx, size=min(k, len(idx)), replace=False).tolist())
    return sorted(keep)


def run_fold(images, patches, keep_idx, held_city, device, seed):
    tr = [i for i in keep_idx if patches[i]["city"] != held_city]
    va = [i for i in keep_idx if patches[i]["city"] == held_city]
    if not va or len(tr) < BATCH:
        return None

    n_batches = max(1, len(tr) // BATCH)
    epochs = max(1, int(round(TARGET_STEPS / n_batches)))

    counts = Counter(patches[i]["label"] for i in tr)
    arr = np.maximum(np.array([counts.get(c, 1) for c in CATEGORIES], dtype=np.float32), 1)
    w = 1.0 / arr
    w = torch.tensor(w / w.sum() * NUM_CLASSES, dtype=torch.float32).to(device)

    set_determinism(seed)
    train_loader = DataLoader(
        ArmDataset([images[i] for i in tr], [patches[i]["mask"] for i in tr], augment=True),
        batch_size=BATCH, shuffle=True, num_workers=0, drop_last=True)
    val_loader = DataLoader(
        ArmDataset([images[i] for i in va], [patches[i]["mask"] for i in va], augment=False),
        batch_size=BATCH, shuffle=False, num_workers=0)

    model = ArmSeg(IN_CHANS).to(device)
    criterion = CombinedLoss(class_weights=w, ignore_index=IGNORE_INDEX,
                             dice_weight=0.5, separation_weight=0.0,
                             separation_margin=2.0, class_a_idx=None, class_b_idx=None)
    optimizer = optim.AdamW([
        {"params": model.encoder.parameters(), "lr": 1e-5},
        {"params": model.decoder.parameters(), "lr": 3e-4},
    ], weight_decay=1e-4)
    scheduler = CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-6)

    curve, per_class_curve, losses = [], [], []
    best, best_ep = -1.0, 0
    for epoch in range(1, epochs + 1):
        model.train()
        freeze_bn_stats(model.encoder)
        ep = 0.0
        for imgs, msks in train_loader:
            imgs, msks = imgs.to(device), msks.to(device)
            optimizer.zero_grad()
            loss, _, _, _ = criterion(model(imgs), msks)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], max_norm=1.0)
            optimizer.step()
            ep += loss.item()
        scheduler.step()
        losses.append(ep / len(train_loader))

        model.eval()
        lg, mk = [], []
        with torch.no_grad():
            for imgs, msks in val_loader:
                lg.append(model(imgs.to(device)).cpu())
                mk.append(msks)
        pc = compute_per_class_iou(torch.cat(lg), torch.cat(mk), NUM_CLASSES, IGNORE_INDEX)
        m = float(np.mean([v for v in pc.values() if v is not None]))
        curve.append(m)
        per_class_curve.append({CATEGORIES[c]: v for c, v in pc.items()})
        if m > best:
            best, best_ep = m, epoch

    del model
    tail = min(TAIL, len(curve))
    pc_tail = {}
    for c in CATEGORIES:
        vals = [h[c] for h in per_class_curve[-tail:] if h[c] is not None]
        pc_tail[c] = float(np.mean(vals)) if vals else None
    return {
        "city": held_city, "n_train": len(tr), "n_val": len(va),
        "epochs": epochs, "n_batches": n_batches, "steps": epochs * n_batches,
        "final": curve[-1], "last5": float(np.mean(curve[-tail:])),
        "best_ON_TEST": best, "best_epoch_ON_TEST": best_ep,
        "final_train_loss": losses[-1],
        "per_class_last5": pc_tail,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fractions", default="0.25,0.5,0.75,1.0")
    ap.add_argument("--seeds", default="1337,7,2024")
    args = ap.parse_args()
    fractions = [float(x) for x in args.fractions.split(",")]
    seeds = [int(x) for x in args.seeds.split(",")]

    device = pick_device()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print("LEARNING-CURVE GATE — does more of this data help?")
    print(f"device {device} | {MODE} | 7-class | EQUAL STEPS ({TARGET_STEPS}) per point")
    print(f"fractions {fractions} | seeds {seeds} | full LOCO ({len(LOCO_CLEAN_CITIES)} folds)")
    print("=" * 78, flush=True)

    set_determinism(seeds[0])
    patches = build_all_patches(verbose=False)
    images = build_arm_images(patches, MODE)
    print(f"{len(patches)} patches; arm images {len(images)} x {images[0].shape}", flush=True)

    results = []
    resume = OUTDIR / "raw.json"
    if resume.exists():
        results = json.loads(resume.read_text())
        print(f"resuming: {len(results)} runs already recorded", flush=True)
    done = {(r["fraction"], r["seed"], r["city"]) for r in results}

    for frac in fractions:
        for seed in seeds:
            rng = np.random.default_rng(seed)
            keep = stratified_subsample(patches, frac, rng)
            cov = Counter((patches[i]["city"], patches[i]["label"]) for i in keep)
            full = Counter((p["city"], p["label"]) for p in patches)
            missing = [k for k in full if k not in cov]
            print(f"\n--- fraction {frac:.2f} seed {seed}: {len(keep)} patches "
                  f"({len(keep) / len(patches) * 100:.1f}% actual), "
                  f"{len(missing)} (city,class) cells lost ---", flush=True)
            for city in LOCO_CLEAN_CITIES:
                if (frac, seed, city) in done:
                    continue
                t0 = time.time()
                r = run_fold(images, patches, keep, city, device, seed)
                if r is None:
                    print(f"  {city:<12} SKIPPED (too few patches)", flush=True)
                    continue
                r.update({"fraction": frac, "seed": seed,
                          "n_patches_total": len(keep),
                          "cells_lost": len(missing)})
                results.append(r)
                resume.write_text(json.dumps(results, indent=2))
                print(f"  {city:<12} n={r['n_train']:>4} ep={r['epochs']:>3} "
                      f"steps={r['steps']:>5} final={r['final']:.4f} "
                      f"last5={r['last5']:.4f} best*={r['best_ON_TEST']:.4f} "
                      f"loss={r['final_train_loss']:.4f} {time.time() - t0:.0f}s",
                      flush=True)

    summarise(results)
    return 0


def summarise(results):
    print("\n" + "=" * 78)
    print("LEARNING CURVE — LOCO mIoU vs patch count")
    print("=" * 78)
    print("  * best_ON_TEST is SELECTED ON TEST and optimistically biased.\n")
    print(f"  {'frac':>6}{'patches':>9}{'cells lost':>12}"
          f"{'final':>18}{'last5':>18}{'best*':>18}")
    by = defaultdict(list)
    for r in results:
        by[r["fraction"]].append(r)
    for frac in sorted(by):
        rows = by[frac]
        per_seed = defaultdict(list)
        for r in rows:
            per_seed[r["seed"]].append(r)
        # LOCO mIoU = mean over the 11 folds, one value per seed
        cells = []
        for key in ("final", "last5", "best_ON_TEST"):
            vals = [float(np.mean([r[key] for r in rs])) for rs in per_seed.values()]
            cells.append(f"{np.mean(vals):>11.4f} +/-{np.std(vals, ddof=1) if len(vals) > 1 else 0:.4f}")
        npat = int(np.mean([r["n_patches_total"] for r in rows]))
        lost = int(np.mean([r["cells_lost"] for r in rows]))
        print(f"  {frac:>6.2f}{npat:>9}{lost:>12}" + "".join(f"{c:>18}" for c in cells))
    print("=" * 78)


if __name__ == "__main__":
    raise SystemExit(main())
